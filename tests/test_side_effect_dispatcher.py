from __future__ import annotations

import asyncio
import importlib

from agent_graph.nodes.dispatch_side_effects import dispatch_side_effects

dispatcher_module = importlib.import_module("agent_graph.nodes.dispatch_side_effects")


def run(coro):
    return asyncio.run(coro)


def test_side_effect_dispatcher_does_not_alert_owner_for_plain_lead(monkeypatch):
    owner_calls: list[dict] = []

    async def fake_owner_alert(payload):
        owner_calls.append(payload)
        return True

    async def fake_redis_get(key):
        del key
        return None

    async def fake_redis_set(key, value, ex=None):
        del key, value, ex
        return None

    monkeypatch.setattr(dispatcher_module, "send_owner_alert", fake_owner_alert)
    monkeypatch.setattr(dispatcher_module, "redis_get", fake_redis_get)
    monkeypatch.setattr(dispatcher_module, "redis_set", fake_redis_set)

    result = run(
        dispatch_side_effects(
            {
                "next_action": {"type": "ask_missing_field", "side_effects": []},
                "customer_data": {"phone": "+5513000000001"},
                "lead_state": {"tipo_servico": "instalacao"},
                "messages": [],
            }
        )
    )

    assert result["executed_side_effects"] == []
    assert owner_calls == []


def test_side_effect_dispatcher_inserts_event_only_when_enabled(monkeypatch):
    insert_calls: list[dict] = []

    async def fake_create_event(lead_state, selected_slot):
        insert_calls.append({"lead_state": lead_state, "selected_slot": selected_slot})
        return {"id": "evt_123"}

    async def fake_redis_get(key):
        del key
        return None

    async def fake_redis_set(key, value, ex=None):
        del key, value, ex
        return None

    monkeypatch.setenv("GOOGLE_CALENDAR_CREATE_EVENTS", "1")
    monkeypatch.setattr(dispatcher_module, "create_service_event", fake_create_event)
    monkeypatch.setattr(dispatcher_module, "redis_get", fake_redis_get)
    monkeypatch.setattr(dispatcher_module, "redis_set", fake_redis_set)

    state = {
        "next_action": {
            "type": "confirm_calendar_slot",
            "selected_slot": {"label": "Amanhã 16:00", "start": "2026-05-27T16:00:00-03:00", "end": "2026-05-27T18:00:00-03:00"},
            "side_effects": [{"type": "google_calendar_insert", "payload": {"slot_choice": 2}}],
        },
        "customer_data": {"phone": "+5513000000001"},
        "lead_state": {"tipo_servico": "instalacao", "appointment": {}},
        "messages": [],
    }
    result = run(dispatch_side_effects(state))

    assert insert_calls
    assert result["lead_state"]["appointment"]["event_status"] == "created"


def test_side_effect_dispatcher_sends_agenda_group_when_event_creation_disabled(monkeypatch):
    agenda_calls: list[str] = []

    async def fake_agenda_message(text):
        agenda_calls.append(text)
        return True

    async def fake_redis_get(key):
        del key
        return None

    async def fake_redis_set(key, value, ex=None):
        del key, value, ex
        return None

    monkeypatch.setenv("GOOGLE_CALENDAR_CREATE_EVENTS", "0")
    monkeypatch.setattr(dispatcher_module, "send_agenda_group_message", fake_agenda_message)
    monkeypatch.setattr(dispatcher_module, "redis_get", fake_redis_get)
    monkeypatch.setattr(dispatcher_module, "redis_set", fake_redis_set)

    state = {
        "next_action": {
            "type": "confirm_calendar_slot",
            "selected_slot": {"label": "Amanhã 16:00", "start": "2026-05-27T16:00:00-03:00", "end": "2026-05-27T18:00:00-03:00"},
            "side_effects": [{"type": "google_calendar_insert", "payload": {"slot_choice": 2}}],
        },
        "customer_data": {"phone": "+5513000000001"},
        "lead_state": {"tipo_servico": "instalacao", "cidade_bairro": "Santos", "appointment": {}},
        "messages": [],
    }
    result = run(dispatch_side_effects(state))

    assert agenda_calls
    assert "Agenda Refrimix" in agenda_calls[0]
    assert result["lead_state"]["appointment"]["event_status"] == "pending_manual_confirmation"
