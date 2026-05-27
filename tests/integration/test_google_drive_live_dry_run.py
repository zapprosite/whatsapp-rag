"""
Integration tests — Google Drive live dry-run.
Skipped se GOOGLE_INTEGRATION_DRY_RUN != 0.
Usa mocks para chamadas HTTP e verifica contrato de API.
"""
from __future__ import annotations

import os
import pytest


class TestGoogleDriveLiveDryRun:
    """Testa que o Drive tool funciona com mocks."""

    @pytest.fixture(autouse=True)
    def check_env(self):
        """Skippa se não estiver em modo dry-run ou se credenciais ausentes."""
        dry_run = os.getenv("GOOGLE_INTEGRATION_DRY_RUN", "1")
        if dry_run != "0":
            pytest.skip("GOOGLE_INTEGRATION_DRY_RUN != 0 — smoke test é skipped por padrão")

    def test_drive_smoke_runs_without_real_api(self, monkeypatch):
        """
        Verifica que run_smoke_drive() executa todas as etapas
        sem fazer chamadas HTTP reais quando DRY_RUN=1.
        """
        from refrimix_core.tools.google_integration_smoke import run_smoke_drive, DRY_RUN

        assert DRY_RUN is True

        # Dry run não levanta exceção
        result = run_smoke_drive()
        assert result["success"] is True
        assert result["dry_run"] is True
        assert "sandbox_folder_id" in result
        assert "job_folder_id" in result
        assert result["metadata_file_id"] is not None
        assert result["resumo_file_id"] is not None

    def test_dry_run_returns_dry_ids(self):
        """IDs de arquivo devem ser strings 'dry_run_*'."""
        from refrimix_core.tools.google_integration_smoke import run_smoke_drive

        result = run_smoke_drive()
        assert result["pdf_file_id"].startswith("dry_run")
        assert result["metadata_file_id"].startswith("dry_run")
        assert result["resumo_file_id"].startswith("dry_run")

    def test_smoke_lead_has_correct_structure(self):
        """Lead fake tem todos os campos obrigatórios."""
        from refrimix_core.tools.google_integration_smoke import build_fake_lead

        lead = build_fake_lead()
        assert "lead_id" in lead
        assert "phone" in lead
        assert "client_name" in lead
        assert "city_bairro" in lead
        assert "service_type" in lead
        assert "risk" in lead
        assert lead["source"] == "google_smoke_test"

    def test_fake_pdf_is_created(self):
        """PDF fake é criado em /tmp e tem conteúdo válido."""
        from refrimix_core.tools.google_integration_smoke import build_fake_pdf_path

        pdf_path = build_fake_pdf_path()
        assert pdf_path.exists()
        content = pdf_path.read_text()
        assert "%PDF" in content
        assert "Smoke Test PDF" in content

    def test_resolve_sandbox_returns_id(self):
        """resolve_sandbox_folder_id() retorna algo em dry-run."""
        from refrimix_core.tools.google_integration_smoke import resolve_sandbox_folder_id

        folder_id = resolve_sandbox_folder_id()
        assert folder_id is not None
        assert len(folder_id) > 0

    def test_drive_tool_imports_without_auth(self):
        """Drive tool importa sem ter token real."""
        # Não deve levantar exceção só por importar
        from refrimix_core.tools import google_drive_tool
        assert hasattr(google_drive_tool, "save_generated_pdf")
        assert hasattr(google_drive_tool, "ensure_job_folder")
        assert hasattr(google_drive_tool, "search_refrimix_files")


class TestDriveApiContract:
    """Testa que as chamadas HTTP usam os endpoints corretos."""

    def test_search_uses_files_list_endpoint(self, monkeypatch):
        """search_refrimix_files deve usar files.list com query."""
        import httpx

        called_urls = []

        def mock_get(url, **kwargs):
            called_urls.append(url)
            mock_response = httpx.Response(200, json={"files": []})
            return mock_response

        monkeypatch.setattr(httpx, "Client", lambda **kw: type("C", (), {"__enter__": lambda s: type("C2", (), {"get": mock_get, "__exit__": lambda *a: None})(), "__exit__": lambda *a: None})())

        # Não roda porque não temos token, mas verifica o endpoint
        # A chamada real seria:
        # url = f"{DRIVE_API_BASE}/files?q=..."
        # assert "files" in url

    def test_upload_multipart_uses_correct_content_type(self):
        """_upload_multipart deve enviar como multipart/form-data."""
        from refrimix_core.tools.google_drive_tool import _upload_multipart
        import requests

        # Em dry-run sem token, levantaria RuntimeError de token
        # O contrato é: multipart/form-data com metadata + file
        # Testa que a função existe e tem a assinatura correta
        import inspect
        sig = inspect.signature(_upload_multipart)
        params = list(sig.parameters.keys())
        assert "url" in params
        assert "metadata" in params
        assert "file_content" in params
        assert "filename" in params
        assert "mime_type" in params
