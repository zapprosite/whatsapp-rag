"""
Document Jobs — Refrimix
Dataclasses para jobs de documento (geração PDF + save Drive).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import uuid


DOCUMENT_TYPES = [
    "quote_pdf",
    "technical_proposal_pdf",
    "service_order_pdf",
    "technical_report_pdf",
    "pmoc_pdf",
    "contract_pdf",
    "sla_pdf",
    "instagram_media_brief",
]

SERVICE_TYPES = [
    "higienizacao",
    "instalacao",
    "manutencao",
    "conserto",
    "vrf",
    "cassete",
    "piso_teto",
    "split",
    "janela",
    "central",
    "torre",
    "estufagem",
    "outro",
]

ORCAMENTO_STATUS = [
    "rascunho",
    "enviado",
    "aprovado",
    "perdido",
    "revisar_humano",
]


@dataclass(frozen=True)
class DocumentJob:
    """
    Job de documento: documento a ser gerado e salvo no Drive.

    Attributes
    ----------
    job_id : str
        Identificador único do job.
    lead_id : str
        ID do lead associated ao documento.
    document_type : str
        Tipo do documento (quote_pdf, service_order_pdf, etc).
    service_type : str
        Tipo de serviço (higienizacao, instalacao, etc).
    target_drive_kind : str
        Pasta operacional destino (orcamentos, ordens_servico, etc).
    template_id : str | None
        ID do template a ser usado na geração.
    input_data : dict
        Dados de entrada para o documento (nome, cidade, etc).
    requires_human_review : bool
        Se o documento precisa de revisão humana antes de envio.
    status : str
        Estado do job: pendente, gerado, salvo, falhou.
    created_at : datetime
        Timestamp de criação.
    updated_at : datetime
        Timestamp de última atualização.
    drive_file_id : str | None
        ID do arquivo no Google Drive (após upload).
    drive_folder_id : str | None
        ID da pasta no Google Drive (após criação/busca).
    local_pdf_path : str | None
        Caminho local do PDF gerado.
    error_message : str | None
        Mensagem de erro caso status seja falhou.
    """

    job_id: str
    lead_id: str
    document_type: str
    service_type: str
    target_drive_kind: str
    template_id: str | None
    input_data: dict
    requires_human_review: bool
    status: str = "pendente"
    created_at: datetime = field(default_factory=lambda: datetime.now())
    updated_at: datetime = field(default_factory=lambda: datetime.now())
    drive_file_id: str | None = None
    drive_folder_id: str | None = None
    local_pdf_path: str | None = None
    error_message: str | None = None

    def mark_generated(self, local_pdf_path: str) -> "DocumentJob":
        """Marca job como gerado (PDF criado localmente)."""
        return replace(
            self,
            status="gerado",
            local_pdf_path=local_pdf_path,
            updated_at=datetime.now(),
        )

    def mark_saved(self, drive_file_id: str, drive_folder_id: str) -> "DocumentJob":
        """Marca job como salvo (uploaded para o Drive)."""
        return replace(
            self,
            status="salvo",
            drive_file_id=drive_file_id,
            drive_folder_id=drive_folder_id,
            updated_at=datetime.now(),
        )

    def mark_failed(self, error: str) -> "DocumentJob":
        """Marca job como falhou."""
        return replace(
            self,
            status="falhou",
            error_message=error,
            updated_at=datetime.now(),
        )


def create_document_job(
    lead_id: str,
    document_type: str,
    service_type: str,
    input_data: dict,
    template_id: str | None = None,
) -> DocumentJob:
    """
    Factory para criar DocumentJob com valores derivados.
    """
    from refrimix_core.domain.drive_taxonomy import (
        document_type_to_folder,
        is_human_review_required,
    )

    folder = document_type_to_folder(document_type)
    if folder is None:
        raise ValueError(f"Tipo de documento desconhecido: {document_type}")

    # Deriva target_drive_kind do nome da pasta
    kind_map = {
        "01_PROPOSTAS_TECNICAS": "propostas_tecnicas",
        "02_CONTRATOS_E_SLA": "contratos_sla",
        "03_ORDENS_DE_SERVICO": "ordens_servico",
        "04_PMOC_E_LAUDOS": "pmoc_laudos",
        "05_ORCAMENTOS": "orcamentos",
        "06_MIDIAS_E_REDES_SOCIAIS": "midias_redes_sociais",
    }
    target_drive_kind = kind_map.get(folder, folder.lower())

    return DocumentJob(
        job_id=str(uuid.uuid4()),
        lead_id=lead_id,
        document_type=document_type,
        service_type=service_type,
        target_drive_kind=target_drive_kind,
        template_id=template_id,
        input_data=input_data,
        requires_human_review=is_human_review_required(document_type),
    )
