"""
test_typing_policy.py — Testes para typing_policy.
"""
from __future__ import annotations

import pytest

from refrimix_core.domain.typing_policy import (
    is_typing_timeout,
    should_start_typing,
    typing_duration_text,
    TYPING_TIMEOUT_SECONDS,
)


class TestShouldStartTyping:
    def test_fast_lane_never_typing(self):
        assert should_start_typing("fast", "Oi", False) is False
        assert should_start_typing("fast", "sim", False) is False

    def test_slow_lane_without_microcopy(self):
        assert should_start_typing("slow", "quanto custa", False) is True

    def test_slow_lane_with_microcopy_already_sent(self):
        # Se microcopy já foi enviada, não ativar typing de novo
        assert should_start_typing("slow", "quanto custa", True) is False


class TestIsTypingTimeout:
    def test_within_timeout(self):
        started = 1000.0
        now = 1000.0 + TYPING_TIMEOUT_SECONDS - 1
        assert is_typing_timeout(started, now) is False

    def test_at_exact_timeout(self):
        started = 1000.0
        now = 1000.0 + TYPING_TIMEOUT_SECONDS
        assert is_typing_timeout(started, now) is True

    def test_past_timeout(self):
        started = 1000.0
        now = 1000.0 + TYPING_TIMEOUT_SECONDS + 10
        assert is_typing_timeout(started, now) is True


class TestTypingDurationText:
    def test_short_duration(self):
        result = typing_duration_text(3.5)
        assert "3.5" in result

    def test_medium_duration(self):
        result = typing_duration_text(10.0)
        assert "10" in result

    def test_near_timeout(self):
        result = typing_duration_text(28.0)
        assert "timeout" in result.lower()
