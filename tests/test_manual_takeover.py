from __future__ import annotations

import asyncio
from typing import Any


def run(coro):
    return asyncio.run(coro)


def test_manual_takeover_still_blocks_ai(monkeypatch):
    from app import worker

    class FakeRedis:
        async def get(self, key: str) -> str | None:
            if key.startswith("manual_takeover:"):
                return "1"
            if key == "whatsapp_rag:bot_enabled":
                return "1"
            return None

        async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
            return True

        async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
            return 1

    class FailingGraph:
        async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("GRAPH não deve ser chamado quando humano assumiu")

    sent: list[tuple[str, str]] = []

    async def fake_send(phone: str, text: str, instance: str = "default") -> bool:
        sent.append((phone, text))
        return True

    monkeypatch.setattr(worker, "GRAPH", FailingGraph())
    monkeypatch.setattr(worker, "send_whatsapp_message", fake_send)

    payload = worker.QueueMessage(phone="5513999999999", message="oi", instance="test")
    run(worker._process_customer_message(payload, FakeRedis(), 1))

    assert sent == []
