"""
Testes de contrato para google_drive_tool.py
Verifica que o tool não inventa credenciais e respeita o contrato de inputs.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestDriveToolContract:
    """Contrato: o tool não deve usar credenciais hardcoded."""

    def test_nao_tem_credenciais_no_codigo(self):
        """Verifica que não há tokens ou secrets no fonte."""
        import refrimix_core.tools.google_drive_tool as tool_module

        source = open(tool_module.__file__).read()

        # Não deve ter tokens reais
        assert "ghp_" not in source
        assert "ya29." not in source  # access token google
        assert "1//0" not in source    # refresh token google

    def test_usa_env_para_root_folder_id(self, monkeypatch):
        """ROOT_FOLDER_ID deve vir do ambiente, nunca hardcoded."""
        import refrimix_core.tools.google_drive_tool as tool_module

        monkeypatch.delenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", raising=False)
        # Sem env, deve ser string vazia (não levanta — só avisa em runtime)
        assert tool_module.ROOT_FOLDER_ID == ""

    def test_folder_ids_comes_from_env(self, monkeypatch):
        """Todos os FOLDER_IDS devem vir de env."""
        import refrimix_core.tools.google_drive_tool as tool_module

        for key in tool_module.FOLDER_IDS:
            monkeypatch.delenv(f"GOOGLE_DRIVE_FOLDER_{key.upper()}", raising=False)

        # Todos devem ser string vazia sem env
        for key, val in tool_module.FOLDER_IDS.items():
            assert val == "", f"{key} deveria vir do env"


class TestDriveToolHelpers:
    """Testa helpers internos com mocks."""

    def test_sanitize_query_previne_injection(self):
        """Query maliciosa deve ser neutralizada."""
        from refrimix_core.domain.drive_naming import sanitize_filename

        # Não deve permitir aspas quebrem a query
        result = sanitize_filename("foo' OR name='")
        assert "'" not in result
        assert '"' not in result

    def test_kind_to_folder_name_mapping(self):
        """Todos os kinds devem ter mapeamento para nome de pasta."""
        from refrimix_core.tools.google_drive_tool import _kind_to_folder_name

        kinds = [
            "propostas_tecnicas",
            "contratos_sla",
            "ordens_servico",
            "pmoc_laudos",
            "orcamentos",
            "midias_redes_sociais",
        ]
        for kind in kinds:
            name = _kind_to_folder_name(kind)
            assert name.startswith("0"), f"{kind} deve mapear para pasta numerada"


class TestCalendarToolContract:
    """Contrato do calendar tool."""

    def test_nao_tem_credenciais_no_codigo(self):
        import refrimix_core.tools.google_calendar_tool as cal_module
        source = open(cal_module.__file__).read()

        assert "ghp_" not in source
        assert "ya29." not in source
        assert "1//0" not in source

    def test_service_duration_tem_default(self):
        from refrimix_core.tools.google_calendar_tool import SERVICE_DURATION

        assert SERVICE_DURATION["higienizacao"] == 90
        assert SERVICE_DURATION["instalacao"] == 180
        assert "outro" in SERVICE_DURATION

    def test_business_hours_configured(self):
        from refrimix_core.tools.google_calendar_tool import (
            BUSINESS_START,
            BUSINESS_END,
            BUSINESS_DAYS,
        )

        assert BUSINESS_START.hour == 8
        assert BUSINESS_END.hour == 18
        assert 1 in BUSINESS_DAYS  # segunda
        assert 5 in BUSINESS_DAYS  # sexta
        assert 6 not in BUSINESS_DAYS  # sábado
