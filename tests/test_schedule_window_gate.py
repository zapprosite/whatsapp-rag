from __future__ import annotations

import pytest

from agent_graph.nodes.nodes import can_ask_schedule_window, has_minimum_real_data_for_appointment


def _lead_ready() -> dict:
    return {
        "tipo_servico": "instalacao",
        "cidade_bairro": "Guarujá",
        "btus": "12000",
        "fotos": {"local_interno": True, "local_externo": True},
        "appointment": {"preferred_window": None, "confirmed_window": False, "appointment_alert_sent": False},
        "appointment_ready": True,
        "instalacao": {},
        "manutencao": {},
        "conserto": {},
        "modelo_aparelho": None,
        "aparelho_ja_comprado": None,
    }


def _lead_partial() -> dict:
    return {
        "tipo_servico": "instalacao",
        "cidade_bairro": "Guarujá",
        "btus": None,
        "fotos": {"local_interno": True, "local_externo": False},
        "appointment": {"preferred_window": None, "confirmed_window": False, "appointment_alert_sent": False},
        "appointment_ready": False,
        "instalacao": {},
        "manutencao": {},
        "conserto": {},
        "modelo_aparelho": None,
        "aparelho_ja_comprado": None,
    }


class TestCanAskScheduleWindow:
    def test_can_ask_when_ready_and_no_window(self):
        lead = _lead_ready()
        assert can_ask_schedule_window(lead, "instalacao") is True

    def test_cannot_ask_when_window_already_set(self):
        lead = _lead_ready()
        lead["appointment"]["preferred_window"] = "tarde"
        assert can_ask_schedule_window(lead, "instalacao") is False

    def test_cannot_ask_when_not_ready(self):
        lead = _lead_partial()
        assert can_ask_schedule_window(lead, "instalacao") is False

    def test_cannot_ask_when_minimum_data_missing(self):
        lead = _lead_ready()
        lead["appointment_ready"] = True
        lead["fotos"]["local_externo"] = False  # dados mínimos incompletos
        assert can_ask_schedule_window(lead, "instalacao") is False


class TestWindowReceivedWhenNotReady:
    """Verifica que has_minimum_real_data_for_appointment bloqueia agendamento prematuro."""

    def test_partial_lead_blocks_minimum_check(self):
        lead = _lead_partial()
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is False

    def test_ready_lead_passes_minimum_check(self):
        lead = _lead_ready()
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is True
