from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage

from agent_graph.nodes.understand_message import understand_message


def run(coro):
    return asyncio.run(coro)


def test_understand_process_question():
    result = run(understand_message({"messages": [HumanMessage(content="Como funciona?")]}))
    understanding = result["message_understanding"]

    assert understanding["kind"] == "process_question"
    assert understanding["asks_process"] is True


def test_understand_capability_side_question():
    result = run(
        understand_message(
            {
                "messages": [HumanMessage(content="Vocês também trabalham com higienização?")],
                "lead_state": {"tipo_servico": "instalacao"},
                "service": "instalacao",
            }
        )
    )
    understanding = result["message_understanding"]

    assert understanding["kind"] == "capability_question"
    assert understanding["service_mentioned"] == "higienizacao"
    assert understanding["is_side_question"] is True


def test_understand_short_answer_window_and_calendar():
    yes = run(understand_message({"messages": [HumanMessage(content="Sim")]}))["message_understanding"]
    window = run(understand_message({"messages": [HumanMessage(content="Tarde")]}))["message_understanding"]
    calendar = run(understand_message({"messages": [HumanMessage(content="Não consegue me dizer um horário?")]}))["message_understanding"]
    price = run(understand_message({"messages": [HumanMessage(content="Quanto fica?")]}))["message_understanding"]

    assert yes["kind"] == "short_answer"
    assert yes["short_answer"] == "yes"
    assert window["kind"] == "window_preference"
    assert window["window"] == "tarde"
    assert calendar["kind"] == "calendar_request"
    assert price["kind"] == "price_question"
