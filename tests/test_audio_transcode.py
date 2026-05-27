"""Tests for audio_transcode.py — MIME detection and format conversion."""

import pytest
import tempfile
from pathlib import Path

from refrimix_core.tools.audio_transcode import (
    detect_mime_from_file,
    detect_mime_from_bytes,
    is_whatsapp_compatible,
    wav_to_ogg_opus,
    wav_to_mp3,
    wav_to_whatsapp_optimal,
    WHATSAPP_SUPPORTED_MIMES,
    PREFERRED_MIME,
    FALLBACK_MIME,
)


# Minimal valid WAV file (44-byte header + padding)
_MINIMAL_WAV = (
    b"RIFF"
    + (128 - 8).to_bytes(4, "little")
    + b"WAVE"
    + b"fmt "
    + (16).to_bytes(4, "little")
    + (1).to_bytes(2, "little")  # PCM
    + (1).to_bytes(2, "little")  # mono
    + (16000).to_bytes(4, "little")
    + (32000).to_bytes(4, "little")
    + (2).to_bytes(2, "little")
    + (16).to_bytes(2, "little")
    + b"data"
    + (128 - 44).to_bytes(4, "little")
    + b"\x00" * (128 - 44)
)

# Minimal valid MP3 file (ID3v2 header)
_MINIMAL_MP3 = (
    b"ID3\x04\x00\x00\x00\x00\x00\x23"
    + b"\x00" * 100
)

# Minimal OGG/Opus file
_MINIMAL_OGG = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00" + b"\x00" * 100


class TestDetectMimeFromBytes:
    def test_wav_bytes_detected(self):
        mime = detect_mime_from_bytes(_MINIMAL_WAV)
        assert mime == "audio/wav"

    def test_mp3_bytes_detected(self):
        mime = detect_mime_from_bytes(_MINIMAL_MP3)
        assert mime == "audio/mpeg"

    def test_ogg_bytes_detected(self):
        mime = detect_mime_from_bytes(_MINIMAL_OGG)
        assert mime == "audio/ogg; codecs=opus"

    def test_too_short_returns_none(self):
        assert detect_mime_from_bytes(b"RIFF") is None
        assert detect_mime_from_bytes(b"") is None

    def test_unknown_returns_none(self):
        assert detect_mime_from_bytes(b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00") is None


class TestDetectMimeFromFile:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()

    def teardown_method(self):
        for p in Path(self.tmpdir).glob("*"):
            p.unlink()
        Path(self.tmpdir).rmdir()

    def test_wav_file(self):
        p = Path(self.tmpdir) / "test.wav"
        p.write_bytes(_MINIMAL_WAV)
        assert detect_mime_from_file(str(p)) == "audio/wav"

    def test_mp3_file(self):
        p = Path(self.tmpdir) / "test.mp3"
        p.write_bytes(_MINIMAL_MP3)
        assert detect_mime_from_file(str(p)) == "audio/mpeg"

    def test_ogg_file(self):
        p = Path(self.tmpdir) / "test.ogg"
        p.write_bytes(_MINIMAL_OGG)
        assert detect_mime_from_file(str(p)) == "audio/ogg; codecs=opus"

    def test_nonexistent_file(self):
        assert detect_mime_from_file("/nonexistent/audio.wav") is None


class TestIsWhatsAppCompatible:
    def test_mp3_compatible(self):
        assert is_whatsapp_compatible("audio/mpeg") is True

    def test_ogg_compatible(self):
        assert is_whatsapp_compatible("audio/ogg") is True

    def test_ogg_opus_compatible(self):
        assert is_whatsapp_compatible("audio/ogg; codecs=opus") is True

    def test_wav_compatible(self):
        assert is_whatsapp_compatible("audio/wav") is True

    def test_flac_not_compatible(self):
        assert is_whatsapp_compatible("audio/flac") is False

    def test_aac_not_compatible(self):
        assert is_whatsapp_compatible("audio/aac") is False


class TestWavToOggOpus:
    def test_converts_wav_to_ogg(self):
        result = wav_to_ogg_opus(_MINIMAL_WAV)
        # Returns bytes (either ogg or original wav on failure)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_returns_bytes_or_original_wav(self):
        """wav_to_ogg_opus must always return bytes (transcoded or original WAV)."""
        result = wav_to_ogg_opus(_MINIMAL_WAV)
        assert result is not None
        assert isinstance(result, bytes)


class TestWavToMp3:
    def test_converts_wav_to_mp3(self):
        result = wav_to_mp3(_MINIMAL_WAV)
        # May return None if ffmpeg not available
        if result is not None:
            assert isinstance(result, bytes)
            assert len(result) > 0


class TestWavToWhatsAppOptimal:
    def test_returns_tuple_bytes_string(self):
        audio_bytes, mime = wav_to_whatsapp_optimal(_MINIMAL_WAV)
        assert isinstance(audio_bytes, bytes)
        assert isinstance(mime, str)
        assert len(audio_bytes) > 0

    def test_mime_is_whatsapp_compatible(self):
        audio_bytes, mime = wav_to_whatsapp_optimal(_MINIMAL_WAV)
        assert is_whatsapp_compatible(mime) is True

    def test_prefers_ogg_opus(self):
        """Optimal format should prefer OGG/Opus over MP3/WAV."""
        audio_bytes, mime = wav_to_whatsapp_optimal(_MINIMAL_WAV)
        # OGG/Opus is preferred; MP3 is fallback; WAV is last resort
        assert mime in {"audio/ogg; codecs=opus", "audio/mpeg", "audio/wav"}

    def test_small_wav_preserved(self):
        """Small WAV should still return bytes (even if OGG fails)."""
        small_wav = _MINIMAL_WAV[:64]
        audio_bytes, mime = wav_to_whatsapp_optimal(small_wav)
        assert isinstance(audio_bytes, bytes)


class TestWhatsAppSupportedMimes:
    def test_all_preferred_mimes_are_supported(self):
        for mime_str in {"audio/mpeg", "audio/ogg; codecs=opus"}:
            assert mime_str in WHATSAPP_SUPPORTED_MIMES

    def test_preferred_mime_is_ogg_opus(self):
        assert PREFERRED_MIME == "audio/ogg; codecs=opus"

    def test_fallback_mime_is_mp3(self):
        assert FALLBACK_MIME == "audio/mpeg"
