from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage


def run(coro):
    return asyncio.run(coro)


def _state() -> dict:
    return {
        "outcome": "appointment_confirmed",
        "handoff_reason": "appointment_confirmed",
        "service": "instalacao",
        "messages": [HumanMessage(content="Tarde")],
        "customer_data": {"phone": "+5513000000001", "name": "Cliente Teste"},
        "lead_state": {
            "tipo_servico": "instalacao",
            "cidade_bairro": "Guarujá",
            "appointment_ready": True,
            "appointment": {
                "preferred_window": "tarde",
                "confirmed_window": True,
                "appointment_alert_sent": False,
            },
        },
    }


def test_appointment_confirmed_not_double_alert():
    from agent_graph.nodes.nodes import dispatch_appointment_alert
    from app.worker import maybe_notify_owner_from_result

    async def _run():
        state = _state()
        redis = AsyncMock()
        with patch("agent_graph.services.alerts.prisma_upsert_lead", new_callable=AsyncMock):
            with patch("agent_graph.services.alerts.send_appointment_alert", new_callable=AsyncMock, return_value=True) as mock_send:
                first = await dispatch_appointment_alert(state)
                second = await dispatch_appointment_alert({**state, "lead_state": first["lead_state"]})
                owner = await maybe_notify_owner_from_result(
                    redis,
                    phone="5513000000001",
                    message_text="Tarde",
                    result={"handoff_mode": "soft_alert", "handoff_reason": "appointment_confirmed"},
                    instance="test",
                )
                return mock_send.call_count, second, owner, redis

    call_count, second, owner, redis = run(_run())
    assert call_count == 1
    assert second == {}
    assert owner is False
    redis.set.assert_not_called()
