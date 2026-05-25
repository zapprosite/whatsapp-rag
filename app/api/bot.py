from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

try:
    from runtime import get_redis
except ModuleNotFoundError:
    from app.runtime import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bot", tags=["bot-control"])

_BOT_KEY = "whatsapp_rag:bot_enabled"


async def _bot_status(r) -> str:
    val = await r.get(_BOT_KEY)
    return "ativo" if val != "0" else "pausado"


@router.get("", response_class=HTMLResponse)
async def bot_panel():
    """Painel visual para ligar/desligar o bot."""
    r = await get_redis()
    status = await _bot_status(r)
    ativo = status == "ativo"
    cor = "#22c55e" if ativo else "#ef4444"
    cor_btn = "#ef4444" if ativo else "#22c55e"
    label = "ATIVO 🟢" if ativo else "PAUSADO 🔴"
    acao = "Pausar IA" if ativo else "Ligar IA"
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
    h1 {{ font-size: 1.4rem; color: #94a3b8; letter-spacing: .05em; }}
    .status {{ font-size: 3rem; font-weight: 800; color: {cor}; }}
    .btn {{ background: {cor_btn}; color: #fff; border: none; border-radius: 1rem;
            padding: 1.2rem 3rem; font-size: 1.4rem; font-weight: 700;
            cursor: pointer; width: 100%; max-width: 320px; transition: opacity .2s; }}
    .btn:hover {{ opacity: .85; }}
    .hint {{ color: #475569; font-size: .85rem; text-align: center; }}
    form {{ width: 100%; display: flex; justify-content: center; }}
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


@router.post("/on")
async def bot_on():
    r = await get_redis()
    await r.set(_BOT_KEY, "1")
    logger.info("Bot ATIVADO")
    return RedirectResponse(url="/bot", status_code=303)


@router.post("/off")
async def bot_off():
    r = await get_redis()
    await r.set(_BOT_KEY, "0")
    logger.info("Bot PAUSADO")
    return RedirectResponse(url="/bot", status_code=303)


@router.get("/status")
async def bot_status_api():
    r = await get_redis()
    status = await _bot_status(r)
    return {"status": status, "bot_enabled": status == "ativo"}
