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
    assert "P M O C" in text
    assert "A R T" in text
    assert "C R E A" in text
    assert "B T U" in text
    assert "link" in text


def test_tts_truncates_at_sentence_boundary():
    text = "Primeira frase curta. " + ("segunda " * 80)

    truncated = _truncate_for_audio(text, 80)

    assert truncated == "Primeira frase curta."


def test_omnivoice_does_not_fallback_to_generic_xtts_for_ptbr(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "omnivoice")
    monkeypatch.setenv("TTS_LOCALE", "pt-BR")
    monkeypatch.setenv("TTS_ALLOW_XTTS_PT_FALLBACK", "0")
    service = TTSService()

    async def no_audio(text: str, voice_style: str) -> bytes | None:
        return None

    async def forbidden_xtts(text: str, voice_style: str) -> bytes | None:
        raise AssertionError("XTTS fallback must stay disabled for pt-BR")

    monkeypatch.setattr(service, "_synthesize_omnivoice", no_audio)
    monkeypatch.setattr(service, "_synthesize_xtts", forbidden_xtts)

    assert run(service.synthesize("Oi, tudo bem?", "influencer")) is None


def test_omnivoice_can_use_xtts_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("TTS_ENGINE", "omnivoice")
    monkeypatch.setenv("TTS_LOCALE", "pt-BR")
    monkeypatch.setenv("TTS_ALLOW_XTTS_PT_FALLBACK", "1")
    service = TTSService()

    async def no_audio(text: str, voice_style: str) -> bytes | None:
        return None

    async def xtts_audio(text: str, voice_style: str) -> bytes | None:
        assert "P M O C" in text
        return b"x" * 1024

    monkeypatch.setattr(service, "_synthesize_omnivoice", no_audio)
    monkeypatch.setattr(service, "_synthesize_xtts", xtts_audio)

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
