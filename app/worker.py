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
from agent_graph.services.whatsapp import (
    normalize_whatsapp_number,
    send_whatsapp_presence,
    send_whatsapp_text,
)
from runtime_config import (
    get_runtime_config,
    is_shadow_mode,
    is_assisted_mode,
    is_canary_mode,
    can_auto_reply,
    IntentFilter,
)

try:
    from lead_repository import prisma_healthcheck
    from mvp_attendance import minimal_mvp_enabled, process_mvp_message
except ModuleNotFoundError:
    from lead_repository import prisma_healthcheck
    from mvp_attendance import minimal_mvp_enabled, process_mvp_message

# Monitoring collectors (inicializados em runtime)
_metrics_collector = None
_status_tracker = None
_feedback_store = None
_outcome_tracker = None


def _get_metrics_collector():
    global _metrics_collector
    if _metrics_collector is None:
        from refrimix_core.monitoring.conversation_metrics import ConversationMetricsCollector
        _metrics_collector = ConversationMetricsCollector()
    return _metrics_collector


def _get_status_tracker():
    global _status_tracker
    if _status_tracker is None:
        from refrimix_core.monitoring.whatsapp_status_tracker import WhatsAppStatusTracker
        _status_tracker = WhatsAppStatusTracker()
    return _status_tracker


def _get_feedback_store():
    global _feedback_store
    if _feedback_store is None:
        from refrimix_core.monitoring.production_feedback import ProductionFeedbackStore
        _feedback_store = ProductionFeedbackStore()
    return _feedback_store


def _get_outcome_tracker():
    global _outcome_tracker
    if _outcome_tracker is None:
        from refrimix_core.monitoring.lead_outcome_tracker import LeadOutcomeTracker
        _outcome_tracker = LeadOutcomeTracker()
    return _outcome_tracker


async def _save_conversation_id(phone: str, conversation_id: str, r: redis.Redis) -> None:
    """Salva conversation_id no lead via Redis (futuro: Postgres)."""
    key = f"conv_id:{phone}"
    await r.set(key, conversation_id, ex=86400)


def _safe_conversation_id(phone: str, msg_id: str = "") -> str:
    """Gera conversation_id estável a partir de phone + msg_id."""
    import hashlib
    key = f"{phone}:{msg_id}" if msg_id else phone
    return hashlib.md5(key.encode()).hexdigest()[:16]

logger = logging.getLogger(__name__)

GRAPH: Any = None
REDIS_POOL: redis.ConnectionPool | None = None
WORKER_TASKS: list[asyncio.Task[None]] = []
SCHEDULER_TASKS: list[asyncio.Task[None]] = []

_QUEUE_KEY = os.getenv("WHATSAPP_QUEUE_KEY", "whatsapp_rag:queue")
_PROCESSING_KEY = os.getenv("WHATSAPP_PROCESSING_QUEUE_KEY", "whatsapp_rag:processing")
_DLQ_KEY = os.getenv("WHATSAPP_DLQ_KEY", "whatsapp_rag:dead_letter")
_BOT_KEY = "whatsapp_rag:bot_enabled"
_WORKER_HEARTBEAT_KEY = "whatsapp_rag:worker_heartbeat"

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
_WORKER_HEARTBEAT_TTL = max(30, int(os.getenv("WORKER_HEARTBEAT_TTL_SECONDS", "30")))
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
    "electrical_risk",
    "repeated_missing_critical_field",
    "appointment_confirmed",
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


def conversation_history_key(phone: str) -> str:
    normalized = normalize_whatsapp_number(phone) or phone
    return f"conv_history:{normalized}"


def conversation_lock_key(phone: str) -> str:
    normalized = normalize_whatsapp_number(phone) or phone
    return f"conv_lock:{_safe_key(normalized)}"


def handoff_state_key(phone: str) -> str:
    normalized = normalize_whatsapp_number(phone) or phone
    return f"handoff_state:{_safe_key(normalized)}"


async def is_manual_takeover(r: redis.Redis, phone: str) -> bool:
    return await r.get(manual_takeover_key(phone)) == "1"


async def set_manual_takeover(r: redis.Redis, phone: str, enabled: bool) -> None:
    key = manual_takeover_key(phone)
    if enabled:
        await r.set(key, "1", ex=_MANUAL_TAKEOVER_TTL)
    else:
        await r.delete(key)


async def reset_test_conversation_state(r: redis.Redis, phone: str) -> dict[str, Any]:
    normalized = normalize_whatsapp_number(phone) or phone
    deleted_keys: list[str] = []

    fixed_keys = [
        conversation_history_key(normalized),
        manual_takeover_key(normalized),
        conversation_lock_key(normalized),
        handoff_state_key(normalized),
    ]
    for key in fixed_keys:
        try:
            removed = await r.delete(key)
        except Exception:
            removed = 0
        if removed:
            deleted_keys.append(key)

    side_effect_pattern = f"side_effect:*:{normalized}:*"
    if hasattr(r, "scan_iter"):
        async for key in r.scan_iter(match=side_effect_pattern):
            try:
                removed = await r.delete(key)
            except Exception:
                removed = 0
            if removed:
                deleted_keys.append(str(key))

    persistent_reset = False
    deleted_events = 0
    if os.getenv("DATABASE_URL"):
        try:
            from prisma import Prisma

            db = Prisma()
            await db.connect()
            try:
                lead = await db.lead.find_unique(where={"phone": normalized})
                if lead:
                    await db.lead.update(
                        where={"phone": normalized},
                        data={
                            "name": None,
                            "service": None,
                            "address": None,
                            "window": None,
                            "service_type": None,
                            "pipeline_stage": "new",
                            "city_bairro": None,
                            "urgency": None,
                            "lead_state": json.dumps({}),
                            "conversation_summary": None,
                            "already_asked_fields": json.dumps([]),
                            "missing_fields": json.dumps(["tipo_servico", "cidade_bairro"]),
                            "do_not_ask": json.dumps([]),
                            "last_user_message_at": None,
                        },
                    )
                    deleted_events = await db.query_raw(
                        "DELETE FROM lead_events WHERE lead_id = $1",
                        str(lead.id),
                    ) or 0
                    persistent_reset = True
            finally:
                await db.disconnect()
        except Exception as e:
            logger.warning("Falha ao resetar estado persistido de teste do admin: %s", e)

    logger.info("Conversa de teste do admin resetada com sucesso")
    return {
        "phone": normalized,
        "deleted_keys": deleted_keys,
        "deleted_keys_count": len(deleted_keys),
        "persistent_reset": persistent_reset,
        "deleted_events": int(deleted_events or 0),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: start queue consumers and tear down on shutdown."""
    global GRAPH, REDIS_POOL, WORKER_TASKS, SCHEDULER_TASKS

    if minimal_mvp_enabled():
        GRAPH = None
        logger.info("Modo MINIMAL_MVP_ENABLED=1 ativo; LangGraph fora do caminho crítico")
    else:
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
            from agenda_scheduler import agenda_digest_loop
        except ModuleNotFoundError:
            from app.agenda_scheduler import agenda_digest_loop

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


async def record_worker_heartbeat(r: redis.Redis, worker_id: int, phase: str) -> None:
    payload = json.dumps(
        {
            "worker_id": worker_id,
            "phase": phase,
            "updated_at": datetime.now().isoformat(),
        },
        ensure_ascii=False,
    )
    await r.set(_WORKER_HEARTBEAT_KEY, payload, ex=_WORKER_HEARTBEAT_TTL)


async def worker_heartbeat_status(r: redis.Redis | None = None) -> dict[str, Any]:
    client = r or await get_redis()
    raw = await client.get(_WORKER_HEARTBEAT_KEY)
    if not raw:
        return {"status": "down", "reason": "heartbeat ausente"}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "down", "reason": "heartbeat inválido"}
    return {"status": "up", **data}


async def postgres_status() -> dict[str, str]:
    return await prisma_healthcheck()


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
    takeover_command = f"assumir {lead_phone}" if reason.startswith("high_value") else ""
    release_command = f"liberar {lead_phone}" if takeover_command else ""
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
            "takeover_command": takeover_command,
            "release_command": release_command,
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
        "appointment_confirmed": "AGENDAMENTO CONFIRMADO",
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
    if reason == "appointment_confirmed":
        return "Confirmar execução e janela diretamente no WhatsApp do cliente."
    if reason == "no_context_needs_human_review":
        return "Ler o histórico e responder manualmente se a intenção continuar incerta."
    if reason == "light_complaint":
        return "Acompanhar em paralelo; o bot pediu detalhes para adiantar a análise."
    if reason == "active_service_followup":
        return "Verificar serviço em andamento, agenda e pendências; cliente já não deve ser tratado como lead novo."
    if reason.startswith("high_value"):
        return "Acompanhar de perto. Se quiser interromper a IA só neste lead, responda no WhatsApp: assumir TELEFONE_DO_LEAD."
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

    # appointment_confirmed é tratado exclusivamente por dispatch_appointment_alert → grupo de agenda
    if reason == "appointment_confirmed":
        logger.info("appointment_confirmed delegado ao dispatch_appointment_alert; worker skip")
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


@asynccontextmanager
async def whatsapp_typing_indicator(phone: str, presence_type: str, instance: str = "default"):
    """Envia sinal de presença dinâmico (composing/recording) e o mantém vivo de forma assíncrona."""
    await send_whatsapp_presence(phone, presence_type, delay_ms=10000, instance=instance)

    async def loop():
        try:
            while True:
                await asyncio.sleep(8)
                await send_whatsapp_presence(phone, presence_type, delay_ms=10000, instance=instance)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("Falha na atualização do sinal de presença: %s", exc)

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(Exception):
            await task


async def _process_customer_message(payload: QueueMessage, r: redis.Redis, worker_id: int) -> None:
    if GRAPH is None and not minimal_mvp_enabled():
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

        # Envia sinal de presença dinâmico (composing/recording) conforme tipo de mensagem e TTS
        tts_enabled = os.getenv("TTS_ENABLED", "1").strip() in {"1", "true", "yes", "on"}
        presence_type = "recording" if (payload.message_type == "audioMessage" and tts_enabled) else "composing"

        async with whatsapp_typing_indicator(phone, presence_type, instance=instance):
            redis_history = await load_history(phone, r)
            if minimal_mvp_enabled():
                result = await process_mvp_message(
                    phone=phone,
                    message_text=message_text,
                    instance=instance,
                    history=redis_history,
                )
                ai_message = next(
                    (
                        _message_text(message)
                        for message in reversed(result.get("messages", []))
                        if isinstance(message, AIMessage) and _message_text(message)
                    ),
                    None,
                )
                if ai_message:
                    await save_history(phone, result["messages"], r)
                    await send_whatsapp_message(phone, ai_message, instance)
                else:
                    logger.warning("Fluxo MVP não retornou resposta para %s", phone)
                return

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

            import hashlib
            response_hash = "N/A"
            if ai_message:
                response_hash = hashlib.md5(ai_message.encode("utf-8")).hexdigest()
                prev_hash_key = f"prev_resp_hash:{phone}"
                prev_user_text_key = f"prev_user_text:{phone}"
                previous_response_hash = await r.get(prev_hash_key)
                previous_user_text = await r.get(prev_user_text_key)

                if previous_response_hash == response_hash and message_text != previous_user_text:
                    logger.warning(
                        "[possible_response_loop] DETECTED LOOP FOR %s. "
                        "Previous response was identical, but user input changed. "
                        "Response: %s", phone, ai_message[:100]
                    )

                await r.set(prev_hash_key, response_hash, ex=1800)
                await r.set(prev_user_text_key, message_text, ex=1800)

            understanding = result.get("message_understanding") or {}
            lead_state = result.get("lead_state") or {}
            comm_dec = lead_state.get("commercial_decision") or result.get("commercial_decision") or {}
            next_action = result.get("next_action") or {}

            logger.info(
                "[DEBUG_LOGS] Phone: %s | MessageType: %s | UserText: %s | "
                "Transcript: %s | UnderstandingKind: %s | LastAskedField: %s | "
                "AppliedShortAnswer: %s | Service: %s | CommercialPath: %s | "
                "NextActionType: %s | ResponseModality: %s | TTSEnabled: %s | "
                "VisionCalled: %s | ResponseHash: %s",
                phone,
                payload.message_type,
                message_text,
                ai_message if payload.message_type == "audioMessage" else "N/A",
                understanding.get("kind"),
                lead_state.get("last_asked_field"),
                result.get("short_answer_applied") or lead_state.get("short_answer_applied"),
                lead_state.get("tipo_servico"),
                comm_dec.get("path"),
                next_action.get("type"),
                result.get("response_modality"),
                os.getenv("TTS_ENABLED", "1"),
                result.get("vision_called", False),
                response_hash,
            )

            if ai_message:
                clean_history = list(messages_with_history) + [AIMessage(content=ai_message)]
                await save_history(phone, clean_history, r)
                logger.info("Histórico salvo: %s (%s msgs)", phone, len(clean_history))

            # ── MONITORING: track inbound message ─────────────────────────────────
            conv_id = _safe_conversation_id(phone, payload.msg_id)
            metrics = _get_metrics_collector()
            metrics.track_metric(conv_id, "message_received", metadata={"intent": result.get("message_understanding", {}).get("kind")})

            # Salvar mappings para o status webhook resolver depois
            if payload.msg_id:
                await r.set(f"msg_conv:{payload.msg_id}", conv_id, ex=86400)
                await r.set(f"msg_phone:{payload.msg_id}", phone, ex=86400)

            intent = result.get("message_understanding", {}).get("kind")
            if is_shadow_mode():
                logger.info(
                    "[SHADOW] resposta gerada para %s (não enviada): %s",
                    phone,
                    (ai_message or "")[:80],
                )
                # Track pending status
                status_tracker = _get_status_tracker()
                if ai_message:
                    status_tracker.track_message_status(
                        payload.msg_id, conv_id,
                        __import__("refrimix_core.monitoring.whatsapp_status_tracker", fromlist=["StatusType"]).StatusType.PENDING,
                    )
                # Save conversation_id to lead
                await _save_conversation_id(phone, conv_id, r)
                return

            # ASSISTED: cria ReviewItem para aprovação humana
            if is_assisted_mode() and ai_message:
                from refrimix_core.review.review_models import ReviewItem
                from refrimix_core.review.review_queue import get_review_queue
                risk = result.get("risk_classification", "unknown")
                modality = result.get("response_modality", "text")
                audio_bytes = result.get("audio_bytes")

                item = ReviewItem.from_worker_response(
                    phone=phone,
                    conversation_id=conv_id,
                    user_message=message_text,
                    ai_response=ai_message,
                    intent=intent,
                    risk=risk,
                    msg_id=payload.msg_id,
                    response_modality=modality,
                    audio_bytes=audio_bytes if isinstance(audio_bytes, bytes) else None,
                )
                get_review_queue().create(item)
                logger.info(
                    "[ASSISTED] ReviewItem created review_id=%s intent=%s priority=%s",
                    item.review_id[:8],
                    item.intent,
                    item.priority.value,
                )

            # CANARY: respeita allowed intents + canary percent
            intent = result.get("message_understanding", {}).get("kind")
            if is_canary_mode():
                if not can_auto_reply(intent):
                    logger.info(
                        "[CANARY] intent '%s' não permitido ou bloqueado para %s — humanidade requerida",
                        intent,
                        phone,
                    )
                    # Track blocked
                    metrics.track_metric(conv_id, "guardrail_blocked", metadata={"intent": intent})
                    outcome_tracker = _get_outcome_tracker()
                    ot = __import__("refrimix_core.monitoring.lead_outcome_tracker", fromlist=["OutcomeType"]).OutcomeType
                    outcome_tracker.track_outcome(conv_id, ot.BLOQUEADO_GUARDRAIL, turning_point="canary_blocked", intent=intent)
                    return
                logger.info("[CANARY] auto-envio liberado para intent=%s phone=%s", intent, phone)

            modality = result.get("response_modality", "text")
            audio_bytes = result.get("audio_bytes")

            if modality == "audio" and isinstance(audio_bytes, bytes) and audio_bytes:
                sent = await send_whatsapp_audio(phone, audio_bytes, instance)
                if sent:
                    metrics.track_metric(conv_id, "audio_sent")
                    if ai_message:
                        status_tracker = _get_status_tracker()
                        st = __import__("refrimix_core.monitoring.whatsapp_status_tracker", fromlist=["StatusType"]).StatusType
                        status_tracker.track_message_status(
                            payload.msg_id, conv_id,
                            st.SENT,
                        )
                else:
                    metrics.track_metric(conv_id, "audio_failed")
                    if ai_message:
                        await send_whatsapp_message(phone, ai_message, instance)
                    metrics.track_metric(conv_id, "text_fallback_sent")
            elif ai_message:
                await send_whatsapp_message(phone, ai_message, instance)
                status_tracker = _get_status_tracker()
                st = __import__("refrimix_core.monitoring.whatsapp_status_tracker", fromlist=["StatusType"]).StatusType
                status_tracker.track_message_status(
                    payload.msg_id, conv_id,
                    st.SENT,
                )
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
            await record_worker_heartbeat(r, worker_id, "idle")
            raw_item = await r.brpoplpush(_QUEUE_KEY, _PROCESSING_KEY, timeout=_QUEUE_POP_TIMEOUT)
            if raw_item is None:
                continue

            await record_worker_heartbeat(r, worker_id, "processing")
            await asyncio.wait_for(process_queue_item(raw_item, worker_id), timeout=_MESSAGE_TIMEOUT)
            await _ack_queue_item(r, raw_item)
            await record_worker_heartbeat(r, worker_id, "processed")

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
