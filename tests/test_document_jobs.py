"""
Testes para document_jobs.py
"""
from __future__ import annotations

import uuid
from dataclasses import replace
from refrimix_core.domain.document_jobs import (
    DocumentJob,
    create_document_job,
    DOCUMENT_TYPES,
    SERVICE_TYPES,
    ORCAMENTO_STATUS,
)


class TestDocumentJobCreation:
    def test_cria_job_minimo(self):
        job = DocumentJob(
            job_id="test-123",
            lead_id="lead-456",
            document_type="quote_pdf",
            service_type="higienizacao",
            target_drive_kind="orcamentos",
            template_id=None,
            input_data={"cliente": "Maria"},
            requires_human_review=False,
        )
        assert job.status == "pendente"
        assert job.drive_file_id is None
        assert job.local_pdf_path is None

    def test_job_id_e_uuid(self):
        job = DocumentJob(
            job_id=str(uuid.uuid4()),
            lead_id="lead-1",
            document_type="quote_pdf",
            service_type="higienizacao",
            target_drive_kind="orcamentos",
            template_id=None,
            input_data={},
            requires_human_review=False,
        )
        assert len(job.job_id) == 36  # UUID len


class TestDocumentJobStateTransitions:
    def test_mark_generated(self):
        job = DocumentJob(
            job_id="test-123",
            lead_id="lead-456",
            document_type="quote_pdf",
            service_type="higienizacao",
            target_drive_kind="orcamentos",
            template_id=None,
            input_data={},
            requires_human_review=False,
        )
        updated = job.mark_generated("/tmp/orcamento.pdf")
        assert updated.status == "gerado"
        assert updated.local_pdf_path == "/tmp/orcamento.pdf"
        # imutável: original inalterada
        assert job.status == "pendente"

    def test_mark_saved(self):
        job = DocumentJob(
            job_id="test-123",
            lead_id="lead-456",
            document_type="quote_pdf",
            service_type="higienizacao",
            target_drive_kind="orcamentos",
            template_id=None,
            input_data={},
            requires_human_review=False,
        )
        updated = job.mark_saved(drive_file_id="file-abc", drive_folder_id="folder-xyz")
        assert updated.status == "salvo"
        assert updated.drive_file_id == "file-abc"
        assert updated.drive_folder_id == "folder-xyz"

    def test_mark_failed(self):
        job = DocumentJob(
            job_id="test-123",
            lead_id="lead-456",
            document_type="quote_pdf",
            service_type="higienizacao",
            target_drive_kind="orcamentos",
            template_id=None,
            input_data={},
            requires_human_review=False,
        )
        updated = job.mark_failed("Token OAuth expirou")
        assert updated.status == "falhou"
        assert updated.error_message == "Token OAuth expirou"


class TestCreateDocumentJob:
    def test_quote_pdf_vai_para_orcamentos(self):
        job = create_document_job(
            lead_id="lead-1",
            document_type="quote_pdf",
            service_type="higienizacao",
            input_data={"cliente": "Maria"},
        )
        assert job.target_drive_kind == "orcamentos"
        assert job.requires_human_review is False

    def test_contract_pdf_exige_revisao(self):
        job = create_document_job(
            lead_id="lead-2",
            document_type="contract_pdf",
            service_type="manutencao",
            input_data={"cliente": "Hotel X"},
        )
        assert job.target_drive_kind == "contratos_sla"
        assert job.requires_human_review is True

    def test_pmoc_pdf_exige_revisao(self):
        job = create_document_job(
            lead_id="lead-3",
            document_type="pmoc_pdf",
            service_type="manutencao",
            input_data={"cliente": "Restaurante Y"},
        )
        assert job.requires_human_review is True

    def test_service_order_nao_exige_revisao(self):
        job = create_document_job(
            lead_id="lead-4",
            document_type="service_order_pdf",
            service_type="higienizacao",
            input_data={},
        )
        assert job.requires_human_review is False

    def test_document_type_desconhecido_levanta(self):
        import pytest
        with pytest.raises(ValueError, match="Tipo de documento desconhecido"):
            create_document_job(
                lead_id="lead-x",
                document_type="nao_existe",
                service_type="higienizacao",
                input_data={},
            )


class TestConstants:
    def test_document_types_tem_todos(self):
        expected = [
            "quote_pdf",
            "technical_proposal_pdf",
            "service_order_pdf",
            "technical_report_pdf",
            "pmoc_pdf",
            "contract_pdf",
            "sla_pdf",
            "instagram_media_brief",
        ]
        assert DOCUMENT_TYPES == expected

    def test_service_types_tem_higienizacao(self):
        assert "higienizacao" in SERVICE_TYPES
        assert "instalacao" in SERVICE_TYPES
        assert "vrf" in SERVICE_TYPES

    def test_orcamento_status_tem_rascunho(self):
        assert "rascunho" in ORCAMENTO_STATUS
        assert "aprovado" in ORCAMENTO_STATUS
        assert "revisar_humano" in ORCAMENTO_STATUS
