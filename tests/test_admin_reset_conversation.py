from __future__ import annotations

import asyncio


def run(coro):
    return asyncio.run(coro)


class FakeRedis:
    def __init__(self) -> None:
        self.store = {
            "conv_history:5513996659382": "[]",
            "manual_takeover:5513996659382": "1",
            "conv_lock:5513996659382": "token",
            "handoff_state:5513996659382": "1",
            "side_effect:google_calendar_insert:5513996659382:abc": "1",
            "whatsapp_rag:bot_enabled": "1",
        }

    async def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    async def scan_iter(self, match: str):
        prefix = match.replace("*", "")
        for key in list(self.store.keys()):
            if key.startswith(prefix):
                yield key


def test_reset_test_conversation_state_clears_phone_scoped_redis(monkeypatch):
    from app import worker

    monkeypatch.delenv("DATABASE_URL", raising=False)
    fake_redis = FakeRedis()

    result = run(worker.reset_test_conversation_state(fake_redis, "5513996659382"))

    assert result["deleted_keys_count"] >= 4
    assert result["persistent_reset"] is False
    assert "conv_history:5513996659382" not in fake_redis.store
    assert "manual_takeover:5513996659382" not in fake_redis.store
    assert "conv_lock:5513996659382" not in fake_redis.store
    assert "handoff_state:5513996659382" not in fake_redis.store
    assert "whatsapp_rag:bot_enabled" in fake_redis.store


def test_reset_admin_route_uses_admin_phone(monkeypatch):
    from app.api import bot

    fake_redis = FakeRedis()

    async def fake_get_redis():
        return fake_redis

    async def fake_reset(r, phone):
        assert r is fake_redis
        assert phone == "5513996659382"
        return {
            "phone": phone,
            "deleted_keys_count": 4,
            "persistent_reset": False,
            "deleted_events": 0,
        }

    monkeypatch.setattr(bot, "get_redis", fake_get_redis)
    monkeypatch.setattr(bot, "reset_test_conversation_state", fake_reset)

    result = run(bot.bot_reset_admin_test_conversation())

    assert result["ok"] is True
    assert result["scope"] == "admin_test_conversation"
    assert result["deleted_keys_count"] == 4
