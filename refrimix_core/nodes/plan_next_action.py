"""
plan_next_action — decide próxima ação baseado no estado.
"""
from __future__ import annotations

from refrimix_core.domain.types import NextActionType, NextAction


def plan_next_action(
    lead_state: dict,
    commercial_decision: dict,
    message_understanding: dict,
) -> dict:
    """
    Decide a próxima ação do catálogo determinístico.
    """
    kind = message_understanding.get("kind", "unknown")
    understanding_window = message_understanding.get("window")
    quantity = message_understanding.get("quantity")
    last_asked_field = lead_state.get("memory", {}).get("last_asked_field")
    current_service = lead_state.get("service", {}).get("type")
    path = commercial_decision.get("path")
    owner_alert = commercial_decision.get("owner_alert", False)

    # ── Greeting sem contexto → welcome ──────────────────────────────────
    if kind == "greeting" and not current_service:
        return _make("welcome_onboarding")

    # ── Maintenance signal → manutencao ───────────────────────────────────
    if kind == "maintenance_signal":
        return _make("offer_technical_visit_maintenance")

    # ── Services question → answer_services_list ─────────────────────────
    if kind == "services_question":
        return _make("answer_services_list")

    # ── Clarification request → answer_clarification ─────────────────────
    if kind == "clarification_request":
        return _make("answer_clarification")

    # ── Greeting com contexto → continuação ─────────────────────────────
    if kind == "greeting" and current_service:
        return _make("ask_basic_service")

    # ── Audio transcription failed ────────────────────────────────────────
    if kind == "audio_transcription_failed":
        return _make("welcome_onboarding", notes=["audio_failed_fallback"])

    # ── Quantity response após pergunta de quantidade ────────────────────
    if kind == "quantity_response" and quantity is not None:
        return _make("offer_hygienization_schedule", quantity=quantity)

    # ── Window preference ─────────────────────────────────────────────────
    if understanding_window and last_asked_field == "preferred_window":
        return _make("save_preferred_window", window=understanding_window)

    # ── Short answer ─────────────────────────────────────────────────────
    if kind == "short_answer":
        if current_service == "instalacao":
            return _make("offer_fixed_installation")
        if current_service == "manutencao":
            return _make("offer_technical_visit_maintenance")
        if current_service == "higienizacao":
            return _make("offer_fixed_hygienization")

    # ── Commercial path → deterministic action ────────────────────────────
    if path == "fixed_installation_simple":
        return _make("offer_fixed_installation")

    if path == "fixed_hygienization":
        qtd = lead_state.get("higienizacao", {}).get("quantidade_aparelhos")
        if qtd is not None:
            return _make("offer_hygienization_schedule", quantity=qtd)
        return _make("offer_fixed_hygienization")

    if path == "technical_visit_50":
        if current_service == "instalacao":
            return _make("offer_technical_visit_installation")
        return _make("offer_technical_visit_maintenance")

    if path == "project_quote":
        return _make_project_visit(owner_alert)

    if path == "ask_basic_service":
        return _make("ask_basic_service")

    # ── Fallback ──────────────────────────────────────────────────────────
    return _make("fallback_recover_context")


def _make(action_type: NextActionType, **kwargs) -> dict:
    return {
        "type": action_type,
        "needs_rag": False,
        "missing_field": None,
        "service": kwargs.pop("service", None),
        "answer_kind": None,
        "window": kwargs.pop("window", None),
        "quantity": kwargs.pop("quantity", None),
        "side_effects": kwargs.pop("side_effects", []),
        "notes": kwargs.pop("notes", []),
        **kwargs,
    }


def _make_project_visit(owner_alert: bool) -> dict:
    if owner_alert:
        return _make(
            "offer_project_visit",
            side_effects=[
                {
                    "type": "send_owner_alert",
                    "payload": {"reason": "high_value_lead"},
                }
            ],
        )
    return _make("offer_project_visit")