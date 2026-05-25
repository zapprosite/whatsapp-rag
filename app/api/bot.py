from __future__ import annotations

import json
import logging
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

try:
    from runtime import get_redis, is_manual_takeover, manual_takeover_key, normalize_whatsapp_number, set_manual_takeover
except ModuleNotFoundError:
    from app.runtime import get_redis, is_manual_takeover, manual_takeover_key, normalize_whatsapp_number, set_manual_takeover

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bot", tags=["bot-control"])

_BOT_KEY = "whatsapp_rag:bot_enabled"
_BOT_META_KEY = "whatsapp_rag:bot_state_meta"
_DEFAULT_BOT_OFF_MESSAGE = "Oi! No momento estou atendendo pessoalmente. Te respondo em breve 🙂"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _source_from_request(request: Request | None) -> str:
    if request is None or request.client is None:
        return "api"
    return f"{request.client.host}:{request.client.port}"


def _redis_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _bot_off_message_configured() -> bool:
    return bool(os.getenv("BOT_OFF_MESSAGE", _DEFAULT_BOT_OFF_MESSAGE))


async def _bot_state(r) -> dict[str, Any]:
    raw_enabled = _redis_text(await r.get(_BOT_KEY))
    enabled = raw_enabled != "0"

    meta: dict[str, Any] = {}
    raw_meta = _redis_text(await r.get(_BOT_META_KEY))
    if raw_meta:
        try:
            parsed = json.loads(raw_meta)
            if isinstance(parsed, dict):
                meta = parsed
        except json.JSONDecodeError:
            meta = {}

    return {
        "status": "ativo" if enabled else "pausado",
        "bot_enabled": enabled,
        "redis_key": _BOT_KEY,
        "updated_at": meta.get("updated_at"),
        "updated_by": meta.get("updated_by"),
        "checked_at": _now_iso(),
        "off_message_configured": _bot_off_message_configured(),
    }


async def _set_bot_enabled(r, enabled: bool, *, source: str) -> dict[str, Any]:
    value = "1" if enabled else "0"
    await r.set(_BOT_KEY, value)
    await r.set(
        _BOT_META_KEY,
        json.dumps(
            {
                "status": "ativo" if enabled else "pausado",
                "bot_enabled": enabled,
                "updated_at": _now_iso(),
                "updated_by": source,
            },
            ensure_ascii=False,
        ),
    )
    return await _bot_state(r)


@router.get("", response_class=HTMLResponse)
async def bot_panel() -> str:
    """Painel operacional para ligar/desligar o bot."""
    r = await get_redis()
    state = await _bot_state(r)
    enabled = "true" if state["bot_enabled"] else "false"
    aria_checked = "true" if state["bot_enabled"] else "false"
    state_label = "ATIVO" if state["bot_enabled"] else "PAUSADO"
    state_help = "IA respondendo leads no WhatsApp" if state["bot_enabled"] else "IA não conduzindo atendimento"
    updated_at = state.get("updated_at") or "não registrada"
    updated_by = state.get("updated_by") or "não registrada"
    off_message_label = "configurada" if state["off_message_configured"] else "não configurada"
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Refrimix Bot</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      color-scheme: dark;
      --bg: #111827;
      --panel: #172033;
      --line: #2b3548;
      --text: #f8fafc;
      --muted: #94a3b8;
      --active: #22c55e;
      --paused: #ef4444;
      --track: #364154;
    }}
    body {{
      min-height: 100vh;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    main {{
      width: min(520px, 100%);
      display: grid;
      gap: 24px;
    }}
    header {{ display: grid; gap: 8px; }}
    h1 {{ font-size: 1.4rem; font-weight: 760; letter-spacing: 0; }}
    .subtitle {{ color: var(--muted); font-size: .95rem; line-height: 1.4; }}
    .control {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 22px;
      display: grid;
      gap: 22px;
    }}
    .row {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; }}
    .label {{ display: grid; gap: 4px; }}
    .label strong {{ font-size: 1.8rem; line-height: 1; }}
    .label span {{ color: var(--muted); font-size: .9rem; }}
    .switch {{
      position: relative;
      width: 92px;
      height: 48px;
      border: 0;
      border-radius: 999px;
      background: var(--track);
      cursor: pointer;
      transition: background .18s ease, opacity .18s ease;
      flex: 0 0 auto;
    }}
    .switch::before {{
      content: "";
      position: absolute;
      width: 38px;
      height: 38px;
      top: 5px;
      left: 5px;
      border-radius: 50%;
      background: #fff;
      transition: transform .18s ease;
      box-shadow: 0 8px 20px rgba(0,0,0,.35);
    }}
    body[data-enabled="true"] .switch {{ background: var(--active); }}
    body[data-enabled="true"] .switch::before {{ transform: translateX(44px); }}
    body[data-enabled="true"] .state {{ color: var(--active); }}
    body[data-enabled="false"] .state {{ color: var(--paused); }}
    .switch[disabled] {{ opacity: .55; cursor: wait; }}
    .meta {{
      border-top: 1px solid var(--line);
      padding-top: 16px;
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: .88rem;
    }}
    code {{ color: #dbeafe; }}
    .error {{ color: #fecaca; min-height: 1.2em; }}
  </style>
</head>
<body data-enabled="{enabled}">
  <main>
    <header>
      <h1>Refrimix WhatsApp Bot</h1>
      <p class="subtitle">Interruptor operacional do atendimento automático no WhatsApp.</p>
    </header>
    <section class="control" aria-live="polite">
      <div class="row">
        <div class="label">
          <strong class="state" id="stateLabel">{state_label}</strong>
          <span id="stateHelp">{state_help}</span>
        </div>
        <button id="toggle" class="switch" type="button" role="switch" aria-checked="{aria_checked}" aria-label="Alternar estado do bot"></button>
      </div>
      <div class="meta">
        <div>Última alteração: <code id="updatedAt">{updated_at}</code></div>
        <div>Origem: <code id="updatedBy">{updated_by}</code></div>
        <div>Redis: <code>{_BOT_KEY}</code></div>
        <div id="offMessage">Mensagem de ausência: {off_message_label}</div>
        <div class="error" id="error"></div>
      </div>
    </section>
  </main>
  <script>
    const body = document.body;
    const button = document.getElementById("toggle");
    const stateLabel = document.getElementById("stateLabel");
    const stateHelp = document.getElementById("stateHelp");
    const updatedAt = document.getElementById("updatedAt");
    const updatedBy = document.getElementById("updatedBy");
    const offMessage = document.getElementById("offMessage");
    const errorBox = document.getElementById("error");

    function render(data) {{
      const enabled = Boolean(data.bot_enabled);
      body.dataset.enabled = String(enabled);
      button.setAttribute("aria-checked", String(enabled));
      stateLabel.textContent = enabled ? "ATIVO" : "PAUSADO";
      stateHelp.textContent = enabled ? "IA respondendo leads no WhatsApp" : "IA não conduzindo atendimento";
      updatedAt.textContent = data.updated_at || "não registrada";
      updatedBy.textContent = data.updated_by || "não registrada";
      offMessage.textContent = "Mensagem de ausência: " + (data.off_message_configured ? "configurada" : "não configurada");
      errorBox.textContent = "";
    }}

    async function request(path, options = {{}}) {{
      const response = await fetch(path, options);
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    }}

    async function refresh() {{
      try {{
        render(await request("/bot/status"));
      }} catch (error) {{
        errorBox.textContent = "Falha ao ler status: " + error.message;
      }}
    }}

    button.addEventListener("click", async () => {{
      button.disabled = true;
      try {{
        render(await request("/bot/toggle", {{ method: "POST" }}));
      }} catch (error) {{
        errorBox.textContent = "Falha ao alternar: " + error.message;
      }} finally {{
        button.disabled = false;
      }}
    }});

    setInterval(refresh, 5000);
  </script>
</body>
</html>"""


@router.post("/on")
async def bot_on(request: Request) -> dict[str, Any]:
    r = await get_redis()
    state = await _set_bot_enabled(r, True, source=_source_from_request(request))
    logger.info("Bot ATIVADO")
    return state


@router.post("/off")
async def bot_off(request: Request) -> dict[str, Any]:
    r = await get_redis()
    state = await _set_bot_enabled(r, False, source=_source_from_request(request))
    logger.info("Bot PAUSADO")
    return state


@router.post("/toggle")
async def bot_toggle(request: Request) -> dict[str, Any]:
    r = await get_redis()
    state = await _bot_state(r)
    next_enabled = not state["bot_enabled"]
    new_state = await _set_bot_enabled(r, next_enabled, source=_source_from_request(request))
    logger.info("Bot alternado para %s", new_state["status"])
    return new_state


@router.get("/status")
async def bot_status_api() -> dict[str, Any]:
    r = await get_redis()
    return await _bot_state(r)


@router.post("/takeover/{phone}")
async def bot_takeover(phone: str) -> dict[str, Any]:
    r = await get_redis()
    normalized = normalize_whatsapp_number(phone)
    await set_manual_takeover(r, normalized, True)
    logger.info("Humano assumiu; IA pausada para este contato: %s", normalized)
    return {
        "phone": normalized,
        "manual_takeover": True,
        "redis_key": manual_takeover_key(normalized),
    }


@router.post("/release/{phone}")
async def bot_release(phone: str) -> dict[str, Any]:
    r = await get_redis()
    normalized = normalize_whatsapp_number(phone)
    await set_manual_takeover(r, normalized, False)
    logger.info("IA liberada para contato: %s", normalized)
    return {
        "phone": normalized,
        "manual_takeover": False,
        "redis_key": manual_takeover_key(normalized),
    }


@router.get("/takeover/{phone}")
async def bot_takeover_status(phone: str) -> dict[str, Any]:
    r = await get_redis()
    normalized = normalize_whatsapp_number(phone)
    active = await is_manual_takeover(r, normalized)
    return {
        "phone": normalized,
        "manual_takeover": active,
        "redis_key": manual_takeover_key(normalized),
    }


@router.get("/groups")
async def bot_groups() -> dict[str, Any]:
    if os.getenv("ENVIRONMENT", "local") not in {"local", "dev", "development", "test"}:
        return {"groups": [], "error": "rota disponível apenas em ambiente local/dev"}
    from agent_graph.services.whatsapp import list_whatsapp_groups

    groups = await list_whatsapp_groups(os.getenv("EVOLUTION_INSTANCE", "default"))
    return {"groups": groups, "count": len(groups)}


async def _agenda_payload(target_date: date, kind: str, *, send: bool, target: str) -> dict[str, Any]:
    from agent_graph.services.agenda_digest import send_agenda_digest

    r = await get_redis()
    actual_target = target if send else "preview"
    result = await send_agenda_digest(
        target_date,
        kind,
        force=not send,
        redis_client=r if send else None,
        target=actual_target,
    )
    if not send:
        result["sent"] = False
    return result


@router.get("/agenda/today")
async def agenda_today() -> dict[str, Any]:
    today = datetime.now().date()
    return await _agenda_payload(today, "morning_today", send=False, target="preview")


@router.get("/agenda/tomorrow")
async def agenda_tomorrow() -> dict[str, Any]:
    tomorrow = datetime.now().date() + timedelta(days=1)
    return await _agenda_payload(tomorrow, "night_tomorrow", send=False, target="preview")


@router.post("/agenda/digest/today")
@router.post("/agenda/send/today")
async def agenda_send_today(
    send: bool = Query(False),
    target: str = Query("group", pattern="^(group|owner|preview)$"),
) -> dict[str, Any]:
    today = datetime.now().date()
    return await _agenda_payload(today, "morning_today", send=send, target=target)


@router.post("/agenda/digest/tomorrow")
@router.post("/agenda/send/tomorrow")
async def agenda_send_tomorrow(
    send: bool = Query(False),
    target: str = Query("group", pattern="^(group|owner|preview)$"),
) -> dict[str, Any]:
    tomorrow = datetime.now().date() + timedelta(days=1)
    return await _agenda_payload(tomorrow, "night_tomorrow", send=send, target=target)


@router.post("/agenda/digest/test")
async def agenda_digest_test(
    send: bool = Query(False),
    target: str = Query("preview", pattern="^(group|owner|preview)$"),
    date_value: date | None = Query(None, alias="date"),
) -> dict[str, Any]:
    target_date = date_value or datetime.now().date()
    return await _agenda_payload(target_date, "manual", send=send, target=target)


@router.post("/agenda/send/date/{yyyy_mm_dd}")
async def agenda_send_date(
    yyyy_mm_dd: date,
    send: bool = Query(False),
    target: str = Query("group", pattern="^(group|owner|preview)$"),
) -> dict[str, Any]:
    return await _agenda_payload(yyyy_mm_dd, "manual", send=send, target=target)
