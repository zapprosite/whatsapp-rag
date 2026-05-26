from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch


def run(coro):
    return asyncio.run(coro)


class TestOwnerAlertNotToLead:
    def test_suppressed_when_owner_equals_lead(self):
        """send_owner_alert não envia quando OWNER_PHONE == lead phone."""
        from agent_graph.services.alerts import send_owner_alert

        alert = {
            "phone": "5513996659382",
            "reason": "high_value_lead",
            "title": "LEAD DE ALTO VALOR",
            "instance": "default",
        }

        async def _run():
            with patch.dict("os.environ", {"OWNER_PHONE": "5513996659382", "OWNER_ALERTS_ENABLED": "1"}):
                with patch("agent_graph.services.alerts.send_whatsapp_text", new_callable=AsyncMock) as mock_send:
                    result = await send_owner_alert(alert)
                    mock_send.assert_not_called()
                    return result

        assert run(_run()) is False

    def test_sent_when_owner_differs_from_lead(self):
        """send_owner_alert envia quando OWNER_PHONE != lead phone."""
        from agent_graph.services.alerts import send_owner_alert

        alert = {
            "phone": "5513999990001",
            "reason": "explicit_handoff",
            "title": "HANDOFF",
            "instance": "default",
        }

        async def _run():
            with patch.dict("os.environ", {"OWNER_PHONE": "5513996659382", "OWNER_ALERTS_ENABLED": "1"}):
                with patch("agent_graph.services.alerts.send_whatsapp_text", new_callable=AsyncMock, return_value=True) as mock_send:
                    result = await send_owner_alert(alert)
                    mock_send.assert_called_once()
                    return result

        assert run(_run()) is True

    def test_suppressed_when_numbers_differ_only_in_formatting(self):
        """Normalização remove traços/espaços para comparação."""
        from agent_graph.services.alerts import send_owner_alert

        alert = {
            "phone": "+55 13 996-659-382",
            "reason": "complaint_or_risk",
            "title": "RECLAMAÇÃO",
            "instance": "default",
        }

        async def _run():
            with patch.dict("os.environ", {"OWNER_PHONE": "5513996659382", "OWNER_ALERTS_ENABLED": "1"}):
                with patch("agent_graph.services.alerts.send_whatsapp_text", new_callable=AsyncMock) as mock_send:
                    result = await send_owner_alert(alert)
                    mock_send.assert_not_called()
                    return result

        assert run(_run()) is False


class TestAppointmentAlertGoesToGroup:
    def test_uses_group_when_configured(self):
        """send_appointment_alert chama send_agenda_group_message quando AGENDA_GROUP_JID configurado."""
        from agent_graph.services.alerts import send_appointment_alert

        lead = {
            "phone": "5513999990001",
            "name": "Cliente Teste",
            "service": "instalacao",
            "address": "Guarujá",
            "window": "tarde",
        }

        async def _run():
            with patch.dict("os.environ", {
                "AGENDA_GROUP_ENABLED": "1",
                "AGENDA_GROUP_JID": "120363123456789@g.us",
            }):
                with patch("agent_graph.services.alerts.send_agenda_group_message", new_callable=AsyncMock, return_value=True) as mock_group:
                    result = await send_appointment_alert(lead)
                    mock_group.assert_called_once()
                    return mock_group.call_args[0][0], result

        msg, result = run(_run())
        assert result is True
        assert "AGENDAMENTO CONFIRMADO" in msg
        assert "instalação" in msg
        assert "tarde" in msg
        # Não deve conter histórico de conversa repetido
        assert msg.count("Will:") == 0

    def test_alert_summary_under_400_chars(self):
        """Resumo do alerta de agenda deve ser compacto."""
        from agent_graph.services.alerts import _format_agenda_alert

        lead = {
            "phone": "5513999990001",
            "name": "João Silva",
            "service": "higienizacao",
            "address": "Santos SP",
            "window": "manhã",
        }
        summary = _format_agenda_alert(lead)
        assert len(summary) < 400

    def test_service_label_uses_accented_form(self):
        """Rótulo de serviço no alerta deve ter acento correto."""
        from agent_graph.services.alerts import _format_agenda_alert

        lead = {"phone": "5513x", "name": "x", "service": "manutencao", "address": "x", "window": "tarde"}
        summary = _format_agenda_alert(lead)
        assert "manutenção" in summary
        assert "manutencao" not in summary

    def test_falls_back_to_owner_when_group_not_configured(self):
        """Sem AGENDA_GROUP_JID, fallback para owner alert."""
        from agent_graph.services.alerts import send_appointment_alert

        lead = {
            "phone": "5513999990001",
            "name": "x",
            "service": "instalacao",
            "address": "Guarujá",
            "window": "tarde",
        }

        async def _run():
            with patch.dict("os.environ", {
                "AGENDA_GROUP_ENABLED": "1",
                "AGENDA_GROUP_JID": "",
                "OWNER_PHONE": "5513996659382",
                "OWNER_ALERTS_ENABLED": "1",
            }):
                with patch("agent_graph.services.alerts.send_whatsapp_text", new_callable=AsyncMock, return_value=True) as mock_owner:
                    result = await send_appointment_alert(lead)
                    return result, mock_owner.called

        result, owner_called = run(_run())
        assert owner_called is True
