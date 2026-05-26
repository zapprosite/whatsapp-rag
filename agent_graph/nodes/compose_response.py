from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage

from agent_graph.domain.commercial_router import decide_commercial_path
from agent_graph.domain.onboarding import greeting_by_time
import agent_graph.nodes.nodes as nodes_module
from agent_graph.domain.actions import NextAction
from agent_graph.domain.response_catalog import ResponseContext, render_response
from agent_graph.nodes.nodes import (
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


def _service_ack(service: str | None) -> str:
    mapping = {
        "instalacao": "Consigo te ajudar com instalação sim.",
        "higienizacao": "Consigo te ajudar com higienização sim.",
        "manutencao": "Consigo te ajudar com manutenção sim.",
        "conserto": "Consigo te ajudar com conserto sim.",
    }
    return mapping.get(service, "Consigo te ajudar sim.")


def _commercial_response(state: dict[str, Any], service: str | None, user_text: str, lead_state: dict[str, Any]) -> str:
    decision = state.get("commercial_decision") or decide_commercial_path({**lead_state, "tipo_servico": service}, user_text).to_dict()
    path = decision.get("path")
    
    greeting = greeting_by_time(datetime.now())
    ctx = ResponseContext(
        greeting=greeting,
        service=service,
        commercial_path=path,
        preferred_window=(lead_state.get("appointment") or {}).get("preferred_window"),
    )
    
    if service == "instalacao" and state.get("message_understanding", {}).get("unavailable_infra"):
        return (
            "Sem infra pronta, entra em avaliação de infraestrutura. Para não travar por aqui, o caminho certo é visita técnica de R$50, abatível se o orçamento final for aprovado.\n\n"
            "Podemos agendar a visita?"
        )
    
    if path == "ask_basic_service":
        return render_response("ask_basic_service", ctx)
    if path == "fixed_installation_simple":
        return render_response("offer_fixed_installation", ctx)
    if path == "fixed_hygienization":
        return render_response("offer_fixed_hygienization", ctx)
    if path == "project_quote":
        return render_response("offer_project_visit", ctx)
    
    return render_response("offer_technical_visit", ctx)


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
    response = await nodes_module.llm_chat(
        [
            {"role": "system", "content": nodes_module.WILL_SYSTEM_PROMPT},
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
    identity = lead_state.setdefault("lead_identity", {})
    greeting = greeting_by_time(datetime.now())

    commercial_decision = lead_state.get("commercial_decision") or {}
    missing_field_name = action.get("missing_field") or _important_missing_field_for_service(service, missing_fields, do_not_ask, lead_state)

    ctx = ResponseContext(
        greeting=greeting,
        service=service,
        name=identity.get("full_name") or lead_state.get("nome"),
        city_bairro=lead_state.get("cidade_bairro"),
        commercial_path=commercial_decision.get("path"),
        price=commercial_decision.get("fixed_price") or commercial_decision.get("visit_price"),
        preferred_window=action.get("slot_label") or action.get("preferred_window") or (state.get("message_understanding") or {}).get("window") or appointment.get("preferred_window"),
        missing_field=missing_field_name,
        last_offer_path=commercial_decision.get("path"),
    )

    catalog_actions = {
        "welcome_onboarding",
        "ask_lead_name",
        "ask_basic_service",
        "ask_optional_contact_info",
        "offer_fixed_installation",
        "offer_fixed_hygienization",
        "offer_technical_visit",
        "offer_project_visit",
        "explain_last_offer",
        "explain_process",
        "answer_capability_question",
        "ask_missing_field",
        "save_preferred_window",
        "fallback_recover_context",
        "reject_security",
        "handoff_human",
        "confirm_calendar_slot",
    }

    if action_type in catalog_actions:
        response = render_response(action_type, ctx)
    elif action_type == "active_service_followup":
        response = _active_service_response(user_text, (state.get("customer_data") or {}).get("active_service") or {})
    elif action_type == "offer_calendar_slots":
        slots = state.get("calendar_slots") or appointment.get("offered_slots") or []
        if not slots:
            response = render_response("calendar_not_enabled", ctx)
        else:
            formatted = format_slots_for_whatsapp(slots)
            response = f"Tenho estas opções disponíveis:\n\n{formatted}\n\nQual opção fica melhor?"
    elif action_type == "answer_question":
        if action.get("answer_kind") == "price":
            response = _direct_price_response(service, user_text, lead_state, missing_fields, do_not_ask)
        elif action.get("answer_kind") == "commercial":
            response = _commercial_response(state, service, user_text, lead_state)
        else:
            response = None
        if not response:
            response = await _llm_answer(state, action)
    else:
        response = render_response("fallback_recover_context", ctx)

    if action_type not in {
        "welcome_onboarding",
        "ask_lead_name",
        "ask_basic_service",
        "ask_optional_contact_info",
        "offer_fixed_installation",
        "offer_fixed_hygienization",
        "offer_technical_visit",
        "offer_project_visit",
        "explain_last_offer",
        "explain_process",
        "answer_capability_question",
        "ask_missing_field",
        "save_preferred_window",
    }:
        response = await _polish_ptbr_if_enabled(response, user_text)
    return {
        "messages": messages + [AIMessage(content=response)],
        "lead_state": lead_state,
        "tts_text": response,
    }
