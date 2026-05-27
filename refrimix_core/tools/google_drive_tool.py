"""
Google Drive Tool — Refrimix
Organiza, salva, busca e cria pastas no Google Drive da Refrimix.
Usa Google Drive API v3, não o caminho GNOME google-drive://.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
import requests

from refrimix_core.domain.drive_taxonomy import DOCUMENT_DRIVE_MAP, DRIVE_FOLDER_KINDS
from refrimix_core.domain.drive_naming import (
    build_job_folder_name,
    sanitize_filename,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.readonly",
]

TOKEN_PATH = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", "/srv/infra/google/refrimix/token.json")
CREDENTIALS_PATH = os.getenv("GOOGLE_OAUTH_CREDENTIALS_PATH", "/srv/infra/google/refrimix/oauth_client.json")

# Pasta raiz da Refrimix (deve constar no .env)
ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
ROOT_FOLDER_NAME = os.getenv("GOOGLE_DRIVE_ROOT_NAME", "refrimix Tecnologia")

# Folder IDs específicos das pastas operacionais (de .env)
FOLDER_IDS = {
    "propostas_tecnicas": os.getenv("GOOGLE_DRIVE_FOLDER_PROPOSTAS_TECNICAS", ""),
    "contratos_sla": os.getenv("GOOGLE_DRIVE_FOLDER_CONTRATOS_SLA", ""),
    "ordens_servico": os.getenv("GOOGLE_DRIVE_FOLDER_ORDENS_SERVICO", ""),
    "pmoc_laudos": os.getenv("GOOGLE_DRIVE_FOLDER_PMOC_LAUDOS", ""),
    "orcamentos": os.getenv("GOOGLE_DRIVE_FOLDER_ORCAMENTOS", ""),
    "midias_redes_sociais": os.getenv(
        "GOOGLE_DRIVE_FOLDER_MIDIAS_REDES_SOCIAIS", ""
    ),
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _get_access_token() -> str:
    """Lê token OAuth e retorna access token."""
    token_file = Path(TOKEN_PATH)
    if not token_file.exists():
        raise RuntimeError(
            f"Token OAuth não encontrado em {TOKEN_PATH}. "
            "Rode o fluxo de OAuth primeiro."
        )
    with open(token_file) as f:
        token_data = json.load(f)
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError(f"access_token ausente em {TOKEN_PATH}")
    return access_token


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_access_token()}"}


# ---------------------------------------------------------------------------
# Folder helpers
# ---------------------------------------------------------------------------

def _create_folder(name: str, parent_id: str) -> dict[str, Any]:
    """Cria uma pasta dentro de parent_id."""
    url = f"{DRIVE_API_BASE}/files"
    payload = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    with httpx.Client() as client:
        resp = client.post(url, headers=_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _find_folder(name: str, parent_id: str) -> dict[str, Any] | None:
    """
    Busca pasta pelo nome dentro de parent_id.
    Usa query da API: name='{name}' and mimeType='application/vnd.google-apps.folder'
    """
    import urllib.parse

    encoded_name = urllib.parse.quote(f"'{name}'")
    query = (
        f"name={encoded_name} and "
        f"mimeType='application/vnd.google-apps.folder' and "
        f"'{parent_id}' in parents and "
        f"trashed=false"
    )
    url = f"{DRIVE_API_BASE}/files?q={query}&fields=files(id,name,mimeType)"
    with httpx.Client() as client:
        resp = client.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    files = data.get("files", [])
    return files[0] if files else None


def _ensure_folder(name: str, parent_id: str) -> str:
    """
    Encontra ou cria pasta. Retorna folder_id.
    """
    existing = _find_folder(name, parent_id)
    if existing:
        return existing["id"]
    created = _create_folder(name, parent_id)
    logger.info("Pasta criada no Drive: %s (%s)", name, created["id"])
    return created["id"]


# ---------------------------------------------------------------------------
# Public API — folders
# ---------------------------------------------------------------------------

def get_refrimix_root_folder_id() -> str:
    """
    Retorna o folder_id raiz da pasta 'refrimix Tecnologia'.
    Valida que a pasta existe e não está no trash.
    """
    if not ROOT_FOLDER_ID:
        raise RuntimeError(
            "GOOGLE_DRIVE_ROOT_FOLDER_ID não está configurado no .env. "
            "Informe o folder_id da pasta raiz do Google Drive da Refrimix."
        )
    return ROOT_FOLDER_ID


def get_operational_folder(kind: str) -> str:
    """
    Retorna o folder_id da pasta operacional.
    Se o folder_id estiver vazio no env, busca pelo nome dentro da raiz.
    """
    if kind not in FOLDER_IDS:
        raise ValueError(f"kind desconhecido: {kind}. Válidos: {DRIVE_FOLDER_KINDS}")

    folder_id = FOLDER_IDS[kind]
    if folder_id:
        return folder_id

    # Fallback: busca pelo nome
    root_id = get_refrimix_root_folder_id()

    # Nome da pasta operacional: ex "01_PROPOSTAS_TECNICAS"
    folder_name = _kind_to_folder_name(kind)
    found = _find_folder(folder_name, root_id)
    if found:
        return found["id"]

    # Se não encontrou, cria
    created = _create_folder(folder_name, root_id)
    logger.info("Pasta operacional criada: %s (%s)", folder_name, created["id"])
    return created["id"]


def _kind_to_folder_name(kind: str) -> str:
    """Converte kind → nome real da pasta no Drive."""
    kind_to_folder = {
        "propostas_tecnicas": "01_PROPOSTAS_TECNICAS",
        "contratos_sla": "02_CONTRATOS_E_SLA",
        "ordens_servico": "03_ORDENS_DE_SERVICO",
        "pmoc_laudos": "04_PMOC_E_LAUDOS",
        "orcamentos": "05_ORCAMENTOS",
        "midias_redes_sociais": "06_MIDIAS_E_REDES_SOCIAIS",
    }
    return kind_to_folder.get(kind, kind)


def ensure_year_month_folder(
    parent_folder_id: str, year: int, month: int
) -> str:
    """
    Garante que existe /{year}/{month:02d}/ dentro de parent_folder_id.
    Retorna o folder_id do mês.
    """
    year_str = str(year)
    month_str = str(month).zfill(2)

    year_folder = _ensure_folder(year_str, parent_folder_id)
    month_folder = _ensure_folder(month_str, year_folder)
    return month_folder


def ensure_job_folder(
    parent_folder_id: str,
    date_str: str,  # YYYY-MM-DD
    phone: str,
    client_name: str | None,
    city_bairro: str | None,
    service_type: str,
) -> str:
    """
    Cria ou encontra a pasta do atendimento.
    Estrutura: {YYYY-MM-DD}_{telefone}_{cliente_ou_sem_nome}_{cidade}_{servico}
    """
    folder_name = build_job_folder_name(date_str, phone, client_name, city_bairro, service_type)
    return _ensure_folder(folder_name, parent_folder_id)


# ---------------------------------------------------------------------------
# Public API — file operations
# ---------------------------------------------------------------------------

def _upload_multipart(
    url: str,
    metadata: dict[str, Any],
    file_content: bytes,
    filename: str,
    mime_type: str,
) -> dict[str, Any]:
    """Upload genérico via multipart usando requests."""
    import io

    metadata_json = json.dumps(metadata)
    files = {
        "metadata": (None, metadata_json, "application/json; charset=UTF-8"),
        "file": (filename, io.BytesIO(file_content), mime_type),
    }
    resp = requests.post(url, files=files, headers={"Authorization": f"Bearer {_get_access_token()}"}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def save_generated_pdf(
    folder_id: str,
    local_pdf_path: str,
    document_type: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Faz upload de um PDF local para o Drive.

    Returns
    -------
    dict com keys: id, name, mimeType, createdTime, webViewLink
    """
    local_path = Path(local_pdf_path)
    if not local_path.exists():
        raise FileNotFoundError(f"PDF não encontrado: {local_pdf_path}")

    filename = local_path.name

    url = f"{DRIVE_UPLOAD_BASE}/files?uploadType=multipart"

    with open(local_path, "rb") as f:
        file_content = f.read()

    result = _upload_multipart(
        url,
        {"name": filename, "parents": [folder_id]},
        file_content,
        filename,
        "application/pdf",
    )
    logger.info("PDF salvo no Drive: %s (id=%s)", result["name"], result["id"])
    return result


def save_lead_summary_markdown(
    folder_id: str,
    lead_summary: dict[str, Any],
) -> dict[str, Any]:
    """
    Salva resumo_lead.md na pasta do atendimento.
    """
    content_lines = [
        f"# Resumo do Lead\n",
        f"**ID:** {lead_summary.get('lead_id', 'N/A')}\n",
        f"**Telefone:** {lead_summary.get('phone', 'N/A')}\n",
        f"**Cliente:** {lead_summary.get('client_name', 'N/A')}\n",
        f"**Cidade/Bairro:** {lead_summary.get('city_bairro', 'N/A')}\n",
        f"**Serviço:** {lead_summary.get('service_type', 'N/A')}\n",
        f"**Intent:** {lead_summary.get('intent', 'N/A')}\n",
        f"**Risco:** {lead_summary.get('risk', 'N/A')}\n",
        f"**Status:** {lead_summary.get('status', 'N/A')}\n",
        f"**Fonte:** {lead_summary.get('source', 'whatsapp_evolution')}\n",
    ]

    if lead_summary.get("message_history"):
        content_lines.append("\n## Histórico de Mensagens\n")
        for msg in lead_summary["message_history"]:
            role = msg.get("role", "user")
            text = msg.get("text", "")
            content_lines.append(f"- **{role}:** {text}\n")

    if lead_summary.get("notes"):
        content_lines.append(f"\n## Observações\n{lead_summary['notes']}\n")

    content = "".join(content_lines)
    return _upload_text_file(
        folder_id,
        "resumo_lead.md",
        content,
        mime_type="text/markdown; charset=UTF-8",
    )


def save_metadata_json(
    folder_id: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Salva metadata.json na pasta do atendimento.
    """
    content = json.dumps(metadata, ensure_ascii=False, indent=2)
    return _upload_text_file(
        folder_id,
        "metadata.json",
        content,
        mime_type="application/json; charset=UTF-8",
    )


def _upload_text_file(
    folder_id: str,
    filename: str,
    content: str,
    mime_type: str = "text/plain; charset=UTF-8",
) -> dict[str, Any]:
    """Helper genérico para fazer upload de arquivo de texto."""
    url = f"{DRIVE_UPLOAD_BASE}/files?uploadType=multipart"
    content_bytes = content.encode("utf-8")

    result = _upload_multipart(
        url,
        {"name": filename, "parents": [folder_id]},
        content_bytes,
        filename,
        mime_type,
    )
    return result


# ---------------------------------------------------------------------------
# Public API — search
# ---------------------------------------------------------------------------

def search_refrimix_files(
    query: str,
    folder_kind: str | None = None,
    mime_type: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Pesquisa arquivos na estrutura Refrimix.

    Uses Drive API query (not fullText) for indexed search.
    Supports: name contains, mimeType, parents, trashed.
    """
    conditions = ["trashed=false"]

    if query:
        # Escapa aspas duplas
        safe_query = query.replace('"', '\\"')
        conditions.append(f"name contains '{safe_query}'")

    if folder_kind:
        folder_id = get_operational_folder(folder_kind)
        conditions.append(f"'{folder_id}' in parents")

    if mime_type:
        conditions.append(f"mimeType = '{mime_type}'")

    q = " and ".join(conditions)
    encoded_q = q.replace(" ", "+")

    url = (
        f"{DRIVE_API_BASE}/files"
        f"?q={encoded_q}"
        f"&fields=files(id,name,mimeType,createdTime,modifiedTime,"
        f"webViewLink,parents)"
        f"&pageSize={limit}"
    )

    with httpx.Client() as client:
        resp = client.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("files", [])


def find_latest_client_documents(
    phone: str,
    client_name: str | None = None,
    document_type: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Busca histórico de documentos do cliente por telefone.
    """
    conditions = [
        "trashed=false",
        f"name contains '{phone}'",
    ]
    if client_name:
        safe_name = sanitize_filename(client_name)
        conditions.append(f" or name contains '{safe_name}'")

    if document_type:
        folder_kind = _document_type_to_kind(document_type)
        if folder_kind:
            folder_id = get_operational_folder(folder_kind)
            conditions.append(f"'{folder_id}' in parents")

    q = " and ".join(conditions)
    encoded_q = q.replace(" ", "+")

    url = (
        f"{DRIVE_API_BASE}/files"
        f"?q={encoded_q}"
        f"&fields=files(id,name,mimeType,createdTime,modifiedTime,webViewLink)"
        f"&orderBy=createdTime desc"
        f"&pageSize={limit}"
    )

    with httpx.Client() as client:
        resp = client.get(url, headers=_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("files", [])


def _document_type_to_kind(document_type: str) -> str | None:
    """Converte document_type → folder kind."""
    doc_to_kind = {
        "quote_pdf": "orcamentos",
        "technical_proposal_pdf": "propostas_tecnicas",
        "service_order_pdf": "ordens_servico",
        "technical_report_pdf": "pmoc_laudos",
        "pmoc_pdf": "pmoc_laudos",
        "contract_pdf": "contratos_sla",
        "sla_pdf": "contratos_sla",
        "instagram_media_brief": "midias_redes_sociais",
    }
    return doc_to_kind.get(document_type)
