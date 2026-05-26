from __future__ import annotations

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
    service_mentioned = _normalize_service(understanding.get("service_mentioned"))
    if service_mentioned and not lead_state.get("tipo_servico") and understanding.get("kind") != "capability_question":
        lead_state["tipo_servico"] = service_mentioned

    last_asked_field = lead_state.get("last_asked_field") or state.get("last_asked_field")
    short_answer_applied = _apply_short_answer(lead_state, last_asked_field, understanding.get("short_answer"))

    if understanding.get("kind") == "window_preference" and understanding.get("window"):
        appointment = lead_state.setdefault("appointment", {})
        appointment["preferred_window"] = understanding["window"]
        appointment["confirmed_window"] = False

    vision_data = deepcopy(state.get("vision_data") or {})
    if state.get("message_type") == "imageMessage" and vision_data:
        _apply_image_state(lead_state, vision_data, last_asked_field)

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
