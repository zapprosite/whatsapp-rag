"""
tests/test_short_answer_fields.py
Valida que respostas curtas de quantidade de aparelhos (dígito ou extenso) são aplicadas corretamente.
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from agent_graph.nodes.nodes import _lead_state_copy
from agent_graph.nodes.reduce_lead_state import apply_short_answer_to_last_asked_field, reduce_lead_state


def run(coro):
    return asyncio.run(coro)


def _state_with_qty_ask(text: str) -> dict:
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "higienizacao"
    lead_state["last_asked_field"] = "quantidade_aparelhos"
    return {
        "lead_state": lead_state,
        "messages": [MagicMock(content=text)],
        "message_understanding": {"kind": "unknown"},
        "message_type": "conversation",
        "customer_data": {},
    }


# ---------------------------------------------------------------------------
# Testes com dígito
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("1", 1),
    ("01", 1),
    ("2", 2),
    ("3", 3),
    ("são 3 aparelhos split", 3),
    ("tenho 5 aparelhos", 5),
])
def test_quantity_digit(text, expected):
    """Dígito numérico após pergunta de quantidade deve ser salvo corretamente."""
    state = _state_with_qty_ask(text)
    result = run(reduce_lead_state(state))
    assert result["lead_state"]["higienizacao"]["quantidade_aparelhos"] == expected
    assert result["short_answer_applied"] is True


# ---------------------------------------------------------------------------
# Testes com palavra por extenso
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("um", 1),
    ("uma", 1),
    ("dois", 2),
    ("duas", 2),
    ("três", 3),
    ("tres", 3),
    ("quatro", 4),
    ("cinco", 5),
    ("dez", 10),
])
def test_quantity_word(text, expected):
    """Palavra por extenso após pergunta de quantidade deve ser salva corretamente."""
    state = _state_with_qty_ask(text)
    result = run(reduce_lead_state(state))
    assert result["lead_state"]["higienizacao"]["quantidade_aparelhos"] == expected
    assert result["short_answer_applied"] is True


# ---------------------------------------------------------------------------
# Testes com frases completas brasileiras
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("tenho um", 1),
    ("só um", 1),
    ("é um só", 1),
    ("é só um aparelho", 1),
    ("tenho dois aparelhos", 2),
])
def test_quantity_phrase(text, expected):
    """Frases completas com número por extenso devem ser parseadas."""
    state = _state_with_qty_ask(text)
    result = run(reduce_lead_state(state))
    assert result["lead_state"]["higienizacao"]["quantidade_aparelhos"] == expected
    assert result["short_answer_applied"] is True


# ---------------------------------------------------------------------------
# Testes da função de aplicação direta
# ---------------------------------------------------------------------------

def test_apply_short_answer_direct_digit():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "higienizacao"
    applied = apply_short_answer_to_last_asked_field(lead_state, "quantidade_aparelhos", "1")
    assert applied is True
    assert lead_state["higienizacao"]["quantidade_aparelhos"] == 1


def test_apply_short_answer_direct_word():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "higienizacao"
    applied = apply_short_answer_to_last_asked_field(lead_state, "quantidade_aparelhos", "um")
    assert applied is True
    assert lead_state["higienizacao"]["quantidade_aparelhos"] == 1


def test_apply_short_answer_no_field():
    """Sem last_asked_field, não deve aplicar nada."""
    lead_state = _lead_state_copy()
    applied = apply_short_answer_to_last_asked_field(lead_state, None, "1")
    assert applied is False


def test_apply_short_answer_wrong_field():
    """Campo diferente de quantidade_aparelhos não deve aplicar número."""
    lead_state = _lead_state_copy()
    applied = apply_short_answer_to_last_asked_field(lead_state, "ponto_eletrico_exclusivo", "1")
    assert applied is False
