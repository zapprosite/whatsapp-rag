from __future__ import annotations

import asyncio
from datetime import datetime

import agent_graph.services.calendar as calendar


def run(coro):
    return asyncio.run(coro)


class _FakeRequest:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _FakeCalendarService:
    def __init__(self):
        self.freebusy_body = None
        self.insert_body = None

    def freebusy(self):
        service = self

        class _FreeBusy:
            def query(self, body):
                service.freebusy_body = body
                return _FakeRequest({"calendars": {"agenda@test": {"busy": []}}})

        return _FreeBusy()

    def events(self):
        service = self

        class _Events:
            def insert(self, calendarId, body):
                service.insert_body = {"calendarId": calendarId, "body": body}
                return _FakeRequest({"id": "evt_123"})

        return _Events()


def test_calendar_service_uses_freebusy_and_formats_slots(monkeypatch):
    fake = _FakeCalendarService()
    monkeypatch.setenv("GOOGLE_CALENDAR_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "agenda@test")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/tmp/fake.json")
    monkeypatch.setattr(calendar, "_build_calendar_service", lambda scope: fake)
    monkeypatch.setattr(calendar, "_now", lambda: datetime(2026, 5, 26, 10, 0, tzinfo=calendar._timezone()))

    slots = run(calendar.suggest_slots("tarde", {}, days=3, max_slots=3))
    formatted = calendar.format_slots_for_whatsapp(slots)

    assert fake.freebusy_body["items"] == [{"id": "agenda@test"}]
    assert fake.freebusy_body["timeMin"]
    assert fake.freebusy_body["timeMax"]
    assert len(slots) == 3
    assert "1. " in formatted and "2. " in formatted and "3. " in formatted


def test_event_insert_only_runs_when_enabled(monkeypatch):
    fake = _FakeCalendarService()
    monkeypatch.setenv("GOOGLE_CALENDAR_ENABLED", "1")
    monkeypatch.setenv("GOOGLE_CALENDAR_ID", "agenda@test")
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_FILE", "/tmp/fake.json")
    monkeypatch.setattr(calendar, "_build_calendar_service", lambda scope: fake)

    slot = {
        "start": "2026-05-27T14:00:00-03:00",
        "end": "2026-05-27T16:00:00-03:00",
        "label": "Amanhã 14:00",
    }
    lead_state = {"tipo_servico": "instalacao", "nome": "Teste", "cidade_bairro": "Guarujá"}

    monkeypatch.setenv("GOOGLE_CALENDAR_CREATE_EVENTS", "0")
    disabled = run(calendar.create_service_event(lead_state, slot))
    assert disabled is None

    monkeypatch.setenv("GOOGLE_CALENDAR_CREATE_EVENTS", "1")
    enabled = run(calendar.create_service_event(lead_state, slot))
    assert enabled == {"id": "evt_123"}
    assert fake.insert_body["calendarId"] == "agenda@test"
