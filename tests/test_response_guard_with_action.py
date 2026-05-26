from __future__ import annotations

from agent_graph.guards.response_guard import validate_response_before_send


def test_response_guard_blocks_window_confirmation_for_process_action():
    ok, violations = validate_response_before_send(
        "Perfeito, deixei o período da tarde registrado.",
        {
            "next_action": {"type": "explain_process"},
            "lead_state": {"tipo_servico": "instalacao"},
        },
    )

    assert ok is False
    assert "action_process_contains_window_confirmation" in violations


def test_response_guard_accepts_numbered_slots_for_offer_action():
    ok, violations = validate_response_before_send(
        "Tenho estas opções disponíveis:\n\n1. Amanhã 14:00\n2. Amanhã 16:00\n3. Sexta 09:00\n\nQual opção fica melhor?",
        {
            "next_action": {"type": "offer_calendar_slots"},
            "lead_state": {"tipo_servico": "instalacao", "appointment": {"offered_slots": [{"label": "A"}, {"label": "B"}, {"label": "C"}]}},
            "calendar_slots": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
        },
    )

    assert ok is True
    assert violations == []
