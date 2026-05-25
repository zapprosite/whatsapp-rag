from __future__ import annotations

import asyncio
from typing import Any

import app.api.webhook as webhook


def run(coro):
    return asyncio.run(coro)


def test_owner_can_pause_one_lead_from_whatsapp(monkeypatch):
    calls: list[tuple[str, bool]] = []
    sent: list[tuple[str, str]] = []

    class FakeRedis:
        pass

    async def fake_get_redis():
        return FakeRedis()

    async def fake_set_manual_takeover(r: Any, phone: str, enabled: bool):
        calls.append((phone, enabled))

    async def fake_send(phone: str, text: str, instance: str = "default"):
        sent.append((phone, text))
        return True

    monkeypatch.setenv("OWNER_PHONE", "5513996659382")
    monkeypatch.setattr(webhook, "get_redis", fake_get_redis)
    monkeypatch.setattr(webhook, "set_manual_takeover", fake_set_manual_takeover)
    monkeypatch.setattr(webhook, "send_whatsapp_message", fake_send)

    parsed = webhook.IncomingWebhook(
        phone="5513996659382",
        message="assumir 5513999999999",
        instance="test",
        message_type="conversation",
        msg_id="cmd-1",
        media_url="",
        media_base64="",
    )

    handled = run(webhook._handle_owner_command(parsed))

    assert handled is True
    assert calls == [("5513999999999", True)]
    assert "liberar 5513999999999" in sent[0][1]


def test_non_owner_command_is_ignored(monkeypatch):
    monkeypatch.setenv("OWNER_PHONE", "5513996659382")
    parsed = webhook.IncomingWebhook(
        phone="5513000000000",
        message="assumir 5513999999999",
        instance="test",
        message_type="conversation",
        msg_id="cmd-2",
        media_url="",
        media_base64="",
    )

    assert run(webhook._handle_owner_command(parsed)) is False
