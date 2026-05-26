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


def base_lead_state(**kwargs) -> dict[str, Any]:
    ls = nodes._lead_state_copy()
    ls.update(kwargs)
    return ls


# ── Utilitários ────────────────────────────────────────────────────────────


def test_is_media_placeholder_audio():
    assert nodes._is_media_placeholder("[áudio]")
    assert nodes._is_media_placeholder("[audio]")
    assert nodes._is_media_placeholder("áudio")
    assert nodes._is_media_placeholder("audio")
    assert not nodes._is_media_placeholder("Santos")
    assert not nodes._is_media_placeholder("manutenção")


def test_is_media_placeholder_imagem():
    assert nodes._is_media_placeholder("[imagem]")
    assert nodes._is_media_placeholder("[image]")
    assert nodes._is_media_placeholder("imagem")
    assert not nodes._is_media_placeholder("foto")


def test_is_invalid_structured_value_common():
    assert nodes._is_invalid_structured_value(None)
    assert nodes._is_invalid_structured_value("")
    assert nodes._is_invalid_structured_value("[áudio]")
    assert nodes._is_invalid_structured_value("local informado")
    assert nodes._is_invalid_structured_value("unknown")
    assert not nodes._is_invalid_structured_value("Santos")
    assert not nodes._is_invalid_structured_value("Guarujá")


# ── Sanitização de lead_state ─────────────────────────────────────────────


def test_sanitize_lead_state_clears_audio_city():
    ls = base_lead_state(cidade_bairro="[áudio]", appointment_ready=True, appointment_score=7)
    result = nodes.sanitize_lead_state(ls)
    assert result["cidade_bairro"] is None
    assert result["appointment_ready"] is False


def test_sanitize_lead_state_keeps_valid_city():
    ls = base_lead_state(cidade_bairro="Santos")
    result = nodes.sanitize_lead_state(ls)
    assert result["cidade_bairro"] == "Santos"


def test_sanitize_lead_state_clears_pipeline_stage_when_city_invalid():
    ls = base_lead_state(cidade_bairro="[imagem]", pipeline_stage="ready_to_schedule")
    result = nodes.sanitize_lead_state(ls)
    assert result["pipeline_stage"] == "qualifying_lead"


# ── state_patch não deve salvar placeholder ────────────────────────────────


def test_clean_state_patch_value_drops_audio():
    assert nodes._clean_state_patch_value("cidade_bairro", "[áudio]") is None
    assert nodes._clean_state_patch_value("cidade_bairro", "[imagem]") is None
    assert nodes._clean_state_patch_value("nome", "unknown") is None


def test_clean_state_patch_value_keeps_valid():
    assert nodes._clean_state_patch_value("cidade_bairro", "Guarujá") == "Guarujá"
    assert nodes._clean_state_patch_value("btus", "12000") == "12000"


# ── Falha STT: marker é retornado, não o placeholder ──────────────────────


def test_audio_transcription_failed_intent(monkeypatch):
    async def stt_fail(*args, **kwargs):
        raise RuntimeError("Groq timeout")

    monkeypatch.setattr("agent_graph.services.stt.transcribe_audio", stt_fail, raising=False)

    state = {
        "messages": [HumanMessage(content="[áudio]")],
        "message_type": "audioMessage",
        "media_url": "http://fake/audio.ogg",
        "media_base64": "",
        "msg_id": "fake123",
        "instance": "test",
        "customer_data": {"phone": "+5513000000001", "diagnostic_mode": False},
        "lead_state": nodes._lead_state_copy(),
        "already_asked_fields": [],
        "missing_fields": ["tipo_servico", "cidade_bairro"],
        "do_not_ask": [],
        "conversation_summary": "",
    }

    result = run(nodes.preprocess_input(state))
    assert result.get("audio_transcription_failed") is True
    last_msg = result["messages"][-1]
    assert last_msg.content == "[AUDIO_TRANSCRIPTION_FAILED]"
    # Classify deve retornar intent dedicado
    classify_result = run(nodes.classify_service(result))
    assert classify_result["intent"] == "audio_transcription_failed"


def test_audio_transcription_failed_generate_response_asks_text(monkeypatch):
    state = {
        "messages": [HumanMessage(content="[AUDIO_TRANSCRIPTION_FAILED]")],
        "intent": "audio_transcription_failed",
        "service": None,
        "outcome": "duvida",
        "handoff_mode": "none",
        "handoff_reason": None,
        "rag_context": [],
        "lead_state": nodes._lead_state_copy(),
        "customer_data": {"phone": "+5513000000001"},
        "is_human": False,
        "audio_transcription_failed": True,
    }
    result = run(nodes.generate_response(state))
    resp = last_ai(result["messages"])
    assert "[áudio]" not in resp
    assert "[AUDIO_TRANSCRIPTION_FAILED]" not in resp
    assert "texto" in resp.lower() or "mandar" in resp.lower()
