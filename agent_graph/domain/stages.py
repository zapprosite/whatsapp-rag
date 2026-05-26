from __future__ import annotations

from typing import Literal

ConversationStage = Literal[
    "new_lead",
    "identifying_service",
    "qualifying_installation",
    "qualifying_maintenance",
    "qualifying_hygienization",
    "qualifying_project",
    "answering_question",
    "ready_to_offer_slots",
    "offered_slots",
    "waiting_slot_choice",
    "appointment_scheduled",
    "active_service_followup",
    "post_sale",
    "human_handoff",
    "blocked_security",
]

CalendarStage = Literal[
    "not_ready",
    "ready_to_check_availability",
    "availability_checked",
    "slots_offered",
    "waiting_slot_choice",
    "event_created",
    "event_failed",
]
