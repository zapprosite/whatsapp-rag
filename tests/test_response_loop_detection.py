"""
tests/test_response_loop_detection.py
Valida que o bot não entra em loop de respostas:
- Mesma resposta não aparece duas vezes consecutivas para mensagens diferentes.
- Bot não repete perguntas de campos já respondidos.
- Frases proibidas não aparecem nas respostas.
"""
from __future__ import annotations

import asyncio
import hashlib
from copy import deepcopy

import pytest

from agent_graph.nodes.nodes import _lead_state_copy
from app import mvp_attendance


def run(coro):
    return asyncio.run(coro)


def _hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


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


# ---------------------------------------------------------------------------
# Frases proibidas que NUNCA devem aparecer
# ---------------------------------------------------------------------------

_FORBIDDEN_PHRASES = [
    "qual é o próximo detalhe que você já consegue me informar",
    "continuando sua instalação, pra eu te orientar certinho",
    "vou adiantar pelo que já tenho",
    "quando puder, me manda as fotos",
    "não consigo agendar sem foto",
]


def test_no_forbidden_phrases_higienizacao(monkeypatch):
    """Fluxo de higienização não deve conter frases proibidas."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "higienização", "Will", "1", "tarde"],
    )
    for resp in responses:
        for phrase in _FORBIDDEN_PHRASES:
            assert phrase.lower() not in resp.lower(), (
                f"Frase proibida encontrada: '{phrase}'\nResposta: {resp}"
            )


def test_no_forbidden_phrases_instalacao(monkeypatch):
    """Fluxo de instalação não deve conter frases proibidas."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "instalação", "Will", "não tenho foto"],
    )
    for resp in responses:
        for phrase in _FORBIDDEN_PHRASES:
            assert phrase.lower() not in resp.lower(), (
                f"Frase proibida encontrada: '{phrase}'\nResposta: {resp}"
            )


# ---------------------------------------------------------------------------
# Mesma resposta consecutiva para mensagens diferentes
# ---------------------------------------------------------------------------

def test_no_consecutive_identical_responses_higienizacao(monkeypatch):
    """Respostas consecutivas para mensagens distintas não podem ser idênticas."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "higienização", "Will", "1", "tarde"],
    )
    for i in range(1, len(responses)):
        assert responses[i] != responses[i - 1], (
            f"Loop: resposta {i} idêntica à {i - 1}\n{responses[i]}"
        )


def test_no_consecutive_identical_responses_manutencao(monkeypatch):
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "manutenção", "Will", "tarde"],
    )
    for i in range(1, len(responses)):
        assert responses[i] != responses[i - 1]


# ---------------------------------------------------------------------------
# Bot não repete perguntas após resposta
# ---------------------------------------------------------------------------

def test_no_repeat_quantos_after_answer(monkeypatch):
    """Bot NÃO pode perguntar 'Quantos aparelhos são?' depois de receber '1'."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "higienização", "Will", "1"],
    )
    # A resposta após "1" não deve conter a pergunta de quantidade
    assert "Quantos aparelhos são?" not in responses[3]


def test_no_repeat_quantos_after_audio_um(monkeypatch):
    """Bot NÃO pode perguntar 'Quantos aparelhos?' depois de receber 'um' (variante áudio)."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "higienização", "Will", "um"],
    )
    assert "Quantos aparelhos são?" not in responses[3]


def test_no_ask_service_when_services_listed(monkeypatch):
    """Depois de responder a lista de serviços, bot não deve perguntar 'qual serviço?'."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "quais serviços oferecem?"],
    )
    last = responses[1]
    assert "instalação, manutenção, higienização ou conserto?" not in last


# ---------------------------------------------------------------------------
# Bot não repete boas-vindas no meio da conversa
# ---------------------------------------------------------------------------

def test_no_welcome_mid_conversation(monkeypatch):
    """Bot não deve dizer 'Bom dia, tudo joia?' depois de uma conversa já iniciada."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "higienização", "Will"],
    )
    # A resposta após nome não deve ser o onboarding novamente
    assert "Bom dia, tudo joia?" not in responses[2]


# ---------------------------------------------------------------------------
# Hashmap de detecção de loops
# ---------------------------------------------------------------------------

def test_response_hash_unique_per_turn(monkeypatch):
    """Hashes de resposta devem ser únicos entre turnos consecutivos distintos."""
    responses, _ = _simulate(
        monkeypatch,
        ["bom dia", "higienização", "Will", "1", "tarde"],
    )
    hashes = [_hash(r) for r in responses]
    for i in range(1, len(hashes)):
        assert hashes[i] != hashes[i - 1], (
            f"Hash duplicado detectado no turno {i}: {responses[i]}"
        )
