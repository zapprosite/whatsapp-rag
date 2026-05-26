from __future__ import annotations

import asyncio
from datetime import datetime

from langchain_core.messages import HumanMessage

from agent_graph.domain.onboarding import greeting_by_time
from agent_graph.nodes.nodes import _lead_state_copy
from agent_graph.nodes.plan_next_action import plan_next_action
from agent_graph.nodes.reduce_lead_state import reduce_lead_state


def run(coro):
    return asyncio.run(coro)


def test_greeting_by_time_morning():
    assert greeting_by_time(datetime.fromisoformat("2026-05-26T08:00:00-03:00")) == "Bom dia"


def test_first_message_bom_dia_triggers_welcome_onboarding():
    state = {
        "messages": [HumanMessage(content="bom dia")],
        "lead_state": _lead_state_copy(),
        "customer_data": {"is_first_message": True, "memory": {"is_conversation_started": False}},
        "conversation_summary": "",
        "missing_fields": [],
        "do_not_ask": [],
        "message_understanding": {"is_greeting": True, "is_generic": True},
    }

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "welcome_onboarding"


def test_conversation_in_progress_does_not_repeat_greeting():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    state = {
        "messages": [HumanMessage(content="bom dia")],
        "lead_state": lead_state,
        "customer_data": {"is_first_message": False, "memory": {"is_conversation_started": True, "has_persistent_lead": True, "postgres_event_count": 2}},
        "conversation_summary": "Lead já está em atendimento.",
        "missing_fields": [],
        "do_not_ask": [],
        "message_understanding": {"is_greeting": True, "is_generic": True},
    }

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] != "welcome_onboarding"


def test_phone_comes_from_customer_data():
    result = run(
        reduce_lead_state(
            {
                "messages": [HumanMessage(content="oi")],
                "lead_state": _lead_state_copy(),
                "customer_data": {"phone": "+5513999999999"},
                "message_understanding": {},
            }
        )
    )
    assert result["lead_state"]["lead_identity"]["phone"] == "+5513999999999"


def test_missing_name_asks_lead_name():
    state = {
        "messages": [HumanMessage(content="Quero instalar um ar")],
        "lead_state": _lead_state_copy(),
        "customer_data": {"is_first_message": True, "memory": {"is_conversation_started": False}},
        "conversation_summary": "",
        "missing_fields": [],
        "do_not_ask": [],
        "message_understanding": {},
    }

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "ask_lead_name"


def test_full_name_is_split_and_saved():
    result = run(
        reduce_lead_state(
            {
                "messages": [HumanMessage(content="William Rodrigues")],
                "lead_state": _lead_state_copy(),
                "customer_data": {"phone": "+5513999999999"},
                "message_understanding": {},
            }
        )
    )
    identity = result["lead_state"]["lead_identity"]
    assert identity["full_name"] == "William Rodrigues"
    assert identity["first_name"] == "William"
    assert identity["last_name"] == "Rodrigues"


def test_email_missing_does_not_block_service():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "manutencao"
    lead_state["lead_identity"]["phone"] = "+5513999999999"
    lead_state["lead_identity"]["full_name"] = "William"
    state = {
        "messages": [HumanMessage(content="meu ar não gela")],
        "lead_state": lead_state,
        "customer_data": {"is_first_message": False, "memory": {"is_conversation_started": True}},
        "conversation_summary": "Lead em andamento",
        "missing_fields": [],
        "do_not_ask": [],
        "message_understanding": {},
    }

    result = run(plan_next_action(state))
    assert result["next_action"]["type"] == "offer_technical_visit"

