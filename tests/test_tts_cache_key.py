"""Tests for TTS cache key generator."""

import hashlib
import os
import pytest
from refrimix_core.domain.tts_cache_key import (
    make_cache_key,
    _normalize_for_cache,
)


class TestMakeCacheKey:
    def test_same_text_same_key(self):
        key1 = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom dia")
        key2 = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom dia")
        assert key1 == key2

    def test_different_engine_different_key(self):
        key_edge = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom dia")
        key_chatterbox = make_cache_key("chatterbox", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom dia")
        assert key_edge != key_chatterbox

    def test_different_voice_different_key(self):
        key_thalita = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom dia")
        key_francisca = make_cache_key("edge", "pt-BR-FranciscaNeural", "+0%", "bom dia")
        assert key_thalita != key_francisca

    def test_different_speed_different_key(self):
        key_normal = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom dia")
        key_fast = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+10%", "bom dia")
        assert key_normal != key_fast

    def test_different_text_different_key(self):
        key1 = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom dia")
        key2 = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "boa tarde")
        assert key1 != key2

    def test_case_insensitive_text(self):
        """Text normalization should produce same key regardless of case."""
        key_lower = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "Bom Dia")
        key_upper = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "BOM DIA")
        assert key_lower == key_upper

    def test_whitespace_normalized(self):
        """Multiple spaces should not affect cache key."""
        key1 = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom   dia")
        key2 = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom dia")
        assert key1 == key2

    def test_leading_trailing_whitespace_normalized(self):
        key1 = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "  bom dia  ")
        key2 = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "bom dia")
        assert key1 == key2

    def test_key_format(self):
        """Cache key should follow tts:{engine}:{voice}:{speed}:{hash} format."""
        key = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "teste")
        assert key.startswith("tts:edge:pt-BR-ThalitaMultilingualNeural:+0%:")
        parts = key.split(":")
        assert len(parts) == 5

    def test_hash_length(self):
        """Hash should be 32 characters (first 32 of sha256 hex)."""
        key = make_cache_key("edge", "pt-BR-ThalitaMultilingualNeural", "+0%", "teste")
        hash_part = key.split(":")[-1]
        assert len(hash_part) == 32
        assert all(c in "0123456789abcdef" for c in hash_part)


class TestNormalizeForCache:
    def test_lowercase(self):
        assert _normalize_for_cache("BOM DIA") == "bom dia"

    def test_strip(self):
        assert _normalize_for_cache("  bom dia  ") == "bom dia"

    def test_collapse_whitespace(self):
        assert _normalize_for_cache("bom   dia") == "bom dia"
        assert _normalize_for_cache("bom \n\t dia") == "bom dia"

    def test_unicode_preserved(self):
        assert _normalize_for_cache("ação joão") == "ação joão"

    def test_empty_string(self):
        assert _normalize_for_cache("") == ""
        assert _normalize_for_cache("   ") == ""
