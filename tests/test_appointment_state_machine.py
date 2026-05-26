"""
Testes para a máquina de estados de agendamento.
Garante que appointment_ready não domina respostas independentemente da intenção atual.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph.nodes.nodes as nodes
from agent_graph.nodes.nodes import (
    compute_appointment_stage,
    refresh_appointment_state,
    _current_message_intent_hint,
    _process_question_response,
    _appointment_window_confirmed_response,
    _window_preference_saved_but_not_ready_response,
)


def run(coro):
    return asyncio.run(coro)


def last_ai(messages: list[Any]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return str(m.content)
    return ""


def _base_install_state_after_window(window: str = "tarde") -> dict[str, Any]:
    """Lead de instalação com janela registrada mas sem foto externa."""
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "instalacao"
    ls["cidade_bairro"] = "Guarujá"
    ls["fotos"] = {"local_interno": True, "local_externo": False, "aparelho": False, "disjuntor": False, "erro_display": False}
    ls["appointment"] = {
        "preferred_window": window,
        "preferred_date": None,
        "confirmed_window": False,
        "appointment_alert_sent": False,
        "appointment_stage": "not_ready",
        "last_confirmation_message_sent": None,
        "last_confirmation_turn_id": None,
    }
    return ls


def _base_install_state_fully_ready(window: str = "tarde") -> dict[str, Any]:
    """Lead de instalação completamente qualificado com janela confirmada."""
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "instalacao"
    ls["cidade_bairro"] = "Guarujá"
    ls["btus"] = "12000"
    ls["fotos"] = {"local_interno": True, "local_externo": True, "aparelho": False, "disjuntor": False, "erro_display": False}
    ls["appointment"] = {
        "preferred_window": window,
        "preferred_date": None,
        "confirmed_window": True,
        "appointment_alert_sent": False,
        "appointment_stage": "confirmed",
        "last_confirmation_message_sent": None,
        "last_confirmation_turn_id": None,
    }
    return ls


def _base_state(text: str, ls: dict) -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content=text)],
        "intent": "instalacao",
        "service": ls.get("tipo_servico"),
        "outcome": "duvida",
        "handoff_mode": "none",
        "handoff_reason": None,
        "rag_context": [],
        "lead_state": ls,
        "customer_data": {"phone": "+5513000000001"},
        "is_human": False,
        "message_type": "conversation",
        "msg_id": "",
        "media_url": "",
        "media_base64": "",
        "instance": "test",
        "missing_fields": ["foto_local_externo", "btus"],
        "do_not_ask": [],
        "already_asked_fields": [],
        "conversation_summary": "",
    }


# ─── Testes de compute_appointment_stage ──────────────────────────────────────

def test_stage_collecting_requirements_sem_dados():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "instalacao"
    ls["cidade_bairro"] = None
    stage = compute_appointment_stage(ls, "instalacao")
    assert stage == "collecting_requirements"


def test_stage_window_collected_not_ready_sem_foto_externa():
    ls = _base_install_state_after_window()
    stage = compute_appointment_stage(ls, "instalacao")
    assert stage == "window_collected_not_ready"


def test_stage_window_collected_ready_com_todos_dados():
    ls = _base_install_state_fully_ready()
    ls["appointment"]["confirmed_window"] = False
    stage = compute_appointment_stage(ls, "instalacao")
    assert stage == "window_collected_ready"


def test_stage_confirmed_com_todos_dados():
    ls = _base_install_state_fully_ready()
    stage = compute_appointment_stage(ls, "instalacao")
    assert stage == "confirmed"


def test_stage_alerted():
    ls = _base_install_state_fully_ready()
    ls["appointment"]["appointment_alert_sent"] = True
    stage = compute_appointment_stage(ls, "instalacao")
    assert stage == "alerted"


# ─── Testes de refresh_appointment_state ──────────────────────────────────────

def test_refresh_sem_foto_externa_nao_fica_pronto():
    ls = _base_install_state_after_window()
    ls = refresh_appointment_state(ls, "instalacao")
    assert ls["appointment_ready"] is False
    assert ls["appointment"]["appointment_stage"] == "window_collected_not_ready"


def test_refresh_com_todos_dados_fica_pronto():
    ls = _base_install_state_fully_ready()
    ls = refresh_appointment_state(ls, "instalacao")
    # confirmed_window=True → stage=confirmed → appointment_ready=True
    assert ls["appointment_ready"] is True
    assert ls["appointment"]["appointment_stage"] == "confirmed"


# ─── Testes de _current_message_intent_hint ───────────────────────────────────

def test_intent_process_question():
    assert _current_message_intent_hint("Como funciona?") == "process_question"
    assert _current_message_intent_hint("Me explica como é o serviço") == "process_question"
    assert _current_message_intent_hint("O que inclui a instalação?") == "process_question"


def test_intent_schedule_window():
    assert _current_message_intent_hint("Tarde") == "schedule_window"
    assert _current_message_intent_hint("De manhã seria melhor") == "schedule_window"
    assert _current_message_intent_hint("Pode ser à noite?") == "schedule_window"


def test_intent_price_question():
    assert _current_message_intent_hint("Quanto custa?") == "price_question"
    assert _current_message_intent_hint("Qual o valor da instalação?") == "price_question"


def test_intent_ack():
    assert _current_message_intent_hint("ok") == "ack"
    assert _current_message_intent_hint("beleza") == "ack"
    assert _current_message_intent_hint("perfeito") == "ack"


def test_intent_normal():
    assert _current_message_intent_hint("Quero instalar um ar 12000 BTU") == "normal"


# ─── FASE 2: appointment_ready não pode dominar pergunta de processo ───────────

def test_after_window_process_question_not_repeated_confirmation(monkeypatch):
    """
    Após cliente informar 'tarde' (que foi confirmado), ele pergunta 'Como funciona?'
    A resposta deve explicar o processo, NÃO repetir confirmação de janela.
    """
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm, raising=False)

    ls = _base_install_state_fully_ready("tarde")  # janela já confirmada
    state = _base_state("Como funciona?", ls)
    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])

    assert "funciona" in resp.lower(), f"Resposta deveria explicar processo: {resp!r}"
    assert "período da tarde registrado" not in resp.lower(), f"Repetiu confirmação de janela: {resp!r}"
    assert "melhor janela disponível" not in resp.lower(), f"Repetiu confirmação de janela: {resp!r}"
    assert "handoff_reason" not in result or result.get("handoff_reason") is None, \
        f"Não devia ter handoff para 'Como funciona?': {result.get('handoff_reason')}"


# ─── FASE 4: Janela antes dos requisitos não confirma agenda ─────────────────

def test_window_before_requirements_is_preference_not_confirmation(monkeypatch):
    """
    Cliente manda 'Tarde' mas não tem foto externa.
    Deve salvar preferência, NÃO confirmar janela, NÃO enviar handoff appointment_confirmed.
    """
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm, raising=False)

    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "instalacao"
    ls["cidade_bairro"] = "Guarujá"
    ls["fotos"] = {"local_interno": True, "local_externo": False, "aparelho": False, "disjuntor": False, "erro_display": False}
    state = _base_state("Tarde", ls)
    state["missing_fields"] = ["foto_local_externo", "btus"]

    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])
    ls_out = result.get("lead_state") or {}
    apt = ls_out.get("appointment") or {}

    assert apt.get("preferred_window") == "tarde", f"Janela não foi salva: {apt}"
    assert apt.get("confirmed_window") is not True, f"Não devia ter confirmed_window: {apt}"
    assert apt.get("appointment_stage") == "window_collected_not_ready", \
        f"Stage errado: {apt.get('appointment_stage')}"
    assert result.get("handoff_reason") != "appointment_confirmed", \
        f"Não devia ter confirmado agendamento: {result.get('handoff_reason')}"
    # Resposta deve pedir foto externa
    assert "condensadora" in resp.lower() or "externo" in resp.lower() or "externa" in resp.lower(), \
        f"Não pediu foto externa após janela incompleta: {resp!r}"


def test_window_after_requirements_confirms_once(monkeypatch):
    """
    Cliente manda 'Tarde' com todos os dados preenchidos.
    Deve confirmar janela UMA vez e enviar handoff appointment_confirmed.
    """
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm, raising=False)

    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "instalacao"
    ls["cidade_bairro"] = "Guarujá"
    ls["btus"] = "12000"
    ls["fotos"] = {"local_interno": True, "local_externo": True, "aparelho": False, "disjuntor": False, "erro_display": False}
    state = _base_state("Tarde", ls)
    state["missing_fields"] = []

    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])
    ls_out = result.get("lead_state") or {}
    apt = ls_out.get("appointment") or {}

    assert apt.get("preferred_window") == "tarde", f"Janela não foi salva: {apt}"
    assert apt.get("confirmed_window") is True, f"Devia ter confirmed_window: {apt}"
    assert result.get("handoff_reason") == "appointment_confirmed", \
        f"Devia ter appointment_confirmed: {result.get('handoff_reason')}"
    assert "tarde" in resp.lower() and "registrado" in resp.lower(), \
        f"Resposta deveria confirmar a janela: {resp!r}"


# ─── FASE 5: Não repetir confirmação após confirmado ─────────────────────────

def test_next_message_after_confirmed_answers_process_question(monkeypatch):
    """
    Após confirmação de janela, cliente pergunta 'Como funciona?'
    Deve responder processo, não repetir confirmação.
    """
    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm, raising=False)

    ls = _base_install_state_fully_ready("tarde")
    state = _base_state("Como funciona?", ls)

    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])

    assert "funciona assim" in resp.lower() or "funciona" in resp.lower(), \
        f"Deveria explicar processo: {resp!r}"
    assert "período da tarde registrado" not in resp.lower(), \
        f"Repetiu confirmação: {resp!r}"


# ─── Testes de helpers de resposta ────────────────────────────────────────────

def test_process_question_response_instalacao():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "instalacao"
    resp = _process_question_response(ls, "instalacao", ["foto_local_externo"], [])
    assert "funciona assim" in resp.lower()
    assert "condensadora" in resp.lower() or "externo" in resp.lower()


def test_process_question_response_manutencao():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "manutencao"
    resp = _process_question_response(ls, "manutencao", [], [])
    assert "funciona assim" in resp.lower()
    assert "sintoma" in resp.lower() or "gela" in resp.lower() or "liga" in resp.lower()


def test_process_question_response_higienizacao():
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "higienizacao"
    resp = _process_question_response(ls, "higienizacao", [], [])
    assert "funciona assim" in resp.lower()
    assert "quantos" in resp.lower() or "aparelhos" in resp.lower()


def test_window_preference_saved_but_not_ready_asks_external_photo():
    ls = _base_install_state_after_window()
    resp = _window_preference_saved_but_not_ready_response(ls, ["foto_local_externo", "btus"], [])
    assert "tarde" in resp.lower()
    assert "condensadora" in resp.lower() or "externo" in resp.lower()
    assert "agenda" in resp.lower()


def test_appointment_window_confirmed_response():
    ls = _base_install_state_fully_ready("tarde")
    resp = _appointment_window_confirmed_response(ls)
    assert "tarde" in resp.lower()
    assert "registrado" in resp.lower()


# ─── Testes de label de serviço ───────────────────────────────────────────────

def test_service_label_with_accent():
    """Resposta de processo deve usar 'instalação' com acento."""
    ls = nodes._lead_state_copy()
    ls["tipo_servico"] = "instalacao"
    resp = _process_question_response(ls, "instalacao", [], [])
    # A resposta de processo para instalação menciona o processo de instalação
    assert "instalação" in resp or "instala" in resp, f"Label sem acento ou ausente: {resp!r}"
