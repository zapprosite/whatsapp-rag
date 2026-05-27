"""
Drive Taxonomy — Refrimix
Mapeia tipo de documento → pasta do Google Drive.
"""
from __future__ import annotations

DOCUMENT_DRIVE_MAP: dict[str, str] = {
    "technical_proposal_pdf": "01_PROPOSTAS_TECNICAS",
    "contract_pdf": "02_CONTRATOS_E_SLA",
    "sla_pdf": "02_CONTRATOS_E_SLA",
    "service_order_pdf": "03_ORDENS_DE_SERVICO",
    "pmoc_pdf": "04_PMOC_E_LAUDOS",
    "technical_report_pdf": "04_PMOC_E_LAUDOS",
    "quote_pdf": "05_ORCAMENTOS",
    "instagram_media_brief": "06_MIDIAS_E_REDES_SOCIAIS",
}

DRIVE_FOLDER_KINDS = [
    "propostas_tecnicas",
    "contratos_sla",
    "ordens_servico",
    "pmoc_laudos",
    "orcamentos",
    "midias_redes_sociais",
]


def document_type_to_folder(document_type: str) -> str | None:
    """Retorna o nome da pasta operacional para o tipo de documento."""
    return DOCUMENT_DRIVE_MAP.get(document_type)


def folder_to_document_types(folder_name: str) -> list[str]:
    """Retorna os tipos de documento que vão naquela pasta."""
    return [dt for dt, f in DOCUMENT_DRIVE_MAP.items() if f == folder_name]


def is_human_review_required(document_type: str) -> bool:
    """Documentos de alto valor exigem revisão humana antes do envio."""
    return document_type in (
        "contract_pdf",
        "sla_pdf",
        "technical_proposal_pdf",
        "pmoc_pdf",
    )
