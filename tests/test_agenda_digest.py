from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

import agent_graph.services.agenda_digest as digest


def run(coro):
    return asyncio.run(coro)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return self.store.pop(key, None) is not None


def service(hour: int, name: str, phone: str = "5513999999999") -> dict[str, Any]:
    target = datetime(2026, 5, 25, hour, 0)
    return {
        "id": name,
        "phone": phone,
        "customer_name": name,
        "service": "instalação split",
        "job_type": "instalacao",
        "status": "scheduled",
        "address": "Rua Teste",
        "city_bairro": "Santos / Gonzaga",
        "scheduled_start": target.isoformat(),
        "scheduled_end": (target + timedelta(hours=1)).isoformat(),
        "scheduled_window": "",
        "notes": "confirmar ponto elétrico",
        "priority": "normal",
        "value_tier": "standard",
    }


def test_agenda_digest_today_empty():
    message = digest.format_agenda_digest(date(2026, 5, 25), [], "morning_today")

    assert "Agenda Refrimix" in message
    assert "Nenhum atendimento estruturado para hoje" in message


def test_agenda_digest_today_with_services():
    services = [service(14, "Maria"), service(9, "João")]

    message = digest.format_agenda_digest(date(2026, 5, 25), services, "morning_today")

    assert message.index("09:00-10:00") < message.index("14:00-15:00")
    assert "João" in message
    assert "Maria" in message


def test_agenda_digest_tomorrow_20h_format():
    message = digest.format_agenda_digest(date(2026, 5, 26), [service(9, "João")], "night_tomorrow")

    assert "Agenda Refrimix — Amanhã" in message
    assert "Resumo para organizar antes de dormir" in message


def test_agenda_digest_morning_format():
    message = digest.format_agenda_digest(date(2026, 5, 25), [service(9, "João")], "morning_today")

    assert "Agenda Refrimix — Hoje" in message
    assert "Bom dia. Agenda operacional de hoje" in message


def test_agenda_digest_uses_group_not_owner(monkeypatch):
    sent: list[str] = []

    async def fake_get_services(target_date: date) -> list[dict[str, Any]]:
        return [service(9, "João")]

    async def fake_group(text: str) -> bool:
        sent.append(text)
        return True

    async def fail_owner(alert: dict[str, Any]) -> bool:
        raise AssertionError("digest não deve ir para OWNER_PHONE por padrão")

    monkeypatch.setenv("AGENDA_GROUP_ENABLED", "1")
    monkeypatch.setenv("AGENDA_GROUP_JID", "120363000000000000@g.us")
    monkeypatch.setattr(digest, "get_services_for_day", fake_get_services)
    monkeypatch.setattr(digest, "send_agenda_group_message", fake_group)
    monkeypatch.setattr(digest, "send_owner_alert", fail_owner)

    result = run(digest.send_agenda_digest(date(2026, 5, 25), "morning_today", force=True))

    assert result["sent"] is True
    assert sent


def test_no_group_jid_no_send(monkeypatch, caplog):
    async def fake_get_services(target_date: date) -> list[dict[str, Any]]:
        return [service(9, "João")]

    monkeypatch.setenv("AGENDA_GROUP_ENABLED", "1")
    monkeypatch.setenv("AGENDA_GROUP_JID", "")
    monkeypatch.setattr(digest, "get_services_for_day", fake_get_services)

    result = run(digest.send_agenda_digest(date(2026, 5, 25), "morning_today", force=True))

    assert result["sent"] is False
    assert result["group_jid_configured"] is False
    assert "AGENDA_GROUP_JID está vazio" in caplog.text


def test_agenda_dedup_lock(monkeypatch):
    calls = 0

    async def fake_get_services(target_date: date) -> list[dict[str, Any]]:
        return [service(9, "João")]

    async def fake_group(text: str) -> bool:
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setenv("AGENDA_GROUP_ENABLED", "1")
    monkeypatch.setenv("AGENDA_GROUP_JID", "120363000000000000@g.us")
    monkeypatch.setattr(digest, "get_services_for_day", fake_get_services)
    monkeypatch.setattr(digest, "send_agenda_group_message", fake_group)
    r = FakeRedis()

    first = run(digest.send_agenda_digest(date(2026, 5, 25), "morning_today", redis_client=r))
    second = run(digest.send_agenda_digest(date(2026, 5, 25), "morning_today", redis_client=r))

    assert first["sent"] is True
    assert second["sent"] is False
    assert second["deduped"] is True
    assert calls == 1
