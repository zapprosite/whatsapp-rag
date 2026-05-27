"""
Integration tests — Google Calendar live dry-run.
Skipped se GOOGLE_INTEGRATION_DRY_RUN != 0.
"""
from __future__ import annotations

import os
import pytest


class TestGoogleCalendarLiveDryRun:
    """Testa Calendar smoke em modo dry-run."""

    @pytest.fixture(autouse=True)
    def check_env(self):
        dry_run = os.getenv("GOOGLE_INTEGRATION_DRY_RUN", "1")
        if dry_run != "0":
            pytest.skip("GOOGLE_INTEGRATION_DRY_RUN != 0")

    def test_calendar_smoke_runs_without_real_api(self):
        """run_smoke_calendar() executa sem chamadas HTTP reais."""
        from refrimix_core.tools.google_integration_smoke import (
            run_smoke_calendar,
            DRY_RUN,
        )

        assert DRY_RUN is True
        result = run_smoke_calendar(job_folder_id="fake_folder_123")
        assert result["success"] is True
        assert result["dry_run"] is True
        assert result["event_id"] is not None

    def test_dry_run_event_has_test_prefix(self):
        """Evento dry-run tem prefixo [TESTE HERMES]."""
        from refrimix_core.tools.google_integration_smoke import (
            run_smoke_calendar,
            CALENDAR_TEST_PREFIX,
        )

        result = run_smoke_calendar(job_folder_id="fake_folder_123")
        summary = result["steps"]["create_event"]["summary"]
        assert CALENDAR_TEST_PREFIX in summary

    def test_dry_run_event_includes_drive_link(self):
        """Evento dry-run inclui link da pasta Drive."""
        from refrimix_core.tools.google_integration_smoke import run_smoke_calendar

        fake_folder_id = "fake_drive_folder_xyz"
        result = run_smoke_calendar(job_folder_id=fake_folder_id)
        drive_link = result["steps"]["create_event"]["drive_folder_link"]
        assert drive_link == fake_folder_id or f"folders/{fake_folder_id}" in drive_link

    def test_freebusy_returns_slots_in_dry_run(self):
        """FreeBusy retorna slots simulados em dry-run."""
        from refrimix_core.tools.google_integration_smoke import run_smoke_calendar

        result = run_smoke_calendar(job_folder_id=None)
        assert "freebusy_slots" in result
        assert len(result["freebusy_slots"]) == 2  # dados simulados

    def test_calendar_tool_imports(self):
        """Calendar tool importa sem ter token real."""
        from refrimix_core.tools import google_calendar_tool
        assert hasattr(google_calendar_tool, "list_available_slots")
        assert hasattr(google_calendar_tool, "create_service_event")
        assert hasattr(google_calendar_tool, "format_slots_for_whatsapp")


class TestCalendarApiContract:
    """Testa que as chamadas Calendar usam endpoints corretos."""

    def test_create_event_payload_has_required_fields(self):
        """Payload do evento inclui campos obrigatórios."""
        from refrimix_core.tools.google_calendar_tool import create_service_event
        import inspect

        sig = inspect.signature(create_service_event)
        params = list(sig.parameters.keys())
        required = ["lead_id", "phone", "service_type", "city_bairro", "start_iso"]
        for p in required:
            assert p in params, f"Parâmetro obrigatório {p} ausente"

    def test_service_duration_defined(self):
        """SERVICE_DURATION tem valores para todos os tipos principais."""
        from refrimix_core.tools.google_calendar_tool import SERVICE_DURATION

        assert SERVICE_DURATION["higienizacao"] == 90
        assert SERVICE_DURATION["instalacao"] == 180
        assert SERVICE_DURATION["manutencao"] == 60
        assert SERVICE_DURATION["outro"] == 60

    def test_business_hours_weekday_only(self):
        """Horário comercial só inclui dias úteis."""
        from refrimix_core.tools.google_calendar_tool import BUSINESS_DAYS, BUSINESS_START, BUSINESS_END

        assert 1 in BUSINESS_DAYS  # segunda
        assert 5 in BUSINESS_DAYS  # sexta
        assert 6 not in BUSINESS_DAYS  # sábado
        assert 7 not in BUSINESS_DAYS  # domingo
        assert BUSINESS_START.hour == 8
        assert BUSINESS_END.hour == 18

    def test_format_slots_for_whatsapp_format(self):
        """format_slots_for_whatsapp formata slots corretamente."""
        from refrimix_core.tools.google_calendar_tool import format_slots_for_whatsapp

        slots = [
            {"date": "2026-01-15", "start": "09:00", "day_label": "Quinta-feira", "slot_index": 1},
            {"date": "2026-01-15", "start": "10:00", "day_label": "Quinta-feira", "slot_index": 2},
        ]
        output = format_slots_for_whatsapp(slots)
        assert "Quinta-feira 15/01 às 09:00" in output
        assert "1." in output
        assert "2." in output

    def test_format_slots_empty(self):
        """Slots vazios retorna mensagem de erro."""
        from refrimix_core.tools.google_calendar_tool import format_slots_for_whatsapp

        output = format_slots_for_whatsapp([])
        assert "Nenhum horário" in output or "nenhum" in output.lower()
