"""
Google Auth — Refrimix
Carrega OAuth credentials e access token para Google Drive/Calendar API.
Nunca expõe tokens em logs ou erros.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths from environment
# ---------------------------------------------------------------------------

TOKEN_PATH = os.getenv(
    "GOOGLE_OAUTH_TOKEN_PATH",
    "/srv/infra/google/refrimix/token.json",
)
CREDENTIALS_PATH = os.getenv(
    "GOOGLE_OAUTH_CREDENTIALS_PATH",
    "/srv/infra/google/refrimix/oauth_client.json",
)

# ---------------------------------------------------------------------------
# Masking
# ---------------------------------------------------------------------------

def _mask(s: str | None, keep: int = 6) -> str:
    """Máscara segura: mostra últimos keep chars."""
    if not s:
        return "<missing>"
    if len(s) <= keep:
        return "*" * len(s)
    return "..." + s[-keep:]


def _mask_path(path: str | None) -> str:
    """Máscara caminho: mostra só o filename."""
    if not path:
        return "<missing>"
    return Path(path).name


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_oauth_token() -> dict[str, Any]:
    """
    Lê o token OAuth do arquivo.
    Raises RuntimeError se arquivo ausente ou token malformado.
    Nunca expõe o access_token no log.
    """
    token_file = Path(TOKEN_PATH)

    if not token_file.exists():
        raise RuntimeError(
            f"Token OAuth não encontrado: {_mask_path(TOKEN_PATH)}. "
            "Rode o fluxo de OAuth primeiro."
        )

    try:
        with open(token_file) as f:
            token_data = json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Token OAuth malformado em {_mask_path(TOKEN_PATH)}: {exc}"
        )

    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError(
            f"access_token ausente no token em {_mask_path(TOKEN_PATH)}"
        )

    logger.info(
        "Token OAuth carregado: path=%s, expires_at=%s",
        _mask_path(TOKEN_PATH),
        _mask(token_data.get("expires_at")),
    )
    return token_data


def get_access_token() -> str:
    """
    Retorna access_token válido.
    Raises RuntimeError se ausente ou expirado.
    """
    import time

    token_data = load_oauth_token()
    expires_at = token_data.get("expires_at")

    if expires_at:
        try:
            expiry_seconds = float(expires_at)
            # 60s buffer para evitar edge case
            if time.time() >= expiry_seconds - 60:
                raise RuntimeError(
                    f"Token OAuth expirado em {_mask_path(TOKEN_PATH)}. "
                    "Rode o refresh OAuth."
                )
        except (ValueError, TypeError):
            pass

    return token_data["access_token"]


def check_credentials() -> dict[str, str]:
    """
    Verifica presença de credentials OAuth.
    Returns dict com status de cada arquivo.
    Nunca expõe conteúdo dos arquivos.
    """
    results: dict[str, str] = {}

    for name, path in [
        ("TOKEN_PATH", TOKEN_PATH),
        ("CREDENTIALS_PATH", CREDENTIALS_PATH),
    ]:
        p = Path(path)
        if p.exists():
            size = p.stat().st_size
            results[name] = f"exists({size} bytes)"
        else:
            results[name] = "MISSING"

    return results


def auth_summary() -> dict[str, Any]:
    """
    Retorna resumo de autenticação para logs de smoke test.
    Sem dados sensíveis.
    """
    cred_status = check_credentials()
    token_status: str
    token_data: dict[str, Any] = {}
    expires_at: str | None = None
    try:
        token_data = load_oauth_token()
        token_status = "loaded"
        expires_at = token_data.get("expires_at")
    except RuntimeError as exc:
        token_status = f"error: {exc}"

    access_token_masked: str | None = None
    if token_status == "loaded":
        access_token_masked = _mask(token_data.get("access_token"))

    return {
        "credentials_path": _mask_path(CREDENTIALS_PATH),
        "token_path": _mask_path(TOKEN_PATH),
        "credentials_status": cred_status.get("CREDENTIALS_PATH", "unknown"),
        "token_status": token_status,
        "expires_at": expires_at,
        "access_token_masked": access_token_masked,
    }
