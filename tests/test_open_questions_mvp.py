from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage
from agent_graph.nodes.understand_message import understand_message
from agent_graph.nodes.plan_next_action import plan_next_action
from agent_graph.nodes.compose_response import compose_response
from agent_graph.guards.response_guard import validate_response_before_send


@pytest.mark.anyio
async def test_understand_message_open_intents():
    # 1. "Quais serviços oferecem?" -> services_list_question
    state1 = {
        "messages": [HumanMessage(content="Quais serviços oferecem?")],
        "lead_state": {}
    }
    res1 = await understand_message(state1)
    und1 = res1["message_understanding"]
    assert und1["kind"] == "services_list_question"

    # 2. "Não entendi" -> clarification_request
    state2 = {
        "messages": [HumanMessage(content="Não entendi")],
        "lead_state": {}
    }
    res2 = await understand_message(state2)
    und2 = res2["message_understanding"]
    assert und2["kind"] == "clarification_request"

    # 3. "o que vocês fazem?" -> services_list_question
    state3 = {
        "messages": [HumanMessage(content="o que vocês fazem?")],
        "lead_state": {}
    }
    res3 = await understand_message(state3)
    und3 = res3["message_understanding"]
    assert und3["kind"] == "services_list_question"


@pytest.mark.anyio
async def test_plan_next_action_open_routing():
    # 1. services_list_question
    state1 = {
        "messages": [],
        "message_understanding": {
            "kind": "services_list_question"
        },
        "lead_state": {}
    }
    res1 = await plan_next_action(state1)
    assert res1["next_action"]["type"] == "answer_services_list"

    # 2. clarification_request
    state2 = {
        "messages": [],
        "message_understanding": {
            "kind": "clarification_request"
        },
        "lead_state": {}
    }
    res2 = await plan_next_action(state2)
    assert res2["next_action"]["type"] == "answer_clarification_llm"

    # 3. process_question sem serviço ativo -> answer_open_question_llm (não ask_basic_service!)
    state3 = {
        "messages": [],
        "message_understanding": {
            "kind": "process_question"
        },
        "lead_state": {}
    }
    res3 = await plan_next_action(state3)
    assert res3["next_action"]["type"] == "answer_open_question_llm"


@pytest.mark.anyio
async def test_compose_response_open_catalog():
    # 1. answer_services_list
    state1 = {
        "messages": [],
        "lead_state": {},
        "next_action": {
            "type": "answer_services_list"
        }
    }
    res1 = await compose_response(state1)
    response_text1 = res1["messages"][-1].content
    assert "Trabalhamos com instalação, manutenção, higienização" in response_text1
    assert "VRF/VRV" in response_text1
    assert "Instalação simples" in response_text1

    # 2. answer_clarification_llm
    state2 = {
        "messages": [],
        "lead_state": {},
        "next_action": {
            "type": "answer_clarification_llm"
        }
    }
    res2 = await compose_response(state2)
    response_text2 = res2["messages"][-1].content
    assert "Claro, vou explicar de forma simples." in response_text2
    assert "R$850" in response_text2
    assert "R$50" in response_text2
    assert "R$200" in response_text2


@pytest.mark.anyio
async def test_compose_response_open_llm_fallback(monkeypatch):
    # Mock llm_chat to avoid live API calls in test
    async def fake_llm_chat(messages, max_retries=2, fast_route=False):
        return "Olá! Sou o Will da Refrimix. Oferecemos instalação de ar por R$850 e higienização por R$200."

    monkeypatch.setattr("agent_graph.nodes.nodes.llm_chat", fake_llm_chat)

    state = {
        "messages": [HumanMessage(content="Vocês atendem de noite?")],
        "lead_state": {},
        "next_action": {
            "type": "answer_open_question_llm"
        }
    }
    res = await compose_response(state)
    response_text = res["messages"][-1].content
    assert "R$850" in response_text
    assert "Will" in response_text
