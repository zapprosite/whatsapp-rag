from __future__ import annotations

from copy import deepcopy
from typing import Any

from langchain_core.messages import AIMessage

from agent_graph.domain.actions import NextAction
from agent_graph.nodes.nodes import (
    WILL_SYSTEM_PROMPT,
    _active_service_response,
    _direct_price_response,
    _human_service_label,
    _important_missing_field_for_service,
    _message_text,
    _normalize_service,
    _polish_ptbr_if_enabled,
    _process_question_response,
    _question_for_field,
    _unknown_recovery_response,
    llm_chat,
)
from agent_graph.services.calendar import format_slots_for_whatsapp


def _latest_user_text(state: dict[str, Any]) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    return _message_text(messages[-1])


def _missing_field_human(field: str | None) -> str:
    mapping = {
        "foto_local_externo": "a foto do local externo onde ficaria a condensadora",
        "foto_local_interno": "a foto do local interno onde ficaria a evaporadora",
        "ponto_eletrico_exclusivo": "a confirmação do ponto elétrico exclusivo",
        "cidade_bairro": "a cidade e o bairro",
        "btus": "a capacidade em BTUs ou o modelo do aparelho",
    }
    return mapping.get(field, "um detalhe importante")


async def _llm_answer(state: dict[str, Any], action: NextAction) -> str:
    user_text = _latest_user_text(state)
    service = action.get("service") or (state.get("lead_state") or {}).get("tipo_servico") or state.get("service")
    rag_context = state.get("rag_context") or []
    context_parts: list[str] = []
    for ctx in rag_context:
        payload = ctx.get("payload", {})
        text = payload.get("text")
        if text:
            context_parts.append(str(text))
    prompt = (
        f"Você é o Will da Refrimix.\n"
        f"Ação obrigatória: {action.get('type')}.\n"
        f"Serviço principal: {_human_service_label(_normalize_service(service))}.\n"
        f"Contexto RAG:\n{chr(10).join(context_parts) or 'Sem contexto recuperado.'}\n\n"
        f"Mensagem do cliente: {user_text}\n\n"
        "Responda em português brasileiro, direto, sem inventar preço ou agenda. "
        "Se precisar perguntar algo, faça só uma pergunta objetiva no final."
    )
    response = await llm_chat(
        [
            {"role": "system", "content": WILL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_retries=2,
    )
    return await _polish_ptbr_if_enabled(response, user_text)


async def compose_response(state: dict[str, Any]) -> dict[str, Any]:
    messages = list(state.get("messages") or [])
    lead_state = deepcopy(state.get("lead_state") or {})
    action = (state.get("next_action") or {"type": "fallback_recover_context"})
    action_type = action.get("type")
    service = _normalize_service(action.get("service") or lead_state.get("tipo_servico") or state.get("service"))
    missing_fields = list(state.get("missing_fields") or [])
    do_not_ask = list(state.get("do_not_ask") or [])
    user_text = _latest_user_text(state)
    appointment = lead_state.setdefault("appointment", {})

    if action_type == "reject_security":
        response = state.get("safe_response") or "Não consigo seguir por esse caminho. Se a sua dúvida for sobre ar-condicionado, me fala em uma frase simples o que você precisa."
    elif action_type == "active_service_followup":
        response = _active_service_response(user_text, (state.get("customer_data") or {}).get("active_service") or {})
    elif action_type == "handoff_human":
        response = "Entendi. Vou deixar isso sinalizado para atendimento humano e adiantar o contexto por aqui."
    elif action_type == "explain_process":
        response = _process_question_response(lead_state, service, missing_fields, do_not_ask)
    elif action_type == "answer_capability_question":
        mentioned = (state.get("message_understanding") or {}).get("service_mentioned")
        if mentioned == "higienizacao":
            response = (
                "Sim, também trabalhamos com higienização.\n\n"
                "Em split padrão, fica R$200 por aparelho. Ajuda quando tem cheiro ruim, sujeira acumulada, mofo ou muito tempo sem limpeza.\n\n"
                "Se quiser incluir também, me confirma quantos aparelhos são."
            )
        else:
            label = _human_service_label(_normalize_service(mentioned))
            response = f"Sim, também trabalhamos com {label}.\n\nSe você quiser, eu já te explico como funciona nesse caso."
    elif action_type == "ask_missing_field":
        field = action.get("missing_field") or _important_missing_field_for_service(service, missing_fields, do_not_ask, lead_state)
        response = _question_for_field(field)
    elif action_type == "save_preferred_window":
        field = action.get("missing_field")
        window = (state.get("message_understanding") or {}).get("window") or appointment.get("preferred_window") or "esse período"
        response = (
            f"Perfeito, deixei a preferência pela {window} anotada.\n\n"
            f"Antes disso, ainda preciso de {_missing_field_human(field)}."
        )
    elif action_type == "offer_calendar_slots":
        slots = state.get("calendar_slots") or appointment.get("offered_slots") or []
        formatted = format_slots_for_whatsapp(slots)
        response = f"Tenho estas opções disponíveis:\n\n{formatted}\n\nQual opção fica melhor?"
    elif action_type == "confirm_calendar_slot":
        response = f"Perfeito, deixei separada a opção de {action.get('slot_label') or 'horário escolhido'} para confirmação."
    elif action_type == "answer_question":
        response = _direct_price_response(service, user_text, lead_state, missing_fields, do_not_ask) if action.get("answer_kind") == "price" else None
        if not response:
            response = await _llm_answer(state, action)
    else:
        response = _unknown_recovery_response(user_text)

    response = await _polish_ptbr_if_enabled(response, user_text)
    return {
        "messages": messages + [AIMessage(content=response)],
        "lead_state": lead_state,
        "tts_text": response,
    }
