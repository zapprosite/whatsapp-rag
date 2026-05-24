from __future__ import annotations
import os, json, asyncio, logging
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
import httpx
from fastapi import FastAPI
from langchain_core.messages import HumanMessage, AIMessage

from agent_graph.graph.graph import build_graph

logger = logging.getLogger(__name__)

GRAPH: Any = None
REDIS_POOL: redis.ConnectionPool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan: start worker background task, tear down on shutdown."""
    global GRAPH, REDIS_POOL

    # Build graph once at startup
    GRAPH = build_graph()
    logger.info("LangGraph compiled OK")

    # Redis connection pool
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_POOL = redis.ConnectionPool.from_url(redis_url, decode_responses=True)
    logger.info(f"Redis pool connected: {redis_url}")

    # Start queue worker task
    worker_task = asyncio.create_task(worker_loop())

    yield

    # Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
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
                logger.info(f"Texto enviado para {phone}: {text[:50]}")
                return True
            logger.warning(f"Evolution API erro {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Falha ao enviar texto para {phone}: {e}")
        return False


async def send_whatsapp_audio(phone: str, audio_bytes: bytes, instance: str = "default") -> bool:
    """Envia áudio WAV via Evolution API sendMedia."""
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
                json={
                    "number": phone,
                    "audio": audio_b64
                },
            )
            if resp.status_code in (200, 201):
                logger.info(f"Áudio enviado para {phone}: {len(audio_bytes)} bytes")
                return True
            logger.warning(f"Evolution API (áudio) erro {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        logger.error(f"Falha ao enviar áudio para {phone}: {e}")
        return False


async def notify_owner(lead_phone: str, lead_message: str, instance: str = "default") -> bool:
    """Notifica o dono (Will) sobre handoff ou intenções de alto valor."""
    owner_phone = "5513996659382"
    text = f"🚨 *ALERTA DE HANDOFF* 🚨\nO lead {lead_phone} solicitou atendimento humano ou fechamento de alto valor.\nMensagem: {lead_message}\nAssuma a conversa no WhatsApp Web."
    return await send_whatsapp_message(owner_phone, text, instance)


_CONV_TTL = int(os.getenv("CONV_TTL_SECONDS", "1800"))  # 30 min de inatividade
_CONV_MAX_TURNS = 6   # janela deslizante: últimos 6 turnos (12 msgs) passados ao LLM
                      # Histórico mais antigo é descartado — evita overflow de contexto


async def load_history(phone: str) -> list:
    """Carrega histórico de conversa do Redis. Retorna lista de BaseMessage."""
    r = await get_redis()
    raw = await r.get(f"conv_history:{phone}")
    if not raw:
        return []
    try:
        turns = json.loads(raw)
        messages = []
        for t in turns:
            if t["role"] == "user":
                messages.append(HumanMessage(content=t["content"]))
            else:
                messages.append(AIMessage(content=t["content"]))
        return messages
    except Exception:
        return []


async def save_history(phone: str, messages: list) -> None:
    """Salva histórico de conversa no Redis com TTL de inatividade."""
    turns = []
    for m in messages:
        if isinstance(m, HumanMessage):
            turns.append({"role": "user", "content": m.content})
        elif isinstance(m, AIMessage):
            turns.append({"role": "assistant", "content": m.content})

    # Mantém só as últimas N trocas para não explodir o contexto
    max_msgs = _CONV_MAX_TURNS * 2
    if len(turns) > max_msgs:
        turns = turns[-max_msgs:]

    r = await get_redis()
    await r.set(f"conv_history:{phone}", json.dumps(turns), ex=_CONV_TTL)


_BOT_KEY     = "whatsapp_rag:bot_enabled"   # "1" = ativo, "0" = pausado
_BOT_OFF_MSG = os.getenv(
    "BOT_OFF_MESSAGE",
    "Oi! No momento estou atendendo pessoalmente. Te respondo em breve 🙂",
)


async def is_bot_enabled(r: redis.Redis) -> bool:
    val = await r.get(_BOT_KEY)
    return val != "0"   # ausente ou "1" → ativo


async def worker_loop() -> None:
    """Poll Redis queue and process messages through LangGraph."""
    logger.info("Worker loop started")
    while True:
        try:
            r = await get_redis()
            # blocking pop from queue, 5s timeout
            raw = await r.blpop("whatsapp_rag:queue", timeout=5)
            if raw is None:
                continue

            _, item = raw
            data = json.loads(item)
            phone = data.get("phone", "")
            message_text = data.get("message", "")
            instance = data.get("instance", "default")
            message_type = data.get("message_type", "conversation")
            msg_id = data.get("msg_id", "")
            media_url = data.get("media_url", "")
            media_base64 = data.get("media_base64", "")

            logger.info(f"Processando [{message_type}] de {phone}: {message_text[:60]}")

            if not message_text:
                continue

            # ── Verifica se bot está ativo ────────────────────────────────
            if not await is_bot_enabled(r):
                logger.info(f"Bot PAUSADO — mensagem de {phone} ignorada pela IA")
                if _BOT_OFF_MSG:
                    await send_whatsapp_message(phone, _BOT_OFF_MSG, instance)
                continue

            # Carrega histórico da conversa deste lead
            history = await load_history(phone)
            is_first_message = len(history) == 0

            # Monta messages com contexto acumulado + nova mensagem do lead
            messages_with_history = history + [HumanMessage(content=message_text)]

            initial_state = {
                "messages": messages_with_history,
                "intent": None,
                "service": None,
                "outcome": None,
                "rag_context": [],
                "customer_data": {"phone": phone, "is_first_message": is_first_message},
                "is_human": False,
                "confidence": 1.0,
                "message_type": message_type,
                "msg_id": msg_id,
                "media_url": media_url,
                "media_base64": media_base64,
                "instance": instance,
                "response_modality": None,
                "audio_bytes": None,
            }

            result = await GRAPH.ainvoke(initial_state)
            
            outcome = result.get("outcome")
            if outcome == "escalar_humano":
                await notify_owner(phone, message_text, instance)

            # ── Extrai resposta do AI (última AIMessage do resultado) ──────────
            messages_out = result.get("messages", [])
            ai_message = next(
                (m.content for m in reversed(messages_out)
                 if isinstance(m, AIMessage) and m.content),
                None,
            )

            # ── Salva histórico limpo: input acumulado + 1 AIMessage final ────
            # Não salva messages_out direto pois add_messages acumula AIMessages
            # intermediárias de cada nó (language_guard, format_whatsapp, etc.)
            if ai_message:
                clean_history = list(messages_with_history) + [AIMessage(content=ai_message)]
                await save_history(phone, clean_history)
                logger.info(f"Histórico salvo: {phone} ({len(clean_history)} msgs)")

            # ── Envia resposta ─────────────────────────────────────────────────
            modality = result.get("response_modality", "text")
            audio_bytes = result.get("audio_bytes")

            if modality == "audio" and audio_bytes:
                sent = await send_whatsapp_audio(phone, audio_bytes, instance)
                if not sent and ai_message:
                    await send_whatsapp_message(phone, ai_message, instance)
            elif ai_message:
                await send_whatsapp_message(phone, ai_message, instance)
            else:
                logger.warning(f"Nenhuma resposta AI no resultado para {phone}")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Worker error: {e}")
            await asyncio.sleep(1)