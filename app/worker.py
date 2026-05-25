from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from typing import Any

import httpx
import redis.asyncio as redis
from fastapi import FastAPI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_graph.graph.graph import build_graph
from agent_graph.services.alerts import send_owner_alert
from agent_graph.services.conversation_memory import build_canonical_history
from agent_graph.services.whatsapp import normalize_whatsapp_number, send_whatsapp_text

logger = logging.getLogger(__name__)

GRAPH: Any = None
REDIS_POOL: redis.ConnectionPool | None = None
WORKER_TASKS: list[asyncio.Task[None]] = []
SCHEDULER_TASKS: list[asyncio.Task[None]] = []

_QUEUE_KEY = os.getenv("WHATSAPP_QUEUE_KEY", "whatsapp_rag:queue")
_PROCESSING_KEY = os.getenv("WHATSAPP_PROCESSING_QUEUE_KEY", "whatsapp_rag:processing")
_DLQ_KEY = os.getenv("WHATSAPP_DLQ_KEY", "whatsapp_rag:dead_letter")
_BOT_KEY = "whatsapp_rag:bot_enabled"

_CONV_TTL = int(os.getenv("CONV_TTL_SECONDS", "1800"))
_CONV_MAX_TURNS = int(os.getenv("CONV_MAX_TURNS", "6"))
_WORKER_COUNT = max(1, int(os.getenv("WORKER_CONCURRENCY", "4")))
_QUEUE_POP_TIMEOUT = int(os.getenv("WORKER_QUEUE_POP_TIMEOUT_SECONDS", "5"))
_MESSAGE_TIMEOUT = float(os.getenv("WORKER_MESSAGE_TIMEOUT_SECONDS", "180"))
_GRAPH_TIMEOUT = float(os.getenv("GRAPH_RESPONSE_TIMEOUT_SECONDS", "45"))
_MAX_ATTEMPTS = max(1, int(os.getenv("WORKER_MAX_ATTEMPTS", "3")))
_LOCK_TTL = int(os.getenv("CONV_LOCK_TTL_SECONDS", "240"))
_LOCK_WAIT = float(os.getenv("CONV_LOCK_WAIT_SECONDS", "20"))
_LOCK_REQUEUE_DELAY = float(os.getenv("CONV_LOCK_REQUEUE_DELAY_SECONDS", "0.4"))
_HANDOFF_ALERT_TTL = int(os.getenv("HANDOFF_ALERT_TTL_SECONDS", "21600"))
_OWNER_ALERT_TTL = int(os.getenv("OWNER_ALERT_DEDUP_TTL_SECONDS", "21600"))
_MANUAL_TAKEOVER_TTL = int(os.getenv("MANUAL_TAKEOVER_TTL_SECONDS", "86400"))
_ACTIVE_SERVICE_STATUSES = tuple(
    s.strip() for s in os.getenv(
        "ACTIVE_SERVICE_STATUSES",
        "scheduled,in_progress,awaiting_parts,awaiting_customer,approved,active",
    ).split(",")
    if s.strip()
)
_COMPLETED_SERVICE_STATUSES = tuple(
    s.strip() for s in os.getenv(
        "COMPLETED_SERVICE_STATUSES",
        "completed,done,finished,concluido,concluído,cancelled,canceled",
    ).split(",")
    if s.strip()
)

_BOT_OFF_MSG = os.getenv(
    "BOT_OFF_MESSAGE",
    "Oi! No momento estou atendendo pessoalmente. Te respondo em breve 🙂",
)
_OWNER_WORTHY_REASONS = {
    "explicit_handoff",
    "complaint_or_risk",
    "sensitive_complaint",
    "no_context_needs_human_review",
    "active_service_followup",
    "high_value_lead",
    "appointment_ready",
    "electrical_risk",
    "repeated_missing_critical_field",
}


class InvalidQueueMessage(ValueError):
    pass


class ConversationBusy(RuntimeError):
    pass


class QueueMessage(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    phone: str
    message: str
    instance: str = "default"
    message_type: str = "conversation"
    msg_id: str = ""
    media_url: str = ""
    media_base64: str = ""
    worker_attempts: int = Field(default=0, alias="_worker_attempts")

    @field_validator(
        "phone",
        "message",
        "instance",
        "message_type",
        "msg_id",
        "media_url",
        "media_base64",
        mode="before",
    )
    @classmethod
    def _stringify(cls, value: Any) -> str:
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)


class RedisConversationLock:
    _RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    end
    return 0
    """

    def __init__(self, client: redis.Redis, phone: str, *, ttl_seconds: int, wait_seconds: float) -> None:
        self.client = client
        self.key = f"conv_lock:{_safe_key(phone)}"
        self.token = str(uuid.uuid4())
        self.ttl_seconds = ttl_seconds
        self.wait_seconds = wait_seconds

    async def __aenter__(self) -> RedisConversationLock:
        deadline = asyncio.get_running_loop().time() + self.wait_seconds
        while True:
            acquired = await self.client.set(self.key, self.token, nx=True, ex=self.ttl_seconds)
            if acquired:
                return self
            if asyncio.get_running_loop().time() >= deadline:
                raise ConversationBusy(f"Conversa ocupada: {self.key}")
            await asyncio.sleep(random.uniform(0.05, 0.25))

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        with suppress(Exception):
            await self.client.eval(self._RELEASE_SCRIPT, 1, self.key, self.token)


def _safe_key(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_:+@.-]", "_", value.strip())
    return cleaned[:160] or "unknown"


def _message_text(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", message)
    return content if isinstance(content, str) else str(content)


def _safe_fallback_response(message_text: str) -> str:
    lowered = message_text.lower()
    if any(term in lowered for term in ("humano", "atendente", "reembolso", "cancelamento", "ninguém", "ninguem")):
        return (
            "Recebi sua mensagem. Tive uma instabilidade aqui, mas já deixei isso sinalizado "
            "e vou adiantar por aqui: me passa o número do orçamento ou serviço e o melhor horário pra retorno?"
        )
    return (
        "Recebi sua mensagem. Tive uma instabilidade rápida pra consultar os detalhes agora, "
        "mas já consigo adiantar: isso é instalação, manutenção ou higienização? Me passa também sua cidade/bairro."
    )


async def load_active_customer_service(phone: str) -> dict[str, Any] | None:
    """Carrega serviço em andamento para o número, quando houver."""
    if not os.getenv("DATABASE_URL") or not _ACTIVE_SERVICE_STATUSES:
        return None

    try:
        from prisma import Prisma

        db = Prisma()
        await db.connect()
        try:
            placeholders = ", ".join(f"${idx}" for idx in range(2, len(_ACTIVE_SERVICE_STATUSES) + 2))
            rows = await db.query_raw(
                f"""
                SELECT id, phone, service, status, address, scheduled_window, notes, updated_at
                FROM customer_services
                WHERE phone = $1
                  AND status IN ({placeholders})
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                phone,
                *_ACTIVE_SERVICE_STATUSES,
            )
        finally:
            await db.disconnect()
    except Exception as e:
        logger.warning("Não consegui consultar serviço ativo de %s: %s", phone, e)
        return None

    if not rows:
        return None

    row = rows[0]
    return {
        "id": str(row.get("id") or ""),
        "phone": str(row.get("phone") or phone),
        "service": row.get("service"),
        "status": row.get("status"),
        "address": row.get("address"),
        "scheduled_window": row.get("scheduled_window"),
        "notes": row.get("notes"),
        "updated_at": str(row.get("updated_at") or ""),
    }


async def load_last_customer_service(phone: str) -> dict[str, Any] | None:
    """Carrega o último serviço concluído/encerrado para diferenciar cliente antigo."""
    if not os.getenv("DATABASE_URL") or not _COMPLETED_SERVICE_STATUSES:
        return None

    try:
        from prisma import Prisma

        db = Prisma()
        await db.connect()
        try:
            placeholders = ", ".join(f"${idx}" for idx in range(2, len(_COMPLETED_SERVICE_STATUSES) + 2))
            rows = await db.query_raw(
                f"""
                SELECT id, phone, service, status, address, scheduled_window, notes, created_at, updated_at
                FROM customer_services
                WHERE phone = $1
                  AND status IN ({placeholders})
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                phone,
                *_COMPLETED_SERVICE_STATUSES,
            )
        finally:
            await db.disconnect()
    except Exception as e:
        logger.warning("Não consegui consultar último serviço de %s: %s", phone, e)
        return None

    if not rows:
        return None

    row = rows[0]
    return {
        "id": str(row.get("id") or ""),
        "phone": str(row.get("phone") or phone),
        "service": row.get("service"),
        "status": row.get("status"),
        "address": row.get("address"),
        "scheduled_window": row.get("scheduled_window"),
        "notes": row.get("notes"),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def manual_takeover_key(phone: str) -> str:
    return f"manual_takeover:{_safe_key(normalize_whatsapp_number(phone) or phone)}"


async def is_manual_takeover(r: redis.Redis, phone: str) -> bool:
    return await r.get(manual_takeover_key(phone)) == "1"


async def set_manual_takeover(r: redis.Redis, phone: str, enabled: bool) -> None:
    key = manual_takeover_key(phone)
    if enabled:
        await r.set(key, "1", ex=_MANUAL_TAKEOVER_TTL)
    else:
        await r.delete(key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: start queue consumers and tear down on shutdown."""
    global GRAPH, REDIS_POOL, WORKER_TASKS, SCHEDULER_TASKS

    GRAPH = build_graph()
    logger.info("LangGraph compiled OK")

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_POOL = redis.ConnectionPool.from_url(redis_url, decode_responses=True)
    logger.info("Redis pool connected: %s", redis_url)

    WORKER_TASKS = [
        asyncio.create_task(worker_loop(worker_id), name=f"whatsapp-rag-worker-{worker_id}")
        for worker_id in range(_WORKER_COUNT)
    ]
    logger.info("Started %s worker task(s)", len(WORKER_TASKS))

    SCHEDULER_TASKS = []
    if os.getenv("AGENDA_GROUP_ENABLED", "1") == "1":
        try:
            from app.agenda_scheduler import agenda_digest_loop
        except ModuleNotFoundError:
            from agenda_scheduler import agenda_digest_loop

        SCHEDULER_TASKS.append(
            asyncio.create_task(agenda_digest_loop(0, get_redis), name="agenda-refrimix-scheduler")
        )
        logger.info("Scheduler de agenda iniciado")

    yield

    for task in SCHEDULER_TASKS:
        task.cancel()
    if SCHEDULER_TASKS:
        await asyncio.gather(*SCHEDULER_TASKS, return_exceptions=True)
    SCHEDULER_TASKS = []

    for task in WORKER_TASKS:
        task.cancel()
    if WORKER_TASKS:
        await asyncio.gather(*WORKER_TASKS, return_exceptions=True)
    WORKER_TASKS = []

    if REDIS_POOL:
        await REDIS_POOL.disconnect()
    logger.info("Worker shutdown complete")


async def get_redis() -> redis.Redis:
    if REDIS_POOL is None:
        raise RuntimeError("Redis pool not initialized")
    return redis.Redis(connection_pool=REDIS_POOL)


async def send_whatsapp_message(phone: str, text: str, instance: str = "default") -> bool:
    """Send text message back to WhatsApp via Evolution API."""
    return await send_whatsapp_text(phone, text, instance)


def _wav_to_ogg_opus(wav_bytes: bytes) -> bytes:
    """Converte WAV (qualquer taxa/canais) para OGG OPUS 16kHz mono via ffmpeg.
    Fazemos a conversão localmente para não depender dos parâmetros internos da
    Evolution API, que produz eco/distorção ao receber WAV 24kHz do Chatterbox.
    Parâmetros: 64kbps, application=voip — otimizado para voz no WhatsApp.
    Fallback: retorna o WAV original se ffmpeg falhar.
    """
    import shutil
    import subprocess
    import tempfile

    ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_in:
            tmp_in.write(wav_bytes)
            tmp_in_path = tmp_in.name
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp_out:
            tmp_out_path = tmp_out.name

        result = subprocess.run(
            [
                ffmpeg, "-y", "-i", tmp_in_path,
                "-c:a", "libopus",
                "-b:a", "64k",
                "-ar", "16000",
                "-ac", "1",
                "-application", "voip",
                tmp_out_path,
            ],
            capture_output=True,
            timeout=15,
        )
        if result.returncode == 0:
            ogg_bytes = open(tmp_out_path, "rb").read()
            logger.info("WAV→OGG OPUS: %d → %d bytes", len(wav_bytes), len(ogg_bytes))
            return ogg_bytes
        logger.warning("ffmpeg WAV→OGG falhou: %s", result.stderr[-300:].decode("utf-8", errors="replace"))
    except Exception as exc:
        logger.warning("_wav_to_ogg_opus erro: %s", exc)
    finally:
        for p in (tmp_in_path, tmp_out_path):
            try:
                import os as _os; _os.unlink(p)
            except Exception:
                pass
    return wav_bytes


async def send_whatsapp_audio(phone: str, audio_bytes: bytes, instance: str = "default") -> bool:
    """Envia áudio OGG OPUS via Evolution API sendWhatsAppAudio.
    Converte WAV→OGG localmente com ffmpeg para garantir qualidade (evita eco
    causado pela conversão interna da Evolution API com WAV 24kHz do Chatterbox).
    """
    import base64

    audio_bytes = _wav_to_ogg_opus(audio_bytes)
    api_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    instance_name = os.getenv("EVOLUTION_INSTANCE", instance)
    audio_b64 = base64.b64encode(audio_bytes).decode()
    number = normalize_whatsapp_number(phone)

    if not number:
        logger.error("Número WhatsApp inválido para envio de áudio: %r", phone)
        return False

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_url}/message/sendWhatsAppAudio/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"number": number, "audio": audio_b64},
            )
            if resp.status_code in (200, 201):
                logger.info("Áudio enviado para %s: %s bytes", number, len(audio_bytes))
                return True
            logger.warning("Evolution API (áudio) erro %s: %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Falha ao enviar áudio para %s: %s", phone, e)
        return False


async def notify_owner(
    lead_phone: str,
    lead_message: str,
    instance: str = "default",
    *,
    handoff_mode: str = "hard_transfer",
    reason: str = "",
    conversation_summary: str = "",
    next_step: str = "",
) -> bool:
    """Notifica o dono (Will) sobre handoff real ou alerta soft de alto valor."""
    title = _alert_title(reason, handoff_mode)
    return await send_owner_alert(
        {
            "title": title,
            "phone": lead_phone,
            "reason": reason or "não informado",
            "last_message": lead_message,
            "summary": conversation_summary or "sem histórico anterior",
            "next_step": next_step or "acompanhar pelo WhatsApp Web",
            "priority": "high" if reason.startswith("high_value") else "normal",
            "instance": instance,
        }
    )


def _summarize_conversation(messages: list[BaseMessage]) -> str:
    turns: list[str] = []
    for message in messages[-8:]:
        content = _message_text(message).strip()
        if not content:
            continue
        role = "Cliente" if isinstance(message, HumanMessage) else "Will"
        compact = re.sub(r"\s+", " ", content)
        turns.append(f"{role}: {compact[:140]}")
    return " | ".join(turns)[-900:]


def _alert_title(reason: str, handoff_mode: str) -> str:
    titles = {
        "appointment_ready": "LEAD PRONTO PARA AGENDAR",
        "no_context_needs_human_review": "REVISÃO HUMANA",
        "active_service_followup": "CLIENTE EM ATENDIMENTO",
        "complaint_or_risk": "RECLAMAÇÃO OU RISCO",
        "sensitive_complaint": "RECLAMAÇÃO OU RISCO",
        "light_complaint": "RECLAMAÇÃO OU RISCO",
        "explicit_handoff": "CLIENTE PEDIU HUMANO",
        "high_value_lead": "LEAD DE ALTO VALOR",
        "high_value_vrf": "LEAD VRF/VRV",
        "high_value_vrv": "LEAD VRF/VRV",
        "high_value_duto": "PROJETO DE DUTOS",
        "high_value_splitao": "SPLITÃO / COMERCIAL",
        "high_value_pmoc": "PMOC / CONTRATO",
        "electrical_risk": "RISCO ELÉTRICO",
    }
    if handoff_mode == "hard_transfer":
        return "HANDOFF HUMANO"
    if reason in titles:
        return titles[reason]
    if reason.startswith("high_value"):
        return "LEAD DE ALTO VALOR"
    return "ALERTA OPERACIONAL"


def _handoff_next_step(handoff_mode: str, reason: str) -> str:
    if handoff_mode == "hard_transfer":
        if reason in {"sensitive_complaint", "complaint_or_risk"}:
            return "Assumir a conversa, pedir dados do orçamento/serviço e dar retorno claro."
        return "Assumir a conversa no WhatsApp Web; o bot já pediu serviço e cidade para adiantar."
    if reason == "appointment_ready":
        return "Confirmar janela de agenda e assumir se o cliente responder horário preferido."
    if reason == "no_context_needs_human_review":
        return "Ler o histórico e responder manualmente se a intenção continuar incerta."
    if reason == "light_complaint":
        return "Acompanhar em paralelo; o bot pediu detalhes para adiantar a análise."
    if reason == "active_service_followup":
        return "Verificar serviço em andamento, agenda e pendências; cliente já não deve ser tratado como lead novo."
    if reason.startswith("high_value"):
        return "Assumir ou acompanhar de perto; pedir planta/fotos, quantidade de ambientes e objetivo do sistema."
    return "Acompanhar sem interromper o bot; revisar dados de qualificação e entrar se fizer sentido."


async def maybe_notify_owner_from_result(
    r: redis.Redis,
    *,
    phone: str,
    message_text: str,
    result: dict[str, Any],
    instance: str,
) -> bool:
    mode = result.get("handoff_mode") or "none"
    if mode == "none":
        return False

    reason = result.get("handoff_reason") or result.get("outcome") or "sem_motivo"
    reason = str(reason)
    if mode == "hard_transfer" and result.get("handoff_already_notified"):
        return False

    owner_worthy = reason in _OWNER_WORTHY_REASONS or reason.startswith("high_value")
    if not owner_worthy:
        logger.info("Motivo de handoff não direcionado ao owner: %s", reason)
        return False

    ttl = _OWNER_ALERT_TTL or _HANDOFF_ALERT_TTL
    alert_key = f"owner_alert:{_safe_key(phone)}:{_safe_key(reason)}:{datetime.now().date().isoformat()}"
    should_alert = await r.set(alert_key, "1", nx=True, ex=ttl)
    if not should_alert:
        logger.info("Alerta owner deduplicado para %s (%s)", phone, reason)
        return False

    messages_out = result.get("messages", [])
    summary = _summarize_conversation(messages_out if isinstance(messages_out, list) else [])
    return await notify_owner(
        phone,
        message_text,
        instance,
        handoff_mode=mode,
        reason=reason,
        conversation_summary=summary,
        next_step=_handoff_next_step(mode, reason),
    )


async def load_history(phone: str, client: redis.Redis | None = None) -> list[BaseMessage]:
    """Carrega histórico de conversa do Redis. Retorna lista de BaseMessage."""
    r = client or await get_redis()
    raw = await r.get(f"conv_history:{phone}")
    if not raw:
        return []
    try:
        turns = json.loads(raw)
        if not isinstance(turns, list):
            return []

        messages: list[BaseMessage] = []
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            role = turn.get("role")
            content = turn.get("content")
            if not isinstance(content, str) or not content.strip():
                continue
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        return messages
    except Exception as e:
        logger.warning("Histórico inválido para %s: %s", phone, e)
        return []


async def save_history(phone: str, messages: list[BaseMessage], client: redis.Redis | None = None) -> None:
    """Salva histórico de conversa no Redis com TTL de inatividade."""
    turns: list[dict[str, str]] = []
    for message in messages:
        if isinstance(message, HumanMessage):
            turns.append({"role": "user", "content": _message_text(message)})
        elif isinstance(message, AIMessage):
            turns.append({"role": "assistant", "content": _message_text(message)})

    max_msgs = _CONV_MAX_TURNS * 2
    if len(turns) > max_msgs:
        turns = turns[-max_msgs:]

    r = client or await get_redis()
    await r.set(f"conv_history:{phone}", json.dumps(turns, ensure_ascii=False), ex=_CONV_TTL)


async def is_bot_enabled(r: redis.Redis) -> bool:
    val = await r.get(_BOT_KEY)
    return val != "0"


def _parse_queue_message(raw_item: str) -> QueueMessage:
    try:
        data = json.loads(raw_item)
    except json.JSONDecodeError as exc:
        raise InvalidQueueMessage(f"Payload não é JSON: {raw_item[:160]}") from exc

    try:
        message = QueueMessage.model_validate(data)
    except ValidationError as exc:
        raise InvalidQueueMessage(f"Payload inválido: {exc}") from exc

    if not message.phone.strip() or not message.message.strip():
        raise InvalidQueueMessage("Payload sem phone/message")
    return message


async def _ack_queue_item(r: redis.Redis, raw_item: str) -> None:
    await r.lrem(_PROCESSING_KEY, 1, raw_item)


async def _dead_letter(r: redis.Redis, raw_item: str, reason: str) -> None:
    payload = {"reason": reason, "raw": raw_item}
    await r.lpush(_DLQ_KEY, json.dumps(payload, ensure_ascii=False))
    await _ack_queue_item(r, raw_item)


async def _requeue_item(
    r: redis.Redis,
    raw_item: str,
    *,
    reason: str,
    increment_attempt: bool,
    delay_seconds: float = 0.0,
) -> None:
    new_item = raw_item
    attempts = 0

    if increment_attempt:
        try:
            data = json.loads(raw_item)
            attempts = int(data.get("_worker_attempts", 0)) + 1
            data["_worker_attempts"] = attempts
            new_item = json.dumps(data, ensure_ascii=False)
        except Exception:
            await _dead_letter(r, raw_item, f"{reason}; falha ao incrementar tentativa")
            return

    await _ack_queue_item(r, raw_item)

    if increment_attempt and attempts >= _MAX_ATTEMPTS:
        await r.lpush(_DLQ_KEY, json.dumps({"reason": reason, "raw": new_item}, ensure_ascii=False))
        logger.error("Mensagem enviada para DLQ após %s tentativa(s): %s", attempts, reason)
        return

    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    await r.lpush(_QUEUE_KEY, new_item)
    logger.warning("Mensagem reenfileirada (%s): %s", reason, new_item[:180])


async def _process_customer_message(payload: QueueMessage, r: redis.Redis, worker_id: int) -> None:
    if GRAPH is None:
        raise RuntimeError("LangGraph não inicializado")

    phone = normalize_whatsapp_number(payload.phone)
    message_text = payload.message.strip()
    instance = payload.instance or "default"

    if not phone:
        logger.error("Mensagem sem número normalizável: %r", payload.phone)
        return

    logger.info(
        "worker=%s processando [%s] de %s: %s",
        worker_id,
        payload.message_type,
        phone,
        message_text[:60],
    )

    if not await is_bot_enabled(r):
        logger.info("Bot PAUSADO; mensagem de %s ignorada pela IA", phone)
        if _BOT_OFF_MSG:
            await send_whatsapp_message(phone, _BOT_OFF_MSG, instance)
        return

    async with RedisConversationLock(r, phone, ttl_seconds=_LOCK_TTL, wait_seconds=_LOCK_WAIT):
        if await is_manual_takeover(r, phone):
            logger.info("Humano assumiu; IA pausada para este contato: %s", phone)
            return

        redis_history = await load_history(phone, r)
        canonical_history, memory_meta = await build_canonical_history(phone, redis_history)
        is_first_message = not bool(memory_meta.get("is_conversation_started"))
        messages_with_history = canonical_history + [HumanMessage(content=message_text)]
        active_service = await load_active_customer_service(phone)
        last_service = None if active_service else await load_last_customer_service(phone)
        if active_service:
            logger.info(
                "Cliente %s tem serviço ativo: %s/%s",
                phone,
                active_service.get("service") or "-",
                active_service.get("status") or "-",
            )
        elif last_service:
            logger.info(
                "Cliente %s tem serviço antigo: %s/%s",
                phone,
                last_service.get("service") or "-",
                last_service.get("status") or "-",
            )

        initial_state = {
            "messages": messages_with_history,
            "intent": None,
            "service": None,
            "outcome": None,
            "handoff_mode": "none",
            "handoff_reason": None,
            "handoff_already_notified": False,
            "rag_context": [],
            "customer_data": {
                "phone": phone,
                "is_first_message": is_first_message,
                "active_service": active_service,
                "last_service": last_service,
                "memory": memory_meta,
            },
            "is_human": False,
            "confidence": 1.0,
            "message_type": payload.message_type,
            "msg_id": payload.msg_id,
            "media_url": payload.media_url,
            "media_base64": payload.media_base64,
            "instance": instance,
            "response_modality": None,
            "audio_bytes": None,
        }

        try:
            result = await asyncio.wait_for(GRAPH.ainvoke(initial_state), timeout=_GRAPH_TIMEOUT)
        except Exception as e:
            logger.exception("Falha no grafo; usando fallback seguro para %s: %s", phone, e)
            fallback = _safe_fallback_response(message_text)
            result = {
                "messages": messages_with_history + [AIMessage(content=fallback)],
                "response_modality": "text",
                "handoff_mode": "none",
                "handoff_reason": None,
                "outcome": "fallback_seguro",
            }

        await maybe_notify_owner_from_result(
            r,
            phone=phone,
            message_text=message_text,
            result=result,
            instance=instance,
        )

        messages_out = result.get("messages", [])
        ai_message = next(
            (
                _message_text(message)
                for message in reversed(messages_out)
                if isinstance(message, AIMessage) and _message_text(message)
            ),
            None,
        )

        if ai_message:
            clean_history = list(messages_with_history) + [AIMessage(content=ai_message)]
            await save_history(phone, clean_history, r)
            logger.info("Histórico salvo: %s (%s msgs)", phone, len(clean_history))

        modality = result.get("response_modality", "text")
        audio_bytes = result.get("audio_bytes")

        if modality == "audio" and isinstance(audio_bytes, bytes) and audio_bytes:
            sent = await send_whatsapp_audio(phone, audio_bytes, instance)
            if not sent and ai_message:
                await send_whatsapp_message(phone, ai_message, instance)
        elif ai_message:
            await send_whatsapp_message(phone, ai_message, instance)
        else:
            logger.warning("Nenhuma resposta AI no resultado para %s", phone)


async def process_queue_item(raw_item: str, worker_id: int) -> None:
    payload = _parse_queue_message(raw_item)
    r = await get_redis()
    await _process_customer_message(payload, r, worker_id)


async def worker_loop(worker_id: int = 0) -> None:
    """Consume Redis queue concurrently while serializing work per conversation."""
    logger.info("Worker %s started", worker_id)
    r = await get_redis()

    while True:
        raw_item: str | None = None
        try:
            raw_item = await r.brpoplpush(_QUEUE_KEY, _PROCESSING_KEY, timeout=_QUEUE_POP_TIMEOUT)
            if raw_item is None:
                continue

            await asyncio.wait_for(process_queue_item(raw_item, worker_id), timeout=_MESSAGE_TIMEOUT)
            await _ack_queue_item(r, raw_item)

        except asyncio.CancelledError:
            raise
        except InvalidQueueMessage as e:
            if raw_item is not None:
                await _dead_letter(r, raw_item, str(e))
            logger.error("Mensagem descartada: %s", e)
        except ConversationBusy as e:
            if raw_item is not None:
                await _requeue_item(
                    r,
                    raw_item,
                    reason=str(e),
                    increment_attempt=False,
                    delay_seconds=_LOCK_REQUEUE_DELAY,
                )
        except asyncio.TimeoutError:
            if raw_item is not None:
                await _requeue_item(r, raw_item, reason="timeout no processamento", increment_attempt=True)
        except Exception as e:
            logger.exception("Worker %s error: %s", worker_id, e)
            if raw_item is not None:
                await _requeue_item(r, raw_item, reason=str(e), increment_attempt=True)
            await asyncio.sleep(0.5)
