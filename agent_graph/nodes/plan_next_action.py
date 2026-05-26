from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent_graph.domain.commercial_router import decide_commercial_path
from agent_graph.domain.actions import NextAction, make_action
from agent_graph.domain.stage_engine import (
    compute_calendar_stage,
    compute_conversation_stage,
    has_requirements_for_calendar,
)
from agent_graph.nodes.nodes import (
    _message_text,
    _important_missing_field_for_service,
    _normalize_service,
)
from agent_graph.services.calendar import suggest_slots


def _slots_offered(lead_state: dict[str, Any]) -> bool:
    return bool((lead_state.get("appointment") or {}).get("offered_slots"))


def _latest_user_text(state: dict[str, Any]) -> str:
    messages = state.get("messages") or []
    if not messages:
        return ""
    return _message_text(messages[-1])


async def plan_next_action(state: dict[str, Any]) -> dict[str, Any]:
    understanding = state.get("message_understanding") or {}
    customer_data = state.get("customer_data") or {}
    lead_state = deepcopy(state.get("lead_state") or {})
    service = _normalize_service(lead_state.get("tipo_servico") or state.get("service"))
    missing_fields = list(state.get("missing_fields") or [])
    do_not_ask = list(state.get("do_not_ask") or [])
    appointment = lead_state.setdefault("appointment", {})
    user_text = _latest_user_text(state)
    commercial_decision = decide_commercial_path({**lead_state, "tipo_servico": service}, user_text)
    calendar_ready = has_requirements_for_calendar(lead_state, service) and bool(commercial_decision.can_schedule_now)
    calendar_stage = compute_calendar_stage(lead_state)
    conversation_stage = compute_conversation_stage(lead_state, understanding, customer_data)
    next_missing = _important_missing_field_for_service(service, missing_fields, do_not_ask, lead_state)
    slot_choice = understanding.get("slot_choice")
    action: NextAction

    if understanding.get("malicious"):
        action = make_action("reject_security")
    elif customer_data.get("active_service"):
        action = make_action("active_service_followup")
    elif state.get("handoff_mode") == "hard_transfer" or state.get("intent") in {"explicit_handoff", "sensitive_complaint"}:
        action = make_action(
            "handoff_human",
            side_effects=[{"type": "send_owner_alert", "payload": {"reason": state.get("handoff_reason") or state.get("intent")}}],
        )
    elif understanding.get("asks_process"):
        action = make_action("explain_process", service=service)
    elif understanding.get("kind") == "capability_question":
        action = make_action("answer_capability_question", service=service)
    elif commercial_decision.owner_alert:
        action = make_action(
            "answer_question",
            service=service,
            answer_kind="commercial",
            side_effects=[{"type": "send_owner_alert", "payload": {"reason": commercial_decision.reason or commercial_decision.path}}],
        )
    elif slot_choice is not None and _slots_offered(lead_state):
        offered_slots = appointment.get("offered_slots") or []
        selected_slot = offered_slots[slot_choice - 1] if 0 < slot_choice <= len(offered_slots) else None
        if selected_slot:
            appointment["selected_slot"] = selected_slot
            action = make_action(
                "confirm_calendar_slot",
                service=service,
                slot_choice=slot_choice,
                slot_label=selected_slot.get("label"),
                selected_slot=selected_slot,
                side_effects=[{"type": "google_calendar_insert", "payload": {"slot_choice": slot_choice}}],
            )
        else:
            action = make_action("fallback_recover_context", notes=["slot_choice_out_of_range"])
    elif understanding.get("kind") == "window_preference":
        if calendar_ready:
            slots = await suggest_slots(understanding.get("window"), lead_state)
            appointment["offered_slots"] = slots
            action = make_action(
                "offer_calendar_slots",
                service=service,
                side_effects=[{"type": "google_calendar_freebusy", "payload": {"period": understanding.get("window")}}],
            )
        else:
            action = make_action("save_preferred_window", service=service, missing_field=next_missing)
    elif understanding.get("kind") == "calendar_request":
        if calendar_ready:
            slots = await suggest_slots(appointment.get("preferred_window"), lead_state)
            appointment["offered_slots"] = slots
            action = make_action(
                "offer_calendar_slots",
                service=service,
                side_effects=[{"type": "google_calendar_freebusy", "payload": {"period": appointment.get("preferred_window")}}],
            )
        else:
            action = make_action("ask_missing_field", service=service, missing_field=next_missing)
    elif understanding.get("short_answer") and state.get("short_answer_applied"):
        if calendar_ready:
            slots = await suggest_slots(appointment.get("preferred_window"), lead_state)
            appointment["offered_slots"] = slots
            action = make_action(
                "offer_calendar_slots",
                service=service,
                side_effects=[{"type": "google_calendar_freebusy", "payload": {"period": appointment.get("preferred_window")}}],
            )
        else:
            action = make_action("ask_missing_field", service=service, missing_field=next_missing)
    elif understanding.get("asks_price"):
        action = make_action("answer_question", service=service, answer_kind="price", needs_rag=False)
    elif understanding.get("unavailable_photo") or understanding.get("unavailable_infra") or understanding.get("asks_time_specific"):
        if calendar_ready and understanding.get("asks_time_specific"):
            slots = await suggest_slots(appointment.get("preferred_window"), lead_state)
            appointment["offered_slots"] = slots
            action = make_action(
                "offer_calendar_slots",
                service=service,
                side_effects=[{"type": "google_calendar_freebusy", "payload": {"period": appointment.get("preferred_window")}}],
            )
        else:
            action = make_action("answer_question", service=service, answer_kind="commercial", needs_rag=False)
    elif state.get("intent") == "unknown":
        action = make_action("fallback_recover_context", needs_rag=True)
    elif next_missing:
        action = make_action("ask_missing_field", service=service, missing_field=next_missing)
    elif understanding.get("kind") in {"answer_question", "price_question"}:
        action = make_action("answer_question", service=service, needs_rag=True)
    else:
        action = make_action("fallback_recover_context")

    lead_state["calendar_stage"] = compute_calendar_stage(lead_state)
    lead_state["conversation_stage"] = conversation_stage
    return {
        "lead_state": lead_state,
        "commercial_decision": commercial_decision.to_dict(),
        "next_action": action,
        "calendar_stage": lead_state.get("calendar_stage"),
        "conversation_stage": lead_state.get("conversation_stage"),
        "calendar_slots": (lead_state.get("appointment") or {}).get("offered_slots") or [],
    }
