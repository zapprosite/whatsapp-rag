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


# ── has_minimum_real_data_for_appointment ─────────────────────────────────


def test_minimum_data_false_when_city_invalid():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "manutencao"
    ls["cidade_bairro"] = "[áudio]"
    assert nodes.has_minimum_real_data_for_appointment(ls, "manutencao") is False


def test_minimum_data_false_when_no_symptom_manutencao():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "manutencao"
    ls["cidade_bairro"] = "Santos"
    assert nodes.has_minimum_real_data_for_appointment(ls, "manutencao") is False


def test_minimum_data_true_manutencao_with_symptom():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "manutencao"
    ls["cidade_bairro"] = "Santos"
    ls["manutencao"] = {"pinga_agua": True}
    assert nodes.has_minimum_real_data_for_appointment(ls, "manutencao") is True


def test_minimum_data_true_instalacao_with_btus():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "instalacao"
    ls["cidade_bairro"] = "Guarujá"
    ls["btus"] = "12000"
    assert nodes.has_minimum_real_data_for_appointment(ls, "instalacao") is True


def test_minimum_data_false_instalacao_without_btus_or_photo():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "instalacao"
    ls["cidade_bairro"] = "Guarujá"
    assert nodes.has_minimum_real_data_for_appointment(ls, "instalacao") is False


# ── appointment_ready não dispara prematuramente ───────────────────────────


def test_bare_manutencao_not_appointment_ready(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return '{"state_patch": {"tipo_servico": "manutencao"}, "detected_service_type": "manutencao"}'

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm)

    state = {
        "messages": [HumanMessage(content="Manutenção")],
        "intent": None,
        "service": None,
        "outcome": "duvida",
        "handoff_mode": "none",
        "handoff_reason": None,
        "rag_context": [],
        "lead_state": nodes._lead_state_copy(),
        "do_not_ask": [],
        "already_asked_fields": [],
        "missing_fields": ["tipo_servico", "cidade_bairro"],
        "conversation_summary": "",
        "customer_data": {"phone": "+5513000000003", "diagnostic_mode": True},
        "is_human": False,
        "message_type": "conversation",
    }

    result = run(nodes.extract_lead_data(state))
    ls = result.get("lead_state") or {}
    assert ls.get("appointment_ready") is False


def test_appointment_ready_requires_real_city(monkeypatch):
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm)

    ls = nodes._lead_state_copy()
    ls.update({
        "tipo_servico": "manutencao",
        "cidade_bairro": "[áudio]",
        "appointment_score": 7,
        "appointment_ready": True,
    })
    ls = nodes.sanitize_lead_state(ls)
    assert ls["appointment_ready"] is False
    assert ls["cidade_bairro"] is None


def test_appointment_score_high_but_minimum_false():
    ls = nodes._lead_state_copy()
    ls.update({
        "tipo_servico": "manutencao",
        "cidade_bairro": "Santos",
        "appointment_score": 7,
    })
    state = {
        "messages": [HumanMessage(content="Manutenção"), HumanMessage(content="Santos"), HumanMessage(content="quero agendar")],
        "service": "manutencao",
        "lead_state": ls,
        "customer_data": {},
    }
    # Sem sintoma: minimum_ok deve ser False
    ok = nodes.has_minimum_real_data_for_appointment(ls, "manutencao")
    assert ok is False
    # _apply_relationship_and_appointment deve respeitar isso
    updated_ls, _ = nodes._apply_relationship_and_appointment(state, ls)
    assert updated_ls["appointment_ready"] is False
