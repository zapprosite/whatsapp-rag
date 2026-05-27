"""
Testes para drive_naming.py
"""
from __future__ import annotations

from datetime import date
from refrimix_core.domain.drive_naming import (
    sanitize_filename,
    build_job_folder_name,
    build_quote_filename,
    build_service_order_filename,
    build_proposal_filename,
    build_contract_filename,
    build_pmoc_filename,
    build_laudo_filename,
)


class TestSanitizeFilename:
    def test_remove_acentos(self):
        assert sanitize_filename("José") == "Jose"

    def test_remove_espacos(self):
        assert sanitize_filename("Hotel X") == "Hotel_X"

    def test_remove_caracteres_perigosos(self):
        assert sanitize_filename("foo/bar\\baz") == "foobarbaz"
        assert sanitize_filename("test*file") == "testfile"

    def test_underscore_entre_palavras(self):
        assert sanitize_filename("Sao Paulo Sul") == "Sao_Paulo_Sul"

    def test_preserve_alphanumeric(self):
        assert sanitize_filename("Casa_123") == "Casa_123"


class TestBuildJobFolderName:
    def test_com_cliente_e_cidade(self):
        result = build_job_folder_name(
            "2026-05-26", "5513999999999", "Maria", "Santos - Gonzaga", "higienizacao"
        )
        # "Santos - Gonzaga" → sanitize: \s e \- viram "_" → "Santos___Gonzaga"
        assert result == "2026-05-26_5513999999999_Maria_Santos___Gonzaga_higienizacao"

    def test_sem_cliente(self):
        result = build_job_folder_name(
            "2026-05-26", "5513999999999", None, "Santos", "higienizacao"
        )
        assert "sem_nome" in result

    def test_sem_cidade(self):
        result = build_job_folder_name(
            "2026-05-26", "5513999999999", "Maria", None, "higienizacao"
        )
        assert "Maria" in result
        assert "Santos" not in result

    def test_acento_sanitizado(self):
        result = build_job_folder_name(
            "2026-05-26", "5513999999999", "João", "São Paulo", "instalacao"
        )
        assert "ã" not in result
        assert "ç" not in result


class TestBuildQuoteFilename:
    def test_nome_completo(self):
        result = build_quote_filename(
            client_name="Maria",
            service_type="higienizacao",
            city_bairro="Santos - Gonzaga",
            doc_date=date(2026, 5, 26),
            status="rascunho",
        )
        assert result == "ORCAMENTO_Maria_higienizacao_Santos_Gonzaga_20260526_rascunho.pdf"

    def test_sem_cidade(self):
        result = build_quote_filename(
            client_name="Maria",
            service_type="higienizacao",
            city_bairro=None,
            doc_date=date(2026, 5, 26),
            status="enviado",
        )
        assert "sem_cidade" in result

    def test_status_sanitizado(self):
        result = build_quote_filename(
            client_name="Maria",
            service_type="higienizacao",
            city_bairro="Santos",
            doc_date=date(2026, 5, 26),
            status="revisar_humano",
        )
        assert "revisar_humano" in result
        assert " " not in result


class TestBuildServiceOrderFilename:
    def test_nome_os(self):
        result = build_service_order_filename(
            client_name="Maria",
            service_type="higienizacao",
            city_bairro="Guaruja",
            doc_date=date(2026, 5, 26),
            status="assinada",
        )
        assert result.startswith("OS_Maria_")
        assert "20260526" in result
        assert "assinada" in result

    def test_status_com_espaco_substituido(self):
        result = build_service_order_filename(
            client_name="João",
            service_type="manutencao",
            city_bairro="Sao Vicente",
            doc_date=date(2026, 5, 27),
            status="em_andamento",
        )
        assert "em_andamento" in result
        assert " " not in result


class TestBuildProposalFilename:
    def test_nome_proposta(self):
        result = build_proposal_filename(
            client_name="Hotel X",
            service_type="vrf",
            city_bairro="Santos",
            doc_date=date(2026, 5, 26),
        )
        assert result.startswith("PROPOSTA_TECNICA_Hotel_X_")
        assert "20260526" in result
        assert ".pdf" in result


class TestBuildContractFilename:
    def test_nome_contrato(self):
        result = build_contract_filename(
            client_name="Condominio Y",
            contract_type="manutencao_recorrente",
            doc_date=date(2026, 6, 1),
        )
        assert result.startswith("CONTRATO_Condominio_Y_")
        assert "20260601" in result


class TestBuildPmocFilename:
    def test_nome_pmoc(self):
        result = build_pmoc_filename(
            client_name="Restaurante Z",
            location="cozinha_principal",
            doc_date=date(2026, 5, 20),
        )
        assert result.startswith("PMOC_Restaurante_Z_")
        assert "cozinha_principal" in result
        assert "20260520" in result

    def test_sem_local(self):
        result = build_pmoc_filename(
            client_name="Clinica W",
            location=None,
            doc_date=date(2026, 5, 20),
        )
        assert "sem_local" in result


class TestBuildLaudoFilename:
    def test_nome_laudo(self):
        result = build_laudo_filename(
            client_name="Fabrica ABC",
            report_type="eletrico",
            city_bairro="Cubatao",
            doc_date=date(2026, 5, 15),
        )
        assert result.startswith("LAUDO_Fabrica_ABC_")
        assert "eletrico" in result
        assert "Cubatao" in result
        assert "20260515" in result
