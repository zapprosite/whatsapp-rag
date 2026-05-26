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


def test_internal_photo_does_not_satisfy_external_photo_request(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm, raising=False)

    lead_state = nodes._lead_state_copy()
    lead_state.update(
        {
            "tipo_servico": "instalacao",
            "cidade_bairro": "Guarujá",
            "btus": "12000",
            "last_asked_field": "foto_local_externo",
            "fotos": {"local_interno": True, "local_externo": False},
            "last_image_analysis": {
                "image_type": "local_interno_instalacao",
                "observations": "parede interna do ambiente",
            },
        }
    )

    result = run(
        nodes.generate_response(
            {
                "messages": [HumanMessage(content="[Imagem recebida: foto do local interno para instalação.]")],
                "intent": "instalacao",
                "service": "instalacao",
                "outcome": "duvida",
                "handoff_mode": "none",
                "handoff_reason": None,
                "rag_context": [],
                "lead_state": lead_state,
                "customer_data": {"phone": "+5513000000001"},
                "missing_fields": ["foto_local_externo"],
                "do_not_ask": ["cidade_bairro", "btus", "foto_local_interno"],
                "message_type": "imageMessage",
            }
        )
    )

    response = last_ai(result["messages"]).lower()
    assert "local interno" in response
    assert "condensadora" in response
    assert "lado externo" in response
    assert result.get("handoff_reason") is None
