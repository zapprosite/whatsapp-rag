"""
test_whatsapp_orchestrator.py — Testes para whatsapp_orchestrator.
Usa asyncio.run() para testar código async sem pytest-asyncio.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from refrimix_core.domain.model_router import Lane
from refrimix_core.runtime.whatsapp_orchestrator import (
    OrchestratorContext,
    process_message,
)


class TestOrchestratorContext:
    def test_context_created(self):
        ctx = OrchestratorContext(
            phone="5511999999999",
            message="Oi",
            instance="default",
            msg_id="test123",
        )
        assert ctx.phone == "5511999999999"
        assert ctx.lane is None
        assert ctx.final_response is None


def _run(coro):
    """Helper para rodar coroutine em teste sync."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestFastLaneRouting:
    def test_greeting_routes_fast(self):
        ctx = _run(process_message(
            phone="5511999999999",
            message="Oi",
            instance="default",
            msg_id="test_greeting",
        ))
        assert ctx.lane == Lane.FAST
        assert ctx.sent_via == "fast"
        assert ctx.final_response is not None
        assert len(ctx.final_response) > 0

    def test_sim_routes_fast(self):
        ctx = _run(process_message(
            phone="5511999999999",
            message="sim",
            instance="default",
            msg_id="test_sim",
        ))
        assert ctx.lane == Lane.FAST
        assert ctx.sent_via == "fast"

    def test_ok_routes_fast(self):
        ctx = _run(process_message(
            phone="5511999999999",
            message="ok",
            instance="default",
            msg_id="test_ok",
        ))
        assert ctx.lane == Lane.FAST
        assert ctx.sent_via == "fast"

    def test_bom_dia_routes_fast(self):
        ctx = _run(process_message(
            phone="5511999999999",
            message="Bom dia",
            instance="default",
            msg_id="test_bomdia",
        ))
        assert ctx.lane == Lane.FAST


class TestSlowLaneRouting:
    def test_price_routes_slow(self):
        with patch(
            "refrimix_core.runtime.whatsapp_orchestrator._call_minimax_slow",
            new_callable=AsyncMock,
            return_value="Instalação fica R$850.",
        ):
            ctx = _run(process_message(
                phone="5511999999999",
                message="quanto custa instalação?",
                instance="default",
                msg_id="test_price",
            ))
        assert ctx.lane == Lane.SLOW
        assert ctx.sent_via == "slow"

    def test_technical_issue_routes_slow(self):
        with patch(
            "refrimix_core.runtime.whatsapp_orchestrator._call_minimax_slow",
            new_callable=AsyncMock,
            return_value="Vou verificar.",
        ):
            ctx = _run(process_message(
                phone="5511999999999",
                message="o ar não gela",
                instance="default",
                msg_id="test_technical",
            ))
        assert ctx.lane == Lane.SLOW


class TestElectricalSafety:
    def test_electrical_confirmed_returns_directive(self):
        ctx = _run(process_message(
            phone="5511999999999",
            message="saiu faísca da tomada e cheira de queimado",
            instance="default",
            msg_id="test_electric",
        ))
        assert ctx.sent_via == "electrical_safety"
        assert ctx.final_response is not None
        assert "Desligue" in ctx.final_response

    def test_electrical_suspected_returns_directive(self):
        ctx = _run(process_message(
            phone="5511999999999",
            message="o disjuntor desarmou",
            instance="default",
            msg_id="test_electric2",
        ))
        assert ctx.sent_via == "electrical_safety"


class TestGuardrailIntegration:
    def test_response_passes_through_when_valid(self):
        with patch(
            "refrimix_core.runtime.whatsapp_orchestrator._call_minimax_slow",
            new_callable=AsyncMock,
            return_value="Instalação de split fica R$850 com material e mão de obra.",
        ):
            with patch(
                "agent_graph.guards.response_guard.validate_response_before_send",
                return_value=(True, []),
            ):
                ctx = _run(process_message(
                    phone="5511999999999",
                    message="quanto custa",
                    instance="default",
                    msg_id="test_guardrail",
                ))
        assert ctx.final_response is not None
        assert ctx.sent_via == "slow"

    def test_invalid_response_gets_error_microcopy(self):
        with patch(
            "refrimix_core.runtime.whatsapp_orchestrator._call_minimax_slow",
            new_callable=AsyncMock,
            return_value="últimas vagas promoção imperdível",
        ):
            with patch(
                "agent_graph.guards.response_guard.validate_response_before_send",
                return_value=(False, ["pushy_sales"]),
            ):
                ctx = _run(process_message(
                    phone="5511999999999",
                    message="quanto custa",
                    instance="default",
                    msg_id="test_guardrail_block",
                ))
        assert ctx.sent_via == "guardrail_blocked"
        assert ctx.final_response is not None


class TestProcessingTime:
    def test_processing_time_recorded(self):
        ctx = _run(process_message(
            phone="5511999999999",
            message="Oi",
            instance="default",
            msg_id="test_time",
        ))
        assert ctx.processing_time_ms >= 0
