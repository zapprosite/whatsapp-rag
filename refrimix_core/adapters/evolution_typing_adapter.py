"""
evolution_typing_adapter.py — Adapter para typing indicator da Evolution API.

Evolution API endpoints:
  POST /messages/typing  — ativa typing
  (ativa enquanto o bot está processando)
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_EVOLUTION_TYPING_URL: str | None = None


def _get_typing_url() -> str:
    global _EVOLUTION_TYPING_URL
    if _EVOLUTION_TYPING_URL is None:
        base = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip("/")
        _EVOLUTION_TYPING_URL = f"{base}/messages/typing"
    return _EVOLUTION_TYPING_URL


async def send_typing_on(phone: str, instance: str = "default") -> bool:
    """Envia typing indicator 'on' para o telefone do cliente."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                _get_typing_url(),
                json={
                    "number": phone,
                    "instanceName": instance,
                },
            )
            resp.raise_for_status()
            logger.debug("Typing ON enviado para %s", phone)
            return True
    except Exception as e:
        logger.warning("Falha ao enviar typing ON para %s: %s", phone, e)
        return False


async def send_typing_off(phone: str, instance: str = "default") -> bool:
    """Envia typing indicator 'off' quando resposta é enviada."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                _get_typing_url(),
                json={
                    "number": phone,
                    "instanceName": instance,
                },
            )
            resp.raise_for_status()
            logger.debug("Typing OFF enviado para %s", phone)
            return True
    except Exception as e:
        logger.warning("Falha ao enviar typing OFF para %s: %s", phone, e)
        return False
