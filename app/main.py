from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

try:
    import worker as worker_module
    from worker import lifespan, get_redis, send_whatsapp_message
except ModuleNotFoundError:
    # Importação a partir da raiz do projeto (testes / verificação)
    import sys, importlib
    sys.path.insert(0, str(Path(__file__).parent))
    import worker as worker_module
    from worker import lifespan, get_redis, send_whatsapp_message
from langchain_core.messages import HumanMessage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Refrimix WhatsApp RAG", version="1.0.0")
app.router.lifespan_context = lifespan


@app.post("/webhook/evolution")
async def receive_webhook(request: Request) -> JSONResponse:
    """Receive webhook from Evolution API, respond immediately."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # ── Extrai campos da Evolution API v2 ─────────────────────────────────────
    data_block = body.get("data", {})
    key_block = data_block.get("key", {})
    msg_block = data_block.get("message", {})

    phone = (
        key_block.get("remote")
        or key_block.get("remoteJid")
        or body.get("sender", {}).get("remote")
        or body.get("from", "")
    )

    instance_name = body.get("instanceName", "") or body.get("instance", "")

    # ── Ignora mensagens enviadas pelo próprio bot (evita loop infinito) ──────
    if key_block.get("fromMe", False):
        return JSONResponse({"status": "ok", "skipped": "fromMe"})

    # ── Deduplica pelo ID da mensagem (Evolution pode disparar webhook 2x) ────
    msg_id = key_block.get("id", "")
    if msg_id:
        r = await get_redis()
        dedup_key = f"processed_msg:{msg_id}"
        if not await r.set(dedup_key, "1", nx=True, ex=60):
            logger.info(f"Mensagem duplicada ignorada: {msg_id}")
            return JSONResponse({"status": "ok", "skipped": "duplicate"})

    # ── Detecta messageType ───────────────────────────────────────────────────
    message_type = data_block.get("messageType", "conversation")
    # Normaliza variações da Evolution API
    if "audioMessage" in msg_block:
        message_type = "audioMessage"
    elif "imageMessage" in msg_block:
        message_type = "imageMessage"
    elif "stickerMessage" in msg_block or "videoMessage" in msg_block:
        # Tipos não suportados — ignora silenciosamente
        return JSONResponse({"status": "ok", "skipped": f"unsupported type: {message_type}"})

    # ── Extrai URL de mídia e Base64 (áudio/imagem) ───────────────────────────
    media_url = ""
    media_base64 = data_block.get("base64", "")
    if message_type == "audioMessage":
        media_url = (
            msg_block.get("audioMessage", {}).get("url", "")
            or data_block.get("mediaUrl", "")
        )
        if not media_base64:
            media_base64 = msg_block.get("audioMessage", {}).get("base64", "")
    elif message_type == "imageMessage":
        media_url = (
            msg_block.get("imageMessage", {}).get("url", "")
            or data_block.get("mediaUrl", "")
        )
        if not media_base64:
            media_base64 = msg_block.get("imageMessage", {}).get("base64", "")

    # ── Extrai texto (caption para imagens, texto para conversas) ─────────────
    message = (
        msg_block.get("conversation")
        or msg_block.get("extendedTextMessage", {}).get("text")
        or msg_block.get("imageMessage", {}).get("caption")
        or msg_block.get("audioMessage", {}).get("caption")
        or body.get("text", "")
        or body.get("content", "")
    )

    # Para áudio/imagem sem caption, placeholder para o RAG não descartar
    if not message:
        if message_type == "audioMessage":
            message = "[áudio]"
        elif message_type == "imageMessage":
            message = "[imagem]"

    # ── Fallbacks de campos ausentes ──────────────────────────────────────────
    if not phone:
        for key in ("phone", "from", "sender", "number"):
            if body.get(key):
                phone = str(body[key])
                break

    if not message and message_type == "conversation":
        for key in ("message", "text", "content", "body"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                message = val.strip()
                break

    if not phone or not message:
        logger.error(
            f"Webhook sem phone/message — phone={phone!r} type={message_type} "
            f"body_keys={list(body.keys())}"
        )
        return JSONResponse({"status": "ok", "skipped": "missing fields"})

    # ── Filtros de grupo/broadcast ────────────────────────────────────────────
    phone_str = str(phone)
    if "@g.us" in phone_str or "group" in phone_str.lower():
        logger.info(f"Ignorando mensagem de grupo: {phone_str}")
        return JSONResponse({"status": "ok", "skipped": "group"})

    if phone_str.endswith("@broadcast"):
        logger.info(f"Ignorando broadcast: {phone_str}")
        return JSONResponse({"status": "ok", "skipped": "broadcast"})

    r = await get_redis()
    await r.lpush("whatsapp_rag:queue", json.dumps({
        "phone": phone,
        "message": message,
        "instance": instance_name,
        "message_type": message_type,
        "msg_id": msg_id,
        "media_url": media_url,
        "media_base64": media_base64,
    }))
    logger.info(f"Enfileirado [{message_type}] de {phone}: {message[:60]}")

    return JSONResponse({"status": "ok"})


@app.get("/health")
async def health() -> dict[str, Any]:
    status: dict[str, str] = {"status": "ok"}

    try:
        r = await get_redis()
        await r.ping()
        status["redis"] = "up"
    except Exception as e:
        status["redis"] = f"down: {e}"

    try:
        from qdrant_client import QdrantClient
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        qc = QdrantClient(url=qdrant_url)
        qc.get_collections()
        status["qdrant"] = "up"
    except Exception as e:
        status["qdrant"] = f"down: {e}"

    status["langgraph"] = "up"
    status["worker"] = "running"
    return status


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "Refrimix WhatsApp RAG", "version": "1.0.0"}


# ══════════════════════════════════════════════════════════════════════════════
# Controle do Bot — liga/desliga IA em tempo real via Redis
# ══════════════════════════════════════════════════════════════════════════════

_BOT_KEY = "whatsapp_rag:bot_enabled"


async def _bot_status(r) -> str:
    val = await r.get(_BOT_KEY)
    return "ativo" if val != "0" else "pausado"


@app.get("/bot", response_class=__import__("fastapi").responses.HTMLResponse)
async def bot_panel():
    """Painel visual para ligar/desligar o bot — abre no celular ou browser."""
    r = await get_redis()
    status = await _bot_status(r)
    ativo = status == "ativo"
    cor      = "#22c55e" if ativo else "#ef4444"
    cor_btn  = "#ef4444" if ativo else "#22c55e"
    label    = "ATIVO 🟢" if ativo else "PAUSADO 🔴"
    acao     = "Pausar IA" if ativo else "Ligar IA"
    endpoint = "/bot/off" if ativo else "/bot/on"
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Refrimix Bot</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #f1f5f9;
            display: flex; flex-direction: column; align-items: center;
            justify-content: center; min-height: 100vh; gap: 2rem; padding: 2rem; }}
    h1   {{ font-size: 1.4rem; color: #94a3b8; letter-spacing: .05em; }}
    .status {{ font-size: 3rem; font-weight: 800; color: {cor}; }}
    .btn {{ background: {cor_btn}; color: #fff; border: none; border-radius: 1rem;
            padding: 1.2rem 3rem; font-size: 1.4rem; font-weight: 700;
            cursor: pointer; width: 100%; max-width: 320px; transition: opacity .2s; }}
    .btn:hover {{ opacity: .85; }}
    .hint {{ color: #475569; font-size: .85rem; text-align: center; }}
    form  {{ width: 100%; display: flex; justify-content: center; }}
  </style>
  <meta http-equiv="refresh" content="10">
</head>
<body>
  <h1>Refrimix WhatsApp Bot</h1>
  <div class="status">{label}</div>
  <form method="post" action="{endpoint}">
    <button class="btn" type="submit">{acao}</button>
  </form>
  <p class="hint">Página atualiza automaticamente a cada 10s<br>
     API: <code>./bot.sh on</code> / <code>./bot.sh off</code></p>
</body>
</html>"""


@app.post("/bot/on")
async def bot_on():
    r = await get_redis()
    await r.set(_BOT_KEY, "1")
    logger.info("Bot ATIVADO")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/bot", status_code=303)


@app.post("/bot/off")
async def bot_off():
    r = await get_redis()
    await r.set(_BOT_KEY, "0")
    logger.info("Bot PAUSADO")
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/bot", status_code=303)


@app.get("/bot/status")
async def bot_status_api():
    r = await get_redis()
    status = await _bot_status(r)
    return {"status": status, "bot_enabled": status == "ativo"}


# ==============
# E2E Test Loop — Perguntas frequentes HVAC Brasil
# ==============

E2E_SCENARIOS = [
    # Instalação — keywords claros: instalação, instalar, split
    ("instalacao", "Quais marcas de ar condicionado split vocês instalam?"),
    ("instalacao", "Faz instalação de janela de vidro no salão comercial?"),
    ("instalacao", "Quanto tempo leva para instalar 3 splits no apartamento?"),
    ("instalacao", "Vocês instalam equipamento que eu já comprei?"),
    ("instalacao", "Preciso instalar 4 equipos e fazer tubulação no forro de gesso"),

    # Manutenção — keywords: manutenção, barulho, consertar, repara, defeito
    ("manutencao", "O ar está fazendo barulho de vibração quando liga"),
    ("manutencao", "O split gela demais e desliga sozinho"),
    ("manutencao", "O ar não esquenta no inverno, o que pode ser?"),
    ("manutencao", "Meu ar condicionado tem vazamento de água"),
    ("manutencao", "O split não liga mais, parece que queimou"),

    # PMOC — keywords: pmoc, laudo, certificado, obrigatório
    ("pmoc", "O que é PMOC e é obrigatório no meu prédio comercial?"),
    ("pmoc", "Preciso do laudo PMOC para o alvará do bombeiros"),
    ("pmoc", "Como funciona o programa de manutenção preventiva PMOC?"),
    ("pmoc", "Quanto custa o programa PMOC para 10 equipamentos?"),
    ("pmoc", "Empresa pedindo atestado PMOC — como solicitar?"),

    # Consultoria — keywords: consultoria, dimensionamento, btu, projeto
    ("consultoria", "Qual capacidade de BTU preciso para sala de reunião?"),
    ("consultoria", "Vocês fazem projeto de ar condicionado para obra nova?"),
    ("consultoria", "Split ou cassete — o que é melhor para loja de 40m²?"),
    ("consultoria", "Dúvida sobre eficiência energética dos equipos"),
    ("consultoria", "Queria uma assessoria para climatizar o apartamento"),

    # Higienização — keywords: higienização, limpeza, ozônio, ácar
    ("hygienizacao", "Qual a diferença entre limpeza e higienização do split?"),
    ("hygienizacao", "Faz higienização com ozônio para eliminar cheiro?"),
    ("hygienizacao", "Quando devo fazer a higienização do ar condicionado?"),
    ("hygienizacao", "Higienização remove ácaros e fungos do dutos?"),
    ("hygienizacao", "Vocês emitem certificado após a higienização?"),

    # Projeto Central — keywords: projeto central, central, multisplit, cassete, galpão
    ("projeto-central", "Preciso de projeto central de climatização para escritório"),
    ("projeto-central", "Split central ou multisplit para 6 ambientes?"),
    ("projeto-central", "Faz dimensionamento de carga térmica para galpão industrial"),
    ("projeto-central", "Projeto para climatização de restaurante com cozinha"),
    ("projeto-central", "Sistema central com controle individual por ambiente"),

    # Human / Desambiguação — triggers claros
    ("explicit_handoff", "Quero falar com atendente humano, não estou conseguindo resolver"),
    ("sensitive_complaint", "Já liguei várias vezes e ninguém responde"),
    ("sensitive_complaint", "Fiz orçamento faz 10 dias e nunca retornaram"),
    ("sensitive_complaint", "Quero cancelamento e reembolso do serviço"),
]


@app.post("/test/e2e")
async def test_e2e(
    start: int = 0,
    limit: int = 5,
    delay: float = 3.0,
) -> dict[str, Any]:
    """
    Run E2E scenarios sequentially through the graph.
    Returns full intent/service/response for each message.
    delay=0 for instant, >0 to simulate real conversation pace.
    """
    results = []
    total = len(E2E_SCENARIOS)
    end = min(start + limit, total)

    for i in range(start, end):
        service_tag, message = E2E_SCENARIOS[i]

        initial_state = {
            "messages": [HumanMessage(content=message)],
            "intent": None,
            "service": None,
            "outcome": None,
            "handoff_mode": "none",
            "handoff_reason": None,
            "handoff_already_notified": False,
            "rag_context": [],
            "customer_data": {"phone": f"+55119000{i:04d}"},
            "is_human": False,
            "confidence": 1.0,
            "message_type": "conversation",
            "media_url": "",
            "instance": "test",
            "response_modality": None,
            "audio_bytes": None,
        }

        result = await worker_module.GRAPH.ainvoke(initial_state)
        messages = result.get("messages", [])
        ai_message = None
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.__class__.__name__ == "AIMessage":
                ai_message = msg.content
                break

        intent = result.get("intent")
        service = result.get("service")
        rag_hits = len(result.get("rag_context", []))

        item = {
            "index": i,
            "service_tag": service_tag,
            "input": message,
            "intent": intent,
            "service": service,
            "handoff_mode": result.get("handoff_mode"),
            "handoff_reason": result.get("handoff_reason"),
            "rag_hits": rag_hits,
            "response": ai_message,
            "correct": intent == service_tag,
        }
        results.append(item)
        logger.info(f"[e2e] {i+1}/{total} [{service_tag}] → intent={intent} correct={item['correct']}")

        if delay > 0 and i < end - 1:
            import asyncio
            await asyncio.sleep(delay)

    return {
        "total": total,
        "range": [start, end],
        "correct": sum(1 for r in results if r["correct"]),
        "results": results,
    }


@app.post("/test/e2e/loop")
async def test_e2e_loop(cycles: int = 1, delay: float = 3.0) -> dict[str, Any]:
    """
    Run full E2E cycle multiple times with delay between runs.
    Use to observe response variation and LLM quality evolution.
    """
    all_results = []
    total_scenarios = len(E2E_SCENARIOS)

    for cycle in range(cycles):
        logger.info(f"[e2e loop] === Cycle {cycle+1}/{cycles} ===")
        results = []
        for i in range(total_scenarios):
            service_tag, message = E2E_SCENARIOS[i]

            initial_state = {
                "messages": [HumanMessage(content=message)],
                "intent": None,
                "service": None,
                "outcome": None,
                "handoff_mode": "none",
                "handoff_reason": None,
                "handoff_already_notified": False,
                "rag_context": [],
                "customer_data": {"phone": f"+55119000{cycle:02d}{i:02d}"},
                "is_human": False,
                "confidence": 1.0,
                "message_type": "conversation",
                "media_url": "",
                "instance": "test",
                "response_modality": None,
                "audio_bytes": None,
            }

            result = await worker_module.GRAPH.ainvoke(initial_state)
            messages = result.get("messages", [])
            ai_message = None
            for msg in reversed(messages):
                if hasattr(msg, "content") and msg.__class__.__name__ == "AIMessage":
                    ai_message = msg.content
                    break

            intent = result.get("intent")
            service = result.get("service")

            results.append({
                "cycle": cycle + 1,
                "index": i,
                "input": message,
                "intent": intent,
                "service_tag": service_tag,
                "service": service,
                "handoff_mode": result.get("handoff_mode"),
                "handoff_reason": result.get("handoff_reason"),
                "correct": intent == service_tag,
                "response": ai_message,
            })

            import asyncio
            await asyncio.sleep(delay)

        all_results.extend(results)

    correct = sum(1 for r in all_results if r["correct"])
    return {
        "cycles": cycles,
        "total": len(all_results),
        "correct": correct,
        "accuracy": round(correct / len(all_results) * 100, 1) if all_results else 0,
        "results": all_results,
    }


@app.post("/test/refine")
async def test_refine(message: str = "O ar está fazendo barulho") -> dict[str, Any]:
    """
    Run the same message 3 times through the graph to observe
    response variation and guardrail behavior.
    """
    responses = []
    for i in range(3):
        initial_state = {
            "messages": [HumanMessage(content=message)],
            "intent": None,
            "service": None,
            "outcome": None,
            "handoff_mode": "none",
            "handoff_reason": None,
            "handoff_already_notified": False,
            "rag_context": [],
            "customer_data": {"phone": "+5511900000001"},
            "is_human": False,
            "confidence": 1.0,
            "message_type": "conversation",
            "media_url": "",
            "instance": "test",
            "response_modality": None,
            "audio_bytes": None,
        }

        result = await worker_module.GRAPH.ainvoke(initial_state)
        messages = result.get("messages", [])
        ai_message = None
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.__class__.__name__ == "AIMessage":
                ai_message = msg.content
                break

        responses.append({
            "run": i + 1,
            "intent": result.get("intent"),
            "service": result.get("service"),
            "handoff_mode": result.get("handoff_mode"),
            "handoff_reason": result.get("handoff_reason"),
            "response": ai_message,
        })

        import asyncio
        await asyncio.sleep(1)

    return {"message": message, "runs": responses}


# ==============
# Legacy test_chat / test_loop (kept for compat)
# ==============

TEST_MESSAGES = [
    "Olá, preciso de uma instalação de ar condicionado split",
    "Quanto custa manutenção preventiva do ar?",
    "Quero fazer PMOC do meu escritório",
    "Preciso de consultoria para projeto de climatização",
    "Vocês fazem higienização de split?",
    "O ar está fazendo barulho estranho",
    "Quero falar com atendente humano",
    "Qual a garantia dos serviços?",
    "Preciso instalar 5 equipos no projeto central",
]


@app.post("/test/loop")
async def test_loop(count: int = 3, interval: float = 5.0) -> dict[str, Any]:
    """
    Fire `count` test messages through the full pipeline at `interval` seconds apart.
    Messages are pushed directly to the Redis queue so the worker processes them.
    """
    r = await get_redis()
    sent = []
    for i in range(count):
        msg = TEST_MESSAGES[i % len(TEST_MESSAGES)]
        payload = {
            "phone": f"+55119000000{i:02d}",
            "message": msg,
            "instance": "test",
        }
        await r.lpush("whatsapp_rag:queue", json.dumps(payload))
        sent.append(msg)
        logger.info(f"[test loop] queued ({i+1}/{count}): {msg[:60]}")
        if i < count - 1 and interval > 0:
            import asyncio
            await asyncio.sleep(interval)

    return {"queued": count, "messages": sent}


@app.post("/test/chat")
async def test_chat(
    message: str = "Olá, preciso de instalação de ar split",
    media_type: str = "conversation",
    media_url: str = "",
) -> dict[str, Any]:
    """
    Run a single message through the graph synchronously and return the AI response.
    Bypasses the Redis queue — directly invokes the graph.
    """
    from langchain_core.messages import HumanMessage

    if worker_module.GRAPH is None:
        return {"error": "Graph not ready — server starting up"}

    phone = "+5511900000001"
    instance = "test"

    initial_state = {
        "messages": [HumanMessage(content=message)],
        "intent": None,
        "service": None,
        "outcome": None,
        "handoff_mode": "none",
        "handoff_reason": None,
        "handoff_already_notified": False,
        "rag_context": [],
        "customer_data": {"phone": phone},
        "is_human": False,
        "confidence": 1.0,
        "message_type": media_type,
        "media_url": media_url,
        "instance": instance,
        "response_modality": None,
        "audio_bytes": None,
    }

    result = await worker_module.GRAPH.ainvoke(initial_state)
    messages = result.get("messages", [])
    ai_message = None
    for msg in reversed(messages):
        if hasattr(msg, "content") and msg.__class__.__name__ == "AIMessage":
            ai_message = msg.content
            break

    if ai_message:
        await send_whatsapp_message(phone, ai_message, instance)

    intent = result.get("intent")
    service = result.get("service")
    rag_hits = len(result.get("rag_context", []))

    return {
        "input": message,
        "intent": intent,
        "service": service,
        "handoff_mode": result.get("handoff_mode"),
        "handoff_reason": result.get("handoff_reason"),
        "rag_hits": rag_hits,
        "response": ai_message,
        "sent_to_whatsapp": bool(ai_message),
    }
