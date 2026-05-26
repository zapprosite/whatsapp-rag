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


# ── Dedup dispatch_appointment_alert ──────────────────────────────────────────


def test_dispatch_appointment_alert_nao_reenvia_se_ja_enviado(monkeypatch):
    """P4 — dedup: deve retornar {} imediatamente se appointment_alert_sent=True."""
    alert_calls: list[str] = []

    async def fake_send_alert(data):
        alert_calls.append("sent")

    async def fake_upsert_lead(data):
        pass

    monkeypatch.setattr(
        "agent_graph.nodes.nodes.dispatch_appointment_alert.__module__",
        "agent_graph.nodes.nodes",
        raising=False,
    )

    # Patchamos as importações lazy dentro de dispatch_appointment_alert
    import agent_graph.services.alerts as alerts_mod
    monkeypatch.setattr(alerts_mod, "send_appointment_alert", fake_send_alert)
    monkeypatch.setattr(alerts_mod, "prisma_upsert_lead", fake_upsert_lead)

    ls = nodes._lead_state_copy()
    ls.update({
        "tipo_servico": "manutencao",
        "cidade_bairro": "Santos",
        "appointment_ready": True,
        "appointment": {
            "preferred_window": "manha",
            "confirmed_window": True,
            "appointment_alert_sent": True,  # ← já enviado
        },
    })

    state = {
        **base_state("Ok, pode confirmar", ls),
        "outcome": "appointment_confirmed",
        "handoff_reason": "appointment_confirmed",
    }

    result = run(nodes.dispatch_appointment_alert(state))

    # Com appointment_alert_sent=True, deve retornar {} sem chamar send_appointment_alert
    assert result == {}, f"Esperado {{}}, obtido {result}"
    assert alert_calls == [], "send_appointment_alert não deve ser chamado no dedup"
