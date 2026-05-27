"""
Drive Naming — Refrimix
Padrões de nomenclatura de arquivos e pastas.
"""
from __future__ import annotations

import unicodedata
import re
from datetime import date


def sanitize_filename(name: str) -> str:
    """Remove acentos, espaços e caracteres perigosos de nomes de arquivo."""
    # Normaliza unicode e remove acentos
    normalized = unicodedata.normalize("NFD", name)
    ascii_str = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    # Substitui espaços e separadores por underscore
    safe = re.sub(r"[\s\-]+", "_", ascii_str)
    # Remove caracteres que não são alfanumérico ou underscore
    safe = re.sub(r"[^a-zA-Z0-9_\.]", "", safe)
    return safe


def build_job_folder_name(
    date_str: str,  # YYYY-MM-DD
    phone: str,
    client_name: str | None,
    city_bairro: str | None,
    service_type: str,
) -> str:
    """
    Monta nome padronizado da pasta do atendimento:
    {YYYY-MM-DD}_{telefone}_{cliente_ou_sem_nome}_{cidade}_{servico}
    """
    parts = [date_str, phone]

    if client_name:
        parts.append(sanitize_filename(client_name))
    else:
        parts.append("sem_nome")

    if city_bairro:
        city_clean = sanitize_filename(city_bairro.replace(" ", "_"))
        parts.append(city_clean)

    parts.append(sanitize_filename(service_type))

    return "_".join(parts)


def build_quote_filename(
    client_name: str,
    service_type: str,
    city_bairro: str | None,
    doc_date: date,
    status: str,
) -> str:
    """
    ORCAMENTO_{cliente}_{servico}_{cidade}_{YYYYMMDD}_{status}.pdf
    """
    date_str = doc_date.strftime("%Y%m%d")
    city = sanitize_filename(city_bairro or "sem_cidade")
    client = sanitize_filename(client_name)
    service = sanitize_filename(service_type)
    status_sanitized = sanitize_filename(status)
    return f"ORCAMENTO_{client}_{service}_{city}_{date_str}_{status_sanitized}.pdf"


def build_service_order_filename(
    client_name: str,
    service_type: str,
    city_bairro: str | None,
    doc_date: date,
    status: str,
) -> str:
    """
    OS_{cliente}_{servico}_{cidade}_{YYYYMMDD}_{status}.pdf
    """
    date_str = doc_date.strftime("%Y%m%d")
    city = sanitize_filename(city_bairro or "sem_cidade")
    client = sanitize_filename(client_name)
    service = sanitize_filename(service_type)
    status_sanitized = sanitize_filename(status)
    return f"OS_{client}_{service}_{city}_{date_str}_{status_sanitized}.pdf"


def build_proposal_filename(
    client_name: str,
    service_type: str,
    city_bairro: str | None,
    doc_date: date,
) -> str:
    """
    PROPOSTA_TECNICA_{cliente}_{servico}_{cidade}_{YYYYMMDD}.pdf
    """
    date_str = doc_date.strftime("%Y%m%d")
    city = sanitize_filename(city_bairro or "sem_cidade")
    client = sanitize_filename(client_name)
    service = sanitize_filename(service_type)
    return f"PROPOSTA_TECNICA_{client}_{service}_{city}_{date_str}.pdf"


def build_contract_filename(
    client_name: str,
    contract_type: str,
    doc_date: date,
) -> str:
    """
    CONTRATO_{cliente}_{tipo}_{YYYYMMDD}.pdf
    """
    date_str = doc_date.strftime("%Y%m%d")
    client = sanitize_filename(client_name)
    ctype = sanitize_filename(contract_type)
    return f"CONTRATO_{client}_{ctype}_{date_str}.pdf"


def build_pmoc_filename(
    client_name: str,
    location: str | None,
    doc_date: date,
) -> str:
    """
    PMOC_{cliente}_{local}_{YYYYMMDD}.pdf
    """
    date_str = doc_date.strftime("%Y%m%d")
    client = sanitize_filename(client_name)
    loc = sanitize_filename(location or "sem_local")
    return f"PMOC_{client}_{loc}_{date_str}.pdf"


def build_laudo_filename(
    client_name: str,
    report_type: str,
    city_bairro: str | None,
    doc_date: date,
) -> str:
    """
    LAUDO_{cliente}_{tipo}_{cidade}_{YYYYMMDD}.pdf
    """
    date_str = doc_date.strftime("%Y%m%d")
    city = sanitize_filename(city_bairro or "sem_cidade")
    client = sanitize_filename(client_name)
    rtype = sanitize_filename(report_type)
    return f"LAUDO_{client}_{rtype}_{city}_{date_str}.pdf"
