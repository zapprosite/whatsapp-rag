from __future__ import annotations

from copy import deepcopy
from typing import Any

from agent_graph.domain.commercial_router import decide_commercial_path
from agent_graph.domain.actions import NextAction, make_action
from agent_graph.domain.field_policy import needs_name
from agent_graph.domain.onboarding import has_objective_request, should_send_welcome
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


def _has_persistent_history(state: dict[str, Any], lead_state: dict[str, Any]) -> bool:
    customer_data = state.get("customer_data") or {}
    memory = customer_data.get("memory") or {}
    return any(
        [
            bool(memory.get("has_persistent_lead")),
            int(memory.get("postgres_event_count") or 0) > 0,
            bool(state.get("conversation_summary")),
            bool((lead_state.get("lead_identity") or {}).get("full_name")),
            bool(lead_state.get("tipo_servico")),
        ]
    )


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
    identity = lead_state.get("lead_identity") or {}
    first_message = bool(customer_data.get("is_first_message"))
    persistent_history = _has_persistent_history(state, lead_state)
    missing_name = needs_name(lead_state)
    onboarding_welcome = should_send_welcome(
        is_first_message=first_message,
        has_persistent_history=persistent_history,
        lead_state=lead_state,
        user_text=user_text,
    )
    can_schedule_now = bool(commercial_decision.can_schedule_now)
    action: NextAction

    import os
    if str(os.getenv("MINIMAL_MVP_ENABLED", "0")).strip() == "1":
        if understanding.get("malicious"):
            action = make_action("reject_security")
        elif state.get("handoff_mode") == "hard_transfer" or state.get("intent") in {"explicit_handoff", "sensitive_complaint"}:
            action = make_action("handoff_human")
        elif understanding.get("is_greeting") and not understanding.get("service_mentioned") and not persistent_history:
            action = make_action("welcome_onboarding", service=None)
        elif understanding.get("kind") == "services_list_question":
            action = make_action("answer_services_list")
        elif understanding.get("kind") == "clarification_request" or understanding.get("asks_clarification"):
            action = make_action("answer_clarification_llm")
        elif missing_name:
            action = make_action("ask_lead_name", service=service)
        elif not service:
            action = make_action("ask_basic_service")
        elif commercial_decision.path == "fixed_installation_simple" and understanding.get("kind") not in {"window_preference", "calendar_request"}:
            action = make_action("offer_fixed_installation", service=service)
        elif service in {"manutencao", "conserto"} or commercial_decision.path == "technical_visit_50":
            action = make_action("offer_technical_visit", service=service)
        elif service == "higienizacao" and commercial_decision.path == "fixed_hygienization":
            qty = lead_state.get("higienizacao", {}).get("quantidade_aparelhos")
            if qty is None:
                action = make_action("offer_fixed_hygienization", service=service, asks_field="quantidade_aparelhos")
            else:
                action = make_action("offer_hygienization_schedule", service=service, asks_field="preferred_window")
        elif commercial_decision.path == "project_quote":
            action = make_action("offer_project_visit", service=service)
        elif understanding.get("kind") == "window_preference":
            action = make_action("save_preferred_window", service=service, missing_field=next_missing)
        else:
            action = make_action("fallback_recover_context")

        lead_state["calendar_stage"] = compute_calendar_stage(lead_state)
        lead_state["conversation_stage"] = conversation_stage
        lead_state["commercial_decision"] = commercial_decision.to_dict()
        return {
            "lead_state": lead_state,
            "commercial_decision": commercial_decision.to_dict(),
            "next_action": action,
            "calendar_stage": lead_state.get("calendar_stage"),
            "conversation_stage": lead_state.get("conversation_stage"),
            "calendar_slots": (lead_state.get("appointment") or {}).get("offered_slots") or [],
        }

    if understanding.get("malicious"):
        action = make_action("reject_security")
    elif customer_data.get("active_service"):
        action = make_action("active_service_followup")
    elif state.get("handoff_mode") == "hard_transfer" or state.get("intent") in {"explicit_handoff", "sensitive_complaint"}:
        action = make_action(
            "handoff_human",
            side_effects=[{"type": "send_owner_alert", "payload": {"reason": state.get("handoff_reason") or state.get("intent")}}],
        )
    elif understanding.get("is_greeting") and not understanding.get("service_mentioned") and not (customer_data.get("memory") or {}).get("is_conversation_started"):
        action = make_action("welcome_onboarding", service=None)
    elif understanding.get("kind") == "services_list_question":
        action = make_action("answer_services_list")
    elif understanding.get("kind") == "clarification_request" or understanding.get("asks_clarification"):
        action = make_action("answer_clarification_llm")
    elif understanding.get("asks_process"):
        action = make_action("explain_process", service=service)
    elif understanding.get("kind") == "capability_question":
        action = make_action("answer_capability_question", service=service)
    elif onboarding_welcome and not has_objective_request(user_text):
        action = make_action("welcome_onboarding", service=service)
    elif first_message and missing_name and (service or has_objective_request(user_text)):
        action = make_action(
            "ask_lead_name",
            service=service,
            notes=["include_greeting"] if onboarding_welcome else [],
        )
    elif slot_choice is not None and _slots_offered(lead_state):
        offered_slots = appointment.get("offered_slots") or []
        selected_slot = offered_slots[slot_choice - 1] if 0 < slot_choice <= len(offered_slots) else None
        if selected_slot:
            appointment["selected_slot"] = selected_slot
            appointment["slot_start"] = selected_slot.get("start")
            appointment["slot_end"] = selected_slot.get("end")
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
    elif state.get("intent") == "unknown":
        action = make_action("fallback_recover_context", needs_rag=True)
    elif understanding.get("kind") in {"process_question", "answer_question"} and not service and not understanding.get("service_mentioned"):
        action = make_action("answer_open_question_llm")
    elif not service:
        action = make_action("ask_basic_service")
    elif commercial_decision.path == "fixed_installation_simple" and understanding.get("kind") not in {"window_preference", "calendar_request"}:
        action = make_action(
            "offer_fixed_installation",
            service=service,
            side_effects=[{"type": "sync_lead_sheet", "payload": {}}],
        )
    elif commercial_decision.path == "fixed_hygienization" and understanding.get("kind") not in {"window_preference", "calendar_request"}:
        qty = lead_state.get("higienizacao", {}).get("quantidade_aparelhos")
        if qty is None:
            action = make_action(
                "offer_fixed_hygienization",
                service=service,
                asks_field="quantidade_aparelhos",
                side_effects=[{"type": "sync_lead_sheet", "payload": {}}],
            )
        else:
            action = make_action(
                "offer_hygienization_schedule",
                service=service,
                asks_field="preferred_window",
                side_effects=[{"type": "sync_lead_sheet", "payload": {}}],
            )
    elif commercial_decision.path == "technical_visit_50" and understanding.get("kind") not in {"window_preference", "calendar_request"}:
        action = make_action(
            "offer_technical_visit",
            service=service,
            side_effects=[{"type": "sync_lead_sheet", "payload": {}}],
        )
    elif commercial_decision.path == "project_quote" and understanding.get("kind") not in {"window_preference", "calendar_request"}:
        effects = [{"type": "sync_lead_sheet", "payload": {}}]
        if commercial_decision.owner_alert:
            effects.append({"type": "send_owner_alert", "payload": {"reason": commercial_decision.reason or commercial_decision.path}})
        action = make_action("offer_project_visit", service=service, side_effects=effects)
    elif understanding.get("kind") == "window_preference":
        if calendar_ready and can_schedule_now:
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
        if can_schedule_now and calendar_ready:
            slots = await suggest_slots(appointment.get("preferred_window"), lead_state)
            appointment["offered_slots"] = slots
            action = make_action(
                "offer_calendar_slots",
                service=service,
                side_effects=[{"type": "google_calendar_freebusy", "payload": {"period": appointment.get("preferred_window")}}],
            )
        else:
            action = make_action("offer_technical_visit" if commercial_decision.path == "technical_visit_50" else "save_preferred_window", service=service, missing_field=next_missing)
    elif understanding.get("short_answer") and state.get("short_answer_applied"):
        if can_schedule_now and calendar_ready:
            slots = await suggest_slots(appointment.get("preferred_window"), lead_state)
            appointment["offered_slots"] = slots
            action = make_action(
                "offer_calendar_slots",
                service=service,
                side_effects=[{"type": "google_calendar_freebusy", "payload": {"period": appointment.get("preferred_window")}}],
            )
        else:
            action = make_action("fallback_recover_context", service=service)
    elif understanding.get("asks_price"):
        if commercial_decision.path == "fixed_installation_simple":
            action = make_action("offer_fixed_installation", service=service)
        elif commercial_decision.path == "fixed_hygienization":
            action = make_action("offer_fixed_hygienization", service=service)
        elif commercial_decision.path == "project_quote":
            action = make_action("offer_project_visit", service=service)
        else:
            action = make_action("offer_technical_visit", service=service)
    elif understanding.get("unavailable_photo") or understanding.get("unavailable_infra") or understanding.get("asks_time_specific"):
        if can_schedule_now and calendar_ready and understanding.get("asks_time_specific"):
            slots = await suggest_slots(appointment.get("preferred_window"), lead_state)
            appointment["offered_slots"] = slots
            action = make_action(
                "offer_calendar_slots",
                service=service,
                side_effects=[{"type": "google_calendar_freebusy", "payload": {"period": appointment.get("preferred_window")}}],
            )
        else:
            if commercial_decision.path == "project_quote":
                action = make_action("offer_project_visit", service=service)
            elif commercial_decision.path == "fixed_hygienization":
                action = make_action("offer_fixed_hygienization", service=service)
            elif commercial_decision.path == "fixed_installation_simple":
                action = make_action("offer_fixed_installation", service=service)
            else:
                action = make_action("offer_technical_visit", service=service)
    elif missing_name and (understanding.get("asks_calendar") or can_schedule_now or first_message):
        action = make_action("ask_lead_name", service=service)
    elif next_missing and not can_schedule_now:
        action = make_action("ask_missing_field", service=service, missing_field=next_missing)
    elif understanding.get("kind") in {"answer_question", "price_question"}:
        action = make_action("answer_question", service=service, needs_rag=True)
    else:
        action = make_action("fallback_recover_context")

    lead_state["calendar_stage"] = compute_calendar_stage(lead_state)
    lead_state["conversation_stage"] = conversation_stage
    lead_state["commercial_decision"] = commercial_decision.to_dict()
    return {
        "lead_state": lead_state,
        "commercial_decision": commercial_decision.to_dict(),
        "next_action": action,
        "calendar_stage": lead_state.get("calendar_stage"),
        "conversation_stage": lead_state.get("conversation_stage"),
        "calendar_slots": (lead_state.get("appointment") or {}).get("offered_slots") or [],
    }
