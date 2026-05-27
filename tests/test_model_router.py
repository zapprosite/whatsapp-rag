"""
test_model_router.py — Testes para model_router.
"""
from __future__ import annotations

import pytest

from refrimix_core.domain.model_router import (
    Lane,
    is_fast_lane_only,
    route,
    should_use_slow_lane,
)


class TestFastLaneOnly:
    def test_oi_alone(self):
        assert is_fast_lane_only("Oi") is True
        assert is_fast_lane_only("oi") is True
        assert is_fast_lane_only("OI") is True

    def test_ola_alone(self):
        assert is_fast_lane_only("Olá") is True
        assert is_fast_lane_only("olá") is True

    def test_bom_dia_alone(self):
        assert is_fast_lane_only("Bom dia") is True
        assert is_fast_lane_only("bom dia") is True

    def test_sim_alone(self):
        assert is_fast_lane_only("sim") is True
        assert is_fast_lane_only("Sim") is True

    def test_nao_alone(self):
        assert is_fast_lane_only("não") is True
        assert is_fast_lane_only("nao") is True

    def test_ok_alone(self):
        assert is_fast_lane_only("ok") is True

    def test_tudo_bem_alone(self):
        assert is_fast_lane_only("td bem") is True
        assert is_fast_lane_only("tudo bem") is True

    def test_vc_funciona_is_fast(self):
        assert is_fast_lane_only("vc funciona?") is True

    def test_price_mention_not_fast(self):
        assert is_fast_lane_only("quanto custa") is False
        assert is_fast_lane_only("qual o preço") is False

    def test_technical_not_fast(self):
        assert is_fast_lane_only("não gela") is False
        assert is_fast_lane_only("btus") is False


class TestShouldUseSlowLane:
    def test_price_mention(self):
        assert should_use_slow_lane("quanto custa a instalação?") is True
        assert should_use_slow_lane("qual o preço?") is True

    def test_technical_issue(self):
        assert should_use_slow_lane("o ar não gela") is True
        assert should_use_slow_lane("vazando água") is True

    def test_btus(self):
        assert should_use_slow_lane("quantos btus preciso?") is True

    def test_tenho_interesse_is_slow(self):
        # "tenho interesse" é sinal comercial → slow lane
        assert should_use_slow_lane("tenho interesse") is True

    def test_quando_vim_is_slow(self):
        # "quando podem vim?" é pergunta sobre agenda → slow
        assert should_use_slow_lane("quando podem vim?") is True

    def test_oi_only_is_not_slow(self):
        assert should_use_slow_lane("oi") is False


class TestRoute:
    def test_greeting_routes_to_fast(self):
        result = route("Oi")
        assert result.lane == Lane.FAST
        assert result.should_send_microcopy is True

    def test_price_routes_to_slow(self):
        result = route("quanto custa")
        assert result.lane == Lane.SLOW

    def test_technical_routes_to_slow(self):
        result = route("o ar não gela")
        assert result.lane == Lane.SLOW

    def test_fast_pattern_overrides_slow(self):
        # "oi quanto custa" — a saudação sozinha seria fast, mas conteúdo comercial vence
        result = route("oi quanto custa instalação")
        assert result.lane == Lane.SLOW

    def test_routing_decision_has_reason(self):
        result = route("oi")
        assert result.reason is not None
        assert len(result.reason) > 0

    def test_sim_routes_to_fast(self):
        result = route("sim")
        assert result.lane == Lane.FAST

    def test_default_is_slow(self):
        # Unknown text defaults to slow for safety
        result = route("asjdhasjd")
        assert result.lane == Lane.SLOW
