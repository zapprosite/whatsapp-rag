"""Audio Delivery Policy — decide how to send audio to WhatsApp.

WhatsApp supports audio via Evolution API with specific MIME types.
This module validates MIME compatibility and routes to the appropriate
send method, with fallback to text when audio is unsuitable.

Rules:
- WAV 16kHz mono is the internal TTS format (from Edge TTS, Chatterbox, OmniVoice).
- WhatsApp prefers MP3 or OGG/Opus over raw WAV.
- Audio must not exceed TTS_MAX_CHARS/TTS_MAX_SECONDS limits.
- Blocked document types always fall back to text.
- On send failure, fall back to text.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


logger = logging.getLogger(__name__)


class AudioMimeType(str, Enum):
    """Supported audio MIME types for WhatsApp via Evolution API."""
    WAV = "audio/wav"
    MP3 = "audio/mpeg"
    OGG_OPUS = "audio/ogg; codecs=opus"
    OGG = "audio/ogg"


class AudioDeliveryReason(str, Enum):
    """Why audio was (or wasn't) sent."""
    SENT_MP3 = "sent_mp3"
    SENT_OGG_OPUS = "sent_ogg_opus"
    SENT_WAV = "sent_wav"  # discouraged but accepted
    BLOCKED_DOC_TYPE = "blocked_doc_type"
    BLOCKED_TOO_LONG = "blocked_too_long"
    BLOCKED_SEND_FAILED = "blocked_send_failed"
    BLOCKED_NO_MIME_SUPPORT = "blocked_no_mime_support"
    BLOCKED_USER_PREFERS_TEXT = "blocked_user_prefers_text"
    TEXT_FALLBACK = "text_fallback"


@dataclass(frozen=True)
class AudioDeliveryDecision:
    should_send_audio: bool
    mime_type: AudioMimeType | None
    reason: AudioDeliveryReason
    local_path: str | None = None  # path sent or would-be path
    fallback_text: str | None = None


# WhatsApp officially supports MP3 and OGG (Opus) via document and audio messages.
# WAV works but is not ideal (large file, may be rechunked by WhatsApp servers).
SUPPORTED_MIMES = {
    AudioMimeType.MP3,
    AudioMimeType.OGG_OPUS,
    AudioMimeType.OGG,
    AudioMimeType.WAV,
}

# Evolution API / WhatsApp native audio message MIME types
PREFERRED_MIMES = {AudioMimeType.MP3, AudioMimeType.OGG_OPUS}

# MIME → file extension
MIME_TO_EXT = {
    AudioMimeType.WAV: ".wav",
    AudioMimeType.MP3: ".mp3",
    AudioMimeType.OGG_OPUS: ".ogg",
    AudioMimeType.OGG: ".ogg",
}


def _get_max_chars() -> int:
    try:
        return int(os.getenv("TTS_MAX_CHARS", "420"))
    except (ValueError, TypeError):
        return 420


def _get_max_seconds() -> int:
    try:
        return int(os.getenv("TTS_MAX_SECONDS", "35"))
    except (ValueError, TypeError):
        return 35


def _mime_to_ext(mime: AudioMimeType) -> str:
    return MIME_TO_EXT.get(mime, ".wav")


def should_send_audio(
    text: str,
    action_type: str,
    document_type: str | None = None,
    user_prefers_text: bool = False,
    local_audio_path: str | None = None,
    detected_mime: AudioMimeType | None = None,
) -> AudioDeliveryDecision:
    """Decide whether to send audio and with which MIME type.

    Args:
        text: original message text
        action_type: business action type (microcopy, schedule_confirmation, etc.)
        document_type: optional PDF/doc type
        user_prefers_text: explicit user preference
        local_audio_path: path to the WAV audio file
        detected_mime: MIME type detected from the audio file

    Returns:
        AudioDeliveryDecision with routing info
    """
    max_chars = _get_max_chars()
    max_seconds = _get_max_seconds()

    # Step 1: user preference
    if user_prefers_text:
        return AudioDeliveryDecision(
            should_send_audio=False,
            mime_type=None,
            reason=AudioDeliveryReason.BLOCKED_USER_PREFERS_TEXT,
            fallback_text=text,
        )

    # Step 2: document type block
    from refrimix_core.domain.tts_policy import BLOCKED_DOC_TYPES

    if document_type in BLOCKED_DOC_TYPES:
        logger.info(
            "Audio delivery blocked: document_type=%s",
            document_type,
            extra={"audio_delivery_reason": AudioDeliveryReason.BLOCKED_DOC_TYPE},
        )
        return AudioDeliveryDecision(
            should_send_audio=False,
            mime_type=None,
            reason=AudioDeliveryReason.BLOCKED_DOC_TYPE,
            fallback_text=text,
        )

    # Step 3: text length
    stripped = text.strip()
    if not stripped or len(stripped) > max_chars:
        return AudioDeliveryDecision(
            should_send_audio=False,
            mime_type=None,
            reason=AudioDeliveryReason.BLOCKED_TOO_LONG,
            fallback_text=text,
        )

    # Step 4: no audio path provided
    if not local_audio_path or not Path(local_audio_path).exists():
        logger.warning("Audio file not found: %s", local_audio_path)
        return AudioDeliveryDecision(
            should_send_audio=False,
            mime_type=None,
            reason=AudioDeliveryReason.BLOCKED_SEND_FAILED,
            fallback_text=text,
        )

    # Step 5: MIME routing
    if detected_mime is None:
        # Default to WAV if not detected (TTSService always produces WAV)
        detected_mime = AudioMimeType.WAV

    # Prefer OGG/Opus or MP3; fall back to WAV if neither is available
    if detected_mime in PREFERRED_MIMES:
        return AudioDeliveryDecision(
            should_send_audio=True,
            mime_type=detected_mime,
            reason=AudioDeliveryReason.SENT_OGG_OPUS
            if detected_mime == AudioMimeType.OGG_OPUS
            else AudioDeliveryReason.SENT_MP3,
            local_path=local_audio_path,
        )

    # WAV detected — acceptable but large; WhatsApp may rechunk it
    if detected_mime == AudioMimeType.WAV:
        logger.debug("Sending WAV directly (will be rechunked by WhatsApp servers)")
        return AudioDeliveryDecision(
            should_send_audio=True,
            mime_type=AudioMimeType.WAV,
            reason=AudioDeliveryReason.SENT_WAV,
            local_path=local_audio_path,
        )

    # Unknown MIME — block and fallback to text
    logger.warning("Unsupported MIME type: %s", detected_mime)
    return AudioDeliveryDecision(
        should_send_audio=False,
        mime_type=None,
        reason=AudioDeliveryReason.BLOCKED_NO_MIME_SUPPORT,
        fallback_text=text,
    )
