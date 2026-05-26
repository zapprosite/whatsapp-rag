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


# ── _detect_high_value_reason ────────────────────────────────────────────


def test_generic_orcamento_not_high_value():
    text = nodes._fold_text("gostaria de fazer um orcamento para o meu ar condicionado")
    reason = nodes._detect_high_value_reason(text, "consultoria")
    assert reason is None


def test_consultoria_intent_alone_not_high_value():
    text = nodes._fold_text("preciso de consultoria")
    reason = nodes._detect_high_value_reason(text, "consultoria")
    assert reason is None


def test_pmoc_without_signal_not_high_value():
    text = nodes._fold_text("quero manutencao preventiva")
    reason = nodes._detect_high_value_reason(text, "pmoc")
    assert reason is None


def test_pmoc_with_laudo_is_high_value():
    text = nodes._fold_text("preciso de laudo pmoc para empresa")
    reason = nodes._detect_high_value_reason(text, "pmoc")
    # Should either match keyword list or new pmoc rule
    assert reason is not None


def test_projeto_central_with_vrf_is_high_value():
    text = nodes._fold_text("tenho um sistema vrf num galpão industrial")
    reason = nodes._detect_high_value_reason(text, "projeto-central")
    assert reason is not None


def test_projeto_central_without_signal_not_high_value():
    # Intent "projeto-central" sozinho sem keyword técnica forte não dispara
    text = nodes._fold_text("quero informacoes sobre climatizacao")
    reason = nodes._detect_high_value_reason(text, "projeto-central")
    assert reason is None


# ── classify_service não marca high_value para orcamento genérico ─────────


def test_generic_orcamento_classify_not_high_value(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return "onboarding"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm)

    state = {
        "messages": [HumanMessage(content="Gostaria de fazer um orçamento para o meu ar condicionado")],
        "intent": None,
        "service": None,
        "outcome": None,
        "handoff_mode": "none",
        "handoff_reason": None,
        "lead_state": nodes._lead_state_copy(),
        "customer_data": {"phone": "+5513000000005"},
        "is_human": False,
        "message_type": "conversation",
        "msg_id": "",
        "media_url": "",
        "media_base64": "",
        "instance": "test",
    }

    result = run(nodes.classify_service(state))
    # Should not have high_value handoff_reason
    assert "high_value" not in (result.get("handoff_reason") or "")


def test_generate_response_generic_orcamento_asks_service_type(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm)

    state = {
        "messages": [HumanMessage(content="Gostaria de fazer um orçamento para o meu ar condicionado")],
        "intent": "onboarding",
        "service": None,
        "outcome": "duvida",
        "handoff_mode": "none",
        "handoff_reason": None,
        "rag_context": [],
        "lead_state": nodes._lead_state_copy(),
        "customer_data": {"phone": "+5513000000005"},
        "is_human": False,
        "message_type": "conversation",
    }

    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])
    assert "esse caso é mais técnico" not in resp.lower()
    assert "sinalizar o gerente" not in resp.lower()
