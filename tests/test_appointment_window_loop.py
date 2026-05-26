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


def base_state(text: str, lead_state: dict | None = None) -> dict[str, Any]:
    ls = lead_state or nodes._lead_state_copy()
    return {
        "messages": [HumanMessage(content=text)],
        "intent": "onboarding",
        "service": ls.get("tipo_servico"),
        "outcome": "duvida",
        "handoff_mode": "none",
        "handoff_reason": None,
        "rag_context": [],
        "lead_state": ls,
        "customer_data": {"phone": "+5513000000002"},
        "is_human": False,
        "message_type": "conversation",
        "msg_id": "",
        "media_url": "",
        "media_base64": "",
        "instance": "test",
    }


# ── Detecção de janela ─────────────────────────────────────────────────────


def test_detect_preferred_window_tarde():
    assert nodes._detect_preferred_window("Tarde") == "tarde"
    assert nodes._detect_preferred_window("pode ser na tarde") == "tarde"


def test_detect_preferred_window_manha():
    assert nodes._detect_preferred_window("manhã") == "manhã"
    assert nodes._detect_preferred_window("de manhã tá ótimo") == "manhã"


def test_detect_preferred_window_none():
    assert nodes._detect_preferred_window("ok") is None
    assert nodes._detect_preferred_window("sim, pode ser") is None


# ── Janela persiste em lead_state ─────────────────────────────────────────


def test_window_tarde_stops_loop_when_appointment_ready(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm)

    ls = nodes._lead_state_copy()
    ls.update({
        "tipo_servico": "manutencao",
        "cidade_bairro": "Santos",
        "appointment_ready": True,
        "appointment_score": 6,
        "appointment": {"preferred_window": None, "confirmed_window": False, "appointment_alert_sent": False},
        "manutencao": {"pinga_agua": True},
    })

    state = base_state("Tarde", ls)
    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])

    assert "manhã ou tarde" not in resp.lower()
    assert "tarde" in resp.lower()
    assert result.get("handoff_reason") == "appointment_confirmed"


def test_window_not_asked_twice_when_already_registered(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm)

    ls = nodes._lead_state_copy()
    ls.update({
        "tipo_servico": "manutencao",
        "cidade_bairro": "Santos",
        "appointment_ready": True,
        "appointment_score": 6,
        "appointment": {"preferred_window": "tarde", "confirmed_window": True, "appointment_alert_sent": False},
        "manutencao": {"pinga_agua": True},
    })

    state = base_state("Tarde", ls)
    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])
    assert "manhã ou tarde" not in resp.lower()


def test_window_tarde_response_does_not_repeat_question(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm)

    ls = nodes._lead_state_copy()
    ls.update({
        "tipo_servico": "manutencao",
        "cidade_bairro": "Santos",
        "appointment_ready": True,
        "appointment_score": 6,
        "appointment": {"preferred_window": None, "confirmed_window": False, "appointment_alert_sent": False},
        "manutencao": {"pinga_agua": True},
    })

    state = base_state("Tarde", ls)
    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])
    # Deve confirmar, não perguntar de novo
    assert "?" not in resp or "tarde" in resp.lower()
    assert "manhã ou tarde" not in resp.lower()
