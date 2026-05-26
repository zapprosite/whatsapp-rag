from __future__ import annotations

import asyncio
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


async def _evolution_request_with_retry(
    method: str,
    url: str,
    headers: dict[str, str],
    json_data: dict[str, Any] | None = None,
    max_retries: int = 3,
) -> httpx.Response | None:
    """Helper para realizar requisições HTTP resilientes com backoff exponencial na Evolution API."""
    delay = 0.5
    last_response = None
    
    async with httpx.AsyncClient(timeout=_EVO_TIMEOUT) as client:
        for attempt in range(max_retries):
            try:
                if method.upper() == "POST":
                    resp = await client.post(url, headers=headers, json=json_data)
                else:
                    resp = await client.get(url, headers=headers)
                
                if resp.status_code in (200, 201):
                    return resp
                
                last_response = resp
                if resp.status_code == 429:
                    logger.warning("Evolution API 429 Rate Limit (tentativa %d/%d)", attempt + 1, max_retries)
                elif resp.status_code >= 500:
                    logger.warning("Evolution API %d Erro no Servidor (tentativa %d/%d)", resp.status_code, attempt + 1, max_retries)
                else:
                    return resp
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.warning("Erro de conexão na Evolution API (tentativa %d/%d): %s", attempt + 1, max_retries, exc)
                
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
                
    return last_response


async def send_whatsapp_text(target: str, text: str, instance: str = "default") -> bool:
    api_url, api_key, instance_name = _evolution_config(instance)
    number = normalize_whatsapp_number(target)
    if not number:
        logger.error("Número WhatsApp inválido para envio de texto: %r", target)
        return False

    try:
        resp = await _evolution_request_with_retry(
            "POST",
            f"{api_url}/message/sendText/{instance_name}",
            headers={"apikey": api_key, "Content-Type": "application/json"},
            json_data={"number": number, "text": text},
        )
        if resp and resp.status_code in (200, 201):
            logger.info("Texto enviado para %s: %s", number, text[:80])
            return True
        logger.warning("Evolution API sendText erro %s: %s", resp.status_code if resp else "N/A", resp.text[:300] if resp else "Sem resposta")
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
        resp = await _evolution_request_with_retry(
            "POST",
            f"{api_url}/message/sendText/{instance_name}",
            headers={"apikey": api_key, "Content-Type": "application/json"},
            json_data={"number": group_jid, "text": text},
        )
        if resp and resp.status_code in (200, 201):
            logger.info("Texto enviado para grupo %s: %s", group_jid, text[:80])
            return True

        fallback = await _evolution_request_with_retry(
            "POST",
            f"{api_url}/message/sendTextGroup/{instance_name}",
            headers={"apikey": api_key, "Content-Type": "application/json"},
            json_data={"groupJid": group_jid, "number": group_jid, "text": text},
        )
        if fallback and fallback.status_code in (200, 201):
            logger.info("Texto enviado para grupo %s via fallback", group_jid)
            return True
        logger.warning(
            "Evolution API grupo erro sendText=%s fallback=%s: %s",
            resp.status_code if resp else "N/A",
            fallback.status_code if fallback else "N/A",
            fallback.text[:300] if fallback else "Sem resposta",
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
    for endpoint in endpoints:
        try:
            resp = await _evolution_request_with_retry("GET", endpoint, headers={"apikey": api_key})
            if not resp or resp.status_code not in (200, 201):
                resp = await _evolution_request_with_retry(
                    "POST",
                    endpoint,
                    headers={"apikey": api_key},
                    json_data={"getParticipants": True},
                )
            if resp and resp.status_code in (200, 201):
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
        resp = await _evolution_request_with_retry(
            "POST",
            f"{api_url}/chat/sendPresence/{instance_name}",
            headers={"apikey": api_key, "Content-Type": "application/json"},
            json_data={
                "number": number,
                "presence": presence,
                "delay": delay_ms,
            },
        )
        if resp and resp.status_code in (200, 201):
            logger.debug("Presença '%s' enviada para %s com delay %d ms", presence, number, delay_ms)
            return True
        logger.warning("Evolution API sendPresence erro %s: %s", resp.status_code if resp else "N/A", resp.text[:300] if resp else "Sem resposta")
        return False
    except Exception as exc:
        logger.error("Falha ao enviar presença para %s: %s", target, exc)
        return False

