"""Tests for audio_delivery_policy."""

import pytest
from pathlib import Path
import tempfile

from refrimix_core.domain.audio_delivery_policy import (
    AudioDeliveryReason,
    AudioDeliveryDecision,
    AudioMimeType,
    PREFERRED_MIMES,
    SUPPORTED_MIMES,
    should_send_audio,
)


class TestShouldSendAudio:
    """Unit tests for the delivery decision logic."""

    def setup_method(self):
        """Create a real temp WAV file for path-based tests."""
        self.wav_path = tempfile.mktemp(suffix=".wav")
        # Write minimal WAV header (44 bytes) + dummy data
        wav_header = (
            b"RIFF"
            + (100 - 8).to_bytes(4, "little")
            + b"WAVE"
            + b"fmt "
            + (16).to_bytes(4, "little")
            + (1).to_bytes(2, "little")  # PCM
            + (1).to_bytes(2, "little")  # mono
            + (16000).to_bytes(4, "little")  # 16kHz
            + (32000).to_bytes(4, "little")  # bytes/sec
            + (2).to_bytes(2, "little")  # block align
            + (16).to_bytes(2, "little")  # bits/sample
            + b"data"
            + (100 - 44).to_bytes(4, "little")
            + b"\x00" * (100 - 44)
        )
        with open(self.wav_path, "wb") as f:
            f.write(wav_header)

    def teardown_method(self):
        Path(self.wav_path).unlink(missing_ok=True)

    def test_short_text_with_wav_allowed(self):
        decision = should_send_audio(
            text="bom dia, tudo joia?",
            action_type="microcopy",
            local_audio_path=self.wav_path,
            detected_mime=AudioMimeType.WAV,
        )
        assert decision.should_send_audio is True
        assert decision.mime_type == AudioMimeType.WAV
        assert decision.reason == AudioDeliveryReason.SENT_WAV

    def test_short_text_with_ogg_preferred(self):
        decision = should_send_audio(
            text="visita confirmada",
            action_type="schedule_confirmation",
            local_audio_path=self.wav_path,
            detected_mime=AudioMimeType.OGG_OPUS,
        )
        assert decision.should_send_audio is True
        assert decision.mime_type == AudioMimeType.OGG_OPUS
        assert decision.reason == AudioDeliveryReason.SENT_OGG_OPUS

    def test_short_text_with_mp3_allowed(self):
        decision = should_send_audio(
            text="te passo o horário",
            action_type="short_followup",
            local_audio_path=self.wav_path,
            detected_mime=AudioMimeType.MP3,
        )
        assert decision.should_send_audio is True
        assert decision.mime_type == AudioMimeType.MP3
        assert decision.reason == AudioDeliveryReason.SENT_MP3

    def test_long_text_blocked(self):
        long_text = "a" * 500
        decision = should_send_audio(
            text=long_text,
            action_type="microcopy",
            local_audio_path=self.wav_path,
            detected_mime=AudioMimeType.WAV,
        )
        assert decision.should_send_audio is False
        assert decision.reason == AudioDeliveryReason.BLOCKED_TOO_LONG

    def test_whitespace_only_blocked(self):
        decision = should_send_audio(
            text="   ",
            action_type="microcopy",
            local_audio_path=self.wav_path,
        )
        assert decision.should_send_audio is False
        assert decision.reason == AudioDeliveryReason.BLOCKED_TOO_LONG

    def test_quote_pdf_blocked(self):
        decision = should_send_audio(
            text="segue o orçamento",
            action_type="microcopy",
            document_type="quote_pdf",
            local_audio_path=self.wav_path,
        )
        assert decision.should_send_audio is False
        assert decision.reason == AudioDeliveryReason.BLOCKED_DOC_TYPE

    def test_pmoc_pdf_blocked(self):
        decision = should_send_audio(
            text="relatório pmoc",
            action_type="microcopy",
            document_type="pmoc_pdf",
            local_audio_path=self.wav_path,
        )
        assert decision.should_send_audio is False
        assert decision.reason == AudioDeliveryReason.BLOCKED_DOC_TYPE

    def test_contract_pdf_blocked(self):
        decision = should_send_audio(
            text="contrato de manutenção",
            action_type="microcopy",
            document_type="contract_pdf",
            local_audio_path=self.wav_path,
        )
        assert decision.should_send_audio is False
        assert decision.reason == AudioDeliveryReason.BLOCKED_DOC_TYPE

    def test_user_prefers_text_blocked(self):
        decision = should_send_audio(
            text="bom dia",
            action_type="microcopy",
            user_prefers_text=True,
            local_audio_path=self.wav_path,
        )
        assert decision.should_send_audio is False
        assert decision.reason == AudioDeliveryReason.BLOCKED_USER_PREFERS_TEXT

    def test_no_audio_path_blocked(self):
        decision = should_send_audio(
            text="bom dia",
            action_type="microcopy",
            local_audio_path=None,
        )
        assert decision.should_send_audio is False
        assert decision.reason == AudioDeliveryReason.BLOCKED_SEND_FAILED

    def test_nonexistent_path_blocked(self):
        decision = should_send_audio(
            text="bom dia",
            action_type="microcopy",
            local_audio_path="/nonexistent/path/audio.wav",
        )
        assert decision.should_send_audio is False
        assert decision.reason == AudioDeliveryReason.BLOCKED_SEND_FAILED

    def test_fallback_text_returned_when_blocked(self):
        text = "visita confirmada para amanhã"
        decision = should_send_audio(
            text=text,
            action_type="microcopy",
            document_type="contract_pdf",
            local_audio_path=self.wav_path,
        )
        assert decision.fallback_text == text

    def test_allowed_actions(self):
        allowed = ["welcome_onboarding", "microcopy", "schedule_confirmation",
                   "visit_orientation", "short_followup", "simple_ack"]
        for action in allowed:
            decision = should_send_audio(
                text="ok",
                action_type=action,
                local_audio_path=self.wav_path,
            )
            assert decision.should_send_audio is True, f"action={action}"

    def test_max_chars_boundary(self):
        # Exactly 420 — allowed
        decision_ok = should_send_audio(
            text="a" * 420,
            action_type="microcopy",
            local_audio_path=self.wav_path,
        )
        assert decision_ok.should_send_audio is True

        # 421 — blocked
        decision_fail = should_send_audio(
            text="a" * 421,
            action_type="microcopy",
            local_audio_path=self.wav_path,
        )
        assert decision_fail.should_send_audio is False
        assert decision_fail.reason == AudioDeliveryReason.BLOCKED_TOO_LONG


class TestAudioMimeTypes:
    def test_wav_is_supported(self):
        assert AudioMimeType.WAV in SUPPORTED_MIMES

    def test_mp3_is_supported(self):
        assert AudioMimeType.MP3 in SUPPORTED_MIMES

    def test_ogg_opus_is_preferred(self):
        assert AudioMimeType.OGG_OPUS in PREFERRED_MIMES

    def test_mp3_is_preferred(self):
        assert AudioMimeType.MP3 in PREFERRED_MIMES

    def test_wav_not_in_preferred(self):
        assert AudioMimeType.WAV not in PREFERRED_MIMES


class TestAudioDeliveryDecision:
    def test_frozen_dataclass(self):
        decision = AudioDeliveryDecision(
            should_send_audio=True,
            mime_type=AudioMimeType.MP3,
            reason=AudioDeliveryReason.SENT_MP3,
            local_path="/tmp/test.wav",
        )
        assert decision.should_send_audio is True
        assert decision.mime_type == AudioMimeType.MP3

    def test_text_fallback_present_when_blocked(self):
        decision = AudioDeliveryDecision(
            should_send_audio=False,
            mime_type=None,
            reason=AudioDeliveryReason.BLOCKED_TOO_LONG,
            fallback_text="visita amanhã",
        )
        assert decision.fallback_text == "visita amanhã"
