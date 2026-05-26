from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch


def run(coro):
    return asyncio.run(coro)


def test_owner_alert_suppressed_when_same_phone():
    from agent_graph.services.alerts import send_owner_alert

    async def _run():
        with patch.dict("os.environ", {"OWNER_PHONE": "5513996659382", "OWNER_ALERTS_ENABLED": "1"}):
            with patch("agent_graph.services.alerts.send_whatsapp_text", new_callable=AsyncMock) as mock_send:
                result = await send_owner_alert(
                    {
                        "phone": "5513996659382",
                        "title": "ALERTA OPERACIONAL",
                        "reason": "high_value_lead",
                        "instance": "test",
                    }
                )
                mock_send.assert_not_called()
                return result

    assert run(_run()) is False
