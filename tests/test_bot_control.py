from __future__ import annotations

import asyncio
import json
from typing import Any

import app.api.bot as bot


def run(coro):
    return asyncio.run(coro)


class FakeRedis:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self.store: dict[str, Any] = dict(initial or {})

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: str, *args: Any, **kwargs: Any) -> bool:
        self.store[key] = value
        return True


def test_bot_state_defaults_to_enabled_and_default_off_message(monkeypatch):
    monkeypatch.delenv("BOT_OFF_MESSAGE", raising=False)

    state = run(bot._bot_state(FakeRedis()))

    assert state["status"] == "ativo"
    assert state["bot_enabled"] is True
    assert state["redis_key"] == bot._BOT_KEY
    assert state["off_message_configured"] is True


def test_bot_state_handles_bytes_and_empty_off_message(monkeypatch):
    monkeypatch.setenv("BOT_OFF_MESSAGE", "")
    r = FakeRedis({bot._BOT_KEY: b"0", bot._BOT_META_KEY: b"not-json"})

    state = run(bot._bot_state(r))

    assert state["status"] == "pausado"
    assert state["bot_enabled"] is False
    assert state["updated_at"] is None
    assert state["updated_by"] is None
    assert state["off_message_configured"] is False


def test_set_bot_enabled_persists_state_and_metadata(monkeypatch):
    monkeypatch.setenv("BOT_OFF_MESSAGE", "Volto em breve")
    r = FakeRedis()

    state = run(bot._set_bot_enabled(r, False, source="pytest"))

    assert r.store[bot._BOT_KEY] == "0"
    assert state["status"] == "pausado"
    assert state["bot_enabled"] is False

    meta = json.loads(r.store[bot._BOT_META_KEY])
    assert meta["status"] == "pausado"
    assert meta["bot_enabled"] is False
    assert meta["updated_at"].endswith("Z")
    assert meta["updated_by"] == "pytest"


def test_bot_panel_renders_accessible_async_switch(monkeypatch):
    r = FakeRedis(
        {
            bot._BOT_KEY: "0",
            bot._BOT_META_KEY: json.dumps(
                {
                    "updated_at": "2026-05-25T10:00:00Z",
                    "updated_by": "pytest",
                }
            ),
        }
    )

    async def fake_get_redis() -> FakeRedis:
        return r

    monkeypatch.setattr(bot, "get_redis", fake_get_redis)

    html = run(bot.bot_panel())

    assert 'body data-enabled="false"' in html
    assert 'role="switch"' in html
    assert 'aria-checked="false"' in html
    assert 'request("/bot/toggle", { method: "POST" })' in html
    assert "2026-05-25T10:00:00Z" in html
    assert "pytest" in html
