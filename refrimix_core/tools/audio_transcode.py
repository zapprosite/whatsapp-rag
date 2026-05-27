"""Audio Transcode — WAV↔MP3↔OGG/Opus via ffmpeg.

WhatsApp accepts MP3 and OGG/Opus natively. WAV works but gets
rechunked by WhatsApp servers (potential quality loss).

This module provides:
- MIME detection from file header
- WAV → MP3 conversion (64kbps, mono, 16kHz)
- WAV → OGG/Opus conversion (64kbps, mono, 16kHz, WhatsApp-optimized)
- Quick check if a MIME type is WhatsApp-compatible
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


logger = logging.getLogger(__name__)

# WhatsApp-supported MIME types ( Evolution API sendWhatsAppAudio )
WHATSAPP_SUPPORTED_MIMES = {"audio/mpeg", "audio/ogg", "audio/ogg; codecs=opus", "audio/wav"}
PREFERRED_MIME = "audio/ogg; codecs=opus"
FALLBACK_MIME = "audio/mpeg"

# ffmpeg audio quality settings optimized for voice on WhatsApp
# 64kbps mono 16kHz — small, clear, fast to transcode
OGG_OPUS_PARAMS = ["-c:a", "libopus", "-b:a", "64k", "-ar", "16000", "-ac", "1", "-application", "voip"]
MP3_PARAMS = ["-c:a", "libmp3lame", "-b:a", "64k", "-ar", "16000", "-ac", "1"]


def _get_ffmpeg_path() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def detect_mime_from_file(file_path: str) -> str | None:
    """Detect MIME type from file magic bytes.

    Reads the first 12 bytes and checks known WAV/MP3/OGG signatures.
    Returns None if unknown.
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(12)

        if header[:3] == b"ID3" or (
            header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
        ):
            return "audio/mpeg"  # MP3
        if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
            return "audio/wav"  # WAV
        if header[:4] == b"OggS":
            return "audio/ogg; codecs=opus"  # OGG/Opus
        return None
    except OSError:
        return None


def is_whatsapp_compatible(mime: str) -> bool:
    """Check if MIME type is accepted by WhatsApp via Evolution API."""
    return mime in WHATSAPP_SUPPORTED_MIMES


def _run_ffmpeg(
    input_bytes: bytes,
    output_ext: str,
    ffmpeg_params: list[str],
    timeout: float = 15.0,
) -> bytes | None:
    """Run ffmpeg to convert audio bytes to the target format.

    Args:
        input_bytes: raw audio bytes (WAV assumed)
        output_ext: .mp3 or .ogg
        ffmpeg_params: ffmpeg argument list for the target codec
        timeout: max seconds for ffmpeg to run

    Returns:
        Transcoded audio bytes or None on failure.
    """
    ffmpeg_path = _get_ffmpeg_path()
    if not Path(ffmpeg_path).exists() and ffmpeg_path == "ffmpeg":
        logger.error("ffmpeg not found in PATH")
        return None

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as inp:
        inp.write(input_bytes)
        inp.flush()
        inp_path = inp.name

    out_path = tempfile.mktemp(suffix=output_ext)

    try:
        cmd = [ffmpeg_path, "-y", "-i", inp_path, *ffmpeg_params, out_path]
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            logger.warning("ffmpeg transcode failed: %s", result.stderr[:200])
            return None
        with open(out_path, "rb") as f:
            return f.read()
    except subprocess.TimeoutExpired:
        logger.warning("ffmpeg timeout after %.1fs", timeout)
        return None
    except OSError as e:
        logger.error("ffmpeg transcode OSError: %s", e)
        return None
    finally:
        for p in (inp_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def wav_to_ogg_opus(wav_bytes: bytes) -> bytes | None:
    """Convert WAV bytes to OGG/Opus 16kHz mono 64kbps (WhatsApp-preferred).

    Returns the original WAV bytes if transcode fails.
    """
    result = _run_ffmpeg(wav_bytes, ".ogg", OGG_OPUS_PARAMS)
    if result is None:
        logger.warning("WAV→OGG/Opus transcode failed; returning original WAV")
        return wav_bytes
    return result


def wav_to_mp3(wav_bytes: bytes) -> bytes | None:
    """Convert WAV bytes to MP3 16kHz mono 64kbps.

    Returns None if transcode fails.
    """
    return _run_ffmpeg(wav_bytes, ".mp3", MP3_PARAMS)


def wav_to_whatsapp_optimal(wav_bytes: bytes) -> tuple[bytes, str]:
    """Convert WAV bytes to WhatsApp-optimal format.

    Tries OGG/Opus first (WhatsApp preferred), falls back to MP3,
    falls back to original WAV.

    Returns:
        (transcoded_bytes, mime_type_string)
    """
    ogg = wav_to_ogg_opus(wav_bytes)
    if ogg and detect_mime_from_bytes(ogg) == "audio/ogg; codecs=opus":
        return ogg, "audio/ogg; codecs=opus"

    mp3 = wav_to_mp3(wav_bytes)
    if mp3:
        return mp3, "audio/mpeg"

    return wav_bytes, "audio/wav"


def detect_mime_from_bytes(audio_bytes: bytes) -> str | None:
    """Detect MIME type from raw bytes (first 12 bytes)."""
    if len(audio_bytes) < 12:
        return None

    header = audio_bytes[:12]

    if header[:3] == b"ID3" or (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "audio/wav"
    if header[:4] == b"OggS":
        return "audio/ogg; codecs=opus"
    return None
