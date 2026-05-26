"""
tests/test_audio_stt_quantity.py
Valida que transcrições de áudio (STT simulado) são processadas pelo mesmo pipeline de texto
e que a quantidade de aparelhos é salva corretamente a partir de áudio.
"""
from __future__ import annotations

import asyncio
import os
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from agent_graph.nodes.nodes import _lead_state_copy
from agent_graph.nodes.reduce_lead_state import reduce_lead_state
from agent_graph.services.tts import should_respond_with_audio


def run(coro):
    return asyncio.run(coro)


def _state_audio(transcript: str) -> dict:
    """Simula estado de entrada de áudio com transcript STT."""
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "higienizacao"
    lead_state["last_asked_field"] = "quantidade_aparelhos"
    return {
        "lead_state": lead_state,
        # O pipeline injeta o transcript como content da mensagem, igual ao texto
        "messages": [MagicMock(content=transcript)],
        "message_understanding": {"kind": "unknown"},
        "message_type": "audioMessage",
        "customer_data": {},
    }


# ---------------------------------------------------------------------------
# Quantidade via áudio (transcript simulado)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("transcript,expected", [
    ("um", 1),
    ("só um", 1),
    ("dois", 2),
    ("é só um aparelho", 1),
    ("tenho 2 aparelhos", 2),
    ("três", 3),
    ("1", 1),
])
def test_quantity_audio_transcript(transcript, expected):
    """Transcript de áudio deve ser reduzido pelo mesmo reducer de texto."""
    state = _state_audio(transcript)
    result = run(reduce_lead_state(state))
    assert result["lead_state"]["higienizacao"]["quantidade_aparelhos"] == expected, (
        f"transcript='{transcript}' esperava {expected}, "
        f"obteve {result['lead_state'].get('higienizacao', {}).get('quantidade_aparelhos')}"
    )
    assert result["short_answer_applied"] is True


# ---------------------------------------------------------------------------
# TTS_ENABLED controla a modalidade de resposta
# ---------------------------------------------------------------------------

def test_tts_disabled_text_input_always_text():
    """Com TTS_ENABLED=0, entrada de texto deve responder texto."""
    os.environ["TTS_ENABLED"] = "0"
    assert should_respond_with_audio("conversation", None, None) is False


def test_tts_enabled_audio_input_responds_audio():
    """Com TTS_ENABLED=1, entrada de áudio deve responder em áudio."""
    os.environ["TTS_ENABLED"] = "1"
    assert should_respond_with_audio("audioMessage", None, None) is True


def test_tts_enabled_text_input_still_text():
    """Com TTS_ENABLED=1, entrada de texto deve continuar respondendo texto."""
    os.environ["TTS_ENABLED"] = "1"
    assert should_respond_with_audio("conversation", None, None) is False


def test_tts_disabled_audio_input_responds_text():
    """Com TTS_ENABLED=0, entrada de áudio deve responder texto (TTS desligado)."""
    os.environ["TTS_ENABLED"] = "0"
    assert should_respond_with_audio("audioMessage", None, None) is False
