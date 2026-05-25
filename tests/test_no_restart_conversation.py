from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph.nodes.nodes as nodes


def run(coro):
    return asyncio.run(coro)


def state_with_installation(text: str = "oi") -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content="quero instalar um split"), AIMessage(content="Me manda a cidade?"), HumanMessage(content=text)],
        "lead_state": {
            "tipo_servico": "instalacao",
            "relationship_type": "qualifying_lead",
            "ask_count_by_field": {},
        },
        "missing_fields": ["foto_local_interno", "foto_local_externo", "cidade_bairro"],
        "do_not_ask": ["tipo_servico"],
        "customer_data": {
            "phone": "5513000000000",
            "memory": {
                "history_source": "postgres",
                "is_conversation_started": True,
                "has_persistent_lead": True,
                "postgres_event_count": 2,
            },
        },
        "handoff_mode": "none",
        "handoff_reason": None,
        "rag_context": [],
        "outcome": None,
        "service": None,
        "intent": None,
    }


def test_greeting_with_persistent_lead_does_not_restart(monkeypatch):
    async def fake_qwen(messages, max_retries=2):
        return "unknown"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_qwen)
    result = run(nodes.classify_service(state_with_installation("oi")))

    assert result["intent"] == "instalacao"
    assert result["service"] == "instalacao"
    assert result["intent"] != "onboarding"
    assert result["continuation_response"]
    assert "instalação" in result["continuation_response"]


def test_short_ok_continues_installation_without_service_question(monkeypatch):
    async def fake_qwen(messages, max_retries=2):
        return "unknown"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_qwen)
    classified = run(nodes.classify_service(state_with_installation("beleza")))
    state = {**state_with_installation("beleza"), **classified}
    generated = run(nodes.generate_response(state))
    response = next(str(message.content) for message in reversed(generated["messages"]) if isinstance(message, AIMessage))

    assert "instalação" in response
    assert "instalação, manutenção ou higienização" not in response
    assert "qual serviço" not in response.lower()


def test_service_correction_requires_explicit_text(monkeypatch):
    async def fake_qwen(messages, max_retries=2):
        return "higienizacao"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_qwen)
    no_correction = run(nodes.classify_service(state_with_installation("limpeza")))
    corrected = run(nodes.classify_service(state_with_installation("na verdade é higienização")))

    assert no_correction["service"] == "instalacao"
    assert corrected["service"] == "higienizacao"
    assert corrected["lead_state"]["previous_tipo_servico"] == "instalacao"
