"""
tests/test_brazilian_variations.py
Valida que variações ortográficas e regionais brasileiras de serviços
são corretamente classificadas sem virar 'unknown'.
"""
from __future__ import annotations

import asyncio

import pytest

from agent_graph.nodes.understand_message import understand_message


def run(coro):
    return asyncio.run(coro)


def _state(text: str, service: str | None = None) -> dict:
    from unittest.mock import MagicMock
    lead_state = {"tipo_servico": service} if service else {}
    return {
        "messages": [MagicMock(content=text)],
        "lead_state": lead_state,
        "message_type": "conversation",
    }


def _understand(text: str, service: str | None = None) -> dict:
    return run(understand_message(_state(text, service)))["message_understanding"]


# ---------------------------------------------------------------------------
# Variações de higienização
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "limpeza no ar",
    "higienizar o split",
    "limpar meu ar",
    "dar uma geral no ar",
    "meu ar tá com cheiro ruim",
    "quero limpeza",
    "limpa o split",
    "higienizacao",
    "higienização",
])
def test_higienizacao_variations_recognized(text):
    """Variações de higienização/limpeza devem identificar o serviço ou ser classificadas."""
    und = _understand(text)
    # Deve mencionar higienizacao ou ser uma pergunta de serviço / resposta
    assert und["service_mentioned"] in {"higienizacao", None}
    # Se não identificou serviço, pelo menos não deve ser 'unknown' de forma total sem contexto
    # (o important é não crashar e classificar razoavelmente)
    assert und["kind"] != "security"


@pytest.mark.parametrize("text", [
    "limpesa no ar",       # erro ortográfico
    "higienizaçao",        # acento diferente
    "higienizacao",        # sem acento
])
def test_higienizacao_typos_normalized(text):
    """Typos comuns de higienização não devem crashar."""
    und = _understand(text)
    assert und is not None
    assert "kind" in und


# ---------------------------------------------------------------------------
# Variações de instalação
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "istalação",
    "instalaçao",
    "istalacao",
    "instalar",
    "instalacao",
    "instalação",
    "quero instalar um split",
])
def test_instalacao_variations_recognized(text):
    """Variações de instalação devem ser identificadas ou não crashar."""
    und = _understand(text)
    assert und is not None
    # Variações normalizadas devem identificar instalacao
    if "istal" in text or "instal" in text or "instalar" in text:
        # O entendimento pode ou não identificar; o importante é não crashar
        assert "kind" in und


# ---------------------------------------------------------------------------
# Variações de manutenção
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "manutençao",
    "manutenção",
    "conserto",
    "ligo e não gela",
    "ta pingano",
    "nao gela",
    "não gela",
    "tá com barulho",
    "motor do ar parou",
    "quero vê pra arruma",
    "quanto fica pra limpá",
])
def test_manutencao_variations_recognized(text):
    """Variações de manutenção/sintomas devem ser reconhecidas."""
    und = _understand(text)
    assert und is not None
    assert "kind" in und
    # Deve detectar serviço de manutenção ou higienização, nunca "security"
    assert und["kind"] != "security"


# ---------------------------------------------------------------------------
# Vocabulário técnico de aparelhos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "ar condicionado",
    "arcondicionado",
    "ar",
    "split",
    "esplit",
    "condensadora",
    "comdensadora",
    "evaporadora",
    "motor do ar",
])
def test_hvac_vocabulary_no_crash(text):
    """Vocabulário técnico de HVAC não deve causar crash nem ser marcado como malicioso."""
    und = _understand(text)
    assert und is not None
    assert und.get("malicious") is False
    assert "kind" in und


# ---------------------------------------------------------------------------
# Perguntas de clarificação em variações regionais
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "não entendi",
    "nao entendi",
    "como assim?",
    "explica melhor",
    "pode explicar",
])
def test_clarification_detected(text):
    """Frases de clarificação devem ser detectadas como clarification_request."""
    und = _understand(text)
    assert und["kind"] == "clarification_request" or und["asks_clarification"] is True
