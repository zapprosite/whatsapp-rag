from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph.nodes.nodes as nodes


def run(coro):
    return asyncio.run(coro)


def last_ai(messages: list[Any]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return str(m.content)
    return ""


# ── _bare_service_selection_response ────────────────────────────────────


def test_bare_manutencao_response():
    ls = nodes._lead_state_copy()
    resp = nodes._bare_service_selection_response("Manutenção", ls)
    assert resp is not None
    assert "sintoma" in resp.lower() or "acontecendo" in resp.lower()


def test_bare_instalacao_response():
    ls = nodes._lead_state_copy()
    resp = nodes._bare_service_selection_response("Instalação", ls)
    assert resp is not None
    assert "btu" in resp.lower() or "cidade" in resp.lower()


def test_bare_higienizacao_response():
    ls = nodes._lead_state_copy()
    resp = nodes._bare_service_selection_response("Higienização", ls)
    assert resp is not None
    assert "aparelhos" in resp.lower() or "cidade" in resp.lower()


def test_bare_conserto_response():
    ls = nodes._lead_state_copy()
    resp = nodes._bare_service_selection_response("Conserto", ls)
    assert resp is not None
    assert "sintoma" in resp.lower() or "liga" in resp.lower()


def test_bare_returns_none_when_service_exists():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "manutencao"
    resp = nodes._bare_service_selection_response("Manutenção", ls)
    assert resp is None


def test_bare_returns_none_when_window_exists():
    ls = nodes._lead_state_copy()
    ls["appointment"] = {"preferred_window": "tarde", "confirmed_window": True, "appointment_alert_sent": False}
    resp = nodes._bare_service_selection_response("Manutenção", ls)
    assert resp is None


# ── generate_response com serviço puro ───────────────────────────────────


def test_generate_response_manutencao_bare_asks_symptom(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm)

    state = {
        "messages": [HumanMessage(content="Manutenção")],
        "intent": "manutencao",
        "service": None,
        "outcome": "duvida",
        "handoff_mode": "none",
        "handoff_reason": None,
        "rag_context": [],
        "lead_state": nodes._lead_state_copy(),
        "customer_data": {"phone": "+5513000000004"},
        "is_human": False,
        "message_type": "conversation",
    }

    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])
    assert result["lead_state"].get("appointment_ready") is False
    assert "manhã ou tarde" not in resp.lower()
    assert "sinalizar o gerente" not in resp.lower()
    assert "[áudio]" not in resp
