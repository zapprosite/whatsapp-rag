from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_EVO_TIMEOUT = 30.0


def normalize_whatsapp_number(value: str) -> str:
    """Converte telefone/JID individual em número aceito pela Evolution API."""
    raw = str(value or "").strip()
    local = raw.split("@", 1)[0].split(":", 1)[0]
    return re.sub(r"\D", "", local)


def _evolution_config(instance: str = "default") -> tuple[str, str, str]:
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080").rstrip("/")
    api_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
    instance_name = os.getenv("EVOLUTION_INSTANCE", instance)
    return api_url, api_key, instance_name


async def send_whatsapp_text(target: str, text: str, instance: str = "default") -> bool:
    api_url, api_key, instance_name = _evolution_config(instance)
    number = normalize_whatsapp_number(target)
    if not number:
        logger.error("Número WhatsApp inválido para envio de texto: %r", target)
        return False

    try:
        async with httpx.AsyncClient(timeout=_EVO_TIMEOUT) as client:
            resp = await client.post(
                f"{api_url}/message/sendText/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"number": number, "text": text},
            )
        if resp.status_code in (200, 201):
            logger.info("Texto enviado para %s: %s", number, text[:80])
            return True
        logger.warning("Evolution API sendText erro %s: %s", resp.status_code, resp.text[:300])
        return False
    except Exception as exc:
        logger.error("Falha ao enviar texto para %s: %s", target, exc)
        return False


async def send_whatsapp_group_text(group_jid: str, text: str, instance: str = "default") -> bool:
    group_jid = str(group_jid or "").strip()
    if "@g.us" not in group_jid:
        logger.warning("AGENDA_GROUP_JID inválido para grupo: %r", group_jid)
        return False

    api_url, api_key, instance_name = _evolution_config(instance)
    try:
        async with httpx.AsyncClient(timeout=_EVO_TIMEOUT) as client:
            resp = await client.post(
                f"{api_url}/message/sendText/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"number": group_jid, "text": text},
            )
            if resp.status_code in (200, 201):
                logger.info("Texto enviado para grupo %s: %s", group_jid, text[:80])
                return True

            fallback = await client.post(
                f"{api_url}/message/sendTextGroup/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"groupJid": group_jid, "number": group_jid, "text": text},
            )
        if fallback.status_code in (200, 201):
            logger.info("Texto enviado para grupo %s via fallback", group_jid)
            return True
        logger.warning(
            "Evolution API grupo erro sendText=%s fallback=%s: %s",
            resp.status_code,
            fallback.status_code,
            fallback.text[:300],
        )
        return False
    except Exception as exc:
        logger.error("Falha ao enviar texto para grupo %s: %s", group_jid, exc)
        return False


def _extract_groups(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("groups", "data", "response"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_groups(value)
            if nested:
                return nested
    return []


async def list_whatsapp_groups(instance: str = "default") -> list[dict]:
    api_url, api_key, instance_name = _evolution_config(instance)
    endpoints = (
        f"{api_url}/group/fetchAllGroups/{instance_name}",
        f"{api_url}/group/findGroupInfos/{instance_name}",
        f"{api_url}/chat/findGroups/{instance_name}",
    )
    async with httpx.AsyncClient(timeout=_EVO_TIMEOUT) as client:
        for endpoint in endpoints:
            try:
                resp = await client.get(endpoint, headers={"apikey": api_key})
                if resp.status_code not in (200, 201):
                    resp = await client.post(endpoint, headers={"apikey": api_key}, json={"getParticipants": True})
                if resp.status_code not in (200, 201):
                    continue
                groups = _extract_groups(resp.json())
                if groups:
                    return groups
            except Exception as exc:
                logger.debug("Falha ao listar grupos em %s: %s", endpoint, exc)
    return []


async def send_whatsapp_presence(target: str, presence: str, delay_ms: int = 15000, instance: str = "default") -> bool:
    """Envia sinal de presença (composing, recording, paused) para a Evolution API.

    Usado para mascarar latência de LLM/TTS mostrando 'digitando...' ou 'gravando áudio...'.
    """
    api_url, api_key, instance_name = _evolution_config(instance)
    number = normalize_whatsapp_number(target)
    if not number:
        logger.error("Número WhatsApp inválido para presença: %r", target)
        return False

    try:
        async with httpx.AsyncClient(timeout=_EVO_TIMEOUT) as client:
            resp = await client.post(
                f"{api_url}/chat/sendPresence/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={
                    "number": number,
                    "presence": presence,
                    "delay": delay_ms,
                },
            )
        if resp.status_code in (200, 201):
            logger.debug("Presença '%s' enviada para %s com delay %d ms", presence, number, delay_ms)
            return True
        logger.warning("Evolution API sendPresence erro %s: %s", resp.status_code, resp.text[:300])
        return False
    except Exception as exc:
        logger.error("Falha ao enviar presença para %s: %s", target, exc)
        return False

