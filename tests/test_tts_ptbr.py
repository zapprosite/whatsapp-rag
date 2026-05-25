from __future__ import annotations

import asyncio

from agent_graph.services.tts import (
    TTSService,
    _normalize_tts_text_ptbr,
    _truncate_for_audio,
    should_respond_with_audio,
)


def run(coro):
    return asyncio.run(coro)


def test_tts_normalizes_written_ptbr_for_speech():
    text = _normalize_tts_text_ptbr(
        "Instalação fica R$ 850,00 em 3x no PIX. PMOC, ART, CREA e 12.000 BTUs: https://x.test"
    )

    assert "oitocentos e cinquenta reais" in text
    assert "três vezes" in text
    assert "Pix" in text
    assert "pê ême ô cê" in text
    assert "a erre tê" in text
    assert "CREA" in text
    assert "bê tê us" in text
    assert "link" in text


def test_tts_truncates_at_sentence_boundary():
    text = "Primeira frase curta. " + ("segunda " * 80)

    truncated = _truncate_for_audio(text, 80)

    assert truncated == "Primeira frase curta."


def test_chatterbox_falls_back_to_omnivoice_without_xtts(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "chatterbox")
    monkeypatch.setenv("TTS_LOCALE", "pt-BR")
    monkeypatch.setenv("TTS_ALLOW_CHATTERBOX_PTBR", "1")
    service = TTSService()

    async def no_audio(text: str, voice_style: str) -> bytes | None:
        return None

    async def omni_audio(text: str, voice_style: str) -> bytes | None:
        assert "pê ême ô cê" in text
        return b"o" * 1024

    monkeypatch.setattr(service, "_synthesize_chatterbox", no_audio)
    monkeypatch.setattr(service, "_synthesize_omnivoice", omni_audio)

    assert run(service.synthesize("Preciso de PMOC", "influencer")) == b"o" * 1024


def test_omnivoice_falls_back_to_chatterbox_without_xtts(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "omnivoice")
    monkeypatch.setenv("TTS_LOCALE", "pt-BR")
    monkeypatch.setenv("TTS_ALLOW_CHATTERBOX_PTBR", "1")
    service = TTSService()

    async def no_audio(text: str, voice_style: str) -> bytes | None:
        return None

    async def chatterbox_audio(text: str, voice_style: str) -> bytes | None:
        return b"c" * 1024

    monkeypatch.setattr(service, "_synthesize_omnivoice", no_audio)
    monkeypatch.setattr(service, "_synthesize_chatterbox", chatterbox_audio)

    assert run(service.synthesize("Oi, tudo bem?", "influencer")) == b"c" * 1024


def test_xtts_engine_name_is_pruned_and_uses_safe_chain(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "xtts")
    monkeypatch.setenv("TTS_ALLOW_CHATTERBOX_PTBR", "1")
    service = TTSService()

    async def chatterbox_audio(text: str, voice_style: str) -> bytes | None:
        return b"x" * 1024

    monkeypatch.setattr(service, "_synthesize_chatterbox", chatterbox_audio)

    assert run(service.synthesize("Preciso de PMOC", "influencer")) == b"x" * 1024


def test_chatterbox_ptbr_is_guarded_and_falls_back_to_omnivoice(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "chatterbox")
    monkeypatch.setenv("TTS_LOCALE", "pt-BR")
    monkeypatch.setenv("TTS_ALLOW_CHATTERBOX_PTBR", "0")
    service = TTSService()

    async def omni_audio(text: str, voice_style: str) -> bytes | None:
        return b"o" * 1024

    monkeypatch.setattr(service, "_synthesize_omnivoice", omni_audio)

    assert run(service.synthesize("Opa, beleza?", "influencer")) == b"o" * 1024


def test_audio_intent_recognizes_modern_brazilian_greetings():
    assert should_respond_with_audio("conversation", None, None, "opa, tudo bem?")
    assert should_respond_with_audio("conversation", None, None, "fala Will, beleza?")
