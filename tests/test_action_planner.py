from __future__ import annotations

import asyncio
import importlib

from agent_graph.nodes.nodes import _lead_state_copy
from agent_graph.nodes.plan_next_action import plan_next_action

planner_module = importlib.import_module("agent_graph.nodes.plan_next_action")


def run(coro):
    return asyncio.run(coro)


def _base_state() -> dict:
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    return {
        "lead_state": lead_state,
        "customer_data": {},
        "missing_fields": ["cidade_bairro", "foto_local_interno", "foto_local_externo", "btus"],
        "do_not_ask": [],
        "message_understanding": {},
    }


def test_process_question_wins_over_preferred_window(monkeypatch):
    state = _base_state()
    state["message_understanding"] = {"kind": "process_question", "asks_process": True}
    state["lead_state"]["appointment"]["preferred_window"] = "tarde"

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "explain_process"


def test_capability_question_returns_capability_action():
    state = _base_state()
    state["message_understanding"] = {
        "kind": "capability_question",
        "asks_capability": True,
        "service_mentioned": "higienizacao",
    }

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "answer_capability_question"


def test_calendar_request_with_missing_requirements_asks_missing_field():
    state = _base_state()
    state["message_understanding"] = {"kind": "calendar_request", "asks_calendar": True}

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "ask_missing_field"


def test_calendar_request_with_requirements_offers_slots(monkeypatch):
    async def fake_slots(period, lead_state, days=7, max_slots=3):
        del period, lead_state, days, max_slots
        return [{"label": "Amanhã 14:00"}, {"label": "Amanhã 16:00"}, {"label": "Sexta 09:00"}]

    monkeypatch.setattr(planner_module, "suggest_slots", fake_slots)

    state = _base_state()
    state["lead_state"].update(
        {
            "cidade_bairro": "Guarujá",
            "btus": "12000",
            "fotos": {"local_interno": True, "local_externo": True},
        }
    )
    state["missing_fields"] = []
    state["do_not_ask"] = ["cidade_bairro", "btus", "foto_local_interno", "foto_local_externo"]
    state["message_understanding"] = {"kind": "calendar_request", "asks_calendar": True}

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "offer_calendar_slots"
    assert len(result["calendar_slots"]) == 3


def test_window_preference_incomplete_saves_window_without_confirming(monkeypatch):
    state = _base_state()
    state["message_understanding"] = {"kind": "window_preference", "window": "tarde"}

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "save_preferred_window"
    assert result["lead_state"]["appointment"]["preferred_window"] is None


def test_window_preference_complete_offers_slots_not_confirmation(monkeypatch):
    async def fake_slots(period, lead_state, days=7, max_slots=3):
        del period, lead_state, days, max_slots
        return [{"label": "Amanhã 14:00"}, {"label": "Amanhã 16:00"}, {"label": "Sexta 09:00"}]

    monkeypatch.setattr(planner_module, "suggest_slots", fake_slots)

    state = _base_state()
    state["lead_state"].update(
        {
            "cidade_bairro": "Guarujá",
            "btus": "12000",
            "fotos": {"local_interno": True, "local_externo": True},
            "appointment": {"preferred_window": "tarde", "confirmed_window": False},
        }
    )
    state["missing_fields"] = []
    state["do_not_ask"] = ["cidade_bairro", "btus", "foto_local_interno", "foto_local_externo"]
    state["message_understanding"] = {"kind": "window_preference", "window": "tarde"}

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "offer_calendar_slots"


def test_slot_choice_confirms_selected_slot():
    state = _base_state()
    state["lead_state"]["appointment"]["offered_slots"] = [
        {"label": "Amanhã 14:00"},
        {"label": "Amanhã 16:00"},
        {"label": "Sexta 09:00"},
    ]
    state["message_understanding"] = {"kind": "slot_choice", "slot_choice": 2}

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "confirm_calendar_slot"
    assert result["next_action"]["slot_label"] == "Amanhã 16:00"
