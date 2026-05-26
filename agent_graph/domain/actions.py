from __future__ import annotations

from typing import Any, Literal, TypedDict

NextActionType = Literal[
    "welcome_onboarding",
    "ask_lead_name",
    "ask_basic_service",
    "ask_optional_contact_info",
    "offer_fixed_installation",
    "offer_fixed_hygienization",
    "offer_technical_visit",
    "offer_project_visit",
    "answer_question",
    "explain_process",
    "answer_capability_question",
    "ask_missing_field",
    "save_preferred_window",
    "offer_calendar_slots",
    "confirm_calendar_slot",
    "handoff_human",
    "reject_security",
    "active_service_followup",
    "fallback_recover_context",
    "explain_last_offer",
]


class SideEffect(TypedDict, total=False):
    type: Literal[
        "send_owner_alert",
        "send_agenda_group_alert",
        "google_calendar_freebusy",
        "google_calendar_insert",
        "tts_synthesize",
        "sync_lead_sheet",
    ]
    payload: dict[str, Any]


class NextAction(TypedDict, total=False):
    type: NextActionType
    needs_rag: bool
    missing_field: str | None
    service: str | None
    answer_kind: str | None
    slot_choice: int | None
    slot_label: str | None
    selected_slot: dict[str, Any] | None
    side_effects: list[SideEffect]
    notes: list[str]


def make_action(action_type: NextActionType, **kwargs: Any) -> NextAction:
    action: NextAction = {
        "type": action_type,
        "needs_rag": bool(kwargs.pop("needs_rag", False)),
        "side_effects": list(kwargs.pop("side_effects", [])),
        "notes": list(kwargs.pop("notes", [])),
    }
    action.update(kwargs)
    return action
