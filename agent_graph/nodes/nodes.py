from __future__ import annotations

import os
import asyncio
import logging
import hashlib
import json
import re
import unicodedata
import httpx
from copy import deepcopy
from typing import Any, TypeGuard

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from agent_graph.utils.context_window import (
    LOCAL_REFRIMIX_SYSTEM_PROMPT,
    ChatMessage,
    fit_chat_messages,
)
from agent_graph.utils.llm_output import strip_llm_markup
from agent_graph.utils.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    sleep_with_backoff,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# System prompt — voz do Will (Refrimix, Guarujá/SP)
WILL_SYSTEM_PROMPT = """Você é o Will, proprietário e atendente comercial técnico da Refrimix Tecnologia em Guarujá/SP. Estamos em Maio de 2026.
Sua função principal NÃO é apenas responder mensagens. Sua função é fazer onboarding do lead, captar dados, qualificar o atendimento e conduzir para orçamento/agendamento.

REGRA ABSOLUTA - ANTI-REPETIÇÃO E MEMÓRIA DE HISTÓRICO:
Antes de responder qualquer mensagem, você DEVE ler todo o histórico da conversa e extrair os dados já informados.
NUNCA pergunte novamente algo que o cliente já disse.
- Se o cliente já informou que é instalação, você deve continuar o fluxo de instalação.
- Se o cliente já informou bairro, cidade, tipo de serviço, marca, BTUs, sintoma ou foto, use essa informação.
- Perguntar algo repetido ou recomeçar o atendimento do zero é um erro gravíssimo!
- Se estiver em dúvida, confirme de forma inteligente, sem recomeçar.
  Exemplo errado: "É instalação, manutenção ou higienização?" (quando o cliente já informou).
  Exemplo certo: "Perfeito, como é uma instalação, preciso agora entender o local para te passar uma orientação correta."

ETAPA 1 — EXTRAÇÃO DE ESTADO MENTAL (JSON MENTAL)
A cada mensagem recebida, atualize mentalmente o seguinte JSON com os dados do lead coletados até agora no histórico da conversa:
{
  "nome": null,
  "cidade_bairro": null,
  "tipo_servico": null,  // instalacao, manutencao, higienizacao, conserto, eletrica, projeto
  "marca": null,
  "btus": null,
  "modelo_aparelho": null, // split, janela, cassete, piso-teto, etc.
  "aparelho_novo_ou_usado": null,
  "sintoma": null,
  "urgencia": null,
  "fotos_recebidas": false,
  "dados_instalacao": {
    "local_evaporadora": null,
    "local_condensadora": null,
    "distancia_aproximada": null,
    "ponto_eletrico": null,
    "tubulacao_existente": null
  },
  "dados_manutencao_higienizacao": {
    "tempo_sem_manutencao": null,
    "cheiro_ruim": null,
    "pinga_agua": null,
    "rinite_alergia": null
  },
  "dados_conserto_eletrica": {
    "liga": null,
    "gela": null,
    "codigo_erro": null,
    "disjuntor_cai": null,
    "fio_esquenta": null
  }
}

ETAPA 2 — RESPOSTA AO CLIENTE
Responda usando apenas as informações que ainda faltam.
- NUNCA pergunte novamente um dado já preenchido no JSON mental.
- Se o campo "tipo_servico" já estiver preenchido, avance no fluxo correspondente e nunca pergunte se é instalação, manutenção ou higienização.
- Uma boa resposta deve confirmar o que já foi entendido e pedir apenas o próximo dado necessário (no máximo 1 a 3 perguntas úteis por vez).

DIRETRIZES DE TOM DE VOZ E ESTILO:
- Tom de voz: Português brasileiro natural, direto, humano, consultivo e profissional (conversa de WhatsApp de empresa séria).
- NUNCA use português europeu ou palavras em espanhol (como "mucho", "equipo", "bueno").
- Evitar formalidade exagerada, gírias demais ou excesso de emojis.
- Respostas curtas, claras e úteis (máximo de 1 a 3 parágrafos curtos).
- Não faça textão, não pressione o cliente com promoções, não invente preços ou disponibilidade e nunca dê diagnóstico definitivo sem avaliação/inspeção local.
- Formate como WhatsApp humano: sem emoji, com parágrafos curtos, linha em branco entre blocos e lista numerada curta quando pedir 2 ou mais dados.
- Não use cabeçalhos markdown, bullets decorativos, "Prezado cliente", "Segue abaixo", "Conforme solicitado" ou "Para prosseguirmos".
- Preços Comerciais da Refrimix:
  - Instalação de split com acesso simples: R$800 no Guarujá ou R$850 em Santos, São Vicente e Praia Grande. Qualquer outra situação (acesso difícil, telhado, altura, distância grande, VRF, central) exige análise técnica no local de R$50 (abatida do orçamento se aprovado).
  - Higienização de split padrão: R$200 por aparelho.
  - Manutenção corretiva / conserto: Não tem preço fixo sem diagnóstico no local. A análise técnica custa R$50 (abatida do valor do serviço se aprovado).

FLUXO DE ONBOARDING POR SERVIÇO:

1. Tipo de serviço não informado:
   Pergunte qual serviço ele precisa.
   Preset: "Oi, tudo bem? Me passa rapidinho o que você precisa no ar-condicionado: instalação, manutenção, higienização ou conserto? Se puder, já me envie também uma foto do aparelho e o bairro/cidade. Assim eu te oriento melhor e evito te passar um valor errado."

2. Instalação:
   Pergunte os dados de instalação que ainda faltam (BTUs, local da evaporadora/condensadora, ponto elétrico, distância, bairro/cidade, fotos).
   Preset: "Perfeito, entendi que é instalação. Pra eu avaliar corretamente e evitar te passar valor errado, me envia: 1. Foto do local onde vai ficar a evaporadora; 2. Foto do local onde vai ficar a condensadora; 3. Capacidade do aparelho em BTUs, se souber; 4. Bairro/cidade."
   Se já tiver BTUs informado: "Perfeito, instalação de split [BTUs]. Agora preciso só entender o local. Me envia uma foto da parede onde vai ficar a evaporadora e outra do local da condensadora? Assim consigo avaliar distância, acesso, dreno e ponto elétrico."
   Se já tiver foto enviada: "Recebi a foto, obrigado. Pelo local, agora preciso confirmar só duas coisas: já existe ponto elétrico exclusivo para o ar-condicionado? E a condensadora vai ficar do outro lado dessa parede ou em outro ponto?"

3. Manutenção / Higienização:
   Pergunte sobre tempo sem manutenção, sintomas e fotos.
   Sintoma Rinite/Cheiro ruim: "Entendi. Quando o ar fica com cheiro ruim, sensação de ar pesado ou começa a incomodar rinite/alergia, normalmente a higienização técnica ajuda bastante, principalmente se o aparelho está há muito tempo sem manutenção. Me manda uma foto do aparelho e o bairro/cidade que eu verifico a melhor opção de atendimento para você."

4. Conserto:
   Pergunte sintomas técnicos (se liga, se gela, se aparece código de erro, se a condensadora liga, disjuntor cai) e peça foto/vídeo.
   Sintoma Não Gela: "Entendi. Quando o ar liga mas não gela, pode ser desde falta de manutenção até falha na parte elétrica, gás, sensor, placa ou compressor. O ideal é avaliar para não trocar peça sem necessidade. Me manda, por favor: 1. Foto do aparelho; 2. Marca e BTUs, se souber; 3. Se a unidade externa está ligando; 4. Bairro/cidade. Com isso eu te digo o melhor caminho para resolver."

5. Risco Elétrico / Disjuntor caindo (TRATAR COMO PRIORIDADE):
   Se disjuntor cair, fio esquentar ou cheiro de queimado, recomende IMEDIATAMENTE deixar o aparelho desligado até a avaliação técnica por segurança.
   Preset: "Nesse caso, o ideal é deixar o aparelho desligado até avaliar, porque pode envolver sobrecarga, disjuntor fora do padrão, cabo inadequado ou falha interna no equipamento. Me envie uma foto do disjuntor, do aparelho e informe o bairro/cidade. Aí conseguimos analisar com mais segurança e te orientar sobre o atendimento."

6. Cliente pergunta preço cedo demais:
   "Consigo te passar uma base, sim. Só não quero te passar um valor errado sem ver o local, porque instalação depende de distância, ponto elétrico, suporte, dreno e acesso da condensadora. Me manda uma foto do local interno e externo que eu já te oriento melhor."

7. Follow-up pós-orçamento:
   "Oi, tudo bem? Passando só para saber se ficou alguma dúvida sobre o orçamento do ar-condicionado. Se quiser, consigo te orientar sobre o melhor dia para fazer o serviço e deixar tudo organizado para evitar retrabalho."

EXEMPLOS VALIDADOS DE FORMATAÇÃO WHATSAPP:
Lead: "Quanto fica instalar um split 12000 em Santos?"
Will: "Perfeito, instalação de split 12.000 BTUs em Santos.

Para acesso simples, fica R$850.

Se tiver telhado, altura, distância grande ou ponto elétrico fora do padrão, precisa avaliar antes para não te passar valor errado.

Me manda uma foto do local interno e uma do local externo?"

Lead: "Quero instalar um ar no quarto"
Will: "Perfeito, instalação no quarto.

Pra eu avaliar certinho, me manda:

1. Foto da parede onde vai a unidade interna
2. Foto do local onde vai a condensadora
3. Bairro/cidade do atendimento

Com isso eu já consigo te orientar melhor."

Lead: "Meu ar tá com cheiro ruim"
Will: "Entendi.

Cheiro ruim normalmente aparece quando o aparelho está com sujeira interna, umidade acumulada ou muito tempo sem higienização.

Pra te orientar certinho, me manda:

1. Foto do aparelho
2. Bairro/cidade
3. Faz quanto tempo que não higieniza?"

Lead: "Queria mudar o horário"
Will: "Vi aqui que você já tem um serviço em andamento com a Refrimix.

Vou tratar isso como acompanhamento, não como orçamento novo.

Me confirma qual período fica melhor pra você: manhã ou tarde?"

Lead: "O disjuntor cai e tem cheiro de queimado"
Will: "Nesse caso, o ideal é deixar o aparelho desligado até avaliar.

Pode envolver sobrecarga, cabo inadequado, disjuntor fora do padrão ou falha interna no equipamento.

Me manda uma foto do disjuntor e do aparelho para eu adiantar a análise."
"""


# ──────────────────────────────────────────────────────────────────────────────
# LLM Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _is_human_message(message: BaseMessage | Any) -> TypeGuard[HumanMessage]:
    return isinstance(message, HumanMessage)


def _is_ai_message(message: BaseMessage | Any) -> TypeGuard[AIMessage]:
    return isinstance(message, AIMessage)


def _message_text(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", message)
    return content if isinstance(content, str) else str(content)


def _breaker_config(prefix: str, default_threshold: int, default_timeout: float) -> CircuitBreakerConfig:
    return CircuitBreakerConfig(
        failure_threshold=_env_int(f"{prefix}_CIRCUIT_FAILURE_THRESHOLD", default_threshold),
        recovery_timeout_seconds=_env_float(f"{prefix}_CIRCUIT_RECOVERY_SECONDS", default_timeout),
        half_open_success_threshold=_env_int(f"{prefix}_CIRCUIT_HALF_OPEN_SUCCESSES", 1),
    )


_MINIMAX_SEMAPHORE = asyncio.Semaphore(_env_int("MINIMAX_CONCURRENCY", 4))
_QWEN_SEMAPHORE = asyncio.Semaphore(_env_int("LOCAL_QWEN_CONCURRENCY", 1))
_PTBR_SEMAPHORE = asyncio.Semaphore(_env_int("LOCAL_PTBR_CONCURRENCY", 1))

_MINIMAX_BREAKER = CircuitBreaker("minimax", _breaker_config("MINIMAX", 4, 45.0))
_QWEN_BREAKER = CircuitBreaker("local-qwen", _breaker_config("LOCAL_QWEN", 3, 30.0))
_PTBR_BREAKER = CircuitBreaker("local-ptbr", _breaker_config("LOCAL_PTBR", 3, 30.0))


def _extract_chat_content(data: dict[str, Any], provider: str) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"{provider} sem choices: {data}")

    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError(f"{provider} choice inválida: {data}")

    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return strip_llm_markup(content)

    text = first.get("text")
    if isinstance(text, str):
        return strip_llm_markup(text)

    raise RuntimeError(f"{provider} sem content textual: {data}")


def _fit_for_qwen(messages: list[ChatMessage], max_tokens: int, context_tokens: int) -> list[ChatMessage]:
    window = fit_chat_messages(
        messages,
        max_context_tokens=context_tokens,
        reserved_output_tokens=max_tokens,
        safety_margin_tokens=_env_int("LOCAL_QWEN_CONTEXT_SAFETY_TOKENS", 192),
        compact_system_prompt=LOCAL_REFRIMIX_SYSTEM_PROMPT,
    )
    if window.dropped_messages or window.compacted_system_prompt or window.trimmed_tokens < window.original_tokens:
        logger.info(
            "Qwen context window: %s -> %s tokens, dropped=%s, compacted_system=%s",
            window.original_tokens,
            window.trimmed_tokens,
            window.dropped_messages,
            window.compacted_system_prompt,
        )
    return window.messages


async def _call_groq(messages: list[ChatMessage], max_retries: int = 3) -> str:
    """Modelo Groq super rápido para saudações e onboarding instantâneo."""
    api_key = os.getenv("GROQ_API_KEY", "")
    base_url = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    max_tokens = _env_int("GROQ_MAX_TOKENS", 250)

    if not api_key:
        raise RuntimeError("GROQ_API_KEY não configurado")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=_env_float("GROQ_TIMEOUT_SECONDS", 15.0)) as client:
                resp = await client.post(
                    f"{base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.3},
                )
                resp.raise_for_status()
                data = resp.json()
                return _extract_chat_content(data, "Groq")
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await asyncio.sleep(0.3 * (attempt + 1))
    raise RuntimeError(f"Groq falhou: {last_error}")


async def _call_minimax(messages: list[ChatMessage], max_retries: int = 5) -> str:
    api_key = os.getenv("MINIMAX_API_KEY", "")
    base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
    model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
    max_tokens = _env_int("MINIMAX_MAX_TOKENS", 400)

    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY não configurado")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async def request() -> str:
                async with _MINIMAX_SEMAPHORE:
                    async with httpx.AsyncClient(timeout=_env_float("MINIMAX_TIMEOUT_SECONDS", 90.0)) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json={"model": model, "messages": messages, "max_tokens": max_tokens},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        if "error" in data:
                            raise RuntimeError(f"MiniMax error: {data['error']}")
                        return _extract_chat_content(data, "MiniMax")

            return await _MINIMAX_BREAKER.call(request)
        except CircuitOpenError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await sleep_with_backoff(attempt, base_seconds=1.0, cap_seconds=20.0)
    raise RuntimeError(f"MiniMax falhou após {max_retries} tentativas: {last_error}")


async def _call_local_qwen(messages: list[ChatMessage], max_retries: int = 2) -> str:
    """Fallback local OpenAI-compatible via llama.cpp/Qwen2.5-VL."""
    base_url = os.getenv("LOCAL_QWEN_BASE_URL", "http://127.0.0.1:8011/v1").rstrip("/")
    model = os.getenv("LOCAL_QWEN_MODEL", "qwen2.5-vl-7b-instruct")
    max_tokens = _env_int("LOCAL_QWEN_MAX_TOKENS", 300)
    context_tokens = _env_int("LOCAL_QWEN_CONTEXT_TOKENS", 4096)

    last_error: Exception | None = None
    for attempt in range(max_retries):
        effective_context_tokens = max(1024, int(context_tokens * (0.72**attempt)))
        fitted_messages = _fit_for_qwen(messages, max_tokens, effective_context_tokens)
        try:
            async def request() -> str:
                async with _QWEN_SEMAPHORE:
                    async with httpx.AsyncClient(timeout=_env_float("LOCAL_QWEN_TIMEOUT_SECONDS", 45.0)) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={"Content-Type": "application/json"},
                            json={
                                "model": model,
                                "messages": fitted_messages,
                                "max_tokens": max_tokens,
                                "temperature": 0.2,
                                "frequency_penalty": 0.5,
                                "presence_penalty": 0.5,
                            },
                        )
                        resp.raise_for_status()
                        return _extract_chat_content(resp.json(), "Qwen local")

            return await _QWEN_BREAKER.call(request)
        except httpx.HTTPStatusError as exc:
            last_error = exc
            body = exc.response.text[:500]
            logger.error("Qwen HTTPStatusError %s: %s", exc.response.status_code, body)
            if attempt < max_retries - 1:
                await sleep_with_backoff(attempt, base_seconds=0.5, cap_seconds=4.0)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await sleep_with_backoff(attempt, base_seconds=0.5, cap_seconds=4.0)
    raise RuntimeError(f"Qwen local falhou: {last_error}")


async def _call_local_ptbr(messages: list[ChatMessage], max_retries: int = 1) -> str:
    """Modelo local PT-BR opcional para polir linguagem sem depender de nuvem."""
    base_url = os.getenv("LOCAL_PTBR_BASE_URL", "").rstrip("/")
    model = os.getenv("LOCAL_PTBR_MODEL", "qwen2.5-7b-pt-br-instruct")
    max_tokens = _env_int("LOCAL_PTBR_MAX_TOKENS", 240)
    if not base_url:
        raise RuntimeError("LOCAL_PTBR_BASE_URL não configurado")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        fitted_messages = fit_chat_messages(
            messages,
            max_context_tokens=_env_int("LOCAL_PTBR_CONTEXT_TOKENS", 4096),
            reserved_output_tokens=max_tokens,
            safety_margin_tokens=128,
            compact_system_prompt=LOCAL_REFRIMIX_SYSTEM_PROMPT,
        ).messages
        try:
            async def request() -> str:
                async with _PTBR_SEMAPHORE:
                    async with httpx.AsyncClient(timeout=_env_float("LOCAL_PTBR_TIMEOUT_SECONDS", 45.0)) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={"Content-Type": "application/json"},
                            json={
                                "model": model,
                                "messages": fitted_messages,
                                "max_tokens": max_tokens,
                                "temperature": 0.15,
                            },
                        )
                        resp.raise_for_status()
                        return _extract_chat_content(resp.json(), "PT-BR local")

            return await _PTBR_BREAKER.call(request)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await sleep_with_backoff(attempt, base_seconds=0.5, cap_seconds=4.0)
    raise RuntimeError(f"PT-BR local falhou: {last_error}")


async def llm_chat(messages: list[ChatMessage], max_retries: int = 2, fast_route: bool = False) -> str:
    """MiniMax principal ou modelos locais (se fast_route for True), com fallback cruzado."""
    if fast_route:
        # 1. Tenta o modelo local PT-BR (Qwen 2.5 7b pt-br) na porta 8211 (custo zero!)
        local_ptbr_url = os.getenv("LOCAL_PTBR_BASE_URL", "")
        if local_ptbr_url:
            try:
                return await _call_local_ptbr(messages, max_retries=1)
            except Exception as e:
                logger.warning(f"Local PT-BR fast route falhou, tentando local Qwen: {e}")

        # 2. Tenta o Qwen local (Qwen 2.5 VL 7b) na porta 8010 (custo zero!)
        try:
            return await _call_local_qwen(messages, max_retries=1)
        except Exception as e:
            logger.warning(f"Local Qwen fast route falhou, tentando Groq/MiniMax: {e}")

        # 3. Tenta Groq (llama-3.1-8b-instant) na nuvem se os locais falharem
        groq_key = os.getenv("GROQ_API_KEY", "")
        if groq_key:
            try:
                return await _call_groq(messages, max_retries=1)
            except Exception as e:
                logger.warning(f"Groq fast route falhou, tentando MiniMax: {e}")

    # Fluxo principal padrão
    minimax_key = os.getenv("MINIMAX_API_KEY", "")
    if minimax_key:
        try:
            return await _call_minimax(messages, max_retries)
        except Exception as e:
            logger.warning(f"MiniMax falhou, usando Qwen local: {e}")

    return await _call_local_qwen(messages)


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _normalize_service(service: str | None) -> str | None:
    if service == "hygienizacao":
        return "higienizacao"
    if service == "conserto":
        return "manutencao"
    return service


def _sales_cache_key(
    service: str | None,
    text: str,
    lead_state: dict[str, Any] | None = None,
    missing_fields: list[str] | None = None,
    do_not_ask: list[str] | None = None,
) -> str:
    normalized = _normalize_text(text)
    text_digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    lead_state = lead_state or {}
    state_fingerprint = {
        "tipo_servico": lead_state.get("tipo_servico"),
        "cidade_bairro": lead_state.get("cidade_bairro"),
        "btus": lead_state.get("btus"),
        "relationship_type": lead_state.get("relationship_type"),
        "pipeline_stage": lead_state.get("pipeline_stage"),
        "missing_fields": list(missing_fields or [])[:3],
        "do_not_ask": sorted(str(field) for field in (do_not_ask or [])),
    }
    state_digest = hashlib.sha256(
        json.dumps(state_fingerprint, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]
    return f"sales_reply:v2:{service or 'none'}:{state_digest}:{text_digest}"


def _looks_like_price_question(text: str) -> bool:
    lowered = _normalize_text(text)
    return any(term in lowered for term in ("quanto", "custa", "valor", "preço", "preco", "orçamento", "orcamento"))


def _lead_state_copy() -> dict[str, Any]:
    return deepcopy(DEFAULT_LEAD_STATE)


def _has_photo_context(lead_state: dict[str, Any]) -> bool:
    fotos = lead_state.get("fotos")
    return isinstance(fotos, dict) and any(bool(value) for value in fotos.values())


def _latest_human_text(messages: list[Any]) -> str:
    return next(
        (_message_text(message) for message in reversed(messages) if _is_human_message(message)),
        "",
    )


def _infer_lead_fields_from_text(lead_state: dict[str, Any], text: str, message_type: str | None = None) -> dict[str, Any]:
    """Fallback determinístico para campos críticos quando o extrator LLM falha."""
    updated = deepcopy(lead_state)
    folded = _fold_text(text)

    if not updated.get("tipo_servico"):
        if _contains_any(folded, ("instalar", "instalacao", "instalação", "colocar ar", "por ar")):
            updated["tipo_servico"] = "instalacao"
        elif _contains_any(folded, ("limpeza", "higienizacao", "higienização", "limpar")):
            updated["tipo_servico"] = "higienizacao"
        elif _contains_any(folded, ("manutencao", "manutenção", "consertar", "nao gela", "não gela", "pingando")):
            updated["tipo_servico"] = "manutencao"

    if not updated.get("btus"):
        btu_match = re.search(r"\b(\d{1,2}\.?\d{3}|\d{4,5})\s*(?:btu|btus)\b", folded)
        if btu_match:
            updated["btus"] = btu_match.group(1).replace(".", "")
        elif (
            updated.get("tipo_servico") in {"instalacao", "manutencao", "higienizacao"}
            or _contains_any(folded, ("split", "ar condicionado", "ar-condicionado", "instalar", "instalacao", "instalação"))
        ):
            common_btu_match = re.search(
                r"\b(7000|7500|9000|12000|18000|22000|24000|30000|36000|48000|60000)\b",
                folded,
            )
            if common_btu_match:
                updated["btus"] = common_btu_match.group(1)

    if not updated.get("cidade_bairro"):
        city_terms = (
            "guaruja", "guarujá", "santos", "sao vicente", "são vicente",
            "praia grande", "cubatao", "cubatão", "mongagua", "mongaguá",
        )
        city = next((term for term in city_terms if term in folded), None)
        bairro_match = re.search(r"\b(?:bairro|no|na|em)\s+([a-z0-9 çãõáéíóúâêô-]{3,40})", folded)
        if city:
            updated["cidade_bairro"] = city
        elif bairro_match:
            updated["cidade_bairro"] = bairro_match.group(1).strip()

    if not updated.get("nome"):
        name_match = re.search(r"\b(?:meu nome e|meu nome é|sou|aqui e|aqui é)\s+([a-záéíóúãõâêôç]{2,}(?:\s+[a-záéíóúãõâêôç]{2,})?)", text, re.I)
        if name_match:
            updated["nome"] = name_match.group(1).strip().title()

    if message_type == "imageMessage" or text.strip().startswith("[Imagem:"):
        fotos = updated.setdefault("fotos", {})
        if isinstance(fotos, dict):
            fotos["aparelho"] = True

    return updated


def should_avoid_reasking(field: str | None, lead_state: dict[str, Any] | None) -> bool:
    if not field:
        return False
    counts = (lead_state or {}).get("ask_count_by_field") or {}
    return int(counts.get(field) or 0) >= 2


def _important_missing_field(
    missing_fields: list[str],
    do_not_ask: list[str],
    lead_state: dict[str, Any] | None = None,
) -> str | None:
    priority = [
        "cidade_bairro",
        "btus",
        "foto_local_interno",
        "foto_local_externo",
        "foto_disjuntor",
        "foto_aparelho",
        "ponto_eletrico_exclusivo",
        "distancia_aproximada",
        "tubulacao_existente",
        "tempo_sem_manutencao",
        "pinga_agua",
        "nome",
    ]
    blocked = set(do_not_ask)
    for field in priority:
        if field in missing_fields and field not in blocked and not should_avoid_reasking(field, lead_state):
            return field
    return next((field for field in missing_fields if field not in blocked), None)


def _question_for_field(field: str | None) -> str:
    return {
        "cidade_bairro": "Em qual cidade e bairro fica o atendimento?",
        "btus": "Qual é a capacidade do aparelho em BTUs?",
        "foto_local_interno": "Pode me mandar uma foto do ponto onde vai a unidade interna?",
        "foto_local_externo": "Pode me mandar uma foto do local da condensadora?",
        "foto_disjuntor": "Pode me mandar uma foto do quadro de luz?",
        "foto_aparelho": "Pode me mandar uma foto do aparelho?",
        "ponto_eletrico_exclusivo": "Já tem ponto elétrico exclusivo para o ar?",
        "distancia_aproximada": "A distância entre as unidades fica perto de quantos metros?",
        "tubulacao_existente": "Já existe tubulação/infra pronta no local?",
        "tempo_sem_manutencao": "Faz quanto tempo que não passa por manutenção?",
        "pinga_agua": "Ele está pingando água?",
        "nome": "Qual é seu nome?",
    }.get(field, "Qual é o próximo detalhe que você já consegue me informar?")


def infer_asked_field_from_response(response: str, missing_fields: list[str]) -> str | None:
    text = _fold_text(response)
    patterns = {
        "cidade_bairro": ("cidade", "bairro", "onde fica"),
        "btus": ("btus", "btu", "capacidade"),
        "foto_local_interno": ("foto do local interno", "foto interna", "unidade interna"),
        "foto_local_externo": ("foto do local externo", "foto externa", "condensadora"),
        "ponto_eletrico_exclusivo": ("ponto eletrico", "ponto elétrico", "energia"),
        "distancia_aproximada": ("distancia", "distância", "metros"),
        "tubulacao_existente": ("tubulacao", "tubulação", "infra pronta"),
        "tempo_sem_manutencao": ("tempo sem manutencao", "tempo sem manutenção", "ultima manutenção", "última manutenção"),
        "pinga_agua": ("pingando", "vazando agua", "vazando água", "pinga"),
        "nome": ("nome",),
    }
    missing = set(missing_fields or [])
    for field, terms in patterns.items():
        if field in missing and any(term in text for term in terms):
            return field
    return None


def _repeated_field_strategy(field: str | None, lead_state: dict[str, Any]) -> str | None:
    if not field or not should_avoid_reasking(field, lead_state):
        return None
    if field == "cidade_bairro":
        return "Vou adiantar pelo que já tenho. Quando puder, me manda o bairro/cidade que eu fecho a disponibilidade certinha."
    if field in {"foto_local_interno", "foto_local_externo", "foto_aparelho"}:
        return "Vou adiantar pelo que já tenho. Quando puder, me manda as fotos que eu confirmo o melhor caminho sem te passar orientação errada."
    return "Vou adiantar pelo que já tenho. Quando puder, me manda esse detalhe que eu fecho a orientação certinha."


def _city_price_for_installation(lead_state: dict[str, Any], text: str) -> str:
    location = _fold_text(" ".join(str(value or "") for value in (lead_state.get("cidade_bairro"), text)))
    if "guaruja" in location:
        return "No Guarujá, instalação de split com acesso simples fica R$800."
    if any(city in location for city in ("santos", "sao vicente", "praia grande")):
        return "Em Santos, São Vicente e Praia Grande, instalação de split com acesso simples fica R$850."
    return "Instalação de split com acesso simples fica R$800 no Guarujá ou R$850 em Santos, São Vicente e Praia Grande."


def _direct_price_response(
    service: str | None,
    text: str,
    lead_state: dict[str, Any] | None = None,
    missing_fields: list[str] | None = None,
    do_not_ask: list[str] | None = None,
) -> str | None:
    if not _looks_like_price_question(text):
        return None
    lead_state = lead_state or {}
    missing_fields = missing_fields or []
    do_not_ask = do_not_ask or []
    next_field = _important_missing_field(missing_fields, do_not_ask, lead_state)
    repeated_strategy = _repeated_field_strategy(next_field, lead_state)
    if repeated_strategy:
        next_question = repeated_strategy
    else:
        next_question = _question_for_field(next_field) if next_field else "Se quiser, me passa uma janela de horário pra eu verificar agenda."
    if service == "instalacao":
        return (
            f"{_city_price_for_installation(lead_state, text)} "
            "Se tiver telhado, escada alta, distância grande, quadro de luz fora do padrão, ponto de dreno pendente ou outro tipo de sistema, a análise técnica no local custa R$50 e abate se aprovar o orçamento. "
            f"{next_question}"
        )
    if service == "higienizacao":
        return (
            "Higienização de split fica R$200 por aparelho. "
            "Para cassete, duto, splitão ou acesso difícil, precisa análise técnica de R$50 abatível. "
            f"{next_question}"
        )
    if service in {"manutencao", "pmoc", "consultoria", "projeto-central"}:
        return (
            "Nesse serviço eu não chuto valor por WhatsApp. A análise técnica no local custa R$50 e esse valor abate se você aprovar o orçamento. "
            f"{next_question}"
        )
    return None


def _active_service_response(user_text: str, active_service: dict[str, Any]) -> str:
    service = _normalize_service(active_service.get("service")) or "serviço"
    status = str(active_service.get("status") or "em andamento").replace("_", " ")
    scheduled = active_service.get("scheduled_window")
    address = active_service.get("address")
    notes = active_service.get("notes")
    lowered = _normalize_text(user_text)

    base = f"Já identifiquei aqui que você tem um serviço de {service} {status} com a Refrimix."
    if scheduled:
        base += f" Está previsto para {scheduled}."
    if address:
        base += f" Local: {address}."
    if notes:
        base += f" Observação registrada: {notes}."

    if _contains_any(lowered, ("atras", "demor", "nao veio", "não veio", "sumiu", "retorno")):
        return (
            f"{base} Vou tratar isso como acompanhamento do serviço, não como venda nova. "
            "Me manda uma foto ou me diz o que mudou para eu sinalizar o gerente agora?"
        )

    if _contains_any(lowered, ("mudar horario", "trocar horario", "remarcar", "reagendar", "agenda")):
        return (
            f"{base} Consigo ajudar a remarcar ou confirmar a janela. "
            "Qual melhor período para você: manhã ou tarde?"
        )

    return (
        f"{base} Vou seguir por acompanhamento, sem te passar orçamento novo. "
        "Me fala o que você precisa atualizar nesse serviço?"
    )


def _past_customer_response(last_service: dict[str, Any]) -> str:
    service = _normalize_service(last_service.get("service")) or "serviço"
    status = str(last_service.get("status") or "concluído").replace("_", " ")
    updated = last_service.get("updated_at") or last_service.get("created_at")
    suffix = f" O último registro que encontrei é de {updated}." if updated else ""
    return (
        f"Vi aqui que você já teve um {service} {status} com a Refrimix.{suffix} "
        "É uma dúvida sobre esse atendimento anterior ou você quer abrir um novo atendimento?"
    )


def _no_context_response() -> str:
    return (
        "Não quero te orientar no escuro. Vou sinalizar o gerente para revisar essa conversa, "
        "e por aqui me manda uma frase curta dizendo se é instalação, manutenção ou higienização?"
    )


def _appointment_ready_response(lead_state: dict[str, Any]) -> str:
    service = lead_state.get("tipo_servico") or "atendimento"
    location = lead_state.get("cidade_bairro") or "local informado"
    return (
        f"Perfeito, já tenho dados suficientes para encaminhar o agendamento de {service} em {location}. "
        "Vou sinalizar o gerente agora para confirmar a melhor janela com você. Qual período você prefere: manhã ou tarde?"
    )


def _default_whatsapp_cta(outcome: str | None) -> str:
    return {
        "onboarding": "Qual serviço você precisa?",
        "analise_tecnica": "Me fala a cidade, o modelo e manda uma foto do aparelho?",
        "higienizacao_preventiva": "Quantos aparelhos são?",
        "reuniao_projeto": "Me manda a planta, metragem e quantidade de ambientes?",
        "duvida": "Qual detalhe você quer resolver primeiro?",
        "escalar_humano": "Me passa seu nome e o endereço do atendimento?",
    }.get(outcome or "", "Me fala a cidade, o modelo e manda uma foto do aparelho?")


_CUSTOMER_EMOJI_RE = re.compile(
    "["
    "\U0001F1E6-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\u2600-\u27BF"
    "\uFE0F"
    "\u200D"
    "]+"
)


def _strip_customer_emojis(text: str) -> str:
    """Remove emojis e símbolos decorativos das respostas enviadas ao cliente."""
    cleaned = _CUSTOMER_EMOJI_RE.sub("", text or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    return cleaned.strip()


def _clean_whatsapp_markdown(text: str) -> str:
    """Limpa markdown pesado preservando quebras úteis para WhatsApp."""
    cleaned = text or ""
    cleaned = re.sub(r"```(?:[a-zA-Z0-9_-]+)?\n?(.*?)```", r"\1", cleaned, flags=re.S)
    cleaned = cleaned.replace("**", "*")
    cleaned = cleaned.replace("__", "_")
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s{0,3}>\s?", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        cleaned = cleaned[1:-1].strip()
    cleaned = "\n".join(re.sub(r"[ \t]{2,}", " ", line).strip() for line in cleaned.splitlines())
    cleaned = re.sub(r"([,;:])(?=\S)", r"\1 ", cleaned)
    cleaned = re.sub(r"(?<!\d)([.!?])(?=[A-Za-zÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç])", r"\1 ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _looks_like_list_line(line: str) -> bool:
    return bool(re.match(r"^\s*(?:\d+[\.)]|[-*•])\s+\S", line or ""))


def _normalize_list_line(line: str, index: int | None = None) -> str:
    body = re.sub(r"^\s*(?:\d+[\.)]|[-*•])\s+", "", line or "").strip()
    body = body.strip("*_ ")
    if not body:
        return ""
    if index is not None:
        return f"{index}. {body}"
    return f"- {body}"


def _split_long_paragraph(text: str, max_len: int = 150) -> list[str]:
    paragraph = re.sub(r"\s+", " ", (text or "").strip())
    if not paragraph:
        return []
    if len(paragraph) <= max_len:
        return [paragraph]

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ])", paragraph)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_len:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [paragraph]


def _repair_robot_phrases(text: str) -> str:
    replacements = {
        r"\b[Pp]rezado cliente,?\s*": "",
        r"\b[Cc]onforme solicitado,?\s*": "",
        r"\b[Ss]egue abaixo,?\s*": "",
        r"\b[Pp]ara prosseguirmos,?\s*": "Pra seguir, ",
    }
    repaired = text
    for pattern, repl in replacements.items():
        repaired = re.sub(pattern, repl, repaired)
    return repaired.strip()


def _limit_customer_questions(text: str, outcome: str | None) -> str:
    allowed = 3 if outcome == "onboarding" else 1
    if text.count("?") <= allowed:
        return text
    chars = list(text)
    question_positions = [i for i, char in enumerate(chars) if char == "?"]
    for pos in question_positions[:-allowed]:
        chars[pos] = "."
    return "".join(chars)


def _inline_requested_fields_block(paragraph: str) -> str | None:
    lower = paragraph.lower()
    stripped = lower.lstrip()
    if "r$" in lower or not stripped.startswith(("me manda", "me envia", "preciso", "confirma", "pra eu")):
        return None
    if not any(trigger in lower for trigger in ("me manda", "me envia", "preciso", "confirma")):
        return None

    candidates = [
        ("Foto do local interno", r"foto (?:do )?(?:local )?intern[ao]|foto interna|foto da parede"),
        ("Foto do local externo", r"foto (?:do )?(?:local )?extern[ao]|foto externa|foto da condensadora"),
        ("Foto do aparelho", r"foto do aparelho|foto do ar"),
        ("Foto do disjuntor", r"foto do disjuntor|foto do quadro"),
        ("Bairro/cidade", r"bairro/cidade|bairro e cidade|cidade/bairro|cidade"),
        ("Marca e BTUs", r"marca e btus|marca.*btus|btus"),
        ("Ponto elétrico exclusivo", r"ponto elétrico|ponto de energia|220v"),
    ]
    items: list[str] = []
    for label, pattern in candidates:
        if re.search(pattern, lower) and label not in items:
            items.append(label)
    if len(items) < 2:
        return None

    intro = "Me manda, por favor:"
    if "avaliar" in lower or "certinho" in lower:
        intro = "Pra eu avaliar certinho, me manda:"
    return intro + "\n\n" + "\n".join(f"{idx}. {item}" for idx, item in enumerate(items, start=1))


def _truncate_whatsapp_blocks(text: str, outcome: str | None, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cta = _default_whatsapp_cta(outcome)
    suffix = f"\n\n{cta}"
    limit = max(1, max_chars - len(suffix))
    blocks = text.split("\n\n")
    kept: list[str] = []
    total = 0
    for block in blocks:
        next_total = total + len(block) + (2 if kept else 0)
        if next_total > limit:
            break
        kept.append(block)
        total = next_total
    base = "\n\n".join(kept).strip()
    if not base:
        base = text[:limit].rsplit(" ", 1)[0].strip()
    if cta.rstrip("?")[:18].lower() not in base.lower() and "?" not in base:
        base = f"{base}{suffix}".strip()
    if len(base) <= max_chars:
        return base.strip()
    candidate = base[:max_chars].rstrip()
    sentence_cut = max(candidate.rfind("."), candidate.rfind("?"), candidate.rfind("!"))
    if sentence_cut >= max(40, int(max_chars * 0.35)):
        return candidate[: sentence_cut + 1].strip()
    return candidate.rsplit(" ", 1)[0].rstrip(" ,;:") + "."


def _format_customer_whatsapp_response(text: str, outcome: str | None, max_chars: int = 850) -> str:
    """Transforma texto bruto do LLM em resposta legível para WhatsApp de cliente."""
    cleaned = _repair_robot_phrases(_strip_customer_emojis(_clean_whatsapp_markdown(text)))
    if not cleaned:
        return ""

    blocks: list[str] = []
    for raw_block in re.split(r"\n\s*\n", cleaned):
        raw_block = raw_block.strip()
        if not raw_block:
            continue

        lines = [line.strip() for line in raw_block.splitlines() if line.strip()]
        if any(_looks_like_list_line(line) for line in lines):
            normalized_lines: list[str] = []
            numbered_index = 1
            use_numbered = sum(1 for line in lines if _looks_like_list_line(line)) >= 2
            for line in lines:
                if _looks_like_list_line(line):
                    normalized_lines.append(
                        _normalize_list_line(line, numbered_index if use_numbered else None)
                    )
                    numbered_index += 1
                else:
                    normalized_lines.append(line.strip("*_ "))
            blocks.append("\n".join(line for line in normalized_lines if line))
            continue

        paragraph = " ".join(lines)
        inline_list = _inline_requested_fields_block(paragraph)
        if inline_list:
            blocks.append(inline_list)
            continue
        blocks.extend(_split_long_paragraph(paragraph, max_len=120))

    visible_blocks = blocks
    if len(visible_blocks) > 4:
        visible_blocks = visible_blocks[:3] + [visible_blocks[-1]]
    formatted = "\n\n".join(visible_blocks).strip()
    formatted = _limit_customer_questions(formatted, outcome)
    formatted = re.sub(r"\n{3,}", "\n\n", formatted).strip()
    formatted = _truncate_whatsapp_blocks(formatted, outcome, max_chars)
    return formatted.strip()


def _shape_whatsapp_response(text: str, outcome: str | None, max_chars: int = 850) -> str:
    """
    Formata resposta para WhatsApp de cliente:
    - sem emoji;
    - com quebras de linha;
    - com listas curtas quando útil;
    - sem markdown pesado;
    - sem parágrafo gigante;
    - com CTA claro.
    """
    formatted = _format_customer_whatsapp_response(text, outcome, max_chars=max_chars)
    if not formatted:
        return _default_whatsapp_cta(outcome)
    return formatted


def _looks_like_incomplete_customer_response(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    last_line = next((line.strip() for line in reversed(stripped.splitlines()) if line.strip()), "")
    if re.match(r"^\d+[\.)]\s+\S", last_line):
        return False
    return stripped[-1] not in ".?!"


def _fallback_after_truncated_format(state: dict[str, Any]) -> str:
    lead_state = state.get("lead_state") or {}
    service = _normalize_service(lead_state.get("tipo_servico") or state.get("service"))
    user_text = _fold_text(_latest_human_text(state.get("messages", [])))
    if service == "manutencao":
        if _contains_any(user_text, ("disjuntor cai", "ponto eletrico", "ponto elétrico", "fio esquenta", "cheiro de queimado")):
            return (
                "Isso é sério. Deixa o ar desligado por segurança.\n\n"
                "Me manda uma foto do disjuntor e do aparelho?"
            )
        return (
            "Entendi. Em manutenção, precisa testar antes de condenar peça.\n\n"
            "Me manda uma foto do aparelho ou do painel de erro e me fala a cidade/bairro?"
        )
    if service == "instalacao":
        return (
            "Entendi. Pra eu avaliar a instalação sem te passar valor errado, preciso ver o local.\n\n"
            "Me manda uma foto do local interno e uma do local externo?"
        )
    return "Entendi. Me passa o serviço, a cidade/bairro e uma foto do aparelho?"


async def _polish_ptbr_if_enabled(response: str, user_text: str) -> str:
    if os.getenv("PTBR_POLISH_ENABLED", "0") != "1":
        return response
    if not os.getenv("LOCAL_PTBR_BASE_URL"):
        return response
    try:
        polished = await _call_local_ptbr([
            {
                "role": "system",
                "content": (
                    "Você reescreve respostas de WhatsApp em português brasileiro natural do Guarujá. "
                    "Preserve todos os preços, nomes de cidade, fatos técnicos e perguntas. "
                    "Não adicione informação nova. "
                    "Não use emoji. "
                    "Não use português europeu. "
                    "Não use espanhol. "
                    "Não use termos fora do nicho de ar-condicionado, como cassete de áudio, split financeiro, carga de bateria, placa do veículo, framework ou cliente HTTP. "
                    "Se houver palavra ambígua, preserve o sentido HVAC-R: ar é ar-condicionado, placa é placa eletrônica, cassete é evaporadora cassete, retorno é acompanhamento de atendimento. "
                    "Use quebras de linha naturais. "
                    "Se forem pedidos 2 ou mais dados, use lista numerada curta. "
                    "Evite texto tudo junto. "
                    "Responda só com a versão final."
                ),
            },
            {
                "role": "user",
                "content": f"Lead: {user_text}\nResposta original: {response}",
            },
        ])
        return polished.strip() or response
    except Exception as e:
        logger.warning(f"Polidor PT-BR local ignorado: {e}")
        return response


async def groq_repair(prompt: str) -> str:
    """Fallback repair (agora redirecionado para o LLM principal)."""
    return await llm_chat(
        [
            {"role": "system", "content": "Você é um tradutor/reescritor para português brasileiro."},
            {"role": "user", "content": prompt},
        ],
        max_retries=1,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Redis Helper
# ──────────────────────────────────────────────────────────────────────────────

async def redis_get(key: str) -> str | None:
    import redis.asyncio
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    client = redis.asyncio.from_url(redis_url, decode_responses=True)
    try:
        return await client.get(key)
    finally:
        await client.aclose()


async def redis_set(key: str, value: str, ex: int | None = None) -> None:
    import redis.asyncio
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    client = redis.asyncio.from_url(redis_url, decode_responses=True)
    try:
        await client.set(key, value, ex=ex)
    finally:
        await client.aclose()


# ──────────────────────────────────────────────────────────────────────────────
# Qdrant Helper
# ──────────────────────────────────────────────────────────────────────────────

_RAG_TIMEOUT_SECONDS = _env_float("RAG_TIMEOUT_SECONDS", 8.0)


def _qdrant_search_with_filters(
    query: str,
    service: str | None,
    top_k: int,
    *,
    segment_market: str | None = None,
    segment_tier: str | None = None,
    goal: str | None = None,
    stage: str | None = None,
) -> list[dict[str, Any]]:
    try:
        return qdrant_search(
            query,
            service,
            top_k,
            segment_market=segment_market,
            segment_tier=segment_tier,
            goal=goal,
            stage=stage,
        )
    except TypeError:
        # Mantém compatibilidade com testes e monkeypatches antigos de qdrant_search.
        return qdrant_search(query, service, top_k)

def qdrant_search(
    query: str,
    service_name: str | None,
    top_k: int = 5,
    *,
    segment_market: str | None = None,
    segment_tier: str | None = None,
    goal: str | None = None,
    stage: str | None = None,
) -> list[dict[str, Any]]:
    from qdrant_client import QdrantClient
    from fastembed import TextEmbedding

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection = os.getenv("QDRANT_COLLECTION", "hermes_hvac_rag_service_staging")
    client = QdrantClient(url=qdrant_url)
    service_name = _normalize_service(service_name)

    try:
        model = TextEmbedding(
            model="nomic-ai/nomic-embed-text-v1.5",
            max_length=512,
        )
        query_embedding = next(model.embed([query]))
    except Exception:
        return []

    from qdrant_client.models import Filter, FieldCondition, MatchAny, MatchValue

    filter_conditions = None
    must_conditions = []
    should_conditions = []
    if service_name:
        should_conditions.append(
            FieldCondition(key="service", match=MatchAny(any=[service_name, "geral", "unknown"]))
        )
        should_conditions.append(FieldCondition(key="service_name", match=MatchValue(value=service_name)))
    if segment_market:
        must_conditions.append(
            FieldCondition(key="segment_market", match=MatchAny(any=[segment_market, "mixed", "unknown"]))
        )
    if segment_tier:
        must_conditions.append(
            FieldCondition(key="segment_tier", match=MatchAny(any=[segment_tier, "unknown"]))
        )
    if goal:
        must_conditions.append(FieldCondition(key="goal", match=MatchAny(any=[goal, "geral"])))
    if stage:
        must_conditions.append(FieldCondition(key="stage", match=MatchAny(any=[stage, "geral"])))
    if must_conditions:
        filter_conditions = Filter(must=must_conditions, should=should_conditions or None)
    elif should_conditions:
        filter_conditions = Filter(should=should_conditions)

    results = client.query_points(
        collection_name=collection,
        query=query_embedding.tolist(),
        limit=top_k,
        query_filter=filter_conditions,
        with_payload=True,
        with_vectors=False,
    )
    min_score = float(os.getenv("RAG_MIN_SCORE", "0.35"))
    ranked = []
    for r in results.points:
        if r.score is not None and r.score < min_score:
            continue
        payload = r.payload or {}
        priority = int(payload.get("priority", 50))
        ranked.append({"id": r.id, "score": r.score, "priority": priority, "payload": payload})

    return sorted(ranked, key=lambda x: (-x["priority"], -(x["score"] or 0)))[:top_k]


async def _search_rag_layers(
    query: str,
    user_text: str,
    service: str | None,
    *,
    segment_market: str | None,
    segment_tier: str | None,
    goal: str | None,
    stage: str | None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Busca RAG em camadas: filtro forte primeiro, relaxamento controlado depois."""
    attempts = [
        {
            "query": query,
            "service": service,
            "segment_market": segment_market,
            "segment_tier": segment_tier,
            "goal": goal,
            "stage": stage,
        },
        {
            "query": query,
            "service": service,
            "segment_market": None,
            "segment_tier": None,
            "goal": goal,
            "stage": None,
        },
        {
            "query": query,
            "service": service,
            "segment_market": None,
            "segment_tier": None,
            "goal": None,
            "stage": None,
        },
        {
            "query": user_text,
            "service": None,
            "segment_market": None,
            "segment_tier": None,
            "goal": None,
            "stage": None,
        },
    ]

    rag_context: list[dict[str, Any]] = []
    seen: set[Any] = set()
    for attempt in attempts:
        results = await asyncio.wait_for(
            asyncio.to_thread(
                _qdrant_search_with_filters,
                attempt["query"],
                attempt["service"],
                top_k,
                segment_market=attempt["segment_market"],
                segment_tier=attempt["segment_tier"],
                goal=attempt["goal"],
                stage=attempt["stage"],
            ),
            timeout=_RAG_TIMEOUT_SECONDS,
        )
        for ctx in results:
            ctx_id = ctx.get("id")
            if ctx_id in seen:
                continue
            rag_context.append(ctx)
            seen.add(ctx_id)
            if len(rag_context) >= top_k:
                return rag_context
        if len(rag_context) >= 3:
            break
    return rag_context[:top_k]


# ──────────────────────────────────────────────────────────────────────────────
# Prisma Helper
# ──────────────────────────────────────────────────────────────────────────────

async def prisma_save_interaction(data: dict[str, Any]) -> None:
    from prisma import Prisma, Json
    prisma = Prisma()
    await prisma.connect()
    try:
        meta = data.get("metadata")
        if meta is not None:
            meta = Json(meta)
            
        await prisma.interaction.create(data={
            "phone": data.get("phone", "unknown"),
            "message": data.get("user_message", ""),
            "intent": data.get("intent"),
            "service": data.get("service"),
            "response": data.get("ai_message", ""),
            "is_human": data.get("is_human", False),
            "metadata": meta,
        })
    finally:
        await prisma.disconnect()


# ──────────────────────────────────────────────────────────────────────────────
# LangGraph Nodes
# ──────────────────────────────────────────────────────────────────────────────

# Mapa de outcomes por serviço — drive comercial
_OUTCOME_MAP: dict[str, str] = {
    "instalacao":      "analise_tecnica",
    "manutencao":      "analise_tecnica",
    "pmoc":            "analise_tecnica",
    "consultoria":     "reuniao_projeto",
    "higienizacao":    "higienizacao_preventiva",
    "projeto-central": "reuniao_projeto",
}

_SERVICE_INTENTS = {
    "instalacao",
    "consultoria",
    "manutencao",
    "pmoc",
    "projeto-central",
    "higienizacao",
}

_EXPLICIT_HANDOFF_TRIGGERS = (
    "atendente humano",
    "falar com pessoa",
    "falar com atendente",
    "pessoa real",
    "humano",
    "atendente",
    "alguem de verdade",
    "quero ligar",
)

_SENSITIVE_COMPLAINT_TRIGGERS = (
    "ninguem responde",
    "ninguem retornou",
    "nao retornou",
    "nao retornaram",
    "nao me retornaram",
    "sem retorno",
    "cancelamento",
    "cancelar",
    "reembolso",
    "refund",
    "devolucao",
    "liguei varias vezes",
    "procon",
    "processo",
    "reclamacao no google",
    "vou denunciar",
    "pessimo atendimento",
)

_LIGHT_COMPLAINT_TRIGGERS = (
    "nao gostei",
    "nao resolveu",
    "continua com problema",
    "continua ruim",
    "ficou ruim",
    "nao ficou bom",
    "ta demorando",
    "esta demorando",
    "atrasou",
    "atrasado",
    "preciso que volte",
)

_SCHEDULING_TERMS = (
    "agenda",
    "agendar",
    "horario",
    "horário",
    "disponibilidade",
    "quando consegue",
    "quando pode",
    "visita",
    "analise tecnica",
    "análise técnica",
    "tecnico vem",
    "técnico vem",
)

_HIGH_VALUE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("vrf", "high_value_vrf"),
    ("vrv", "high_value_vrv"),
    ("duto", "high_value_duto"),
    ("dutado", "high_value_duto"),
    ("rede de dutos", "high_value_duto"),
    ("projeto de duto", "high_value_duto"),
    ("splitao", "high_value_splitao"),
    ("splitão", "high_value_splitao"),
    ("piso teto", "high_value_piso_teto"),
    ("piso-teto", "high_value_piso_teto"),
    ("cassete", "high_value_cassete"),
    ("self contained", "high_value_self"),
    ("fancoil", "high_value_fancoil"),
    ("fan coil", "high_value_fancoil"),
    ("chiller", "high_value_chiller"),
    ("sistema central", "high_value_sistema_central"),
    ("ar central", "high_value_sistema_central"),
    ("climatização central", "high_value_sistema_central"),
    ("climatizacao central", "high_value_sistema_central"),
    ("carga térmica", "high_value_carga_termica"),
    ("carga termica", "high_value_carga_termica"),
    ("obra grande", "high_value_obra"),
    ("obra comercial", "high_value_obra"),
    ("prédio", "high_value_predio"),
    ("predio", "high_value_predio"),
    ("condomínio", "high_value_condominio"),
    ("condominio", "high_value_condominio"),
    ("hotel", "high_value_hotel"),
    ("restaurante", "high_value_restaurante"),
    ("mercado", "high_value_mercado"),
    ("supermercado", "high_value_supermercado"),
    ("clínica", "high_value_clinica"),
    ("clinica", "high_value_clinica"),
    ("laboratório", "high_value_laboratorio"),
    ("laboratorio", "high_value_laboratorio"),
    ("hospital", "high_value_hospital"),
    ("escritório", "high_value_empresa"),
    ("escritorio", "high_value_empresa"),
    ("empresa", "high_value_empresa"),
    ("loja", "high_value_loja"),
    ("galpão", "high_value_galpao"),
    ("galpao", "high_value_galpao"),
    ("pmoc", "high_value_pmoc"),
    ("laudo", "high_value_laudo"),
    ("art", "high_value_art"),
    ("contrato mensal", "high_value_contrato"),
    ("contrato de manutenção", "high_value_contrato"),
    ("contrato de manutencao", "high_value_contrato"),
    ("consultoria", "high_value_consultoria"),
    ("projeto", "high_value_projeto"),
    ("central de climatizacao", "high_value_projeto_central"),
    ("galpao industrial", "high_value_galpao"),
    ("orcamento grande", "high_value_orcamento_grande"),
    ("contrato", "high_value_contrato"),
)

_HANDOFF_STATE_TTL = _env_int("HANDOFF_STATE_TTL_SECONDS", 7200)


def _fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_accents.split())


def _contains_any(text: str, triggers: tuple[str, ...] | list[str]) -> bool:
    for trigger in triggers:
        if _keyword_in_text(trigger, text):
            return True
    return False


def _keyword_in_text(keyword: str, text: str) -> bool:
    folded_keyword = _fold_text(keyword)
    if len(folded_keyword) <= 3 and " " not in folded_keyword:
        if re.search(rf"\b{re.escape(folded_keyword)}\b", text):
            return True
        return False
    return folded_keyword in text


def _detect_high_value_reason(text: str, intent: str | None) -> str | None:
    for keyword, reason in _HIGH_VALUE_KEYWORDS:
        folded_keyword = _fold_text(keyword)
        if len(folded_keyword) <= 3:
            if re.search(rf"\b{re.escape(folded_keyword)}\b", text):
                return reason
            continue
        if folded_keyword in text:
            return reason

    multiple_devices = re.search(
        r"\b([3-9]|[1-9][0-9]+)\s*(aparelhos?|splits?|máquinas?|maquinas?|equipamentos?|evaporadoras?)\b",
        text,
    )
    if multiple_devices:
        return "high_value_multiplos_aparelhos"

    if re.search(r"\b([4-9][8-9]000|[5-9][0-9]000|[1-9][0-9]{5,})\s*(btus?|btu/h)?\b", text):
        return "high_value_btus_altos"
    if re.search(r"\b([5-9]|[1-9][0-9]+)\s*(tr|toneladas?\s+de\s+refrigeracao)\b", text):
        return "high_value_btus_altos"

    if any(term in text for term in ("varios aparelhos", "varias maquinas", "muitos aparelhos")):
        return "high_value_multiplos_aparelhos"

    if intent in ("pmoc", "consultoria", "projeto-central"):
        return f"high_value_{intent.replace('-', '_')}"

    return None


def _fallback_service_for_high_value(text: str) -> str | None:
    if _contains_any(text, ("vrf", "vrv", "duto", "dutado", "restaurante", "galpao", "sistema central", "multi split", "multisplit", "splitao", "splitão", "cassete", "piso teto", "piso-teto")):
        return "projeto-central"
    if _contains_any(text, ("pmoc", "laudo", "art", "preventiva")):
        return "pmoc"
    if _contains_any(text, ("consultoria", "projeto", "dimensionamento", "empresa", "condominio")):
        return "consultoria"
    return None


def classify_high_value_project(text: str, lead_state: dict) -> dict | None:
    folded = _fold_text(text)
    reason = _detect_high_value_reason(folded, lead_state.get("tipo_servico") or lead_state.get("service"))
    if not reason:
        return None
    if reason in {"high_value_vrf", "high_value_vrv"}:
        project_type = "vrf"
    elif reason == "high_value_duto":
        project_type = "duto"
    elif reason in {"high_value_splitao", "high_value_piso_teto", "high_value_cassete", "high_value_btus_altos"}:
        project_type = "comercial_leve"
    elif reason in {"high_value_pmoc", "high_value_laudo", "high_value_art", "high_value_contrato"}:
        project_type = "pmoc"
    else:
        project_type = "contrato_ou_multiaparelho"
    return {
        "is_high_value": True,
        "reason": reason,
        "project_type": project_type,
        "recommended_service": "pmoc" if project_type == "pmoc" else "projeto-central",
        "owner_priority": "high",
        "questions": [
            "cidade/bairro",
            "tipo de ambiente",
            "quantidade de ambientes",
            "planta ou fotos",
            "prazo desejado",
        ],
    }


def _high_value_consultative_response() -> str:
    return (
        "Esse caso é mais técnico e vale avaliar com cuidado para evitar erro de dimensionamento e retrabalho. "
        "Me passa a cidade, o tipo de ambiente e a quantidade de máquinas ou ambientes pra eu direcionar certinho?"
    )


def _looks_like_pmoc_preventive_plan(text: str) -> bool:
    has_preventive_term = any(
        term in text
        for term in (
            "manutencao preventiva",
            "preventiva",
            "preventivo",
            "preventivo trimestral",
            "manutencao trimestral",
            "programa preventivo",
        )
    )
    if not has_preventive_term:
        return False

    has_multiple_devices = bool(
        re.search(
            r"\b([2-9]|[1-9][0-9])\s*(aparelhos?|equipamentos?|equipos?|splits?|maquinas?|evaporadoras?)\b",
            text,
        )
    )
    has_business_context = any(
        term in text
        for term in (
            "empresa",
            "loja",
            "clinica",
            "condominio",
            "restaurante",
            "contrato",
            "laudo",
            "art",
            "certificado",
            "alvara",
            "trimestral",
        )
    )
    return has_multiple_devices or has_business_context


def _handoff_state_key(phone: str) -> str:
    safe_phone = re.sub(r"[^0-9A-Za-z_:+@.-]", "_", phone.strip())[:160] or "unknown"
    return f"handoff_state:{safe_phone}"


def _handoff_initial_response(reason: str | None) -> str:
    if reason == "sensitive_complaint":
        return (
            "Poxa, sinto muito por isso. Já vou sinalizar o Will pra olhar pessoalmente por aqui. "
            "Enquanto ele entra, me passa o número do orçamento ou serviço e o melhor horário pra retorno?"
        )
    return (
        "Entendido. Já vou sinalizar o Will pra assumir por aqui. "
        "Enquanto ele entra, me passa qual serviço você precisa e em qual cidade?"
    )


def _handoff_followup_response(reason: str | None) -> str:
    if reason == "sensitive_complaint":
        return (
            "Já deixei isso sinalizado aqui. Enquanto isso, me passa o número do orçamento ou serviço "
            "e o melhor horário pra retorno que eu adianto pra ele."
        )
    return (
        "Já deixei isso sinalizado aqui. Enquanto isso, me passa qual serviço você precisa, "
        "a cidade e um resumo do caso pra eu adiantar."
    )


def _unknown_recovery_response(user_text: str) -> str:
    text = _fold_text(user_text)
    if "ar" in text and any(term in text for term in ("estranho", "problema", "ruim", "esquisito", "nao ta legal", "nao esta legal", "deu ruim")):
        return (
            "Entendi. Quando você fala que o ar tá estranho, ele não gela, pinga, faz barulho ou tem cheiro? "
            "Se puder, me manda uma foto ou vídeo curto também."
        )
    if any(term in text for term in ("faz", "voces fazem", "tem como", "consegue")) and len(text.split()) <= 5:
        return "Consigo te ajudar sim. Você quer instalação, manutenção ou higienização?"
    if _looks_like_price_question(user_text):
        return (
            "Entendi. Pra eu te passar um valor certo, preciso saber qual serviço você quer: "
            "instalação, manutenção ou higienização?"
        )
    return "Entendi. Pra eu te orientar certinho: isso é instalação, manutenção ou higienização?"


def _light_complaint_response(user_text: str) -> str:
    return (
        "Entendi, sinto muito pelo transtorno. Me passa o que aconteceu e, se tiver, o número do orçamento "
        "ou uma foto/vídeo do problema pra eu conseguir adiantar a análise por aqui."
    )


async def classify_service(state: dict[str, Any]) -> dict[str, Any]:
    """Classifica serviço e política de handoff sem transformar dúvida em humano."""
    messages = state.get("messages", [])
    lead_state = deepcopy(state.get("lead_state") or {})
    if not messages:
        return {
            "intent": None,
            "service": None,
            "outcome": None,
            "handoff_mode": "none",
            "handoff_reason": None,
            "handoff_already_notified": False,
        }

    last_message = messages[-1]
    user_text = _message_text(last_message)
    text_lower = _fold_text(user_text)
    security = {}
    try:
        from agent_graph.guards.security_guard import detect_malicious_or_instruction_injection

        security = detect_malicious_or_instruction_injection(user_text)
    except Exception as e:
        logger.warning("Falha no security_guard: %s", e)
    if security.get("is_malicious") and security.get("risk_level") in {"medium", "high"}:
        lead_state["security_rejected"] = True
        return {
            "intent": "security_rejected",
            "service": lead_state.get("tipo_servico"),
            "outcome": "duvida",
            "messages": messages,
            "handoff_mode": "soft_alert" if security.get("risk_level") == "high" else "none",
            "handoff_reason": "malicious_or_injection_attempt" if security.get("risk_level") == "high" else None,
            "handoff_already_notified": False,
            "lead_state": lead_state,
            "security_guard": security,
            "safe_response": security.get("safe_response"),
            "conversation_objective": "security_reject",
        }
    recent_human = [
        _message_text(message)
        for message in messages[-6:]
        if _is_human_message(message) and _message_text(message)
    ]
    semantic_text = _fold_text(" | ".join(recent_human[-3:])) if len(recent_human) > 1 else text_lower

    if _contains_any(text_lower, _EXPLICIT_HANDOFF_TRIGGERS):
        lead_state["human_takeover"] = True
        lead_state["relationship_type"] = "human_takeover"
        return {
            "intent": "explicit_handoff",
            "service": None,
            "outcome": "escalar_humano",
            "messages": messages,
            "handoff_mode": "hard_transfer",
            "handoff_reason": "explicit_handoff",
            "handoff_already_notified": False,
            "lead_state": lead_state,
        }

    if _contains_any(text_lower, _SENSITIVE_COMPLAINT_TRIGGERS):
        lead_state["relationship_type"] = "complaint_or_risk"
        return {
            "intent": "sensitive_complaint",
            "service": None,
            "outcome": "escalar_humano",
            "messages": messages,
            "handoff_mode": "hard_transfer",
            "handoff_reason": "sensitive_complaint",
            "handoff_already_notified": False,
            "lead_state": lead_state,
        }

    conversation_in_progress = is_conversation_in_progress(state, lead_state)

    # Saudações e mensagens curtas sem serviço → onboarding (não escalar humano)
    GREETING_WORDS = [
        "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite",
        "e aí", "eai", "e ai", "tudo bem", "tudo bom", "como vai",
        "alguém", "alguem", "tem alguém", "quero informação", "quero informacao",
        "opa",
    ]
    if _contains_any(text_lower, GREETING_WORDS) and len(text_lower.split()) <= 8:
        if conversation_in_progress:
            service = lead_state.get("tipo_servico") or state.get("service")
            intent = service or "duvida"
            outcome = _OUTCOME_MAP.get(service, "duvida")
            lead_state, relationship_type = _apply_relationship_and_appointment(
                {**state, "service": service, "intent": intent},
                lead_state,
            )
            response = _continuation_response(lead_state, state.get("missing_fields") or [], state.get("do_not_ask") or [])
            return {
                "intent": intent,
                "service": service,
                "outcome": outcome,
                "messages": messages,
                "handoff_mode": "none",
                "handoff_reason": None,
                "handoff_already_notified": False,
                "lead_state": lead_state,
                "continuation_response": response,
                "conversation_objective": "recover_context",
            }
        return {
            "intent": "onboarding",
            "service": None,
            "outcome": "onboarding",
            "messages": messages,
            "handoff_mode": "none",
            "handoff_reason": None,
            "handoff_already_notified": False,
            "lead_state": lead_state,
        }

    # Scoring por keywords
    SCORE_MAP: dict[tuple[str, int], str] = {
        ("quanto custa instalar", 8): "instalacao",
        ("quanto fica pra instalar", 8): "instalacao",
        ("quanto sai instalar", 8): "instalacao",
        ("custa instalar", 7): "instalacao",
        ("preço pra instalar", 7): "instalacao",
        ("preço de instalação", 7): "instalacao",
        ("vocês instalam", 6): "instalacao",
        ("colocar ar", 5): "instalacao",
        ("por ar", 5): "instalacao",
        ("splits novos", 5): "instalacao",
        ("split novo", 5): "instalacao",
        ("pra por", 4): "instalacao",
        ("instalação de", 3): "instalacao",
        ("instalar", 1): "instalacao",
        ("instalação", 1): "instalacao",
        ("split", 2): "instalacao",
        ("equipamento que eu já comprei", 5): "instalacao",
        ("não esquenta", 5): "manutencao",
        ("não aquece", 5): "manutencao",
        ("não gela", 6): "manutencao",
        ("nao gela", 6): "manutencao",
        ("não está gelando", 6): "manutencao",
        ("não tá gelando", 6): "manutencao",
        ("nao ta gelando", 6): "manutencao",
        ("parou de gelar", 6): "manutencao",
        ("barulho de vibração", 5): "manutencao",
        ("barulho", 3): "manutencao",
        ("vazamento", 4): "manutencao",
        ("pingando", 5): "manutencao",
        ("pingar", 5): "manutencao",
        ("pingou", 5): "manutencao",
        ("comecou a pingar", 6): "manutencao",
        ("pinga agua", 5): "manutencao",
        ("vazando agua", 5): "manutencao",
        ("placa eletrônica", 6): "manutencao",
        ("placa eletronica", 6): "manutencao",
        ("problema na placa", 6): "manutencao",
        ("placa queimou", 6): "manutencao",
        ("queda de energia", 5): "manutencao",
        ("não liga", 4): "manutencao",
        ("queimou", 3): "manutencao",
        ("deu ruim no ar", 3): "manutencao",
        ("corretiva", 3): "manutencao",
        ("gela demais", 3): "manutencao",
        ("manutenção", 1): "manutencao",
        ("consertar", 1): "manutencao",
        ("defeito", 1): "manutencao",
        ("pmoc", 8): "pmoc",
        ("laudo pmoc", 9): "pmoc",
        ("art", 5): "pmoc",
        ("certificado dos aparelhos", 5): "pmoc",
        ("certificado", 3): "pmoc",
        ("contrato de manutencao", 4): "pmoc",
        ("programa preventivo", 5): "pmoc",
        ("preventivo trimestral", 5): "pmoc",
        ("manutencao trimestral", 4): "pmoc",
        ("manutenção preventiva", 2): "pmoc",
        ("alvará do bombeiros", 4): "pmoc",
        ("higienização", 5): "higienizacao",
        ("higienizacao", 5): "higienizacao",
        ("ozônio", 4): "higienizacao",
        ("ácaros", 4): "higienizacao",
        ("fungos", 3): "higienizacao",
        ("sanitização", 3): "higienizacao",
        ("faz limpeza", 6): "higienizacao",
        ("limpeza de split", 6): "higienizacao",
        ("limpeza do ar", 4): "higienizacao",
        ("limpeza", 4): "higienizacao",
        ("limpar", 2): "higienizacao",
        ("mofo", 3): "higienizacao",
        ("cheiro", 1): "higienizacao",
        ("projeto de climatização", 4): "consultoria",
        ("projeto de ar", 4): "consultoria",
        ("split ou cassete", 6): "consultoria",
        ("ajuda pra escolher", 5): "consultoria",
        ("escolher o equipamento", 5): "consultoria",
        ("dimensionar ar", 5): "consultoria",
        ("dimensionar", 4): "consultoria",
        ("consultoria", 3): "consultoria",
        ("assessoria", 3): "consultoria",
        ("btu", 3): "consultoria",
        ("dimensionamento", 3): "consultoria",
        ("obra nova", 4): "consultoria",
        ("eficiência energética", 4): "consultoria",
        ("eficiencia energetica", 4): "consultoria",
        ("o que é melhor", 3): "consultoria",
        ("qual capacidade", 3): "consultoria",
        ("melhor para", 2): "consultoria",
        ("vrf", 9): "projeto-central",
        ("vrv", 9): "projeto-central",
        ("duto", 7): "projeto-central",
        ("dutado", 7): "projeto-central",
        ("splitão", 7): "projeto-central",
        ("splitao", 7): "projeto-central",
        ("projeto central", 5): "projeto-central",
        ("central de climatização", 6): "projeto-central",
        ("multi split", 4): "projeto-central",
        ("multisplit", 4): "projeto-central",
        ("cassete", 2): "projeto-central",
        ("galpão", 3): "projeto-central",
        ("restaurante", 3): "projeto-central",
        ("para climatização", 2): "projeto-central",
        ("sistema central", 5): "projeto-central",
        ("controle individual", 4): "projeto-central",
        ("carga térmica", 4): "projeto-central",
        ("carga termica", 4): "projeto-central",
        ("6 ambientes", 4): "projeto-central",
        ("vários ambientes", 4): "projeto-central",
    }

    scores: dict[str, int] = {}
    for (keyword, weight), svc in SCORE_MAP.items():
        if _keyword_in_text(keyword, semantic_text):
            scores[svc] = scores.get(svc, 0) + weight

    intent = max(scores, key=lambda k: scores[k]) if scores else None
    sorted_scores = sorted(scores.values(), reverse=True) if scores else []
    top_score = sorted_scores[0] if sorted_scores else 0
    runner_up = sorted_scores[1] if len(sorted_scores) > 1 else 0

    # LLM override: consulta o classificador local para zero-score ou ambiguidade.
    try:
        prompt = (
            f"Classifique a mensagem do cliente entre: "
            f"instalacao, consultoria, manutencao, pmoc, projeto-central, higienizacao, unknown, explicit_handoff, sensitive_complaint\n"
            f"'instalacao' = instalar aparelho novo\n"
            f"'manutencao' = consertar/reparar aparelho existente\n"
            f"'pmoc' = plano preventivo obrigatório/laudo técnico\n"
            f"'consultoria' = dúvida técnica, assessoria, qual equipamento escolher, projeto de obra\n"
            f"'projeto-central' = sistema central, multisplit, vários ambientes, carga térmica\n"
            f"'higienizacao' = limpeza, higienização, cheiro, ácaros\n"
            f"'explicit_handoff' = cliente pede claramente humano/atendente/pessoa real\n"
            f"'sensitive_complaint' = cancelamento, reembolso, ameaça pública/legal ou reclamação forte de falta de retorno\n"
            f"'unknown' = mensagem vaga, gíria, áudio ruim, fora de domínio ou intenção incerta. Nunca use handoff para dúvida incerta.\n"
            f"Use português brasileiro real: considere histórico, elipse e contexto. Em HVAC, 'ar' geralmente significa ar-condicionado.\n"
            f"Histórico recente do lead: \"{' | '.join(recent_human[-3:])}\"\n"
            f"Mensagem: \"{user_text}\"\n"
            f"Responda apenas o nome da categoria, sem explicação."
        )
        resp = await _call_local_qwen([{"role": "user", "content": prompt}])
        intent_llm = resp.strip().lower().replace(" ", "-")
        if intent_llm == "hygienizacao":
            intent_llm = "higienizacao"
        if intent_llm in ("human", "handoff"):
            intent_llm = "explicit_handoff"
        if intent_llm in ("duvida", "dúvida", "fora-de-dominio", "fora-do-dominio"):
            intent_llm = "unknown"
        VALID = _SERVICE_INTENTS | {"unknown", "explicit_handoff", "sensitive_complaint"}
        if intent_llm in VALID:
            if not scores:
                # Sem keyword match — confia no LLM
                intent = intent_llm
            else:
                strong_keyword = top_score >= 3 and (runner_up == 0 or top_score > runner_up * 2)
                if not strong_keyword:
                    intent = intent_llm
    except Exception as e:
        logger.warning(f"LLM classify falhou, mantendo keyword: {e}")

    if _looks_like_pmoc_preventive_plan(semantic_text):
        intent = "pmoc"

    high_value_service = _fallback_service_for_high_value(semantic_text)
    if high_value_service and intent in {None, "unknown", "instalacao"}:
        intent = high_value_service

    # Se intent ainda None (sem keywords e LLM falhou) → recuperação conversacional, não handoff.
    if intent is None:
        intent = high_value_service or "unknown"

    current_service = _normalize_service(lead_state.get("tipo_servico"))
    correction = detect_service_correction(user_text, current_service)
    if correction and correction != current_service:
        lead_state["service_changed_by_user"] = True
        lead_state["previous_tipo_servico"] = current_service
        lead_state["tipo_servico"] = correction
        intent = correction
    elif current_service and intent in _SERVICE_INTENTS and intent != current_service and not (
        current_service == "instalacao" and high_value_service in {"pmoc", "projeto-central", "consultoria"}
    ):
        intent = current_service
    elif current_service and intent in {None, "unknown"}:
        intent = current_service

    intent = _normalize_service(intent)
    if intent in ("explicit_handoff", "sensitive_complaint"):
        lead_state["human_takeover"] = intent == "explicit_handoff"
        lead_state["relationship_type"] = "human_takeover" if intent == "explicit_handoff" else "complaint_or_risk"
        return {
            "intent": intent,
            "service": None,
            "outcome": "escalar_humano",
            "messages": messages,
            "handoff_mode": "hard_transfer",
            "handoff_reason": intent,
            "handoff_already_notified": False,
            "lead_state": lead_state,
        }

    service = intent if intent in _SERVICE_INTENTS else None
    outcome = _OUTCOME_MAP.get(intent, "duvida")
    handoff_mode = "none"
    handoff_reason = None

    high_value_reason = _detect_high_value_reason(semantic_text, intent)
    if high_value_reason:
        project = classify_high_value_project(semantic_text, lead_state) or {}
        if project:
            lead_state["high_value_project"] = project
            if not service:
                service = project.get("recommended_service")
                intent = service or intent
            outcome = "reuniao_projeto"
        handoff_mode = "soft_alert"
        handoff_reason = high_value_reason
    elif _contains_any(text_lower, _LIGHT_COMPLAINT_TRIGGERS):
        handoff_mode = "soft_alert"
        handoff_reason = "light_complaint"
        if intent == "unknown":
            outcome = "duvida"

    if intent == "unknown":
        lead_state["unknown_context_count"] = int(lead_state.get("unknown_context_count") or 0) + 1
    else:
        lead_state["unknown_context_count"] = 0

    lead_state, relationship_type = _apply_relationship_and_appointment(
        {**state, "service": service, "intent": intent, "handoff_mode": handoff_mode, "handoff_reason": handoff_reason},
        lead_state,
    )
    if relationship_type == "no_context":
        handoff_mode = "soft_alert"
        handoff_reason = "no_context_needs_human_review"
    elif lead_state.get("appointment_ready") and handoff_mode == "none":
        handoff_mode = "soft_alert"
        handoff_reason = "appointment_ready"
        outcome = "analise_tecnica" if outcome == "duvida" else outcome

    conversation_objective = compute_conversation_objective(
        {
            **state,
            "service": service,
            "intent": intent,
            "handoff_mode": handoff_mode,
            "handoff_reason": handoff_reason,
            "missing_fields": state.get("missing_fields") or [],
        },
        lead_state,
    )

    return {
        "intent": intent,
        "service": service,
        "outcome": outcome,
        "messages": messages,
        "handoff_mode": handoff_mode,
        "handoff_reason": handoff_reason,
        "handoff_already_notified": False,
        "lead_state": lead_state,
        "conversation_objective": conversation_objective,
    }


async def retrieve_knowledge(state: dict[str, Any]) -> dict[str, Any]:
    """Busca contexto técnico e comercial no Qdrant com FastEmbed."""
    messages = state.get("messages", [])
    service = _normalize_service(state.get("service"))
    lead_state = state.get("lead_state") or {}
    lead_mind = lead_state.get("lead_mind") if isinstance(lead_state, dict) else {}
    segment = (lead_mind or {}).get("segment") or {}
    conversation_goal = state.get("conversation_objective") or lead_state.get("conversation_goal")
    stage = lead_state.get("pipeline_stage") or lead_state.get("relationship_type")

    if not messages:
        return {"rag_context": [], "messages": messages}

    last_message = messages[-1]
    user_text = _message_text(last_message)
    recent_human = [
        _message_text(m) for m in messages[-6:]
        if _is_human_message(m) and _message_text(m)
    ]
    try:
        from agent_graph.services.domain_disambiguation import build_rag_query, select_response_template

        query, domain_disambiguation = build_rag_query(user_text, lead_state, recent_human)
        selected_template = select_response_template(state, user_text)
    except Exception as e:
        logger.warning("domain_disambiguation falhou; usando query simples: %s", e)
        query = f"servico={service or 'geral'} lead={' | '.join(recent_human[-3:])}"
        domain_disambiguation = {"original_query": user_text, "rewritten_query": query, "matched_terms": [], "applied_rules": []}
        selected_template = None

    try:
        rag_context = await _search_rag_layers(
            query,
            user_text,
            service,
            segment_market=segment.get("market"),
            segment_tier=segment.get("tier"),
            goal=conversation_goal,
            stage=stage,
            top_k=5,
        )
    except asyncio.TimeoutError:
        logger.warning("Qdrant search excedeu timeout de %.1fs", _RAG_TIMEOUT_SECONDS)
        rag_context = []
    except Exception as e:
        logger.warning(f"Qdrant search falhou: {e}")
        rag_context = []

    return {
        "rag_context": rag_context,
        "service": service,
        "messages": messages,
        "domain_disambiguation": domain_disambiguation,
        "selected_template": selected_template,
    }


async def generate_response(state: dict[str, Any]) -> dict[str, Any]:
    """Gera resposta na voz do Will usando RAG + MiniMax (Groq fallback)."""
    messages = state.get("messages", [])
    rag_context = state.get("rag_context", [])
    service = _normalize_service(state.get("service"))
    intent = _normalize_service(state.get("intent"))
    outcome = state.get("outcome", "duvida")
    handoff_mode = state.get("handoff_mode", "none")
    handoff_reason = state.get("handoff_reason")
    lead_state = deepcopy(state.get("lead_state") or {})

    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    user_text = _message_text(last_message)
    customer_data = state.get("customer_data") or {}
    active_service = customer_data.get("active_service")
    last_service = customer_data.get("last_service")
    if state.get("intent") == "security_rejected" or state.get("safe_response"):
        ai_message = AIMessage(content=state.get("safe_response") or "Não consigo seguir com esse pedido por aqui. Posso te ajudar com instalação, manutenção, higienização ou conserto?")
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service or lead_state.get("tipo_servico"),
            "outcome": "duvida",
            "handoff_mode": state.get("handoff_mode", "none"),
            "handoff_reason": state.get("handoff_reason"),
            "lead_state": lead_state,
            "conversation_objective": "security_reject",
        }
    if isinstance(active_service, dict) and active_service.get("status"):
        ai_message = AIMessage(content=_active_service_response(user_text, active_service))
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service or _normalize_service(active_service.get("service")),
            "outcome": "acompanhamento_servico",
            "handoff_mode": "soft_alert",
            "handoff_reason": "active_service_followup",
            "lead_state": {**lead_state, "relationship_type": "active_customer", "is_existing_customer": True},
        }

    relationship_type = compute_relationship_type({**state, "lead_state": lead_state})
    if relationship_type == "past_customer" and isinstance(last_service, dict):
        ai_message = AIMessage(content=_past_customer_response(last_service))
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service or _normalize_service(last_service.get("service")),
            "outcome": "pos_venda_ou_novo_atendimento",
            "handoff_mode": handoff_mode,
            "handoff_reason": handoff_reason,
            "lead_state": {**lead_state, "relationship_type": "past_customer", "is_existing_customer": True},
        }

    if relationship_type == "no_context" and int(lead_state.get("unknown_context_count") or 0) >= 2:
        ai_message = AIMessage(content=_no_context_response())
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service,
            "outcome": "duvida",
            "handoff_mode": "soft_alert",
            "handoff_reason": "no_context_needs_human_review",
            "lead_state": lead_state,
        }

    if state.get("continuation_response") or (
        is_conversation_in_progress(state, lead_state)
        and _is_short_continuation_text(user_text)
        and (lead_state.get("tipo_servico") or service)
    ):
        response = state.get("continuation_response") or _continuation_response(
            lead_state,
            state.get("missing_fields") or [],
            state.get("do_not_ask") or [],
        )
        if response:
            ai_message = AIMessage(content=response)
            return {
                "messages": messages + [ai_message],
                "rag_context": rag_context,
                "service": service or lead_state.get("tipo_servico"),
                "outcome": outcome,
                "handoff_mode": handoff_mode,
                "handoff_reason": handoff_reason,
                "lead_state": lead_state,
                "already_asked_fields": state.get("already_asked_fields") or [],
                "missing_fields": state.get("missing_fields") or [],
                "do_not_ask": state.get("do_not_ask") or [],
                "conversation_objective": state.get("conversation_objective") or "recover_context",
            }

    if str(handoff_reason or "").startswith("high_value"):
        ai_message = AIMessage(content=_high_value_consultative_response())
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service or (lead_state.get("high_value_project") or {}).get("recommended_service"),
            "outcome": "reuniao_projeto",
            "handoff_mode": "soft_alert",
            "handoff_reason": handoff_reason,
            "lead_state": lead_state,
        }

    if lead_state.get("appointment_ready"):
        ai_message = AIMessage(content=_appointment_ready_response(lead_state))
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service or lead_state.get("tipo_servico"),
            "outcome": "analise_tecnica",
            "handoff_mode": "soft_alert",
            "handoff_reason": "appointment_ready",
            "lead_state": {**lead_state, "appointment_ready": True},
        }

    if handoff_reason == "light_complaint":
        ai_message = AIMessage(content=_light_complaint_response(user_text))
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service,
            "outcome": outcome,
        }

    if intent == "unknown":
        ai_message = AIMessage(content=_unknown_recovery_response(user_text))
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service,
            "outcome": outcome,
        }

    human_count = sum(1 for m in messages if _is_human_message(m))
    do_not_ask = state.get("do_not_ask") or []
    missing_fields = state.get("missing_fields") or []
    already_asked_fields = state.get("already_asked_fields") or []
    cache_key = _sales_cache_key(service, user_text, lead_state, missing_fields, do_not_ask)
    can_use_sales_cache = (
        human_count <= 1
        and not do_not_ask
        and not active_service
        and not last_service
        and lead_state.get("relationship_type") in (None, "new_lead")
    )
    if can_use_sales_cache:
        try:
            cached = await redis_get(cache_key)
            if cached:
                from agent_graph.guards.response_guard import validate_response_before_send

                ok, _violations = validate_response_before_send(cached, state)
                if ok:
                    logger.info(f"Resposta validada via Redis cache: {cache_key}")
                    ai_message = AIMessage(content=cached)
                    return {
                        "messages": messages + [ai_message],
                        "rag_context": rag_context,
                        "service": service,
                        "outcome": outcome,
                    }
        except Exception as e:
            logger.warning(f"Redis sales cache falhou: {e}")

    direct_response = _direct_price_response(
        service,
        user_text,
        lead_state,
        state.get("missing_fields") or [],
        state.get("do_not_ask") or [],
    )
    if direct_response:
        direct_response = await _polish_ptbr_if_enabled(direct_response, user_text)
        ai_message = AIMessage(content=direct_response)
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service,
            "outcome": outcome,
        }

    context_parts = []
    for ctx in rag_context:
        payload = ctx.get("payload", {})
        text = payload.get("text")
        if not text:
            continue
        doc_type = payload.get("doc_type", "technical")
        title = payload.get("title", "contexto")
        context_parts.append(f"[{doc_type} | {title}]\n{text}")
    context_str = "\n---\n".join(context_parts) or ""
    domain_disambiguation = state.get("domain_disambiguation") or {}
    selected_template = state.get("selected_template")
    try:
        from agent_graph.services.domain_disambiguation import template_context_for_prompt

        template_context = template_context_for_prompt(selected_template if isinstance(selected_template, dict) else None)
    except Exception:
        template_context = "Nenhum template específico. Use as regras de estado e o contexto recuperado."
    if _contains_any(_normalize_text(user_text), _SCHEDULING_TERMS):
        try:
            from agent_graph.services.calendar import get_availability_summary

            availability = await get_availability_summary()
        except Exception:
            availability = ""
        if availability:
            context_str = "\n---\n".join(
                part for part in (context_str, f"[agenda | disponibilidade]\n{availability}") if part
            )

    # CTA por outcome — guia o Will a conduzir o lead pro próximo passo certo
    outcome_cta = {
        "onboarding":              "Se o cliente ainda não disse o que deseja, cumprimente-o educadamente e pergunte qual serviço precisa. Se ele já disse, NUNCA pergunte 'como posso ajudar' ou 'qual serviço precisa'; continue o fluxo específico daquele serviço.",
        "analise_tecnica":         "Finalize oferecendo análise técnica no local por R$50, abatida se aprovar o orçamento, e peça cidade/bairro, modelo e foto do equipamento.",
        "higienizacao_preventiva": "Se for split, cite R$200 por aparelho e peça quantidade/cidade. Se não for split, conduza para análise técnica de R$50 abatível.",
        "reuniao_projeto":         "Finalize pedindo planta, metragem e quantidade de ambientes, e proponha análise/reunião técnica de R$50 abatível quando houver visita ao local.",
        "duvida":                  "Responda a dúvida tecnicamente, mas de forma simples, e pergunte se precisa de mais alguma ajuda.",
        "escalar_humano":          "Informe com empatia que um especialista da equipe (ou você mesmo em breve) vai assumir o atendimento.",
    }.get(outcome, "Avance a conversa fazendo uma pergunta técnica simples para qualificar o problema do cliente.")

    if handoff_mode == "soft_alert":
        outcome_cta = (
            "Caso de alto valor ou risco comercial: responda normalmente, sem dizer que vai passar para humano. "
            "Peça dados de qualificação como cidade/bairro, quantidade de aparelhos, tipo de estabelecimento e urgência."
        )

    # ── Monta multi-turn com histórico de conversa ────────────────────────────
    # system + histórico alternado (user/assistant) + última mensagem com contexto RAG
    llm_messages: list[ChatMessage] = [
        {"role": "system", "content": WILL_SYSTEM_PROMPT},
    ]

    # Adiciona histórico (todas as mensagens exceto a última — que vira user_prompt abaixo)
    for msg in messages[:-1]:
        if _is_human_message(msg):
            llm_messages.append({"role": "user", "content": _message_text(msg)})
        elif _is_ai_message(msg):
            llm_messages.append({"role": "assistant", "content": _message_text(msg)})

    conversation_objective = state.get("conversation_objective") or compute_conversation_objective(state, lead_state)

    # Última mensagem do lead enriquecida com contexto RAG e CTA
    user_prompt = (
        f"==========================================================\n"
        f"[INÍCIO DO CONTEXTO RECUPERADO DA REFRIMIX - USE APENAS ISSO COMO BASE TÉCNICA E COMERCIAL]\n"
        f"{context_str or 'Nenhum contexto recuperado. Você NÃO DEVE inventar preços ou informações técnicas. Peça mais detalhes ao cliente.'}\n"
        f"[FIM DO CONTEXTO RECUPERADO]\n"
        f"==========================================================\n\n"
        f"ESTADO DO ONBOARDING DO LEAD:\n"
        f"- Estado estruturado atual: {json.dumps(lead_state, ensure_ascii=False)}\n"
        f"- Informações já fornecidas (PROIBIDO PERGUNTAR): {do_not_ask}\n"
        f"- Próximas informações em falta que você deve obter: {missing_fields}\n\n"
        f"DESAMBIGUAÇÃO DE DOMÍNIO HVAC-R:\n"
        f"- Query original: {domain_disambiguation.get('original_query') or user_text}\n"
        f"- Query desambiguada para RAG: {domain_disambiguation.get('rewritten_query') or user_text}\n"
        f"- Termos ambíguos detectados: {domain_disambiguation.get('matched_terms') or []}\n"
        f"- Regras aplicadas: {domain_disambiguation.get('applied_rules') or []}\n\n"
        f"TEMPLATE FLEXÍVEL RECOMENDADO:\n"
        f"{template_context}\n\n"
        f"Objetivo único desta resposta: {conversation_objective}.\n"
        f"Não tente cumprir outro objetivo.\n"
        f"Política comercial: venda consultiva, sem pressão, sem promoção agressiva, sem 'últimas vagas', sem 'vamos fechar?' cedo demais. Explique o risco de passar valor errado, peça o dado mínimo e mostre o próximo passo.\n"
        f"Serviço identificado: {service or 'não classificado'}\n"
        f"Modo de handoff: {handoff_mode}; motivo: {handoff_reason or 'nenhum'}.\n"
        f"Meta para esta mensagem específica: {outcome_cta}\n\n"
        f"MENSAGEM ATUAL DO CLIENTE:\n"
        f"\"{user_text}\"\n\n"
        f"CONTRATO DE GERAÇÃO DA RESPOSTA (OBRIGATÓRIO):\n"
        f"1. Responda de forma profissional e direta, em no máximo 4 frases.\n"
        f"2. ATENÇÃO MÁXIMA: Se o cliente perguntar preço/prazo/detalhe que NÃO está explícito no bloco de contexto acima, VOCÊ NÃO PODE INVENTAR. Responda elegantemente que precisa calcular ou avaliar os detalhes.\n"
        f"3. Faça no máximo UMA pergunta ao final para obter o PRÓXIMO campo da lista de informações em falta ({missing_fields}).\n"
        f"4. NUNCA faça perguntas ou peça dados sobre informações que já foram fornecidas ({do_not_ask}).\n"
        f"5. Não ofereça handoff humano, especialista ou atendimento manual quando o modo de handoff for 'none' ou 'soft_alert'.\n"
        f"6. Nunca diga visita gratuita. Fora os dois preços fixos, conduza para análise técnica de R$50 abatível no orçamento aprovado.\n"
        f"7. Formate como WhatsApp humano: sem emoji; com parágrafos curtos; com linha em branco entre blocos; se pedir 2 ou mais dados, use lista numerada; não entregue texto tudo junto; não use cabeçalhos markdown; não use bullets decorativos; não use 'Prezado cliente'; não use português europeu; não use espanhol.\n"
        f"8. Estrutura ideal: primeiro bloco confirma o que entendeu; segundo bloco explica o necessário em 1 ou 2 frases; terceiro bloco pede o próximo dado ou lista os dados necessários; última linha conduz para orçamento/agendamento.\n"
        f"9. Não use emoji em mensagens para cliente final.\n"
        f"10. Não use termos fora do nicho de ar-condicionado. Exemplos proibidos: cassete de áudio, split financeiro, carga de bateria, placa do veículo, framework, cliente HTTP, como modelo de linguagem."
    )
    llm_messages.append({"role": "user", "content": user_prompt})

    fast_route = (outcome == "onboarding") or (intent == "onboarding")
    try:
        response = await llm_chat(llm_messages, max_retries=2, fast_route=fast_route)
    except Exception as e:
        logger.warning(f"LLM falhou em generate_response: {e}")
        response = {
            "analise_tecnica": (
                "Pode deixar que a gente resolve! "
                "A análise técnica no local custa R$50 e abate se você aprovar o orçamento. Me manda a cidade e o modelo do aparelho?"
            ),
            "higienizacao_preventiva": (
                "Ótimo! A higienização é fundamental pra qualidade do ar. "
                "Me fala quantos aparelhos são e o endereço que eu já calculo o orçamento."
            ),
            "reuniao_projeto": (
                "Pra esse tipo de projeto, melhor a gente sentar e conversar com a planta em mãos. "
                "Me manda planta, metragem e quantidade de ambientes para eu ver agenda e adiantar a análise?"
            ),
        }.get(outcome or "", "Me manda mais detalhes que eu te ajudo!")

    # ── Guardrail Conversacional Anti-Burrice (Anti-Repetição) ───────────────
    forbidden_mapping = {
        "tipo_servico": ["instala", "higieni", "manuten", "consert", "limp", "eletri"],
        "cidade_bairro": ["cidade", "bairro", "onde você", "seu endereço", "onde fica"],
        "btus": ["btu", "potencia", "capacidade"],
        "marca": ["marca", "fabricante"],
        "modelo_aparelho": ["modelo", "aparelho", "equipamento"],
        "aparelho_ja_comprado": ["já comprou", "já tem o ar", "adquiriu"],
        "foto_aparelho": ["foto do aparelho", "foto da evaporadora", "imagem do ar"],
        "foto_local_interno": ["foto de dentro", "foto do local interno", "imagem interna"],
        "foto_local_externo": ["foto de fora", "foto do local externo", "imagem externa"],
        "foto_disjuntor": ["foto do disjuntor", "foto do quadro"],
        "ponto_eletrico_exclusivo": ["ponto elétrico", "ponto de energia", "220v"],
        "distancia_aproximada": ["distancia", "metros", "tubulação"],
        "tubulacao_existente": ["infraestrutura", "tubulação pronta", "infra pronta"],
        "tempo_sem_manutencao": ["tempo sem", "última manutenção", "quanto tempo"],
        "cheiro_ruim": ["cheiro", "odor"],
        "pinga_agua": ["pingando", "vazando água", "pinga"],
        "rinite_alergia": ["rinite", "alergia"],
    }

    detected_violations = []
    response_lower = response.lower()
    for field in do_not_ask:
        keywords = forbidden_mapping.get(field, [])
        if "?" in response_lower:
            for kw in keywords:
                if kw in response_lower:
                    detected_violations.append(field)
                    break
                    
    if detected_violations:
        logger.warning(
            "Guardrail conversacional detectou perguntas repetitivas proibidas: %s. Resposta original: %r",
            detected_violations,
            response
        )
        correct_prompt = (
            "Você é o Will da Refrimix. Corrija a resposta abaixo removendo qualquer pergunta ou pedido "
            "sobre informações que o cliente já nos forneceu e que estão marcadas como proibidas.\n\n"
            f"Campos já fornecidos e PROIBIDOS de perguntar: {', '.join(detected_violations)}\n\n"
            f"Resposta original: \"{response}\"\n\n"
            "Escreva a nova versão da resposta de forma natural, educada e direta, sem fazer nenhuma pergunta sobre os campos proibidos. Retorne APENAS o texto da nova resposta:"
        )
        try:
            corrected = await llm_chat([
                {"role": "system", "content": WILL_SYSTEM_PROMPT},
                {"role": "user", "content": correct_prompt}
            ])
            corrected = corrected.strip()
            if corrected:
                logger.info("Resposta corrigida pelo Guardrail: %r", corrected)
                response = corrected
        except Exception as e:
            logger.warning("Falha ao rodar LLM corretivo no Guardrail: %s", e)

    response = await _polish_ptbr_if_enabled(response, user_text)
    ai_message = AIMessage(content=response)
    return {
        "messages": messages + [ai_message],
        "rag_context": rag_context,
        "service": service,
        "outcome": outcome,
        "lead_state": lead_state,
        "already_asked_fields": already_asked_fields,
        "missing_fields": missing_fields,
        "do_not_ask": do_not_ask,
    }


async def language_guard_check(state: dict[str, Any]) -> dict[str, Any]:
    """Valida e corrige resposta do LLM — garante pt-BR sem drift CJK/árabe."""
    messages = state.get("messages", [])
    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    ai_response = _message_text(last_message)
    rag_context = state.get("rag_context", [])
    service = state.get("service", "não classificado")
    outcome = state.get("outcome", "duvida")

    context_str = "\n".join(
        ctx["payload"].get("text", "")
        for ctx in rag_context
        if ctx.get("payload", {}).get("text")
    ) or "Sem contexto."

    user_text = next(
        (_message_text(m) for m in messages if _is_human_message(m)),
        "",
    )

    original_prompt = (
        f"Serviço: {service}\n"
        f"Contexto: {context_str}\n"
        f"Mensagem do lead: {user_text}\n"
        f"Responda em português brasileiro coloquial como o Will da Refrimix."
    )

    from agent_graph.guards.language_guard import LanguageGuard

    guard = LanguageGuard(expected_lang="pt-BR", majority_threshold=0.50, max_retries=2)

    async def retry_llm(prompt: str) -> str:
        return await llm_chat([
            {"role": "system", "content": WILL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])

    try:
        fixed_response = await guard.validate_and_fix(
            ai_response,
            retry_llm,
            original_prompt,
            groq_repair_callable=groq_repair,
        )
    except Exception as e:
        logger.warning("LanguageGuard repair falhou; usando resposta original sanitizada: %s", e)
        from agent_graph.guards.language_guard import sanitize_hard

        fixed_response = sanitize_hard(ai_response) or (
            "Tive uma instabilidade técnica aqui. Me manda o endereço e os detalhes do aparelho "
            "que eu já te ajudo pelo WhatsApp."
        )

    return {"messages": messages[:-1] + [AIMessage(content=fixed_response)]}


async def response_guard_check(state: dict[str, Any]) -> dict[str, Any]:
    messages = state.get("messages", [])
    if not messages:
        return {"messages": messages}

    response = _message_text(messages[-1])
    lead_state = deepcopy(state.get("lead_state") or {})
    missing_fields = state.get("missing_fields") or []
    do_not_ask = state.get("do_not_ask") or []
    asked_field = infer_asked_field_from_response(response, missing_fields)

    if asked_field:
        counts = lead_state.setdefault("ask_count_by_field", {})
        counts[asked_field] = int(counts.get(asked_field) or 0) + 1
        lead_state["last_asked_field"] = asked_field
        if counts[asked_field] >= 2 and asked_field in missing_fields:
            state = {
                **state,
                "handoff_mode": "soft_alert" if state.get("handoff_mode") in (None, "none") else state.get("handoff_mode"),
                "handoff_reason": state.get("handoff_reason") or "repeated_missing_critical_field",
            }

    try:
        from agent_graph.guards.response_guard import validate_response_before_send

        ok, violations = validate_response_before_send(response, {**state, "lead_state": lead_state})
    except Exception as e:
        logger.warning("response_guard falhou: %s", e)
        ok, violations = True, []

    fixed = response
    if not ok:
        service = lead_state.get("tipo_servico") or state.get("service")
        relationship = lead_state.get("relationship_type")
        if state.get("conversation_objective") == "security_reject":
            fixed = state.get("safe_response") or response
        elif relationship == "active_customer":
            fixed = "Vi aqui que você já tem atendimento em andamento com a Refrimix.\n\nMe fala o que precisa atualizar nesse serviço?"
        elif lead_state.get("appointment_ready") or relationship == "ready_to_schedule":
            fixed = "Perfeito, já tenho o principal para seguir com o atendimento.\n\nMe confirma o melhor período: manhã ou tarde?"
        elif service == "manutencao":
            user_text = _fold_text(_latest_human_text(state.get("messages", [])))
            if _contains_any(user_text, ("disjuntor cai", "ponto eletrico", "ponto elétrico", "fio esquenta", "cheiro de queimado")):
                fixed = (
                    "Isso é sério. O ideal é deixar o ar desligado agora por segurança.\n\n"
                    "Pode envolver sobrecarga, cabo inadequado, disjuntor fora do padrão ou falha no equipamento.\n\n"
                    "Me manda uma foto do disjuntor e do aparelho?"
                )
            else:
                fixed = (
                    "Entendi. Em manutenção, precisa testar antes de condenar peça ou passar valor fechado.\n\n"
                    "Me manda uma foto do aparelho ou do painel de erro e me fala a cidade/bairro?"
                )
        elif service == "instalacao":
            next_field = _important_missing_field(missing_fields, do_not_ask, lead_state)
            next_question = _repeated_field_strategy(next_field, lead_state) or _question_for_field(next_field)
            fixed = (
                "Continuando sua instalação, pra eu te orientar certinho só falta confirmar o próximo detalhe.\n\n"
                f"{next_question}"
            )
        else:
            next_field = _important_missing_field(missing_fields, do_not_ask, lead_state)
            fixed = _repeated_field_strategy(next_field, lead_state) or (
                f"Continuando o atendimento, {_question_for_field(next_field).lower()}"
            )

    return {
        "messages": messages[:-1] + [AIMessage(content=fixed)],
        "lead_state": lead_state,
        "response_guard_violations": violations,
        "handoff_mode": state.get("handoff_mode"),
        "handoff_reason": state.get("handoff_reason"),
    }


async def format_whatsapp(state: dict[str, Any]) -> dict[str, Any]:
    """
    Formata resposta final para WhatsApp preservando quebras, listas curtas e CTA.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    raw = _message_text(last_message)

    formatted = _clean_whatsapp_markdown(raw)
    formatted = _shape_whatsapp_response(formatted, state.get("outcome"))
    formatted = _strip_customer_emojis(formatted)
    formatted = re.sub(r"\n{3,}", "\n\n", formatted).strip()
    formatted = formatted.strip()
    if _looks_like_incomplete_customer_response(formatted):
        logger.warning("format_whatsapp detectou resposta possivelmente truncada; aplicando fallback")
        formatted = _fallback_after_truncated_format(state)

    if len(formatted) > 1500:
        formatted = _truncate_whatsapp_blocks(
            formatted,
            state.get("outcome"),
            1450,
        )
        formatted = f"{formatted}\n\nQual a sua dúvida principal?".strip()

    tts_text = None
    try:
        from agent_graph.services.speech_adapter import build_tts_text

        lead_state = state.get("lead_state") or {}
        lead_mind = lead_state.get("lead_mind") if isinstance(lead_state, dict) else None
        goal = state.get("conversation_objective") or lead_state.get("conversation_goal")
        tts_text = build_tts_text(formatted, lead_mind if isinstance(lead_mind, dict) else None, goal)
    except Exception as e:
        logger.warning("speech_adapter falhou: %s", e)

    return {"messages": messages[:-1] + [AIMessage(content=formatted)], "tts_text": tts_text}


async def save_interaction(state: dict[str, Any]) -> dict[str, Any]:
    """Persiste interação no PostgreSQL via Prisma."""
    messages = state.get("messages", [])
    intent = state.get("intent")
    service = state.get("service")
    outcome = state.get("outcome")
    customer_data = state.get("customer_data", {})
    phone = customer_data.get("phone", "unknown")
    diagnostic_no_send = bool(customer_data.get("diagnostic_mode")) and not bool(customer_data.get("send_requested"))

    user_message = next((_message_text(m) for m in reversed(messages) if _is_human_message(m)), None)
    ai_message = next((_message_text(m) for m in reversed(messages) if _is_ai_message(m)), None)
    lead_state = state.get("lead_state") or {}
    memory = customer_data.get("memory") or {}

    if not diagnostic_no_send:
        try:
            await prisma_save_interaction({
                "phone": phone,
                "user_message": user_message or "",
                "intent": intent,
                "service": service,
                "ai_message": ai_message or "",
                "is_human": state.get("is_human", False),
                "metadata": {
                    "outcome": outcome,
                    "handoff_mode": state.get("handoff_mode"),
                    "handoff_reason": state.get("handoff_reason"),
                    "active_service": customer_data.get("active_service"),
                    "last_service": customer_data.get("last_service"),
                    "relationship_type": lead_state.get("relationship_type"),
                    "conversation_goal": state.get("conversation_objective") or lead_state.get("conversation_goal"),
                    "lead_state": {
                        "tipo_servico": lead_state.get("tipo_servico"),
                        "cidade_bairro": lead_state.get("cidade_bairro"),
                        "btus": lead_state.get("btus"),
                        "last_asked_field": lead_state.get("last_asked_field"),
                        "ask_count_by_field": lead_state.get("ask_count_by_field"),
                    },
                    "response_guard_violations": state.get("response_guard_violations") or [],
                    "history_source": memory.get("history_source"),
                    "is_conversation_started": memory.get("is_conversation_started"),
                },
            })
        except Exception as e:
            logger.error(f"Falha ao salvar interação: {e}")

    # ── Cria LeadEvent transacional para resposta da IA (Assistant) ───────────
    if phone and phone != "unknown" and ai_message and not diagnostic_no_send:
        from prisma import Prisma
        db = Prisma()
        await db.connect()
        try:
            lead = await db.lead.find_unique(where={"phone": phone})
            if lead:
                summary = update_conversation_summary(phone, messages, lead_state)
                do_not_ask, already_asked_fields, missing_fields = compute_fields_status(lead_state)
                await db.lead.update(
                    where={"phone": phone},
                    data={
                        "lead_state": json.dumps(lead_state),
                        "conversation_summary": summary,
                        "already_asked_fields": json.dumps(already_asked_fields),
                        "missing_fields": json.dumps(missing_fields),
                        "do_not_ask": json.dumps(do_not_ask),
                        "service_type": lead_state.get("tipo_servico"),
                        "city_bairro": lead_state.get("cidade_bairro"),
                    },
                )
                await db.leadevent.create(
                    data={
                        "lead_id": lead.id,
                        "role": "assistant",
                        "message": ai_message,
                        "extracted_data": json.dumps({}),
                    }
                )
        except Exception as e:
            logger.warning("Falha ao salvar LeadEvent para assistant: %s", e)
        finally:
            await db.disconnect()

    return {"messages": messages}


async def route_human(state: dict[str, Any]) -> dict[str, Any]:
    """Hard handoff: responde uma vez e evita loop de passagem humana."""
    messages = state.get("messages", [])
    customer_data = state.get("customer_data", {})
    phone = customer_data.get("phone", "")
    reason = state.get("handoff_reason") or state.get("intent") or "explicit_handoff"
    already_notified = False

    if phone:
        key = _handoff_state_key(phone)
        try:
            existing = await redis_get(key)
            already_notified = bool(existing)
            if not already_notified:
                value = json.dumps({"reason": reason}, ensure_ascii=False)
                await redis_set(key, value, ex=_HANDOFF_STATE_TTL)
        except Exception as e:
            logger.warning("Redis handoff_state falhou para %s: %s", phone, e)

    content = _handoff_followup_response(reason) if already_notified else _handoff_initial_response(reason)
    handoff = AIMessage(content=content)
    return {
        "messages": messages + [handoff],
        "is_human": True,
        "handoff_mode": "hard_transfer",
        "handoff_reason": reason,
        "handoff_already_notified": already_notified,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa 3 — preprocess_input (STT + Vision)
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_LEAD_STATE = {
  "tipo_servico": None,
  "nome": None,
  "cidade_bairro": None,
  "tipo_imovel": None,
  "marca": None,
  "btus": None,
  "modelo_aparelho": None,
  "aparelho_ja_comprado": None,
  "fotos": {
    "aparelho": False,
    "local_interno": False,
    "local_externo": False,
    "disjuntor": False,
    "erro_display": False
  },
  "instalacao": {
    "local_evaporadora": None,
    "local_condensadora": None,
    "distancia_aproximada": None,
    "ponto_eletrico_exclusivo": None,
    "tubulacao_existente": None,
    "precisa_suporte": None,
    "precisa_dreno": None
  },
  "manutencao": {
    "tempo_sem_manutencao": None,
    "cheiro_ruim": None,
    "pinga_agua": None,
    "rinite_alergia": None
  },
  "conserto": {
    "liga": None,
    "gela": None,
    "codigo_erro": None,
    "condensadora_liga": None,
    "disjuntor_cai": None
  },
  "eletrica": {
    "disjuntor_cai": None,
    "fio_esquenta": None,
    "cheiro_queimado": None,
    "circuito_individual": None
  },
  "relationship_type": "new_lead",
  "conversation_goal": None,
  "customer_status": None,
  "is_existing_customer": False,
  "active_service_id": None,
  "last_completed_service": None,
  "appointment_score": 0,
  "appointment_ready": False,
  "unknown_context_count": 0,
  "human_takeover": False,
  "last_asked_field": None,
  "ask_count_by_field": {}
}


def compute_appointment_score(state: dict[str, Any]) -> int:
    """Pontua prontidão de agendamento com sinais objetivos já informados."""
    lead_state = state.get("lead_state") or {}
    messages = state.get("messages", [])
    full_text = _fold_text(" ".join(_message_text(m) for m in messages if _is_human_message(m)))
    score = 0

    if lead_state.get("tipo_servico") or state.get("service"):
        score += 2
    if lead_state.get("cidade_bairro"):
        score += 2
    if _contains_any(full_text, _SCHEDULING_TERMS):
        score += 2
    if lead_state.get("nome"):
        score += 1
    if _has_photo_context(lead_state) or state.get("message_type") == "imageMessage":
        score += 1
    if _contains_any(full_text, _WINDOW_PATTERNS):
        score += 1

    return score


def compute_relationship_type(state: dict[str, Any]) -> str:
    """Classifica a relação operacional sem tratar cliente ativo como lead novo."""
    customer_data = state.get("customer_data") or {}
    lead_state = state.get("lead_state") or {}
    messages = state.get("messages", [])
    user_text = _fold_text(_latest_human_text(messages))
    active_service = customer_data.get("active_service")
    last_service = customer_data.get("last_service")

    if isinstance(active_service, dict) and active_service.get("status"):
        return "active_customer"
    if state.get("handoff_mode") == "hard_transfer" or lead_state.get("human_takeover") or _contains_any(user_text, _EXPLICIT_HANDOFF_TRIGGERS):
        return "human_takeover"
    if state.get("handoff_reason") in {"sensitive_complaint", "light_complaint", "complaint_or_risk"} or _contains_any(user_text, _SENSITIVE_COMPLAINT_TRIGGERS + _LIGHT_COMPLAINT_TRIGGERS):
        return "complaint_or_risk"
    if isinstance(last_service, dict) and last_service and not active_service:
        return "past_customer"
    if int(lead_state.get("unknown_context_count") or 0) >= 2:
        return "no_context"

    service = lead_state.get("tipo_servico") or state.get("service")
    city = lead_state.get("cidade_bairro")
    wants_schedule = _contains_any(user_text, _SCHEDULING_TERMS)
    if service and city and wants_schedule:
        return "ready_to_schedule"
    if service:
        return "qualifying_lead"
    return "new_lead"


def _apply_relationship_and_appointment(state: dict[str, Any], lead_state: dict[str, Any]) -> tuple[dict[str, Any], str]:
    enriched_state = {**state, "lead_state": lead_state}
    customer_data = enriched_state.get("customer_data") or {}
    active_service = customer_data.get("active_service")
    last_service = customer_data.get("last_service")

    if isinstance(active_service, dict) and active_service.get("id"):
        lead_state["active_service_id"] = active_service.get("id")
        lead_state["customer_status"] = active_service.get("status")
        lead_state["is_existing_customer"] = True
    if isinstance(last_service, dict) and last_service:
        lead_state["last_completed_service"] = last_service
        lead_state["is_existing_customer"] = True

    relationship_type = compute_relationship_type(enriched_state)
    lead_state["relationship_type"] = relationship_type

    score = compute_appointment_score(enriched_state)
    lead_state["appointment_score"] = score
    if score >= 5:
        lead_state["appointment_ready"] = True

    return lead_state, relationship_type


def is_conversation_in_progress(state: dict[str, Any], lead_state: dict[str, Any]) -> bool:
    customer_memory = (state.get("customer_data") or {}).get("memory") or {}
    return any([
        lead_state.get("tipo_servico"),
        lead_state.get("cidade_bairro"),
        lead_state.get("btus"),
        lead_state.get("relationship_type") not in (None, "new_lead"),
        bool(state.get("conversation_summary")),
        bool(customer_memory.get("has_persistent_lead")),
        int(customer_memory.get("postgres_event_count") or 0) > 0,
    ])


def detect_service_correction(user_text: str, current_service: str | None) -> str | None:
    if not current_service:
        return None
    text = _fold_text(user_text)
    correction_terms = (
        "na verdade",
        "corrigindo",
        "nao e instalacao",
        "não é instalação",
        "nao é instalação",
        "quis dizer",
        "troquei",
    )
    explicit = _contains_any(text, correction_terms)
    if "é limpeza" in text or "e limpeza" in text:
        explicit = True
    if "é manutenção" in text or "e manutencao" in text or "é manutencao" in text:
        explicit = True
    if not explicit:
        return None

    if _contains_any(text, ("higienizacao", "higienização", "limpeza", "limpar")):
        return "higienizacao"
    if _contains_any(text, ("manutencao", "manutenção", "conserto", "consertar", "defeito")):
        return "manutencao"
    if _contains_any(text, ("instalacao", "instalação", "instalar", "colocar ar")):
        return "instalacao"
    return None


def _is_short_continuation_text(text: str) -> bool:
    folded = _fold_text(text)
    if len(folded.split()) > 8:
        return False
    terms = (
        "oi", "ola", "olá", "opa", "bom dia", "boa tarde", "boa noite",
        "ok", "sim", "beleza", "pode ser", "isso", "certo", "ta", "tá",
    )
    return _contains_any(folded, terms)


def _continuation_response(
    lead_state: dict[str, Any],
    missing_fields: list[str],
    do_not_ask: list[str],
) -> str | None:
    service = lead_state.get("tipo_servico")
    relationship = lead_state.get("relationship_type")
    if lead_state.get("appointment_ready") or relationship == "ready_to_schedule":
        return "Perfeito, já tenho o principal para agenda.\n\nMe confirma o melhor período: manhã ou tarde?"
    next_field = _important_missing_field(missing_fields, do_not_ask, lead_state)
    repeated_strategy = _repeated_field_strategy(next_field, lead_state)
    if repeated_strategy:
        return repeated_strategy
    if service == "instalacao":
        if next_field in {"foto_local_interno", "foto_local_externo"}:
            return (
                "Continuando sua instalação, pra eu te orientar certinho só falta ver o local.\n\n"
                "Me manda uma foto do local interno e uma do local externo?"
            )
        return f"Continuando sua instalação, pra eu te orientar certinho só falta o próximo detalhe.\n\n{_question_for_field(next_field)}"
    if service == "higienizacao":
        return "Continuando a higienização, só preciso confirmar quantos aparelhos são e o bairro/cidade."
    if service == "manutencao":
        return "Continuando a análise do aparelho, me confirma se ele liga normalmente ou aparece algum código de erro?"
    if service:
        return f"Continuando o atendimento de {service}, {_question_for_field(next_field).lower()}"
    return None


def compute_conversation_objective(state: dict[str, Any], lead_state: dict[str, Any]) -> str:
    customer_data = state.get("customer_data") or {}
    user_text = _fold_text(_latest_human_text(state.get("messages", [])))
    if state.get("security_guard", {}).get("is_malicious") or state.get("intent") == "security_rejected":
        return "security_reject"
    if customer_data.get("active_service"):
        return "active_service_followup"
    if state.get("handoff_mode") == "hard_transfer" or lead_state.get("relationship_type") in {"human_takeover", "complaint_or_risk"}:
        return "human_handoff"
    if lead_state.get("appointment_ready") or lead_state.get("relationship_type") == "ready_to_schedule":
        return "schedule_service"
    if state.get("service") or lead_state.get("tipo_servico"):
        missing = state.get("missing_fields") or []
        return "qualify_quote" if missing else "schedule_service"
    if _contains_any(user_text, ("como", "por que", "porque", "qual", "quanto", "duvida", "dúvida")):
        return "answer_question"
    if is_conversation_in_progress(state, lead_state):
        return "recover_context"
    return "recover_context"


def update_conversation_summary(phone: str, messages: list[Any], lead_state: dict[str, Any]) -> str:
    service = lead_state.get("tipo_servico") or "serviço não definido"
    city = lead_state.get("cidade_bairro") or "cidade/bairro não informado"
    stage = lead_state.get("relationship_type") or "new_lead"
    do_not_ask, _asked, missing = compute_fields_status(lead_state)
    last_question = lead_state.get("last_asked_field")
    human_text = " ".join(_message_text(m) for m in messages[-6:] if _is_human_message(m))
    objections = []
    folded = _fold_text(human_text)
    if "caro" in folded:
        objections.append("achou caro")
    if "vou ver" in folded or "te aviso" in folded:
        objections.append("vai decidir depois")
    ready = "pronto para agenda" if lead_state.get("appointment_ready") else "ainda em qualificação"
    return (
        f"Lead {phone} quer {service} em {city}. Etapa: {stage}. "
        f"Dados coletados: {', '.join(do_not_ask) if do_not_ask else 'nenhum campo estruturado confirmado'}. "
        f"Faltam: {', '.join(missing) if missing else 'sem campos críticos pendentes'}. "
        f"Última pergunta: {last_question or 'não registrada'}. "
        f"Objeções: {', '.join(objections) if objections else 'nenhuma registrada'}. "
        f"Status: {ready}."
    )

def compute_fields_status(lead_state: dict) -> tuple[list[str], list[str], list[str]]:
    """
    Computa do_not_ask, already_asked_fields e missing_fields com base no lead_state.
    Retorna (do_not_ask, already_asked_fields, missing_fields).
    """
    tipo_servico = lead_state.get("tipo_servico")
    
    # 1. Determina quais campos já foram preenchidos (flat list)
    filled_fields = []
    
    # Campos gerais
    for field in ["tipo_servico", "nome", "cidade_bairro", "tipo_imovel", "marca", "btus", "modelo_aparelho", "aparelho_ja_comprado"]:
        if lead_state.get(field) is not None:
            filled_fields.append(field)
            
    # Fotos
    fotos = lead_state.get("fotos", {})
    for f in ["aparelho", "local_interno", "local_externo", "disjuntor", "erro_display"]:
        if fotos.get(f):
            filled_fields.append(f"foto_{f}")
            
    # Instalação
    inst = lead_state.get("instalacao", {})
    for field in ["local_evaporadora", "local_condensadora", "distancia_aproximada", "ponto_eletrico_exclusivo", "tubulacao_existente", "precisa_suporte", "precisa_dreno"]:
        if inst.get(field) is not None:
            filled_fields.append(field)
            
    # Manutenção/Higienização
    manut = lead_state.get("manutencao", {})
    for field in ["tempo_sem_manutencao", "cheiro_ruim", "pinga_agua", "rinite_alergia"]:
        if field in manut and manut[field] is not None:
            filled_fields.append(field)
            
    # Conserto
    cons = lead_state.get("conserto", {})
    for field in ["liga", "gela", "codigo_erro", "condensadora_liga", "disjuntor_cai"]:
        if field in cons and cons[field] is not None:
            filled_fields.append(field)
            
    # Elétrica
    elet = lead_state.get("eletrica", {})
    for field in ["disjuntor_cai", "fio_esquenta", "cheiro_queimado", "circuito_individual"]:
        if field in elet and elet[field] is not None:
            filled_fields.append(field)
            
    # do_not_ask e already_asked_fields são basicamente os campos preenchidos
    do_not_ask = list(set(filled_fields))
    already_asked_fields = list(set(filled_fields))
    
    # 2. Computa missing_fields de acordo com o tipo_servico
    missing_fields = []
    
    if not tipo_servico:
        # Se não tem tipo_servico, os campos básicos em falta são tipo_servico e cidade_bairro
        if "tipo_servico" not in do_not_ask:
            missing_fields.append("tipo_servico")
        if "cidade_bairro" not in do_not_ask:
            missing_fields.append("cidade_bairro")
    elif tipo_servico == "instalacao":
        reqs = ["cidade_bairro", "btus", "foto_local_interno", "foto_local_externo", "ponto_eletrico_exclusivo", "distancia_aproximada", "tubulacao_existente"]
        for r in reqs:
            if r not in do_not_ask:
                missing_fields.append(r)
    elif tipo_servico in ["manutencao", "higienizacao"]:
        reqs = ["cidade_bairro", "tempo_sem_manutencao", "cheiro_ruim", "pinga_agua", "rinite_alergia", "foto_aparelho"]
        for r in reqs:
            if r not in do_not_ask:
                missing_fields.append(r)
    elif tipo_servico == "conserto":
        reqs = ["cidade_bairro", "liga", "gela", "codigo_erro", "foto_aparelho"]
        for r in reqs:
            if r not in do_not_ask:
                missing_fields.append(r)
    elif tipo_servico == "eletrica":
        reqs = ["cidade_bairro", "disjuntor_cai", "fio_esquenta", "cheiro_queimado", "foto_disjuntor"]
        for r in reqs:
            if r not in do_not_ask:
                missing_fields.append(r)
                
    return do_not_ask, already_asked_fields, missing_fields

async def preprocess_input(state: dict[str, Any]) -> dict[str, Any]:
    """
    Pré-processa input multimodal antes de classify_service:
    - audioMessage → transcreve com Groq Whisper → substitui texto
    - imageMessage → analisa com Vision LLM → prepend descrição ao texto
    - conversation → passa direto
    - Inicializa/carrega o lead_state estruturado e campos associados a partir do Postgres 17.
    """
    message_type = state.get("message_type", "conversation")
    media_url = state.get("media_url", "")
    media_base64 = state.get("media_base64", "")
    msg_id = state.get("msg_id", "")
    instance = state.get("instance", "")
    messages = state.get("messages", [])

    # ── 1. Inicializa o estado com os dados do banco ────────────────────────
    customer_data = state.get("customer_data", {})
    phone = customer_data.get("phone", "unknown")
    diagnostic_no_send = bool(customer_data.get("diagnostic_mode")) and not bool(customer_data.get("send_requested"))
    
    lead_state = None
    already_asked_fields = []
    missing_fields = []
    do_not_ask = []
    conversation_summary = ""
    
    if diagnostic_no_send:
        lead_state = _lead_state_copy()
        missing_fields = ["tipo_servico", "cidade_bairro"]
    elif phone and phone != "unknown":
        from prisma import Prisma
        import json
        db = Prisma()
        await db.connect()
        try:
            lead = await db.lead.find_unique(where={"phone": phone})
            if not lead:
                # Cria novo lead no Postgres com estado inicial padrão
                lead = await db.lead.create(
                    data={
                        "phone": phone,
                        "name": customer_data.get("name"),
                        "lead_state": json.dumps(_lead_state_copy()),
                        "already_asked_fields": json.dumps([]),
                        "missing_fields": json.dumps(["tipo_servico", "cidade_bairro"]),
                        "do_not_ask": json.dumps([]),
                    }
                )
            
            # Carrega campos do Postgres 17
            lead_state = json.loads(lead.lead_state) if isinstance(lead.lead_state, str) else (lead.lead_state or _lead_state_copy())
            if not lead_state:
                lead_state = _lead_state_copy()
                
            already_asked_fields = json.loads(lead.already_asked_fields) if isinstance(lead.already_asked_fields, str) else (lead.already_asked_fields or [])
            missing_fields = json.loads(lead.missing_fields) if isinstance(lead.missing_fields, str) else (lead.missing_fields or ["tipo_servico", "cidade_bairro"])
            do_not_ask = json.loads(lead.do_not_ask) if isinstance(lead.do_not_ask, str) else (lead.do_not_ask or [])
            conversation_summary = lead.conversation_summary or ""
        except Exception as e:
            logger.warning("Falha ao carregar Lead do Postgres em preprocess_input: %s", e)
            lead_state = _lead_state_copy()
            missing_fields = ["tipo_servico", "cidade_bairro"]
        finally:
            await db.disconnect()
    else:
        lead_state = _lead_state_copy()
        missing_fields = ["tipo_servico", "cidade_bairro"]

    # ── 2. Processa mídia multimodal ────────────────────────────────────────
    if message_type == "audioMessage" and (media_url or media_base64 or msg_id):
        try:
            from agent_graph.services.stt import transcribe_audio
            transcript = await transcribe_audio(media_url, instance or None, msg_id, media_base64)
            logger.info(f"STT transcript: {transcript[:80]!r}")
            # Substitui última HumanMessage pelo texto transcrito
            new_messages = list(messages)
            if new_messages and _is_human_message(new_messages[-1]):
                new_messages[-1] = HumanMessage(content=transcript)
            else:
                new_messages.append(HumanMessage(content=transcript))
            return {
                "messages": new_messages,
                "message_type": message_type,
                "lead_state": lead_state,
                "already_asked_fields": already_asked_fields,
                "missing_fields": missing_fields,
                "do_not_ask": do_not_ask,
                "conversation_summary": conversation_summary,
            }
        except Exception as e:
            logger.error(f"STT falhou: {e}")

    elif message_type == "imageMessage" and (media_url or media_base64 or msg_id):
        try:
            from agent_graph.services.vision import analyze_image
            caption = ""
            if messages and _is_human_message(messages[-1]):
                caption = _message_text(messages[-1]) or ""
            description = await analyze_image(media_url, caption, instance or None, msg_id, media_base64)
            logger.info(f"Vision description: {description[:80]!r}")
            combined = f"[Imagem: {description}]"
            if caption:
                combined = f"[Imagem: {description}]\n{caption}"
            new_messages = list(messages)
            if new_messages and _is_human_message(new_messages[-1]):
                new_messages[-1] = HumanMessage(content=combined)
            else:
                new_messages.append(HumanMessage(content=combined))
            return {
                "messages": new_messages,
                "message_type": message_type,
                "lead_state": lead_state,
                "already_asked_fields": already_asked_fields,
                "missing_fields": missing_fields,
                "do_not_ask": do_not_ask,
                "conversation_summary": conversation_summary,
            }
        except Exception as e:
            logger.error(f"Vision falhou: {e}")

    return {
        "messages": messages,
        "message_type": message_type,
        "lead_state": lead_state,
        "already_asked_fields": already_asked_fields,
        "missing_fields": missing_fields,
        "do_not_ask": do_not_ask,
        "conversation_summary": conversation_summary,
    }

async def extract_lead_data(state: dict[str, Any]) -> dict[str, Any]:
    """
    Nó Extrator (Extractor LLM):
    - Lê a última mensagem do cliente e o histórico.
    - Chama o LLM (Qwen local) para extrair novos dados estruturados e obter um patch JSON.
    - Mescla o patch ao lead_state no Postgres.
    - Registra a mensagem do usuário como LeadEvent.
    """
    from datetime import datetime
    
    messages = state.get("messages", [])
    if not messages:
        return {}

    customer_data = state.get("customer_data", {})
    phone = customer_data.get("phone", "unknown")
    diagnostic_no_send = bool(customer_data.get("diagnostic_mode")) and not bool(customer_data.get("send_requested"))
    
    lead_state = state.get("lead_state") or _lead_state_copy()
    last_message = messages[-1]
    user_text = _message_text(last_message)
    conversation_summary = state.get("conversation_summary") or ""
    recent_lines: list[str] = []
    for message in messages[-6:]:
        role = "Cliente" if _is_human_message(message) else "Will" if _is_ai_message(message) else "Sistema"
        text = _message_text(message).strip()
        if text:
            recent_lines.append(f"{role}: {text}")
    recent_history = "\n".join(recent_lines) or "Sem histórico recente."
    
    prompt = (
        "Você é um extrator de dados para atendimento comercial de ar-condicionado no Brasil.\n\n"
        "Leia o histórico da conversa e a nova mensagem do cliente abaixo.\n"
        "Atualize APENAS os dados que o cliente informou claramente na última mensagem ou no histórico recente.\n"
        "Não invente nenhuma informação. Não tente adivinhar. Não apague dados existentes. Nunca marque um campo como null/None se ele já estava preenchido.\n\n"
        f"ESTADO ATUAL DO LEAD (JSON):\n{json.dumps(lead_state, ensure_ascii=False, indent=2)}\n\n"
        f"HISTÓRICO RESUMIDO:\n{conversation_summary or 'Sem resumo salvo.'}\n\n"
        f"ÚLTIMAS MENSAGENS:\n{recent_history}\n\n"
        f"CAMPOS JÁ INFORMADOS:\n{state.get('do_not_ask') or []}\n\n"
        "REGRA: Se tipo_servico já existe no estado atual, mantenha esse valor, exceto se o cliente corrigir explicitamente com termos como 'na verdade', 'corrigindo' ou 'quis dizer'.\n\n"
        f"NOVA MENSAGEM DO CLIENTE:\n\"{user_text}\"\n\n"
        "Retorne APENAS um JSON válido no seguinte formato exato, sem explicações:\n"
        "{\n"
        "  \"state_patch\": {\n"
        "     // altere apenas os campos que o cliente informou claramente na nova mensagem ou no histórico\n"
        "     // Exemplos de campos válidos no primeiro nível:\n"
        "     // \"tipo_servico\" (valores: \"instalacao\", \"manutencao\", \"higienizacao\", \"conserto\", \"eletrica\", \"projeto\"), \"nome\", \"cidade_bairro\", \"marca\", \"btus\"\n"
        "  },\n"
        "  \"detected_service_type\": null // string com o tipo de serviço detectado ou null\n"
        "}"
    )
    
    state_patch = {}
    detected_service_type = None
    
    try:
        resp = await _call_local_qwen([{"role": "user", "content": prompt}])
        clean_resp = resp.strip()
        if "```json" in clean_resp:
            clean_resp = clean_resp.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_resp:
            clean_resp = clean_resp.split("```")[1].strip()
            
        data = json.loads(clean_resp)
        state_patch = data.get("state_patch") or {}
        detected_service_type = data.get("detected_service_type")
    except Exception as e:
        logger.warning("Falha ao rodar LLM Extractor em extract_lead_data: %s", e)
        
    current_service = _normalize_service(lead_state.get("tipo_servico"))
    corrected_service = detect_service_correction(user_text, current_service)
    patch_service = _normalize_service(state_patch.get("tipo_servico")) if isinstance(state_patch, dict) else None
    if current_service and patch_service and patch_service != current_service and patch_service != corrected_service:
        state_patch.pop("tipo_servico", None)

    if state_patch:
        for k, v in state_patch.items():
            if v is not None:
                if k == "tipo_servico" and isinstance(v, str):
                    v = _normalize_service(v) or v
                if k in lead_state and isinstance(lead_state[k], dict) and isinstance(v, dict):
                    lead_state[k].update(v)
                else:
                    lead_state[k] = v
    if corrected_service and corrected_service != current_service:
        lead_state["previous_tipo_servico"] = current_service
        lead_state["service_changed_by_user"] = True
        lead_state["tipo_servico"] = corrected_service
                    
    if detected_service_type and not lead_state.get("tipo_servico"):
        lead_state["tipo_servico"] = detected_service_type

    lead_state = _infer_lead_fields_from_text(lead_state, user_text, state.get("message_type"))
        
    do_not_ask, already_asked_fields, missing_fields = compute_fields_status(lead_state)
    lead_state, relationship_type = _apply_relationship_and_appointment(state, lead_state)
    pipeline_stage = "ready_to_schedule" if lead_state.get("appointment_ready") else relationship_type
    lead_state["pipeline_stage"] = pipeline_stage
    conversation_goal = compute_conversation_objective(
        {**state, "service": lead_state.get("tipo_servico") or state.get("service"), "lead_state": lead_state},
        lead_state,
    )
    lead_state["conversation_goal"] = conversation_goal

    try:
        from agent_graph.domain.lead_mind import compact_lead_mind_if_needed, update_from_lead_state

        lead_mind = update_from_lead_state(
            lead_state.get("lead_mind") if isinstance(lead_state.get("lead_mind"), dict) else None,
            lead_state,
            user_text,
            phone=phone if phone != "unknown" else None,
            conversation_goal=conversation_goal,
            conversation_summary=conversation_summary,
            do_not_ask=do_not_ask,
            missing_fields=missing_fields,
        )
        lead_state["lead_mind"] = compact_lead_mind_if_needed(lead_mind)
    except Exception as e:
        logger.warning("Falha ao atualizar lead_mind: %s", e)
    
    if phone and phone != "unknown" and not diagnostic_no_send:
        from prisma import Prisma
        db = Prisma()
        await db.connect()
        try:
            lead = await db.lead.find_unique(where={"phone": phone})
            if lead:
                await db.lead.update(
                    where={"phone": phone},
                    data={
                        "lead_state": json.dumps(lead_state),
                        "already_asked_fields": json.dumps(already_asked_fields),
                        "missing_fields": json.dumps(missing_fields),
                        "do_not_ask": json.dumps(do_not_ask),
                        "service_type": lead_state.get("tipo_servico"),
                        "city_bairro": lead_state.get("cidade_bairro"),
                        "pipeline_stage": pipeline_stage,
                        "last_user_message_at": datetime.now(),
                    }
                )
                
                await db.leadevent.create(
                    data={
                        "lead_id": lead.id,
                        "role": "user",
                        "message": user_text,
                        "extracted_data": json.dumps(state_patch),
                    }
                )
        except Exception as e:
            logger.warning("Falha ao salvar dados de extração no Postgres: %s", e)
        finally:
            await db.disconnect()
            
    return {
        "lead_state": lead_state,
        "already_asked_fields": already_asked_fields,
        "missing_fields": missing_fields,
        "do_not_ask": do_not_ask,
        "service": lead_state.get("tipo_servico") or state.get("service"),
        "conversation_objective": conversation_goal,
        "handoff_mode": "soft_alert" if lead_state.get("appointment_ready") else state.get("handoff_mode"),
        "handoff_reason": "appointment_ready" if lead_state.get("appointment_ready") else state.get("handoff_reason"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa 5 — decide_response_modality + tts_voice_clone
# ──────────────────────────────────────────────────────────────────────────────

async def decide_response_modality(state: dict[str, Any]) -> dict[str, Any]:
    """
    Decide se a resposta vai em áudio ou texto, com base em:
    - Tipo da mensagem inbound (espelha áudio)
    - Intent (pmoc/consultoria → sempre texto)
    - Conteúdo (saudações → áudio)
    """
    from agent_graph.services.tts import should_respond_with_audio

    message_type = state.get("message_type", "conversation")
    intent = state.get("intent")
    outcome = state.get("outcome")
    messages = state.get("messages", [])

    user_text = next(
        (_message_text(m) for m in messages if _is_human_message(m)),
        "",
    )

    use_audio = should_respond_with_audio(message_type, intent, outcome, user_text)
    modality = "audio" if use_audio else "text"
    logger.info(f"Response modality: {modality} (message_type={message_type}, intent={intent})")

    return {"response_modality": modality}


async def tts_voice_clone(state: dict[str, Any]) -> dict[str, Any]:
    """
    Se modality == 'audio', sintetiza resposta com Coqui XTTS (voz do Will).
    Armazena audio_bytes no state para o worker enviar via Evolution API.
    """
    if state.get("response_modality") != "audio":
        return {}

    from agent_graph.services.tts import synthesize, choose_voice_style

    messages = state.get("messages", [])
    intent = state.get("intent")
    outcome = state.get("outcome")
    goal = state.get("conversation_objective") or (state.get("lead_state") or {}).get("conversation_goal")

    ai_text = state.get("tts_text") or next(
        (_message_text(m) for m in reversed(messages) if _is_ai_message(m)),
        "",
    )

    if not ai_text:
        return {"response_modality": "text"}

    voice_style = choose_voice_style(goal or intent, outcome)
    try:
        audio_bytes = await synthesize(ai_text, voice_style)
        if audio_bytes:
            logger.info(f"TTS OK: {len(audio_bytes)} bytes (style={voice_style})")
            return {"audio_bytes": audio_bytes}
        # XTTS indisponível — degrada para texto silenciosamente
        logger.warning("XTTS indisponível, degradando para texto")
        return {"response_modality": "text"}
    except Exception as e:
        logger.error(f"TTS falhou: {e}")
        return {"response_modality": "text"}


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa 6 — dispatch_appointment_alert
# ──────────────────────────────────────────────────────────────────────────────

# Keywords que indicam intenção de agendar (extraídos da fala do lead)
_ADDRESS_PATTERNS: tuple[str, ...] = (
    "rua ", "av ", "avenida ", "bairro ", "cep ", "praia grande",
    "santos", "são vicente", "guarujá", "cubatão", "mongaguá",
    "itanhaém", "peruíbe",
)

_WINDOW_PATTERNS: tuple[str, ...] = (
    "manhã", "tarde", "noite", "segunda", "terça", "quarta",
    "quinta", "sexta", "sábado", "domingo", "amanhã", "hoje",
    "próxima semana", "semana que vem",
)


def _extract_appointment_data(messages: list, customer_data: dict, service: str | None) -> dict | None:
    """
    Extrai dados de agendamento das mensagens do lead.
    Retorna dict com {address, window} se detectar, ou None.
    """
    full_text = " ".join(
        _message_text(m).lower() for m in messages if _is_human_message(m) and _message_text(m)
    )

    address = next((p for p in _ADDRESS_PATTERNS if p in full_text), None)
    window = next((p for p in _WINDOW_PATTERNS if p in full_text), None)

    # Só dispara alerta se tiver pelo menos endereço OU janela
    if not address and not window:
        return None

    return {
        "phone": customer_data.get("phone", ""),
        "name": customer_data.get("name"),
        "service": service,
        "address": address,
        "window": window,
    }


async def dispatch_appointment_alert(state: dict[str, Any]) -> dict[str, Any]:
    """
    Detecta intenção de agendamento nas mensagens e, se encontrar
    endereço ou janela de horário, envia alerta WhatsApp para o dono.
    """
    outcome = state.get("outcome", "")
    service = state.get("service")
    messages = state.get("messages", [])
    customer_data = state.get("customer_data", {})
    if bool(customer_data.get("diagnostic_mode")) and not bool(customer_data.get("send_requested")):
        return {}

    lead_state = state.get("lead_state") or {}
    # Só verifica outcomes que levam a visita/reunião ou lead já pronto para agenda.
    if outcome not in ("analise_tecnica", "higienizacao_preventiva", "reuniao_projeto") and not lead_state.get("appointment_ready"):
        return {}

    lead_data = _extract_appointment_data(messages, customer_data, service)
    if not lead_data or not lead_data.get("window"):
        return {}
    lead_data["reason"] = "appointment_confirmed"
    lead_data["last_message"] = _latest_human_text(messages)

    from agent_graph.services.alerts import send_appointment_alert, prisma_upsert_lead

    try:
        await prisma_upsert_lead(lead_data)
    except Exception as e:
        logger.error(f"Lead upsert falhou: {e}")

    try:
        await send_appointment_alert(lead_data)
    except Exception as e:
        logger.error(f"Alert dispatch falhou: {e}")

    return {}
