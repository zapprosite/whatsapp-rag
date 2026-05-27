"""
Testes para drive_taxonomy.py
"""
from __future__ import annotations

from refrimix_core.domain.drive_taxonomy import (
    DOCUMENT_DRIVE_MAP,
    document_type_to_folder,
    folder_to_document_types,
    is_human_review_required,
    DRIVE_FOLDER_KINDS,
)


class TestDocumentTypeToFolder:
    def test_quote_vai_para_orcamentos(self):
        assert document_type_to_folder("quote_pdf") == "05_ORCAMENTOS"

    def test_service_order_vai_para_ordens_servico(self):
        assert document_type_to_folder("service_order_pdf") == "03_ORDENS_DE_SERVICO"

    def test_pmoc_e_laudo_vai_para_pmoc_laudos(self):
        assert document_type_to_folder("pmoc_pdf") == "04_PMOC_E_LAUDOS"
        assert document_type_to_folder("technical_report_pdf") == "04_PMOC_E_LAUDOS"

    def test_contract_e_sla_vai_para_contratos_sla(self):
        assert document_type_to_folder("contract_pdf") == "02_CONTRATOS_E_SLA"
        assert document_type_to_folder("sla_pdf") == "02_CONTRATOS_E_SLA"

    def test_technical_proposal_vai_para_propostas_tecnicas(self):
        assert document_type_to_folder("technical_proposal_pdf") == "01_PROPOSTAS_TECNICAS"

    def test_instagram_vai_para_midias(self):
        assert document_type_to_folder("instagram_media_brief") == "06_MIDIAS_E_REDES_SOCIAIS"

    def test_desconhecido_retorna_none(self):
        assert document_type_to_folder("qualquer_coisa") is None


class TestFolderToDocumentTypes:
    def test_orcamentos_tem_quote(self):
        assert "quote_pdf" in folder_to_document_types("05_ORCAMENTOS")

    def test_ordens_servico_tem_service_order(self):
        assert "service_order_pdf" in folder_to_document_types("03_ORDENS_DE_SERVICO")

    def test_pmoc_laudos_tem_pmoc_e_laudo(self):
        folder_types = folder_to_document_types("04_PMOC_E_LAUDOS")
        assert "pmoc_pdf" in folder_types
        assert "technical_report_pdf" in folder_types


class TestHumanReviewRequired:
    def test_contrato_exige_revisao(self):
        assert is_human_review_required("contract_pdf") is True

    def test_sla_exige_revisao(self):
        assert is_human_review_required("sla_pdf") is True

    def test_proposta_tecnica_exige_revisao(self):
        assert is_human_review_required("technical_proposal_pdf") is True

    def test_pmoc_exige_revisao(self):
        assert is_human_review_required("pmoc_pdf") is True

    def test_orcamento_nao_exige_revisao(self):
        assert is_human_review_required("quote_pdf") is False

    def test_os_nao_exige_revisao(self):
        assert is_human_review_required("service_order_pdf") is False

    def test_laudo_tecnico_nao_exige_revisao(self):
        # Laudo técnico é baixo valor, não exige revisão automática
        assert is_human_review_required("technical_report_pdf") is False


class TestDocumentDriveMapCompleteness:
    def test_todos_os_documentos_mapeados(self):
        from refrimix_core.domain.document_jobs import DOCUMENT_TYPES

        for doc_type in DOCUMENT_TYPES:
            folder = document_type_to_folder(doc_type)
            assert folder is not None, f"{doc_type} sem pasta mapeada"
            assert folder in DOCUMENT_DRIVE_MAP.values()
