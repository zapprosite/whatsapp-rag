from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

try:
    from runtime import get_redis, normalize_whatsapp_number, queue_key, send_whatsapp_message, set_manual_takeover
except ModuleNotFoundError:
    from runtime import get_redis, normalize_whatsapp_number, queue_key, send_whatsapp_message, set_manual_takeover

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])

_WEBHOOK_REDIS_TIMEOUT = float(os.getenv("WEBHOOK_REDIS_TIMEOUT_SECONDS", "3.0"))
_UNSUPPORTED_MESSAGE_TYPES = {"stickerMessage", "videoMessage", "documentMessage"}

# Status webhook mappings (Evolution API -> StatusType)
_WHATSAPP_STATUS_MAP = {
    "sent": "sent",
    "delivered": "delivered",
    "read": "read",
    "failed": "failed",
    "pending": "pending",
}


@dataclass(frozen=True)
class IncomingWebhook:
    phone: str
    message: str
    instance: str
    message_type: str
    msg_id: str
    media_url: str
    media_base64: str


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and str(value).strip():
            return str(value).strip()
    return ""


def _mask_identifier(value: Any) -> str:
    text = str(value or "")
    digits = re.sub(r"\D+", "", text)
    if len(digits) >= 8:
        return f"{digits[:4]}...{digits[-4:]}"
    if text:
        return "<masked>"
    return ""


def _redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"remotejid", "remotejidalt", "participant", "participantalt", "remote", "id", "from", "phone", "number", "sender"}:
                redacted[key] = _mask_identifier(item)
            elif lowered in {"conversation", "caption", "text", "content", "body", "message"}:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    return value


def _unwrap_message_block(message: dict[str, Any]) -> dict[str, Any]:
    current = message
    for wrapper in ("ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2"):
        nested = _as_dict(_as_dict(current.get(wrapper)).get("message"))
        if nested:
            current = nested
    return current


def _is_phone_jid(value: Any) -> bool:
    return isinstance(value, str) and value.endswith("@s.whatsapp.net") and bool(normalize_whatsapp_number(value))


def _is_lid_jid(value: Any) -> bool:
    return isinstance(value, str) and value.endswith("@lid")


def _detect_message_type(data_block: dict[str, Any], msg_block: dict[str, Any]) -> str:
    if "audioMessage" in msg_block:
        return "audioMessage"
    if "imageMessage" in msg_block:
        return "imageMessage"
    if "extendedTextMessage" in msg_block or "conversation" in msg_block:
        return "conversation"
    return _first_text(data_block.get("messageType"), data_block.get("type"), "conversation")


def _extract_message_text(body: dict[str, Any], data_block: dict[str, Any], msg_block: dict[str, Any]) -> str:
    button_response = _as_dict(msg_block.get("buttonsResponseMessage"))
    template_response = _as_dict(msg_block.get("templateButtonReplyMessage"))
    list_response = _as_dict(msg_block.get("listResponseMessage"))
    single_select = _as_dict(list_response.get("singleSelectReply"))
    data_message = data_block.get("message")

    return _first_text(
        msg_block.get("conversation"),
        _as_dict(msg_block.get("extendedTextMessage")).get("text"),
        _as_dict(msg_block.get("imageMessage")).get("caption"),
        _as_dict(msg_block.get("audioMessage")).get("caption"),
        _as_dict(msg_block.get("videoMessage")).get("caption"),
        button_response.get("selectedDisplayText"),
        button_response.get("selectedButtonId"),
        template_response.get("selectedDisplayText"),
        template_response.get("selectedId"),
        list_response.get("title"),
        list_response.get("description"),
        single_select.get("selectedRowId"),
        data_message if isinstance(data_message, str) else "",
        data_block.get("text"),
        data_block.get("content"),
        body.get("message"),
        body.get("text"),
        body.get("content"),
        body.get("body"),
    )


def _extract_phone(body: dict[str, Any], data_block: dict[str, Any], key_block: dict[str, Any]) -> str:
    sender = _as_dict(body.get("sender"))
    data_sender = _as_dict(data_block.get("sender"))
    candidates = (
        key_block.get("remoteJidAlt"),
        key_block.get("participantAlt"),
        key_block.get("remote"),
        key_block.get("remoteJid"),
        key_block.get("participant"),
        sender.get("remoteJidAlt"),
        sender.get("participantAlt"),
        sender.get("remote"),
        sender.get("id"),
        data_sender.get("remoteJidAlt"),
        data_sender.get("participantAlt"),
        data_sender.get("remote"),
        data_sender.get("id"),
        data_block.get("from"),
        data_block.get("phone"),
        data_block.get("number"),
        body.get("phone"),
        body.get("from"),
        body.get("number"),
    )
    phone_jid = next((candidate for candidate in candidates if _is_phone_jid(candidate)), "")
    if phone_jid:
        return phone_jid
    non_lid = next((candidate for candidate in candidates if isinstance(candidate, str) and candidate.strip() and not _is_lid_jid(candidate)), "")
    if non_lid:
        return non_lid
    return _first_text(*candidates)


def _is_from_me(body: dict[str, Any], data_block: dict[str, Any], key_block: dict[str, Any]) -> bool:
    return any(
        value is True or (isinstance(value, str) and value.strip().lower() == "true")
        for value in (key_block.get("fromMe"), data_block.get("fromMe"), body.get("fromMe"))
    )


def _owner_phone() -> str:
    return normalize_whatsapp_number(os.getenv("OWNER_PHONE", ""))


def _manual_takeover_command(text: str) -> tuple[str, str] | None:
    normalized = text.strip().lower()
    match = re.search(r"\b(assumir|pausar|humano|liberar|retomar)\b\s+(\+?\d[\d\s().-]{8,})", normalized)
    if not match:
        return None
    action = match.group(1)
    phone = normalize_whatsapp_number(match.group(2))
    if not phone:
        return None
    if action in {"assumir", "pausar", "humano"}:
        return "assumir", phone
    return "liberar", phone


async def _handle_owner_command(parsed: IncomingWebhook) -> bool:
    owner = _owner_phone()
    if not owner or parsed.phone != owner:
        return False
    command = _manual_takeover_command(parsed.message)
    if not command:
        return False
    action, lead_phone = command
    r = await get_redis()
    enabled = action == "assumir"
    await set_manual_takeover(r, lead_phone, enabled)
    if enabled:
        response = (
            f"IA pausada só para o lead {lead_phone}.\n\n"
            f"Responda o cliente manualmente. Para liberar depois, envie: liberar {lead_phone}"
        )
    else:
        response = f"IA liberada novamente para o lead {lead_phone}."
    await send_whatsapp_message(parsed.phone, response, parsed.instance)
    return True


def parse_evolution_webhook(body: dict[str, Any]) -> tuple[IncomingWebhook | None, str | None]:
    event = body.get("event")
    if event and event != "messages.upsert":
        return None, f"ignored event: {event}"

    data_block = _as_dict(body.get("data"))
    key_block = _as_dict(data_block.get("key"))
    msg_block = _unwrap_message_block(_as_dict(data_block.get("message")))

    # Ignorar grupos de forma robusta e precoce
    is_group = False
    for jid in (
        key_block.get("remoteJid"),
        key_block.get("remote"),
        key_block.get("remoteJidAlt"),
        body.get("sender", {}).get("remoteJid") if isinstance(body.get("sender"), dict) else None,
    ):
        if jid and ("@g.us" in str(jid) or "group" in str(jid).lower()):
            is_group = True
            break
    if is_group:
        return None, "group"

    if _is_from_me(body, data_block, key_block):
        return None, "fromMe"

    message_type = _detect_message_type(data_block, msg_block)
    if message_type in _UNSUPPORTED_MESSAGE_TYPES:
        return None, f"unsupported type: {message_type}"
    if any(name in msg_block for name in _UNSUPPORTED_MESSAGE_TYPES):
        return None, f"unsupported type: {message_type}"

    phone_raw = _extract_phone(body, data_block, key_block)
    if "@g.us" in phone_raw or "group" in phone_raw.lower():
        return None, "group"
    if phone_raw.endswith("@broadcast"):
        return None, "broadcast"

    message = _extract_message_text(body, data_block, msg_block)
    media_base64 = _first_text(data_block.get("base64"))
    media_url = ""

    if message_type == "audioMessage":
        audio = _as_dict(msg_block.get("audioMessage"))
        media_url = _first_text(audio.get("url"), audio.get("mediaUrl"), data_block.get("mediaUrl"))
        media_base64 = media_base64 or _first_text(audio.get("base64"))
        message = message or "[áudio]"
    elif message_type == "imageMessage":
        image = _as_dict(msg_block.get("imageMessage"))
        media_url = _first_text(image.get("url"), image.get("mediaUrl"), data_block.get("mediaUrl"))
        media_base64 = media_base64 or _first_text(image.get("base64"))
        message = message or "[imagem]"

    if not phone_raw or not message:
        return None, "missing fields"

    phone = normalize_whatsapp_number(phone_raw)
    if not phone:
        return None, "invalid phone"

    return IncomingWebhook(
        phone=phone,
        message=message,
        instance=_first_text(body.get("instanceName"), body.get("instance"), data_block.get("instance"), "default"),
        message_type=message_type,
        msg_id=_first_text(key_block.get("id"), data_block.get("id"), body.get("id")),
        media_url=media_url,
        media_base64=media_base64,
    ), None


@router.post("/evolution")
async def receive_webhook(request: Request) -> JSONResponse:
    """Recebe webhook da Evolution API e enfileira para o worker responder."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    parsed, skipped = parse_evolution_webhook(body)
    if skipped:
        if skipped == "missing fields":
            data_dbg = _as_dict(body.get("data"))
            logger.warning(
                "Webhook missing fields — event=%s key=%s msg_keys=%s messageType=%s",
                body.get("event"),
                _redact_payload(_as_dict(data_dbg.get("key"))),
                list(_as_dict(data_dbg.get("message")).keys()),
                data_dbg.get("messageType"),
            )
        else:
            logger.info("Webhook ignorado: %s body_keys=%s", skipped, list(body.keys()))
        return JSONResponse({"status": "ok", "skipped": skipped})

    if parsed and parsed.phone and not parsed.phone.startswith("55"):
        logger.warning(
            "Webhook phone suspeito (%s) — payload data.key=%s sender=%s",
            _mask_identifier(parsed.phone),
            _redact_payload(_as_dict(_as_dict(body.get("data")).get("key"))),
            _redact_payload(body.get("sender")),
        )

    assert parsed is not None
    if await _handle_owner_command(parsed):
        return JSONResponse({"status": "ok", "skipped": "owner_command"})

    payload = {
        "phone": parsed.phone,
        "message": parsed.message,
        "instance": parsed.instance,
        "message_type": parsed.message_type,
        "msg_id": parsed.msg_id,
        "media_url": parsed.media_url,
        "media_base64": parsed.media_base64,
    }

    try:
        r = await get_redis()
        if parsed.msg_id:
            dedup_key = f"processed_msg:{parsed.msg_id}"
            is_new = await asyncio.wait_for(r.set(dedup_key, "1", nx=True, ex=60), timeout=_WEBHOOK_REDIS_TIMEOUT)
            if not is_new:
                logger.info("Mensagem duplicada ignorada: %s", parsed.msg_id)
                return JSONResponse({"status": "ok", "skipped": "duplicate"})

        target_queue = queue_key()
        await asyncio.wait_for(
            r.lpush(target_queue, json.dumps(payload, ensure_ascii=False)),
            timeout=_WEBHOOK_REDIS_TIMEOUT,
        )
    except Exception as e:
        logger.exception("Webhook falhou ao enfileirar mensagem: %s", e)
        return JSONResponse({"status": "error", "error": "queue_unavailable"}, status_code=503)

    logger.info("Enfileirado [%s] de %s em %s", parsed.message_type, _mask_identifier(parsed.phone), target_queue)
    return JSONResponse({"status": "ok"})


# ── WhatsApp Status Webhook ───────────────────────────────────────────────────
@router.post("/evolution-status")
async def receive_status_webhook(request: Request) -> JSONResponse:
    """Recebe webhook de status de mensagem (sent/delivered/read/failed).

    NÃO gera resposta nova — só atualiza o rastreador de status.
    Status updates não devem fazer o bot responder (evita "vi que você leu").
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Evolution API status callback structure
    event = body.get("event", "")
    data = _as_dict(body.get("data", {}))
    key = _as_dict(data.get("key", {}))

    # Só processa eventos de status, não mensagens novas
    if event and not event.startswith("message."):
        # Callback de status — processar
        pass
    elif event == "messages.update":
        # Status update via messages.update
        pass
    else:
        return JSONResponse({"status": "ok", "skipped": "not_a_status_event"})

    msg_id = _first_text(key.get("id"), data.get("id"))
    if not msg_id:
        return JSONResponse({"status": "ok", "skipped": "no_message_id"})

    # Extrair status do payload — Evolution envia via data.update ключ
    update_data = _as_dict(data.get("update", {}))
    status_str = _first_text(
        update_data.get("status"),
        data.get("status"),
        body.get("status"),
        body.get("update", {}).get("status") if isinstance(body.get("update"), dict) else None,
    )
    if not status_str:
        return JSONResponse({"status": "ok", "skipped": "no_status_field"})

    # Mapear para StatusType
    from refrimix_core.monitoring.whatsapp_status_tracker import StatusType
    try:
        status = StatusType(status_str.lower())
    except ValueError:
        logger.info("Status desconhecido ignorado: %s", status_str)
        return JSONResponse({"status": "ok", "skipped": f"unknown_status:{status_str}"})

    # Resolver conversation_id via Redis (msg_id → phone → conv_id)
    try:
        r = await get_redis()
        # Primeiro: verificar se temos o msg_id como key direta
        conv_id_key = f"msg_conv:{msg_id}"
        conv_id_raw = await asyncio.wait_for(r.get(conv_id_key), timeout=_WEBHOOK_REDIS_TIMEOUT)
        if conv_id_raw:
            conv_id = conv_id_raw
        else:
            # Fallback: derive do phone lookup — busca phone pelo msg_id
            phone_key = f"msg_phone:{msg_id}"
            phone_raw = await asyncio.wait_for(r.get(phone_key), timeout=_WEBHOOK_REDIS_TIMEOUT)
            if phone_raw:
                import hashlib
                conv_id = hashlib.md5(f"{phone_raw}:{msg_id}".encode()).hexdigest()[:16]
            else:
                conv_id = f"unknown_{msg_id[:12]}"
    except Exception as e:
        logger.warning("Status webhook: falha ao buscar conversation_id: %s", e)
        conv_id = f"unknown_{msg_id[:12]}"

    # Atualizar tracker
    try:
        from worker import _get_status_tracker
        tracker = _get_status_tracker()
        tracker.track_message_status(msg_id, conv_id, status)
        logger.info(
            "[STATUS] msg_id=%s conv=%s status=%s",
            _mask_identifier(msg_id),
            _mask_identifier(conv_id),
            status.value,
        )
    except Exception as e:
        logger.warning("Falha ao atualizar status tracker: %s", e)

    return JSONResponse({"status": "ok", "respond": False})
