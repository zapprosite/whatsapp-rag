from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from agent_graph.nodes.compose_response import compose_response
from agent_graph.nodes.nodes import _lead_state_copy


def run(coro):
    return asyncio.run(coro)


def last_ai(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return str(message.content)
    return ""


def test_compose_explain_process_installation():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    result = run(
        compose_response(
            {
                "messages": [HumanMessage(content="Como funciona?")],
                "lead_state": lead_state,
                "missing_fields": ["foto_local_externo"],
                "do_not_ask": [],
                "next_action": {"type": "explain_process", "service": "instalacao"},
            }
        )
    )
    response = last_ai(result["messages"])
    assert "Funciona assim" in response
    assert "condensadora" in response


def test_compose_save_preferred_window_and_missing_field():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["appointment"]["preferred_window"] = "tarde"
    result = run(
        compose_response(
            {
                "messages": [HumanMessage(content="Tarde")],
                "lead_state": lead_state,
                "message_understanding": {"window": "tarde"},
                "next_action": {"type": "save_preferred_window", "missing_field": "foto_local_externo"},
            }
        )
    )
    response = last_ai(result["messages"])
    assert "preferência pela tarde anotada" in response
    assert "local externo" in response


def test_compose_offer_calendar_slots():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    result = run(
        compose_response(
            {
                "messages": [HumanMessage(content="Horário")],
                "lead_state": lead_state,
                "calendar_slots": [
                    {"label": "Amanhã 14:00"},
                    {"label": "Amanhã 16:00"},
                    {"label": "Sexta 09:00"},
                ],
                "next_action": {"type": "offer_calendar_slots"},
            }
        )
    )
    response = last_ai(result["messages"])
    assert "1. Amanhã 14:00" in response
    assert "2. Amanhã 16:00" in response
    assert "3. Sexta 09:00" in response


def test_compose_confirm_calendar_slot():
    result = run(
        compose_response(
            {
                "messages": [HumanMessage(content="2")],
                "lead_state": _lead_state_copy(),
                "next_action": {"type": "confirm_calendar_slot", "slot_label": "Amanhã 16:00"},
            }
        )
    )
    assert "Amanhã 16:00" in last_ai(result["messages"])
