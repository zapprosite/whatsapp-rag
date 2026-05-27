"""
Integration tests — PDF Skill + Drive contract.

Verifica que:
1. Hermes PDF skill gera arquivo local corretamente
2. Drive tool recebe o arquivo e faz upload
3. Fluxo completo: gerar → salvar → metadata atualizada
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path


class TestPdfSkillDriveContract:
    """Contrato entre Hermes PDF skill e Drive tool."""

    def test_fake_pdf_builder_produces_file(self):
        """build_fake_pdf_path() cria arquivo no filesystem."""
        from refrimix_core.tools.google_integration_smoke import build_fake_pdf_path

        pdf_path = build_fake_pdf_path()
        try:
            assert pdf_path.exists()
            assert pdf_path.stat().st_size > 100
            assert pdf_path.suffix == ".pdf"
        finally:
            # Cleanup
            if pdf_path.exists():
                pdf_path.unlink()

    def test_drive_tool_save_pdf_has_correct_signature(self):
        """save_generated_pdf tem assinatura correta."""
        from refrimix_core.tools.google_drive_tool import save_generated_pdf
        import inspect

        sig = inspect.signature(save_generated_pdf)
        params = list(sig.parameters.keys())
        required = ["folder_id", "local_pdf_path", "document_type", "metadata"]
        for p in required:
            assert p in params, f"Parâmetro {p} ausente"

    def test_document_job_state_transitions(self):
        """DocumentJob transita corretamente entre estados."""
        from refrimix_core.domain.document_jobs import create_document_job

        job = create_document_job(
            lead_id="lead-test-1",
            document_type="quote_pdf",
            service_type="higienizacao",
            input_data={"cliente": "Teste"},
        )
        assert job.status == "pendente"

        updated = job.mark_generated("/tmp/test.pdf")
        assert updated.status == "gerado"
        assert updated.local_pdf_path == "/tmp/test.pdf"
        assert job.status == "pendente"  # imutável

        updated2 = updated.mark_saved(
            drive_file_id="file-abc",
            drive_folder_id="folder-xyz",
        )
        assert updated2.status == "salvo"
        assert updated2.drive_file_id == "file-abc"
        assert updated2.drive_folder_id == "folder-xyz"

    def test_document_type_to_folder_contract(self):
        """DOCUMENT_DRIVE_MAP cobre todos os tipos de PDF skill."""
        from refrimix_core.domain.drive_taxonomy import DOCUMENT_DRIVE_MAP
        from refrimix_core.domain.document_jobs import DOCUMENT_TYPES

        for doc_type in DOCUMENT_TYPES:
            folder = DOCUMENT_DRIVE_MAP.get(doc_type)
            assert folder is not None, f"{doc_type} sem pasta mapeada"
            assert "0" in folder  # todas são "0X_NOME"

    def test_naming_functions_produce_safe_filenames(self):
        """build_*_filename produz nomes sem caracteres perigosos."""
        from refrimix_core.domain.drive_naming import (
            build_quote_filename,
            build_service_order_filename,
            build_proposal_filename,
            build_contract_filename,
        )
        from datetime import date

        d = date(2026, 5, 26)

        names = [
            build_quote_filename("José & María", "higienização", "São Paulo", d, "rascunho"),
            build_service_order_filename("Cliente Teste", "instalação", "Rio de Janeiro", d, "enviado"),
            build_proposal_filename("Empresa X", "vrf", "Curitiba", d),
            build_contract_filename("Condomínio Y", "manutenção", d),
        ]

        dangerous = ["'", '"', "&", " ", "/", "\\", "\n", "\r"]
        for name in names:
            for char in dangerous:
                assert char not in name, f"Caractere perigoso {repr(char)} em {name}"

    def test_job_folder_name_reuses_same_lead_id(self):
        """SMOKE_LEAD_ID é fixo por processo — mesmo lead em todas as etapas."""
        from refrimix_core.tools.google_integration_smoke import (
            build_fake_lead,
            SMOKE_LEAD_ID,
        )

        lead1 = build_fake_lead()
        lead2 = build_fake_lead()
        # Mesmo lead_id por run (comportamento correto para smoke)
        assert lead1["lead_id"] == lead2["lead_id"] == SMOKE_LEAD_ID
        # Mas phone e nome são iguais
        assert lead1["phone"] == lead2["phone"]

    def test_dry_run_smoke_returns_all_file_ids(self):
        """Smoke completo retorna todos os file_ids esperados."""
        from refrimix_core.tools.google_integration_smoke import run_full_smoke

        result = run_full_smoke()
        assert result["success"] is True
        assert result["dry_run"] is True
        drive = result["drive"]
        assert drive["pdf_file_id"] is not None
        assert drive["metadata_file_id"] is not None
        assert drive["resumo_file_id"] is not None

    def test_smoke_result_structure(self):
        """Estrutura do resultado do smoke é completa."""
        from refrimix_core.tools.google_integration_smoke import run_full_smoke

        result = run_full_smoke()
        assert "success" in result
        assert "drive" in result
        assert "calendar" in result
        assert "smoke_lead_id" in result
        assert "dry_run" in result

        # Calendar
        cal = result["calendar"]
        assert "event_id" in cal
        assert "freebusy_slots" in cal
        assert "steps" in cal

        # Drive
        drv = result["drive"]
        assert "job_folder_id" in drv
        assert "sandbox_folder_id" in drv
        assert "steps" in drv


class TestPdfDriveNamingContract:
    """Verifica que a nomenclatura de arquivo respeita o padrão."""

    def test_orcamento_naming_pattern(self):
        """ORCAMENTO segue padrão: ORCAMENTO_{cliente}_{servico}_{cidade}_{data}_{status}."""
        from refrimix_core.domain.drive_naming import build_quote_filename
        from datetime import date

        name = build_quote_filename(
            client_name="Maria Silva",
            service_type="higienizacao",
            city_bairro="Santos - Gonzaga",
            doc_date=date(2026, 5, 26),
            status="rascunho",
        )
        assert name.startswith("ORCAMENTO_Maria_Silva_higienizacao_")
        assert name.endswith(".pdf")
        assert "20260526" in name
        assert "rascunho" in name

    def test_os_naming_pattern(self):
        """OS segue padrão: OS_{cliente}_{servico}_{cidade}_{data}_{status}."""
        from refrimix_core.domain.drive_naming import build_service_order_filename
        from datetime import date

        name = build_service_order_filename(
            client_name="João Santos",
            service_type="manutencao",
            city_bairro="São Vicente",
            doc_date=date(2026, 6, 1),
            status="assinada",
        )
        assert name.startswith("OS_")
        assert "Joao_Santos" in name  # acento removido
        assert "20260601" in name
        assert "assinada" in name

    def test_proposta_naming_pattern(self):
        """PROPOSTA_TECNICA não tem status (é destino final)."""
        from refrimix_core.domain.drive_naming import build_proposal_filename
        from datetime import date

        name = build_proposal_filename(
            client_name="Hotel Luxo",
            service_type="vrf",
            city_bairro="Campinas",
            doc_date=date(2026, 7, 15),
        )
        assert name.startswith("PROPOSTA_TECNICA_Hotel_Luxo_")
        assert "20260715" in name
        assert "rascunho" not in name  # não tem status
