from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def run(coro):
    return asyncio.run(coro)


class TestDispatchAppointmentAlertDedup:
    """Garante que dispatch_appointment_alert não envia alerta duplicado na mesma sessão."""

    def test_dedup_via_lead_state_flag(self):
        """Se appointment_alert_sent já está True, dispatch retorna {} sem enviar."""
        from agent_graph.nodes.nodes import dispatch_appointment_alert

        state = {
            "outcome": "appointment_confirmed",
            "service": "instalacao",
            "messages": [],
            "customer_data": {},
            "lead_state": {
                "tipo_servico": "instalacao",
                "cidade_bairro": "Guarujá",
                "appointment": {
                    "preferred_window": "tarde",
                    "confirmed_window": True,
                    "appointment_alert_sent": True,  # já enviado
                },
            },
        }

        async def _run():
            with patch("agent_graph.services.alerts.send_appointment_alert", new_callable=AsyncMock) as mock_send:
                result = await dispatch_appointment_alert(state)
                mock_send.assert_not_called()
                return result

        result = run(_run())
        assert result == {}

    def test_no_window_no_alert(self):
        """Sem preferred_window, dispatch retorna {} sem enviar."""
        from agent_graph.nodes.nodes import dispatch_appointment_alert

        state = {
            "outcome": "appointment_confirmed",
            "service": "instalacao",
            "messages": [],
            "customer_data": {},
            "lead_state": {
                "tipo_servico": "instalacao",
                "cidade_bairro": "Guarujá",
                "appointment": {
                    "preferred_window": None,
                    "confirmed_window": False,
                    "appointment_alert_sent": False,
                },
            },
        }

        async def _run():
            with patch("agent_graph.services.alerts.send_appointment_alert", new_callable=AsyncMock) as mock_send:
                result = await dispatch_appointment_alert(state)
                mock_send.assert_not_called()
                return result

        result = run(_run())
        assert result == {}


class TestWorkerSkipsAppointmentConfirmed:
    """maybe_notify_owner_from_result deve ignorar reason=appointment_confirmed."""

    def test_appointment_confirmed_not_sent_to_owner(self):
        from app.worker import maybe_notify_owner_from_result
        import redis.asyncio as aioredis

        mock_redis = AsyncMock(spec=aioredis.Redis)

        result_dict = {
            "handoff_mode": "soft_alert",
            "handoff_reason": "appointment_confirmed",
        }

        async def _run():
            return await maybe_notify_owner_from_result(
                mock_redis,
                phone="5513999999999",
                message_text="Tarde",
                result=result_dict,
                instance="default",
            )

        sent = run(_run())
        assert sent is False
        mock_redis.set.assert_not_called()
