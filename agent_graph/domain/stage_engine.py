from __future__ import annotations

from typing import Any

from agent_graph.domain.commercial_router import decide_commercial_path
from agent_graph.domain.stages import CalendarStage, ConversationStage
from agent_graph.nodes.nodes import _normalize_service, _is_invalid_structured_value


def has_requirements_for_calendar(lead_state: dict[str, Any], service: str | None) -> bool:
    service = _normalize_service(service or lead_state.get("tipo_servico"))
    appointment = lead_state.get("appointment") or {}
    if appointment.get("confirmed_window") and appointment.get("selected_slot"):
        return True
    if service and _is_invalid_structured_value(lead_state.get("cidade_bairro")):
        return False
    decision = decide_commercial_path({**lead_state, "tipo_servico": service})
    return bool(decision.can_schedule_now)


def compute_calendar_stage(lead_state: dict[str, Any]) -> CalendarStage:
    service = lead_state.get("tipo_servico")
    appointment = lead_state.get("appointment") or {}
    if appointment.get("event_status") == "created":
        return "event_created"
    if appointment.get("event_status") == "failed":
        return "event_failed"
    if appointment.get("selected_slot"):
        return "waiting_slot_choice"
    if appointment.get("offered_slots"):
        return "slots_offered"
    if has_requirements_for_calendar(lead_state, service):
        if appointment.get("availability_checked_at"):
            return "availability_checked"
        return "ready_to_check_availability"
    return "not_ready"


def compute_conversation_stage(
    lead_state: dict[str, Any],
    message_understanding: dict[str, Any] | None,
    customer_data: dict[str, Any] | None,
) -> ConversationStage:
    customer_data = customer_data or {}
    understanding = message_understanding or {}
    service = _normalize_service(lead_state.get("tipo_servico"))
    calendar_stage = compute_calendar_stage(lead_state)

    if understanding.get("malicious") or lead_state.get("security_rejected"):
        return "blocked_security"
    if customer_data.get("active_service"):
        return "active_service_followup"
    if lead_state.get("human_takeover") or lead_state.get("relationship_type") in {"human_takeover", "complaint_or_risk"}:
        return "human_handoff"
    if lead_state.get("last_completed_service"):
        return "post_sale"
    if understanding.get("asks_process") or understanding.get("asks_capability") or understanding.get("kind") in {
        "price_question",
        "process_question",
        "capability_question",
    }:
        return "answering_question"
    if calendar_stage in {"event_created"}:
        return "appointment_scheduled"
    if calendar_stage == "slots_offered":
        return "offered_slots"
    if calendar_stage == "waiting_slot_choice":
        return "waiting_slot_choice"
    if calendar_stage in {"ready_to_check_availability", "availability_checked"}:
        return "ready_to_offer_slots"
    if service == "instalacao":
        return "qualifying_installation"
    if service == "manutencao":
        return "qualifying_maintenance"
    if service == "higienizacao":
        return "qualifying_hygienization"
    if service in {"pmoc", "consultoria", "projeto-central"}:
        return "qualifying_project"
    if service:
        return "identifying_service"
    return "new_lead"
