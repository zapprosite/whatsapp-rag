"""
Tipos do Refrimix Core V2 — contrato de tipos entre todos os módulos.
"""
from __future__ import annotations

from typing import Annotated, Literal, TypedDict


# ── Commercial Path ────────────────────────────────────────────────────────────
CommercialPath = Literal[
    "ask_basic_service",
    "fixed_installation_simple",
    "fixed_hygienization",
    "technical_visit_50",
    "project_quote",
]

# ── Actions do Catálogo ─────────────────────────────────────────────────────────
NextActionType = Literal[
    "welcome_onboarding",
    "answer_services_list",
    "answer_clarification",
    "ask_lead_name",
    "ask_basic_service",
    "offer_fixed_installation",
    "offer_technical_visit_installation",
    "offer_technical_visit_maintenance",
    "offer_fixed_hygienization",
    "offer_hygienization_schedule",
    "offer_project_visit",
    "save_preferred_window",
    "fallback_recover_context",
]

ResponseModality = Literal["text", "audio"]


# ── LeadState ─────────────────────────────────────────────────────────────────
class Identity(TypedDict, total=False):
    name: str | None
    phone: str | None


class ServiceInfo(TypedDict, total=False):
    type: str | None  # instalacao | manutencao | higienizacao
    city_bairro: str | None


class Installation(TypedDict, total=False):
    btus: int | None
    has_photos: bool
    ponto_eletrico_exclusivo: bool | None
    distancia_aproximada: float | None  # metros
    infra_pronta: bool | None


class Higienizacao(TypedDict, total=False):
    quantidade_aparelhos: int | None
    aparelho_funcionando: bool | None


class Maintenance(TypedDict, total=False):
    symptom: str | None
    risk_electric: bool


class Appointment(TypedDict, total=False):
    preferred_window: str | None  # "manha" | "tarde"
    status: str | None  # "pending" | "confirmed" | "scheduled"


class Commercial(TypedDict, total=False):
    path: CommercialPath | None
    fixed_price: int | None
    visit_price: int | None
    owner_alert: bool


class Memory(TypedDict, total=False):
    last_asked_field: str | None
    last_answered_field: str | None
    do_not_ask: list[str]
    last_response_hash: str | None


class LeadState(TypedDict, total=False):
    identity: Identity
    service: ServiceInfo
    installation: Installation
    higienizacao: Higienizacao
    maintenance: Maintenance
    appointment: Appointment
    commercial: Commercial
    memory: Memory


# ── Pipeline Input ─────────────────────────────────────────────────────────────
class PipelineInput(TypedDict, total=False):
    phone: str
    message_id: str
    message_type: str  # text | audioMessage | imageMessage
    text: str
    transcript: str | None
    media_url: str
    instance: str
    timestamp: str
    raw: dict


# ── Commercial Decision ────────────────────────────────────────────────────────
class CommercialDecision(TypedDict, total=False):
    path: CommercialPath
    can_schedule_now: bool
    fixed_price: int | None
    visit_price: int | None
    owner_alert: bool
    reason: str | None


# ── Next Action ────────────────────────────────────────────────────────────────
class SideEffect(TypedDict, total=False):
    type: Literal[
        "send_owner_alert",
        "send_agenda_group_alert",
        "tts_synthesize",
        "sync_lead_sheet",
    ]
    payload: dict


class NextAction(TypedDict, total=False):
    type: NextActionType
    needs_rag: bool
    missing_field: str | None
    service: str | None
    answer_kind: str | None
    window: str | None
    quantity: int | None
    side_effects: list[SideEffect]
    notes: list[str]


# ── Pipeline Output ───────────────────────────────────────────────────────────
class PipelineOutput(TypedDict, total=False):
    phone: str
    action: NextActionType
    response_text: str
    response_modality: ResponseModality
    side_effects: list[SideEffect]
    lead_state_patch: dict
    commercial_decision: CommercialDecision
    debug: dict