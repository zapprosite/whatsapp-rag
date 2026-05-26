from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph.nodes.nodes as nodes


def run(coro):
    return asyncio.run(coro)


def last_ai(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return str(message.content)
    return ""


def test_current_print_regression_como_funciona_after_tarde_incomplete(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm, raising=False)

    lead_state = nodes._lead_state_copy()
    lead_state.update(
        {
            "tipo_servico": "instalacao",
            "cidade_bairro": "Guarujá",
            "fotos": {"local_interno": True, "local_externo": False},
            "appointment": {
                "preferred_window": "tarde",
                "confirmed_window": False,
                "appointment_alert_sent": False,
            },
        }
    )

    result = run(
        nodes.generate_response(
            {
                "messages": [HumanMessage(content="Como funciona?")],
                "intent": "instalacao",
                "service": "instalacao",
                "outcome": "duvida",
                "handoff_mode": "none",
                "handoff_reason": None,
                "rag_context": [],
                "lead_state": lead_state,
                "customer_data": {"phone": "+5513000000001"},
                "missing_fields": ["foto_local_externo", "btus"],
                "do_not_ask": ["cidade_bairro", "foto_local_interno"],
                "message_type": "conversation",
            }
        )
    )

    response = last_ai(result["messages"]).lower()
    assert "funciona assim" in response
    assert "condensadora" in response or "foto do local" in response
    assert "período da tarde registrado" not in response
    assert "melhor janela disponível" not in response
    assert result.get("handoff_reason") is None
