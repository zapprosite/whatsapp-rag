"""
tests/test_hvacr_loop_scenarios.py
Cenários end-to-end de atendimento HVAC-R para detectar loops e regressões de política comercial.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from agent_graph.nodes.nodes import _lead_state_copy
from app import mvp_attendance


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers de mock compartilhados
# ---------------------------------------------------------------------------

def _mock_repo_stateful(monkeypatch, lead_state=None, *, event_count: int = 0):
    store = {
        "lead_state": lead_state or _lead_state_copy(),
        "event_count": event_count,
        "events": [],
        "pipeline_stage": "new",
        "service_type": (lead_state or {}).get("tipo_servico") if lead_state else None,
    }

    async def fake_load(phone, name=None):
        return {
            "id": "lead-1",
            "phone": phone,
            "name": store["lead_state"].get("nome"),
            "service_type": store["service_type"],
            "pipeline_stage": store["pipeline_stage"],
            "city_bairro": store["lead_state"].get("cidade_bairro"),
            "lead_state": deepcopy(store["lead_state"]),
            "event_count": store["event_count"],
            "available_columns": set(),
        }

    async def fake_update(phone, lead_state, *, pipeline_stage, service_type, city_bairro=None):
        store["lead_state"] = lead_state
        store["pipeline_stage"] = pipeline_stage
        store["service_type"] = service_type

    async def fake_event(phone, role, message, extracted_data=None):
        store["events"].append({"role": role, "message": message})
        store["event_count"] += 1

    monkeypatch.setattr(mvp_attendance, "load_or_create_lead", fake_load)
    monkeypatch.setattr(mvp_attendance, "update_lead_state", fake_update)
    monkeypatch.setattr(mvp_attendance, "create_lead_event", fake_event)
    return store


def _simulate(monkeypatch, turns: list[str], lead_state=None):
    store = _mock_repo_stateful(monkeypatch, lead_state, event_count=0)
    history = []
    responses = []
    for msg in turns:
        result = run(
            mvp_attendance.process_mvp_message(
                phone="5513999999999",
                message_text=msg,
                instance="default",
                history=history,
            )
        )
        history = result["messages"]
        responses.append(str(result["messages"][-1].content))
    return responses, store


def _last(responses):
    return responses[-1]


# ---------------------------------------------------------------------------
# 1. test_services_list_question
# ---------------------------------------------------------------------------

def test_services_list_question(monkeypatch):
    """'Quais serviços oferecem?' deve retornar answer_services_list, nunca ask_basic_service."""
    responses, _ = _simulate(monkeypatch, ["bom dia", "quais serviços oferecem?"])
    last = _last(responses)
    assert "Instalação" in last or "instalação" in last
    assert "Higienização" in last or "higienização" in last
    # Não deve responder com a pergunta determinística ask_basic_service
    assert "instalação, manutenção, higienização ou conserto?" not in last


def test_services_list_no_loop(monkeypatch):
    """Bot NÃO pode repetir ask_basic_service depois do cliente perguntar a lista de serviços."""
    responses, _ = _simulate(monkeypatch, ["bom dia", "quais serviços oferecem?", "não entendi"])
    assert "instalação, manutenção, higienização ou conserto?" not in responses[1]


# ---------------------------------------------------------------------------
# 2. test_clarification_request
# ---------------------------------------------------------------------------

def test_clarification_request(monkeypatch):
    """'Não entendi' deve acionar answer_clarification, nunca repetir exatamente a resposta anterior."""
    responses, _ = _simulate(monkeypatch, ["bom dia", "não entendi"])
    last = _last(responses)
    # Deve explicar de forma simplificada
    assert "R$850" in last or "R$200" in last or "R$50" in last or "explicar" in last.lower() or "simples" in last.lower()
    # Não deve ser igual à resposta de onboarding
    assert last != "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?"


# ---------------------------------------------------------------------------
# 3. Higienização feliz completo
# ---------------------------------------------------------------------------

def test_higienizacao_feliz_completo(monkeypatch):
    """Fluxo completo de higienização: bom dia > serviço > nome > quantidade > período."""
    responses, store = _simulate(
        monkeypatch,
        ["bom dia", "preciso fazer uma higienização no meu ar", "William Rodrigues", "1", "tarde"],
    )

    assert "Bom dia, tudo joia?" in responses[0]
    # Deve pedir nome
    assert "nome" in responses[1].lower()
    # Deve oferecer R$200 e perguntar quantidade
    assert "R$200" in responses[2]
    assert "Quantos aparelhos" in responses[2]
    # Depois de "1", NÃO deve repetir "Quantos aparelhos"
    assert "Quantos aparelhos" not in responses[3]
    assert "1 aparelho" in responses[3] or "R$200" in responses[3]
    # Deve perguntar período
    assert "manhã" in responses[3].lower() or "tarde" in responses[3].lower()
    # Depois de "tarde", deve salvar a preferência
    assert "tarde" in responses[4].lower() or "anotad" in responses[4].lower()
    # Estado deve estar correto
    assert store["lead_state"].get("nome") == "William Rodrigues"
    assert store["lead_state"].get("higienizacao", {}).get("quantidade_aparelhos") == 1


def test_higienizacao_nao_repete_quantos_aparelhos(monkeypatch):
    """Depois de receber '1', o bot nunca mais deve perguntar 'Quantos aparelhos são?'."""
    responses, store = _simulate(
        monkeypatch,
        ["bom dia", "higienização", "Will", "1", "tarde"],
    )
    for resp in responses[3:]:
        assert "Quantos aparelhos" not in resp


# ---------------------------------------------------------------------------
# 4. test_installation_no_photo_visit
# ---------------------------------------------------------------------------

def test_installation_no_photo_visit(monkeypatch):
    """'Não tenho foto' deve gerar visita técnica R$50 abatível, nunca pedir foto em loop."""
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["nome"] = "Will"
    responses, _ = _simulate(
        monkeypatch,
        ["não tenho foto agora"],
        lead_state=lead_state,
    )
    last = _last(responses)
    assert "visita técnica de R$50" in last or "R$50" in last
    assert "foto ajuda" in last.lower() or "não trava" in last.lower()
    # Não deve pedir foto de novo logo depois
    assert "me manda as fotos" not in last.lower()
    assert "sem foto não consigo" not in last.lower()


# ---------------------------------------------------------------------------
# 5. test_maintenance_default_visit
# ---------------------------------------------------------------------------

def test_maintenance_default_visit(monkeypatch):
    """'meu ar não gela' deve ser roteado para manutenção / análise técnica R$50."""
    lead_state = _lead_state_copy()
    lead_state["nome"] = "Will"
    responses, store = _simulate(
        monkeypatch,
        ["meu ar não gela"],
        lead_state=lead_state,
    )
    last = _last(responses)
    assert "R$50" in last
    # Deve ser manutenção
    assert "manutenção" in last.lower() or "análise" in last.lower() or "visita" in last.lower()


# ---------------------------------------------------------------------------
# 6. test_no_same_response_loop
# ---------------------------------------------------------------------------

def test_no_same_response_loop(monkeypatch):
    """Duas mensagens distintas não podem gerar resposta idêntica consecutiva."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "higienização", "Will", "1", "tarde"],
    )
    for i in range(1, len(responses)):
        assert responses[i] != responses[i - 1], (
            f"Loop detectado: respostas[{i - 1}] == respostas[{i}]\n{responses[i]}"
        )


# ---------------------------------------------------------------------------
# 7. Onboarding básico sem loop de serviço
# ---------------------------------------------------------------------------

def test_onboarding_nao_cai_em_ask_basic_service_loop(monkeypatch):
    """Após onboarding, 'não entendi' nunca deve virar ask_basic_service se o bot não perguntou serviço."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "não entendi", "como assim?"],
    )
    # Nem a segunda nem a terceira resposta pode ser exatamente o ask_basic_service genérico
    for resp in responses[1:]:
        assert resp != "Entendi.\n\nIsso é instalação, manutenção, higienização ou conserto?"


# ---------------------------------------------------------------------------
# 8. Alto valor – roteamento project_quote
# ---------------------------------------------------------------------------

def test_high_value_vrf_project_quote(monkeypatch):
    """Mensagem com VRF deve ser roteada como project_quote, nunca como instalação simples."""
    lead_state = _lead_state_copy()
    lead_state["nome"] = "Will"
    responses, store = _simulate(
        monkeypatch,
        ["preciso de VRF para loja"],
        lead_state=lead_state,
    )
    last = _last(responses)
    # Não deve falar em R$850
    assert "R$850" not in last
    # Deve mencionar visita técnica / projeto
    assert "visita" in last.lower() or "projeto" in last.lower() or "R$50" in last


def test_high_value_cassete_project_quote(monkeypatch):
    """Cassete deve virar project_quote."""
    lead_state = _lead_state_copy()
    lead_state["nome"] = "Will"
    responses, _ = _simulate(monkeypatch, ["quero um cassete"], lead_state=lead_state)
    last = _last(responses)
    assert "R$850" not in last
    assert "visita" in last.lower() or "projeto" in last.lower() or "R$50" in last
