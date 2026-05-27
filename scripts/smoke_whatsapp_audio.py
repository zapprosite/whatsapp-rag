#!/usr/bin/env .venv/bin/python
r"""Smoke test for WhatsApp audio delivery pipeline.

CONFIRM_WHATSAPP_AUDIO_TEST=1  →  runs full end-to-end including real WhatsApp send
Default / CI                    →  TTS + transcode only, no WhatsApp send

Usage:
    # Dry-run (TTS + transcode, no WhatsApp):
    .venv/bin/python scripts/smoke_whatsapp_audio.py

    # Real send (requires active WhatsApp session):
    CONFIRM_WHATSAPP_AUDIO_TEST=1 .venv/bin/python scripts/smoke_whatsapp_audio.py

Environment:
    TTS_ENGINE=edge
    TTS_EDGE_VOICE=pt-BR-ThalitaMultilingualNeural
    EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import sys
import tempfile
from pathlib import Path

# ── paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
logger = logging.getLogger("smoke_whatsapp_audio")


# ── test phrases ─────────────────────────────────────────────────────────────
TEST_PHRASES = [
    "bom dia, tudo joia?",
    "visita confirmada para amanhã às 14h.",
    "manter equipamento desligado até avaliação.",
    "fechado. a visita técnica fica cinquenta reais.",
]

# Phrases that must NOT be sent as audio
BLOCKED_PHRASES = [
    ("orçamento detalhado com todos os itens", "quote_pdf"),
    ("relatório de manutenção preventiva obligatorio", "pmoc_pdf"),
    ("a" * 500, "too_long"),
]


def _get_test_phone() -> str:
    return os.getenv("WHATSAPP_TEST_PHONE", os.getenv("EVOLUTION_TEST_PHONE", "5511999999999"))


def _get_instance() -> str:
    return os.getenv("EVOLUTION_INSTANCE", "default")


async def _smoke_tts_and_transcode() -> bool:
    """TTS synthesis + MIME detection + transcode. No WhatsApp send."""
    from refrimix_core.tools.audio_transcode import (
        detect_mime_from_bytes,
        wav_to_whatsapp_optimal,
        is_whatsapp_compatible,
    )

    all_ok = True

    for phrase in TEST_PHRASES:
        logger.info("=== TTS + transcode: %s", phrase[:50])
        try:
            # Synthesize via Edge TTS
            audio_bytes = await _synthesize_test(phrase)
            if not audio_bytes:
                logger.error("TTS failed for: %s", phrase[:50])
                all_ok = False
                continue

            # Detect MIME
            mime = detect_mime_from_bytes(audio_bytes)
            logger.info("  MIME detectado: %s (bytes=%d)", mime, len(audio_bytes))

            # Transcode to WhatsApp-optimal
            optimal_bytes, optimal_mime = wav_to_whatsapp_optimal(audio_bytes)
            logger.info(
                "  Ótimo: mime=%s bytes=%d whatsapp_compatible=%s",
                optimal_mime,
                len(optimal_bytes),
                is_whatsapp_compatible(optimal_mime),
            )

            # Validate
            if not is_whatsapp_compatible(optimal_mime):
                logger.error("  FALHA: MIME %s não é compatível com WhatsApp", optimal_mime)
                all_ok = False
            else:
                logger.info("  OK")

        except Exception as e:
            logger.error("  ERRO: %s", e)
            all_ok = False

    return all_ok


async def _synthesize_test(text: str) -> bytes | None:
    """Synthesize text via Edge TTS (sync, non-cached for smoke test)."""
    try:
        import edge_tts

        voice = os.getenv("TTS_EDGE_VOICE", "pt-BR-ThalitaMultilingualNeural")
        speed = os.getenv("TTS_EDGE_SPEED", "+0%")

        mp3_path = tempfile.mktemp(suffix=".mp3")
        wav_path = tempfile.mktemp(suffix=".wav")

        try:
            communicate = edge_tts.Communicate(text, voice=voice, rate=speed)
            await communicate.save(mp3_path)

            import subprocess

            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", mp3_path,
                    "-ar", "16000", "-ac", "1",
                    "-c:a", "pcm_s16le",
                    wav_path,
                ],
                capture_output=True,
                timeout=15,
            )
            if result.returncode != 0:
                return None

            with open(wav_path, "rb") as f:
                return f.read()

        finally:
            for p in (mp3_path, wav_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    except Exception as e:
        logger.error("Edge TTS smoke failed: %s", e)
        return None


async def _smoke_delivery_policy() -> bool:
    """Smoke the delivery policy decisions."""
    from refrimix_core.domain.audio_delivery_policy import should_send_audio

    all_ok = True

    # Allowed phrases
    for phrase in TEST_PHRASES:
        wav_path = _make_minimal_wav()
        decision = should_send_audio(
            text=phrase,
            action_type="microcopy",
            local_audio_path=wav_path,
        )
        if not decision.should_send_audio:
            logger.error("  FALHA policy: %s foi bloqueado (expected allow)", phrase[:40])
            all_ok = False
        else:
            logger.info("  OK policy allow: %s", phrase[:40])
        Path(wav_path).unlink(missing_ok=True)

    # Blocked phrases
    for phrase, doc_type in BLOCKED_PHRASES:
        wav_path = _make_minimal_wav()
        dt = doc_type if doc_type != "too_long" else None
        decision = should_send_audio(
            text=phrase,
            action_type="microcopy",
            document_type=dt,
            local_audio_path=wav_path,
        )
        if decision.should_send_audio:
            logger.error("  FALHA policy: %s foi permitido (expected block)", phrase[:40])
            all_ok = False
        else:
            logger.info("  OK policy block: %s (%s)", phrase[:40], decision.reason)
        Path(wav_path).unlink(missing_ok=True)

    return all_ok


def _make_minimal_wav() -> str:
    """Create a minimal valid WAV file and return its path."""
    wav = (
        b"RIFF"
        + (128 - 8).to_bytes(4, "little")
        + b"WAVE"
        + b"fmt "
        + (16).to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + (16000).to_bytes(4, "little")
        + (32000).to_bytes(4, "little")
        + (2).to_bytes(2, "little")
        + (16).to_bytes(2, "little")
        + b"data"
        + (128 - 44).to_bytes(4, "little")
        + b"\x00" * (128 - 44)
    )
    path = tempfile.mktemp(suffix=".wav")
    with open(path, "wb") as f:
        f.write(wav)
    return path


async def _smoke_whatsapp_send(audio_bytes: bytes, mime: str) -> bool:
    """Send real audio to WhatsApp via Evolution API. Only if CONFIRM_WHATSAPP_AUDIO_TEST=1."""
    import httpx

    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    api_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
    instance = _get_instance()
    phone = _get_test_phone()

    # OGG/Opus → base64 for Evolution API
    audio_b64 = base64.b64encode(audio_bytes).decode()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_url}/message/sendWhatsAppAudio/{instance}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"number": phone, "audio": audio_b64},
            )
            if resp.status_code in (200, 201):
                logger.info("WhatsApp send OK: %s bytes to %s", len(audio_bytes), phone)
                return True
            logger.error("WhatsApp send failed %s: %s", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        logger.error("WhatsApp send exception: %s", e)
        return False


async def main() -> int:
    logger.info("WhatsApp Audio Delivery Smoke Test")
    logger.info("CONFIRM_WHATSAPP_AUDIO_TEST=%s", os.getenv("CONFIRM_WHATSAPP_AUDIO_TEST", "not set"))

    # 1. Policy smoke
    logger.info("\n=== [1/3] Delivery Policy smoke ===")
    policy_ok = await _smoke_delivery_policy()
    logger.info("Policy: %s", "PASS" if policy_ok else "FAIL")

    # 2. TTS + transcode smoke
    logger.info("\n=== [2/3] TTS + Transcode smoke ===")
    tts_ok = await _smoke_tts_and_transcode()
    logger.info("TTS+Transcode: %s", "PASS" if tts_ok else "FAIL")

    # 3. Real WhatsApp send (only with flag)
    confirm = os.getenv("CONFIRM_WHATSAPP_AUDIO_TEST", "0").strip() in {"1", "true", "yes", "on"}
    whatsapp_ok = True
    if confirm:
        logger.info("\n=== [3/3] Real WhatsApp send (CONFIRM_WHATSAPP_AUDIO_TEST=1) ===")
        phrase = TEST_PHRASES[0]
        audio_bytes = await _synthesize_test(phrase)
        if audio_bytes:
            from refrimix_core.tools.audio_transcode import wav_to_whatsapp_optimal
            optimal_bytes, optimal_mime = wav_to_whatsapp_optimal(audio_bytes)
            whatsapp_ok = await _smoke_whatsapp_send(optimal_bytes, optimal_mime)
        else:
            whatsapp_ok = False
        logger.info("WhatsApp send: %s", "PASS" if whatsapp_ok else "FAIL")
    else:
        logger.info("\n=== [3/3] WhatsApp send SKIPPED (need CONFIRM_WHATSAPP_AUDIO_TEST=1) ===")

    all_ok = policy_ok and tts_ok and whatsapp_ok
    logger.info("\n=== RESULT: %s ===", "ALL PASS" if all_ok else "SOME FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
