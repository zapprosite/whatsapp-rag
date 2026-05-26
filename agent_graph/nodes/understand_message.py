from __future__ import annotations

import re
from typing import Any

from agent_graph.nodes.nodes import _message_text, _normalize_service, _detect_preferred_window


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _detect_service_mentioned(text: str) -> str | None:
    mapping = (
        ("higienizacao", ("higienizacao", "higienização", "limpeza")),
        ("instalacao", ("instalacao", "instalação", "instalar")),
        ("manutencao", ("manutencao", "manutenção", "conserto", "reparo")),
        ("consultoria", ("consultoria", "dimensionamento", "btu")),
        ("pmoc", ("pmoc",)),
        ("projeto-central", ("vrf", "vrv", "cassete", "multisplit", "projeto")),
    )
    for service, terms in mapping:
        if any(term in text for term in terms):
            return service
    return None


def _short_answer_kind(text: str) -> str | None:
    yes_terms = {"sim", "s", "isso", "tem", "tem sim", "já", "ja", "pode ser", "ok", "positivo"}
    no_terms = {"nao", "não", "n", "negativo", "nao tem", "não tem"}
    if text in yes_terms:
        return "yes"
    if text in no_terms:
        return "no"
    return None


async def understand_message(state: dict[str, Any]) -> dict[str, Any]:
    messages = state.get("messages") or []
    user_text = _message_text(messages[-1]) if messages else ""
    text = _fold(user_text)
    current_service = _normalize_service((state.get("lead_state") or {}).get("tipo_servico") or state.get("service"))
    service_mentioned = _detect_service_mentioned(text)
    window = _detect_preferred_window(user_text)
    slot_choice = int(text) if re.fullmatch(r"[123]", text) else None
    short_answer = _short_answer_kind(text)

    asks_process = any(
        term in text
        for term in (
            "como funciona",
            "como vocês fazem",
            "como voces fazem",
            "me explica",
            "qual o processo",
            "o que inclui",
        )
    )
    asks_price = any(term in text for term in ("quanto", "quanto fica", "valor", "preço", "preco", "custa"))
    asks_calendar = any(
        term in text
        for term in (
            "horário",
            "horario",
            "agenda",
            "agendar",
            "marcar",
            "qual dia",
            "que dia",
        )
    )
    asks_time_specific = any(
        term in text
        for term in (
            "nao consegue me dizer um horario",
            "não consegue me dizer um horário",
            "consegue me dizer um horario",
            "consegue me dizer um horário",
            "me dizer um horario",
            "me dizer um horário",
        )
    )
    unavailable_photo = any(term in text for term in ("nao tenho foto", "não tenho foto", "sem foto", "nao tenho as fotos", "não tenho as fotos"))
    unavailable_infra = any(term in text for term in ("nao tenho infra", "não tenho infra", "sem infra", "nao tenho infraestrutura", "não tenho infraestrutura", "nao tenho tubulacao", "não tenho tubulação"))
    asks_capability = any(
        term in text
        for term in (
            "vocês trabalham com",
            "voces trabalham com",
            "vocês fazem",
            "voces fazem",
            "também trabalham com",
            "tambem trabalham com",
        )
    ) and service_mentioned is not None

    malicious = False
    security_guard = state.get("security_guard") or {}
    if security_guard.get("is_malicious"):
        malicious = True
    else:
        try:
            from agent_graph.guards.security_guard import detect_malicious_or_instruction_injection

            malicious = bool(detect_malicious_or_instruction_injection(user_text).get("is_malicious"))
        except Exception:
            malicious = False

    kind = "unknown"
    if malicious:
        kind = "security"
    elif asks_process:
        kind = "process_question"
    elif asks_capability:
        kind = "capability_question"
    elif short_answer:
        kind = "short_answer"
    elif window:
        kind = "window_preference"
    elif slot_choice is not None:
        kind = "slot_choice"
    elif asks_calendar:
        kind = "calendar_request"
    elif asks_price:
        kind = "price_question"
    elif state.get("message_type") == "imageMessage":
        kind = "image_upload"
    elif current_service or service_mentioned:
        kind = "answer_question"

    understanding = {
        "kind": kind,
        "service_mentioned": service_mentioned,
        "is_side_question": bool(asks_capability and current_service and service_mentioned and service_mentioned != current_service),
        "short_answer": short_answer,
        "window": window,
        "slot_choice": slot_choice,
        "asks_process": asks_process,
        "asks_price": asks_price,
        "asks_calendar": asks_calendar,
        "asks_time_specific": asks_time_specific,
        "asks_capability": asks_capability,
        "unavailable_photo": unavailable_photo,
        "unavailable_infra": unavailable_infra,
        "malicious": malicious,
    }
    return {"message_understanding": understanding}
