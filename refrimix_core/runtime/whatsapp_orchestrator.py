"""
whatsapp_orchestrator.py — Orquestrador principal do WhatsApp Runtime.

Fluxo:
  1. Recebe QueueMessage do worker
  2. model_router decide fast/slow
  3. Fast lane: Qwen 3B → microcopy → responde
  4. Slow lane: typing ON → MiniMax → guardrail → envia
  5. Salva decisão no Postgres

Não faz:
  - Não lê do Redis queue (worker faz isso)
  - Não envia via Evolution raw (worker faz isso)
  - Não persiste lead_state (worker faz isso)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from refrimix_core.adapters.evolution_typing_adapter import send_typing_off, send_typing_on
from refrimix_core.domain.conversation_style import sanitize_output
from refrimix_core.domain.model_router import Lane, RoutingDecision, route
from refrimix_core.domain.natural_microcopy import (
    FALLBACK_RESPONSE,
    GREETING_MICROCOPY,
    TYPING_PLACEHOLDER,
    count_questions,
    is_faq_rigged,
    select_error,
    select_greeting,
    select_transition,
)
from refrimix_core.domain.typing_policy import (
    TYPING_TIMEOUT_SECONDS,
    is_typing_timeout,
    should_start_typing,
)
from refrimix_core.domain.whatsapp_runtime_policy import (
    check_electrical_risk,
    client_already_explained_problem,
    count_questions as policy_count_questions,
    enforce_question_limit,
    get_electrical_directive,
    can_show_instagram,
    validate_response,
)
from refrimix_core.domain.whatsapp_runtime_policy import (
    ElectricalRisk,
    INSTAGRAM_COPY,
)

logger = logging.getLogger(__name__)


# ── Dataclasses de estado ─────────────────────────────────────────────────────

@dataclass
class OrchestratorContext:
    """Contexto acumulado durante o processamento de UMA mensagem."""
    phone: str
    message: str
    instance: str
    msg_id: str
    message_type: str = "conversation"
    media_url: str = ""
    media_base64: str = ""

    lane: Lane | None = None
    routing_decision: RoutingDecision | None = None
    microcopy_sent: bool = False
    final_response: str | None = None
    sent_via: str | None = None  # "fast", "slow", "error", "guardrail_blocked"
    processing_time_ms: float = 0.0
    lead_state: dict[str, Any] = field(default_factory=dict)


# ── Fast Lane ───────────────────────────────────────────────────────────────

async def _run_fast_lane(
    ctx: OrchestratorContext,
    client_name: str | None = None,
) -> str:
    """Executa fast lane: retorna microcopy ou resposta rápida via Qwen 3B."""
    import random

    text = ctx.message.strip().lower()
    folded = text

    # Padrão de saudação pura → saudação simples
    greeting_patterns = (
        r"^oi\s*$", r"^olá\s*$", r"^ola\s*$",
        r"^bom\s*d(ia|a)\s*$", r"^boa\s*tarde\s*$", r"^boa\s*noite\s*$",
        r"^td\s*bém?\s*$", r"^e\s*ai\s*$", r"^iai\s*$",
        r"^blz\s*$", r"^beleza\s*$", r"^opa\s*$",
    )
    import re
    for p in greeting_patterns:
        if re.match(p, folded):
            return select_greeting(client_name)

    # "vc funciona?" / "vc atende?" → auto-introdução
    if "vc funciona" in folded or "vc atende" in folded:
        return "Sim! Sou a assistente virtual da Refrimix, especializada em climatização (instalação, manutenção e higienização). Em que posso te ajudar?"

    # Afirmar/negativa curta
    affirmative_short = {"sim", "s", "ok", "blz", "beleza", "tem", "tenho", "pode ser", "combinado", "show", "ótimo"}
    negative_short = {"não", "nao", "n", "negativo", "nao tenho", "não tenho"}
    if folded.strip() in affirmative_short:
        return random.choice(("Perfeito!", "Ótimo!", "Combinado!", "👍"))
    if folded.strip() in negative_short:
        return random.choice(("Sem problemas!", "Entendi!", "Ok!", "Certo!"))

    # Fallback: encaminhar para slow lane
    return ""


# ── Slow Lane ───────────────────────────────────────────────────────────────

async def _call_minimax_slow(
    ctx: OrchestratorContext,
) -> str:
    """Chama MiniMax M2.7 para interpretação e resposta final."""
    # Import dinâmico para lazy load
    try:
        from agent_graph.nodes.nodes import _call_local_qwen
    except ImportError:
        logger.error("MiniMax não disponível — fallback")
        return FALLBACK_RESPONSE[0]

    system_prompt = (
        "Você é a assistente virtual da Refrimix HVAC-R Brasil, empresa de climatização. "
        "Atendimento via WhatsApp — seja educada, direta, técnica, com linguagem brasileira natural.\n\n"
        "Você deve falar em português brasileiro, com tom profissional, direto e natural, "
        "como um assistente executivo técnico. Use Edge TTS local (voz pt-BR-ThalitaMultilingualNeural). "
        "Respostas curtas, claras e funcionais. Nada de exagero, floreio, beep, saudação longa ou tom robótico. "
        "Nunca imite pessoa real. Mantenha o comportamento estável, profissional e consistente.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1. Máximo 2 perguntas por resposta.\n"
        "2. Não usar 'Como posso ajudar?' se cliente já explicou o problema.\n"
        "3. Nome, foto, marca, BTUs são dados úteis — não bloqueiam nada.\n"
        "4. Dados técnicos incompletos = bloqueia PREÇO FECHADO, mas NÃO bloqueia visita técnica.\n"
        "5. Caso elétrico = primeiro orientar DESLIGAR, depois analisar.\n"
        "6. Instagram SOMENTE em momento útil (agendamento confirmado, cliente perguntou).\n"
        "7. Não parecer FAQ — voz humana, não robô.\n"
        "8. Não inventar preço.\n\n"
        f"Mensagem do cliente: {ctx.message}"
    )

    try:
        result = await _call_local_qwen(
            [{"role": "user", "content": system_prompt}],
            max_retries=1,
        )
        return result.strip()
    except Exception as e:
        logger.warning("MiniMax falhou: %s", e)
        return FALLBACK_RESPONSE[0]


# ── Guardrail ────────────────────────────────────────────────────────────────

async def _apply_guardrail(
    response: str,
    ctx: OrchestratorContext,
) -> tuple[bool, str]:
    """
    Valida resposta com guardrail_validator.
    Retorna (approved, blocked_response).
    """
    # Import dinâmico
    try:
        from agent_graph.guards.response_guard import validate_response_before_send
        approved, reasons = validate_response_before_send(response, ctx.lead_state)
        if not approved:
            logger.warning("Guardrail bloqueou resposta para %s: %s", ctx.msg_id, reasons)
            return False, select_error()
        return True, response
    except ImportError:
        # Sem guardrail disponível = permite
        return True, response


# ── Instagram momento útil ──────────────────────────────────────────────────

def _append_instagram_if_applicable(
    response: str,
    last_messages: list[str],
) -> str:
    """Adiciona Instagram copy se momento é útil (não é spam)."""
    if not can_show_instagram(last_messages):
        return response
    import random
    return response + "\n\n" + random.choice(INSTAGRAM_COPY)


# ── Main Orchestrator ────────────────────────────────────────────────────────

async def process_message(
    phone: str,
    message: str,
    instance: str,
    msg_id: str,
    message_type: str = "conversation",
    media_url: str = "",
    media_base64: str = "",
    lead_state: dict[str, Any] | None = None,
    conversation_history: list[str] | None = None,
    client_name: str | None = None,
) -> OrchestratorContext:
    """
    Processa uma mensagem e retorna contexto com resposta e metadados.
    """
    ctx = OrchestratorContext(
        phone=phone,
        message=message,
        instance=instance,
        msg_id=msg_id,
        media_url=media_url,
        media_base64=media_base64,
        message_type=message_type,
        lead_state=lead_state or {},
    )
    t0 = time.monotonic()

    # 1. Routing
    ctx.routing_decision = route(message)
    ctx.lane = ctx.routing_decision.lane

    logger.info(
        "[%s] Routing: lane=%s intent=%s reason=%s",
        msg_id[:8],
        ctx.lane.value,
        ctx.routing_decision.intent,
        ctx.routing_decision.reason,
    )

    # 2. Fast Lane
    if ctx.lane == Lane.FAST:
        response = await _run_fast_lane(ctx, client_name)
        ctx.final_response = response
        ctx.sent_via = "fast"
        ctx.microcopy_sent = True
        ctx.processing_time_ms = (time.monotonic() - t0) * 1000
        return ctx

    # 3. Slow Lane
    # 3a. Verificar risco elétrico ( PRIORIDADE)
    electrical_risk = check_electrical_risk(message)
    if electrical_risk != ElectricalRisk.NONE:
        directive = get_electrical_directive(electrical_risk)
        if directive:
            ctx.final_response = directive
            ctx.sent_via = "electrical_safety"
            ctx.processing_time_ms = (time.monotonic() - t0) * 1000
            return ctx

    # 3b. Enviar typing ON
    typing_task: asyncio.Task | None = None
    if should_start_typing(ctx.lane.value, message, ctx.microcopy_sent):
        typing_task = asyncio.create_task(send_typing_on(phone, instance))

    # 3c. Enviar microcopy de transição
    if ctx.routing_decision.should_send_microcopy and not ctx.microcopy_sent:
        microcopy = select_transition()
        ctx.microcopy_sent = True
        # Não bloqueia — microcopy é enviada E typing ativado em paralelo

    # 3d. Aguardar typing iniciar E chamar MiniMax em paralelo
    if typing_task:
        await typing_task

    minimax_task = asyncio.create_task(_call_minimax_slow(ctx))

    # 3e. Aguardar MiniMax com timeout
    try:
        response = await asyncio.wait_for(minimax_task, timeout=TYPING_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning("MiniMax timeout para %s", msg_id[:8])
        await send_typing_off(phone, instance)
        ctx.final_response = (
            "Opa, demorei um pouco mais do que esperava! "
            "Me passa sua cidade e bairro que já vou verificando aqui."
        )
        ctx.sent_via = "minimax_timeout"
        ctx.processing_time_ms = (time.monotonic() - t0) * 1000
        return ctx

    # 3f. Desativar typing
    await send_typing_off(phone, instance)

    # 3g. Aplicar guardrail
    approved, final_text = await _apply_guardrail(response, ctx)
    if not approved:
        ctx.final_response = final_text  # select_error()
        ctx.sent_via = "guardrail_blocked"
        ctx.processing_time_ms = (time.monotonic() - t0) * 1000
        return ctx

    # 3h. Enforce question limit
    final_text = enforce_question_limit(final_text)

    # 3i. Instagram momento útil
    history = conversation_history or []
    final_text = _append_instagram_if_applicable(final_text, history)

    # 3j. Sanitização final
    final_text = sanitize_output(final_text)

    ctx.final_response = final_text
    ctx.sent_via = "slow"
    ctx.processing_time_ms = (time.monotonic() - t0) * 1000
    return ctx
