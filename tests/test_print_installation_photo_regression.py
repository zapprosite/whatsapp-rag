from __future__ import annotations

"""Reproduz o fluxo do print: cliente manda foto interna → bot pede foto interna de novo.

Estes testes são unitários/de integração parcial — não precisam de LLM real.
Verificam as funções determinísticas do pipeline de agendamento e foto.
"""

import pytest

from agent_graph.nodes.nodes import (
    compute_fields_status,
    can_ask_schedule_window,
    has_minimum_real_data_for_appointment,
    _important_missing_field_for_service,
    _question_for_field,
    _detect_preferred_window,
)


def _build_lead(
    tipo_servico: str = "instalacao",
    cidade_bairro: str | None = "Guarujá",
    fotos: dict | None = None,
    btus: str | None = None,
    appointment: dict | None = None,
    appointment_ready: bool = False,
) -> dict:
    return {
        "tipo_servico": tipo_servico,
        "cidade_bairro": cidade_bairro,
        "btus": btus,
        "modelo_aparelho": None,
        "aparelho_ja_comprado": None,
        "fotos": fotos or {},
        "instalacao": {},
        "manutencao": {},
        "conserto": {},
        "eletrica": {},
        "appointment": appointment or {"preferred_window": None, "confirmed_window": False, "appointment_alert_sent": False},
        "appointment_ready": appointment_ready,
        "relationship_type": "qualifying_lead",
    }


class TestPhotoStageProgression:
    def test_after_internal_photo_missing_is_external(self):
        """Após foto interna, missing_fields deve conter externo, não interno."""
        lead = _build_lead(fotos={"local_interno": True})
        _, _, missing = compute_fields_status(lead)
        assert "foto_local_interno" not in missing
        assert "foto_local_externo" in missing

    def test_next_field_for_instalacao_is_externo_after_interno(self):
        """_important_missing_field_for_service deve pedir externo quando interno já existe."""
        lead = _build_lead(fotos={"local_interno": True})
        _, _, missing = compute_fields_status(lead)
        do_not_ask = ["foto_local_interno", "cidade_bairro"]
        next_f = _important_missing_field_for_service("instalacao", missing, do_not_ask, lead)
        assert next_f == "foto_local_externo"

    def test_question_for_externo_field(self):
        q = _question_for_field("foto_local_externo")
        assert "condensadora" in q.lower() or "externo" in q.lower()

    def test_not_appointment_ready_with_only_internal(self):
        lead = _build_lead(fotos={"local_interno": True}, btus="12000")
        # sem local_externo, não pode estar pronto
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is False

    def test_appointment_ready_requires_both_photos_and_equipment(self):
        lead = _build_lead(
            fotos={"local_interno": True, "local_externo": True},
            btus="12000",
        )
        assert has_minimum_real_data_for_appointment(lead, "instalacao") is True


class TestWindowBeforeReady:
    def test_tarde_detected_correctly(self):
        assert _detect_preferred_window("Tarde") == "tarde"
        assert _detect_preferred_window("prefiro a tarde") == "tarde"

    def test_manha_detected_correctly(self):
        assert _detect_preferred_window("Manhã") == "manhã"
        assert _detect_preferred_window("de manha") == "manhã"

    def test_no_window_detected_in_unrelated_text(self):
        assert _detect_preferred_window("quero instalar um split") is None

    def test_can_not_ask_window_when_no_appointment_ready(self):
        lead = _build_lead(fotos={"local_interno": True})
        assert can_ask_schedule_window(lead, "instalacao") is False

    def test_can_not_ask_window_when_already_set(self):
        lead = _build_lead(
            fotos={"local_interno": True, "local_externo": True},
            btus="12000",
            appointment={"preferred_window": "tarde", "confirmed_window": False, "appointment_alert_sent": False},
            appointment_ready=True,
        )
        assert can_ask_schedule_window(lead, "instalacao") is False

    def test_can_ask_window_when_ready_and_no_window(self):
        lead = _build_lead(
            fotos={"local_interno": True, "local_externo": True},
            btus="12000",
            appointment_ready=True,
        )
        assert can_ask_schedule_window(lead, "instalacao") is True


class TestAlertSummaryCompact:
    def test_format_agenda_alert_compact(self):
        from agent_graph.services.alerts import _format_agenda_alert

        lead = {
            "phone": "5513999990001",
            "name": "Maria",
            "service": "instalacao",
            "address": "Guarujá",
            "window": "tarde",
        }
        summary = _format_agenda_alert(lead)
        # Não tem histórico de conversa repetido
        assert summary.count("Will:") == 0
        assert summary.count("Cliente:") <= 1
        # Tem acento correto
        assert "instalação" in summary
        assert "instalacao" not in summary
        # É compacto
        assert len(summary) < 400

    def test_format_agenda_alert_contains_key_fields(self):
        from agent_graph.services.alerts import _format_agenda_alert

        lead = {
            "phone": "5513999990001",
            "name": "João",
            "service": "higienizacao",
            "address": "Santos",
            "window": "manhã",
        }
        summary = _format_agenda_alert(lead)
        assert "AGENDAMENTO CONFIRMADO" in summary
        assert "5513999990001" in summary
        assert "João" in summary
        assert "higienização" in summary
        assert "Santos" in summary
        assert "manhã" in summary
