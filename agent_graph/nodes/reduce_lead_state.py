from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from agent_graph.domain.stage_engine import compute_calendar_stage, compute_conversation_stage
from agent_graph.nodes.nodes import (
    _lead_state_copy,
    _normalize_service,
    compute_fields_status,
    sanitize_lead_state,
)

_SHORT_ANSWER_FIELD_MAP: dict[str, tuple[str, str]] = {
    "ponto_eletrico_exclusivo": ("instalacao", "ponto_eletrico_exclusivo"),
    "tubulacao_existente": ("instalacao", "tubulacao_existente"),
    "aparelho_ja_comprado": ("root", "aparelho_ja_comprado"),
    "tempo_sem_manutencao": ("manutencao", "tempo_sem_manutencao"),
    "cheiro_ruim": ("manutencao", "cheiro_ruim"),
    "pinga_agua": ("manutencao", "pinga_agua"),
    "liga": ("conserto", "liga"),
    "gela": ("conserto", "gela"),
}


def _extract_email(text: str) -> str | None:
    match = re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", text)
    return match.group(0) if match else None


def _extract_full_name(text: str) -> str | None:
    cleaned = text.strip()
    if not cleaned or "@" in cleaned or any(ch.isdigit() for ch in cleaned):
        return None
    match = re.search(
        r"(?:meu nome e|meu nome é|sou|aqui e|aqui é)?\s*([A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-záéíóúâêôãõç]+(?:\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]?[a-záéíóúâêôãõç]+){0,3})$",
        cleaned,
        re.I,
    )
    if not match:
        return None
    candidate = " ".join(part.capitalize() for part in match.group(1).split())
    if len(candidate.split()) > 4:
        return None
    return candidate


def _update_identity_from_state(lead_state: dict[str, Any], customer_data: dict[str, Any], user_text: str) -> None:
    identity = lead_state.setdefault("lead_identity", {})
    phone = customer_data.get("phone")
    if phone:
        identity["phone"] = phone

    email = _extract_email(user_text)
    if email and not identity.get("email"):
        identity["email"] = email
        lead_state["email"] = email

    name_source = lead_state.get("nome") or identity.get("full_name") or _extract_full_name(user_text)
    if name_source:
        parts = str(name_source).strip().split()
        identity["full_name"] = " ".join(parts)
        identity["first_name"] = parts[0]
        identity["last_name"] = " ".join(parts[1:]) if len(parts) > 1 else None
        lead_state["nome"] = identity["full_name"]

    if lead_state.get("address") and not identity.get("address"):
        identity["address"] = lead_state["address"]

    if identity.get("full_name") or identity.get("first_name"):
        identity["identity_status"] = "identified"
    elif identity.get("phone"):
        identity["identity_status"] = "missing_name"
    else:
        identity["identity_status"] = "missing_phone"


def _apply_short_answer(
    lead_state: dict[str, Any],
    last_asked_field: str | None,
    short_answer: str | None,
) -> bool:
    if not last_asked_field or short_answer not in {"yes", "no"}:
        return False
    target = _SHORT_ANSWER_FIELD_MAP.get(last_asked_field)
    if not target:
        return False
    value = short_answer == "yes"
    bucket, field = target
    if bucket == "root":
        lead_state[field] = value
    else:
        lead_state.setdefault(bucket, {})
        lead_state[bucket][field] = value
    return True


def apply_short_answer_to_last_asked_field(
    lead_state: dict[str, Any],
    last_asked_field: str | None,
    user_text: str,
) -> bool:
    if not last_asked_field or not user_text:
        return False
    
    cleaned = re.sub(r"\s+", " ", user_text.strip().lower())
    
    if last_asked_field == "quantidade_aparelhos":
        word_to_num = {
            "um": 1, "uma": 1, "1": 1,
            "dois": 2, "duas": 2, "2": 2,
            "tres": 3, "três": 3, "3": 3,
            "quatro": 4, "4": 4,
            "cinco": 5, "5": 5,
            "seis": 6, "meia": 6, "6": 6,
            "sete": 7, "7": 7,
            "oito": 8, "8": 8,
            "nove": 9, "9": 9,
            "dez": 10, "10": 10
        }
        
        match = re.search(r"\b(\d+)\b", cleaned)
        if match:
            try:
                qty = int(match.group(1))
                lead_state.setdefault("higienizacao", {})
                lead_state["higienizacao"]["quantidade_aparelhos"] = qty
                return True
            except ValueError:
                pass
                
        for word, val in word_to_num.items():
            if re.search(rf"\b{word}\b", cleaned):
                lead_state.setdefault("higienizacao", {})
                lead_state["higienizacao"]["quantidade_aparelhos"] = val
                return True
                
    return False


def _apply_image_state(
    lead_state: dict[str, Any],
    vision_data: dict[str, Any],
    expected_field: str | None,
) -> None:
    image_type = vision_data.get("image_type")
    fotos = lead_state.setdefault("fotos", {})
    lead_state["last_image_analysis"] = vision_data
    lead_state["image_mismatch"] = None

    if image_type == "local_interno_instalacao":
        if expected_field == "foto_local_externo":
            lead_state["image_mismatch"] = {
                "expected": "foto_local_externo",
                "received": "local_interno_instalacao",
            }
            return
        fotos["local_interno"] = True
        return

    if image_type == "local_externo_instalacao":
        if expected_field == "foto_local_interno":
            lead_state["image_mismatch"] = {
                "expected": "foto_local_interno",
                "received": "local_externo_instalacao",
            }
            return
        fotos["local_externo"] = True
        return

    if image_type in {"equipamento_ar_condicionado", "etiqueta_tecnica"}:
        fotos["aparelho"] = True
        equipment_context = vision_data.get("equipment_context") or {}
        if equipment_context.get("brand") and not lead_state.get("marca"):
            lead_state["marca"] = equipment_context["brand"]
        if equipment_context.get("model") and not lead_state.get("modelo_aparelho"):
            lead_state["modelo_aparelho"] = equipment_context["model"]
        if equipment_context.get("btus") and not lead_state.get("btus"):
            lead_state["btus"] = str(equipment_context["btus"])
        return

    if image_type == "quadro_eletrico_disjuntor":
        fotos["disjuntor"] = True


async def reduce_lead_state(state: dict[str, Any]) -> dict[str, Any]:
    lead_state = sanitize_lead_state(deepcopy(state.get("lead_state") or _lead_state_copy()))
    understanding = state.get("message_understanding") or {}
    customer_data = state.get("customer_data") or {}
    messages = state.get("messages") or []
    user_text = str(getattr(messages[-1], "content", "") or "") if messages else ""
    service_mentioned = _normalize_service(understanding.get("service_mentioned"))
    if service_mentioned and not lead_state.get("tipo_servico") and understanding.get("kind") != "capability_question":
        lead_state["tipo_servico"] = service_mentioned

    last_asked_field = lead_state.get("last_asked_field") or state.get("last_asked_field")
    short_answer_applied = _apply_short_answer(lead_state, last_asked_field, understanding.get("short_answer"))
    if not short_answer_applied:
        short_answer_applied = apply_short_answer_to_last_asked_field(lead_state, last_asked_field, user_text)

    if understanding.get("kind") == "window_preference" and understanding.get("window"):
        appointment = lead_state.setdefault("appointment", {})
        appointment["preferred_window"] = understanding["window"]
        appointment["confirmed_window"] = False

    vision_data = deepcopy(state.get("vision_data") or {})
    if state.get("message_type") == "imageMessage" and vision_data:
        _apply_image_state(lead_state, vision_data, last_asked_field)

    _update_identity_from_state(lead_state, customer_data, user_text)
    lead_state = sanitize_lead_state(lead_state)
    do_not_ask, already_asked_fields, missing_fields = compute_fields_status(lead_state)
    lead_state["calendar_stage"] = compute_calendar_stage(lead_state)
    lead_state["conversation_stage"] = compute_conversation_stage(
        lead_state,
        understanding,
        state.get("customer_data") or {},
    )

    return {
        "lead_state": lead_state,
        "do_not_ask": do_not_ask,
        "already_asked_fields": already_asked_fields,
        "missing_fields": missing_fields,
        "short_answer_applied": short_answer_applied,
        "conversation_stage": lead_state.get("conversation_stage"),
        "calendar_stage": lead_state.get("calendar_stage"),
    }

