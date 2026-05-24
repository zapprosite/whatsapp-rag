from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import uuid
from contextlib import asynccontextmanager, suppress
from typing import Any

import httpx
import redis.asyncio as redis
from fastapi import FastAPI
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from agent_graph.graph.graph import build_graph

logger = logging.getLogger(__name__)

GRAPH: Any = None
REDIS_POOL: redis.ConnectionPool | None = None
WORKER_TASKS: list[asyncio.Task[None]] = []

_QUEUE_KEY = os.getenv("WHATSAPP_QUEUE_KEY", "whatsapp_rag:queue")
_PROCESSING_KEY = os.getenv("WHATSAPP_PROCESSING_QUEUE_KEY", "whatsapp_rag:processing")
_DLQ_KEY = os.getenv("WHATSAPP_DLQ_KEY", "whatsapp_rag:dead_letter")
_BOT_KEY = "whatsapp_rag:bot_enabled"

_CONV_TTL = int(os.getenv("CONV_TTL_SECONDS", "1800"))
_CONV_MAX_TURNS = int(os.getenv("CONV_MAX_TURNS", "6"))
_WORKER_COUNT = max(1, int(os.getenv("WORKER_CONCURRENCY", "4")))
_QUEUE_POP_TIMEOUT = int(os.getenv("WORKER_QUEUE_POP_TIMEOUT_SECONDS", "5"))
_MESSAGE_TIMEOUT = float(os.getenv("WORKER_MESSAGE_TIMEOUT_SECONDS", "180"))
_MAX_ATTEMPTS = max(1, int(os.getenv("WORKER_MAX_ATTEMPTS", "3")))
_LOCK_TTL = int(os.getenv("CONV_LOCK_TTL_SECONDS", "240"))
_LOCK_WAIT = float(os.getenv("CONV_LOCK_WAIT_SECONDS", "20"))
_LOCK_REQUEUE_DELAY = float(os.getenv("CONV_LOCK_REQUEUE_DELAY_SECONDS", "0.4"))
_HANDOFF_ALERT_TTL = int(os.getenv("HANDOFF_ALERT_TTL_SECONDS", "21600"))

_BOT_OFF_MSG = os.getenv(
    "BOT_OFF_MESSAGE",
    "Oi! No momento estou atendendo pessoalmente. Te respondo em breve 🙂",
)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: start queue consumers and tear down on shutdown."""
    global GRAPH, REDIS_POOL, WORKER_TASKS

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

    yield

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
    api_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    instance_name = os.getenv("EVOLUTION_INSTANCE", instance)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_url}/message/sendText/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"number": phone, "text": text},
            )
            if resp.status_code in (200, 201):
                logger.info("Texto enviado para %s: %s", phone, text[:50])
                return True
            logger.warning("Evolution API erro %s: %s", resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Falha ao enviar texto para %s: %s", phone, e)
        return False


async def send_whatsapp_audio(phone: str, audio_bytes: bytes, instance: str = "default") -> bool:
    """Envia áudio WAV via Evolution API sendWhatsAppAudio."""
    import base64

    api_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    instance_name = os.getenv("EVOLUTION_INSTANCE", instance)
    audio_b64 = base64.b64encode(audio_bytes).decode()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_url}/message/sendWhatsAppAudio/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"number": phone, "audio": audio_b64},
            )
            if resp.status_code in (200, 201):
                logger.info("Áudio enviado para %s: %s bytes", phone, len(audio_bytes))
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
    owner_phone = os.getenv("OWNER_PHONE", "5513996659382")
    title = "ALERTA DE HANDOFF" if handoff_mode == "hard_transfer" else "ALERTA DE LEAD ALTO VALOR"
    text = (
        f"🚨 *{title}* 🚨\n\n"
        f"Telefone: {lead_phone}\n"
        f"Motivo: {reason or 'não informado'}\n"
        f"Último pedido: {lead_message}\n"
        f"Resumo: {conversation_summary or 'sem histórico anterior'}\n"
        f"Próximo passo recomendado: {next_step or 'acompanhar pelo WhatsApp Web'}"
    )
    return await send_whatsapp_message(owner_phone, text, instance)


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


def _handoff_next_step(handoff_mode: str, reason: str) -> str:
    if handoff_mode == "hard_transfer":
        if reason == "sensitive_complaint":
            return "Assumir a conversa, pedir dados do orçamento/serviço e dar retorno claro."
        return "Assumir a conversa no WhatsApp Web; o bot já pediu serviço e cidade para adiantar."
    if reason == "light_complaint":
        return "Acompanhar em paralelo; o bot pediu detalhes para adiantar a análise."
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
    if mode == "hard_transfer" and result.get("handoff_already_notified"):
        return False

    if mode == "soft_alert":
        alert_key = f"handoff_alert:{_safe_key(phone)}:{_safe_key(reason)}"
        should_alert = await r.set(alert_key, "1", nx=True, ex=_HANDOFF_ALERT_TTL)
        if not should_alert:
            logger.info("Alerta soft deduplicado para %s (%s)", phone, reason)
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

    phone = payload.phone.strip()
    message_text = payload.message.strip()
    instance = payload.instance or "default"

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
        history = await load_history(phone, r)
        is_first_message = len(history) == 0
        messages_with_history = history + [HumanMessage(content=message_text)]

        initial_state = {
            "messages": messages_with_history,
            "intent": None,
            "service": None,
            "outcome": None,
            "handoff_mode": "none",
            "handoff_reason": None,
            "handoff_already_notified": False,
            "rag_context": [],
            "customer_data": {"phone": phone, "is_first_message": is_first_message},
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

        result = await GRAPH.ainvoke(initial_state)

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
