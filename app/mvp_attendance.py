from __future__ import annotations

import os
import re
import unicodedata
from copy import deepcopy
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from agent_graph.domain.commercial_router import decide_commercial_path
from agent_graph.domain.onboarding import is_generic_greeting_or_message
from agent_graph.nodes.nodes import _lead_state_copy, sanitize_lead_state

from app.lead_repository import create_lead_event, load_or_create_lead, update_lead_state

_WELCOME_RESPONSE = "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?"
_ASK_SERVICE_RESPONSE = "Entendi.\n\nIsso é instalação, manutenção, higienização ou conserto?"
_ASK_NAME_RESPONSE = "Perfeito.\n\nMe passa seu nome pra eu deixar o atendimento certinho?"
_INSTALL_SIMPLE_RESPONSE = (
    "Instalação simples costa/costa, até 3 metros e com acesso fácil, fica R$850 com material e mão de obra.\n\n"
    "Se no local tiver algo fora do padrão, o técnico explica antes e o valor pode ajustar.\n\n"
    "Qual período fica melhor: manhã ou tarde?"
)
_INSTALL_VISIT_RESPONSE = (
    "Sem problema.\n\n"
    "A foto ajuda a adiantar, mas não trava o atendimento.\n\n"
    "Seguimos como visita técnica de R$50. Se o orçamento final for aprovado, esse valor pode ser abatido.\n\n"
    "Qual período fica melhor: manhã ou tarde?"
)
_MAINTENANCE_RESPONSE = (
    "Para manutenção, o caminho correto é visita/análise técnica.\n\n"
    "A visita fica R$50 e pode ser abatida se o orçamento final for aprovado.\n\n"
    "Qual período fica melhor para a visita?"
)
_HYGIENIZATION_RESPONSE = (
    "Higienização de split padrão fica R$200 por aparelho, desde que o equipamento esteja funcionando e instalado dentro do padrão.\n\n"
    "Se o aparelho não estiver climatizando, o atendimento pode virar análise de manutenção por R$50.\n\n"
    "Quantos aparelhos são?"
)

_SERVICE_KEYWORDS = {
    "instalacao": ("instalacao", "instalação", "instalar"),
    "manutencao": ("manutencao", "manutenção", "conserto", "consertar", "nao gela", "não gela"),
    "higienizacao": ("higienizacao", "higienização", "higienizar", "limpeza", "limpar"),
}
_MORNING_TERMS = ("manha", "manhã", "de manhã")
_AFTERNOON_TERMS = ("tarde",)
_NO_PHOTO_TERMS = ("nao tenho foto", "não tenho foto", "sem foto")
_INVALID_NAME_TERMS = {
    "bom dia",
    "boa tarde",
    "boa noite",
    "instalacao",
    "instalação",
    "instalar",
    "manutencao",
    "manutenção",
    "higienizacao",
    "higienização",
    "conserto",
    "limpeza",
}
_INVALID_NAME_TOKENS = {"nao", "não", "tenho", "foto", "sem", "quero", "preciso", "manhã", "tarde"}


def minimal_mvp_enabled() -> bool:
    return str(os.getenv("MINIMAL_MVP_ENABLED", "0")).strip() == "1"


def _fold(text: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text.strip().lower())


def _message_text(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", message)
    return content if isinstance(content, str) else str(content or "")


def _last_assistant_text(history: list[BaseMessage]) -> str:
    for message in reversed(history):
        if isinstance(message, AIMessage):
            return _message_text(message)
    return ""


def _detect_service(text: str, lead_state: dict[str, Any]) -> str | None:
    folded = _fold(text)
    for service, keywords in _SERVICE_KEYWORDS.items():
        if any(keyword in folded for keyword in keywords):
            return "manutencao" if service == "manutencao" else service
    existing = lead_state.get("tipo_servico")
    return str(existing) if existing else None


def _detect_name(text: str) -> str | None:
    match = re.search(r"\b(?:meu nome e|meu nome é|sou|pode chamar de)\s+([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{1,60})", text, re.IGNORECASE)
    if match:
        candidate = match.group(1).strip()
        if _fold(candidate) not in _INVALID_NAME_TERMS:
            return candidate
        return None
    stripped = text.strip()
    stripped_folded = _fold(stripped)
    stripped_tokens = stripped_folded.split()
    if (
        re.fullmatch(r"[A-Za-zÀ-ÿ][A-Za-zÀ-ÿ' -]{1,60}", stripped)
        and len(stripped.split()) <= 4
        and stripped_folded not in _INVALID_NAME_TERMS
        and not any(token in _INVALID_NAME_TOKENS for token in stripped_tokens)
    ):
        return stripped
    return None


def _detect_window(text: str) -> str | None:
    folded = _fold(text)
    if any(term in folded for term in _MORNING_TERMS):
        return "manhã"
    if any(term in folded for term in _AFTERNOON_TERMS):
        return "tarde"
    return None


def _answered_service_prompt(previous_assistant: str, current_service: str | None) -> bool:
    if not current_service:
        return False
    return previous_assistant in {_WELCOME_RESPONSE, _ASK_SERVICE_RESPONSE}


def _service_pipeline_stage(service: str | None, decision_path: str | None) -> str:
    if not service:
        return "awaiting_service"
    if decision_path in {"fixed_installation_simple", "fixed_hygienization", "technical_visit_50"}:
        return "quoted"
    return "qualified"


def _base_state(phone: str, lead: dict[str, Any] | None = None) -> dict[str, Any]:
    state = deepcopy((lead or {}).get("lead_state") or _lead_state_copy())
    state = sanitize_lead_state(state)
    identity = state.setdefault("lead_identity", {})
    identity["phone"] = phone
    identity["identity_status"] = "identified" if identity.get("full_name") else "missing_name"
    state.setdefault("appointment", {})
    state.setdefault("fotos", {})
    state.setdefault("instalacao", {})
    state.setdefault("last_messages", {})
    return state


def update_lead_state_mvp(lead_state: dict[str, Any], user_text: str, phone: str) -> dict[str, Any]:
    updated = _base_state(phone, {"lead_state": lead_state})
    updated["last_messages"]["user"] = user_text

    detected_service = _detect_service(user_text, updated)
    if detected_service:
        updated["tipo_servico"] = detected_service

    detected_name = _detect_name(user_text)
    if detected_name:
        updated["nome"] = detected_name
        parts = detected_name.split()
        identity = updated.setdefault("lead_identity", {})
        identity["full_name"] = detected_name
        identity["first_name"] = parts[0] if parts else None
        identity["last_name"] = " ".join(parts[1:]) if len(parts) > 1 else None
        identity["identity_status"] = "identified"

    preferred_window = _detect_window(user_text)
    if preferred_window:
        updated.setdefault("appointment", {})["preferred_window"] = preferred_window

    folded = _fold(user_text)
    if any(term in folded for term in _NO_PHOTO_TERMS):
        updated.setdefault("fotos", {})["local_interno"] = False
        updated["fotos"]["local_externo"] = False

    return sanitize_lead_state(updated)


def compose_response_mvp(
    user_text: str,
    lead_state: dict[str, Any],
    *,
    is_first_message: bool,
    previous_assistant: str,
) -> tuple[str, dict[str, Any]]:
    service = lead_state.get("tipo_servico")
    if is_first_message and is_generic_greeting_or_message(user_text) and not service:
        lead_state["pipeline_stage"] = "new"
        return _WELCOME_RESPONSE, lead_state

    if not service:
        lead_state["pipeline_stage"] = "awaiting_service"
        return _ASK_SERVICE_RESPONSE, lead_state

    if _answered_service_prompt(previous_assistant, service) and not lead_state.get("nome"):
        lead_state["pipeline_stage"] = "awaiting_name"
        return _ASK_NAME_RESPONSE, lead_state

    decision = decide_commercial_path(lead_state, user_text).to_dict()
    lead_state["commercial_decision"] = decision
    lead_state["pipeline_stage"] = _service_pipeline_stage(service, decision.get("path"))

    if decision.get("path") == "fixed_installation_simple":
        return _INSTALL_SIMPLE_RESPONSE, lead_state
    if service in {"manutencao", "conserto"} or decision.get("path") == "technical_visit_50" and service == "manutencao":
        return _MAINTENANCE_RESPONSE, lead_state
    if service == "higienizacao" and decision.get("path") == "fixed_hygienization":
        return _HYGIENIZATION_RESPONSE, lead_state
    if decision.get("path") == "technical_visit_50":
        if service == "higienizacao":
            return _MAINTENANCE_RESPONSE, lead_state
        return _INSTALL_VISIT_RESPONSE, lead_state
    if service == "higienizacao":
        return _HYGIENIZATION_RESPONSE, lead_state
    if service in {"manutencao", "conserto"}:
        return _MAINTENANCE_RESPONSE, lead_state
    return _INSTALL_VISIT_RESPONSE, lead_state


async def process_mvp_message(
    *,
    phone: str,
    message_text: str,
    instance: str,
    history: list[BaseMessage],
) -> dict[str, Any]:
    del instance
    lead = await load_or_create_lead(phone)
    lead_state = update_lead_state_mvp(lead.get("lead_state") or {}, message_text, phone)
    previous_assistant = _last_assistant_text(history)
    is_first_message = not history and int(lead.get("event_count") or 0) == 0
    response_text, lead_state = compose_response_mvp(
        message_text,
        lead_state,
        is_first_message=is_first_message,
        previous_assistant=previous_assistant,
    )
    lead_state.setdefault("last_messages", {})["assistant"] = response_text
    service = lead_state.get("tipo_servico")
    pipeline_stage = str(lead_state.get("pipeline_stage") or _service_pipeline_stage(service, (lead_state.get("commercial_decision") or {}).get("path")))
    await update_lead_state(
        phone,
        lead_state,
        pipeline_stage=pipeline_stage,
        service_type=service,
        city_bairro=lead_state.get("cidade_bairro"),
    )
    await create_lead_event(phone, "user", message_text, extracted_data={"tipo_servico": service})
    await create_lead_event(phone, "assistant", response_text, extracted_data={"pipeline_stage": pipeline_stage})

    messages = list(history) + [HumanMessage(content=message_text), AIMessage(content=response_text)]
    return {
        "messages": messages,
        "lead_state": lead_state,
        "response_modality": "text",
        "handoff_mode": "none",
        "handoff_reason": None,
        "outcome": "minimal_mvp",
    }
