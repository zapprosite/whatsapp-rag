from __future__ import annotations

import asyncio
import importlib
import sys
import types
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agent_graph.services.leads_export import LEAD_EXPORT_HEADERS, build_lead_row, export_leads_csv
from agent_graph.nodes.dispatch_side_effects import dispatch_side_effects


@dataclass
class FakeLead:
    phone: str = "+5513999999999"
    name: str | None = "William"
    email: str | None = None
    service_type: str | None = "instalacao"
    service: str | None = "instalacao"
    commercial_path: str | None = "technical_visit_50"
    pipeline_stage: str | None = "qualifying_lead"
    city_bairro: str | None = "Santos"
    address: str | None = None
    appointment_window: str | None = None
    appointment_slot_start: datetime | None = None
    appointment_slot_end: datetime | None = None
    google_event_id: str | None = None
    lead_status: str | None = "open"
    source: str | None = "whatsapp"
    lead_state: dict | str | None = None
    created_at: datetime = datetime(2026, 5, 26, 9, 0, 0)
    updated_at: datetime = datetime(2026, 5, 26, 10, 0, 0)


def run(coro):
    return asyncio.run(coro)


def test_build_lead_row_has_expected_headers():
    lead = FakeLead(
        lead_state={
            "lead_identity": {"full_name": "William", "email": None, "address": None},
            "appointment": {},
            "commercial_decision": {"path": "technical_visit_50"},
            "last_messages": {"user": "oi", "assistant": "ola"},
        }
    )
    row = build_lead_row(lead)
    assert list(row.keys()) == LEAD_EXPORT_HEADERS


def test_build_lead_row_without_email_or_address_does_not_break():
    lead = FakeLead(lead_state={"lead_identity": {}, "appointment": {}, "commercial_decision": {}, "last_messages": {}})
    row = build_lead_row(lead)
    assert row["email"] == ""
    assert row["address"] == ""


def test_export_leads_csv_writes_headers(tmp_path, monkeypatch):
    leads = [FakeLead(lead_state={"lead_identity": {}, "appointment": {}, "commercial_decision": {}, "last_messages": {}})]

    class FakePrismaClient:
        async def connect(self):
            return None

        async def disconnect(self):
            return None

        class lead:
            @staticmethod
            async def find_many(where=None, order=None):
                del where, order
                return leads

    fake_prisma = types.SimpleNamespace(Prisma=lambda: FakePrismaClient())
    monkeypatch.setitem(sys.modules, "prisma", fake_prisma)

    output = run(export_leads_csv(path=str(tmp_path / "leads.csv")))
    content = Path(output).read_text(encoding="utf-8")
    assert "created_at,updated_at,phone,name,email" in content


def test_exports_csv_is_ignored():
    content = Path(".gitignore").read_text(encoding="utf-8")
    assert "exports/*.csv" in content


def test_google_sheets_disabled_does_not_run_sync(monkeypatch):
    monkeypatch.setenv("LEADS_SHEET_ENABLED", "0")

    async def fake_redis_get(key):
        del key
        return None

    async def fake_redis_set(key, value, ex=None):
        del key, value, ex
        return None

    dispatcher_module = importlib.import_module("agent_graph.nodes.dispatch_side_effects")

    monkeypatch.setattr(dispatcher_module, "redis_get", fake_redis_get)
    monkeypatch.setattr(dispatcher_module, "redis_set", fake_redis_set)

    result = run(
        dispatch_side_effects(
            {
                "next_action": {"type": "offer_technical_visit", "side_effects": [{"type": "sync_lead_sheet", "payload": {}}]},
                "customer_data": {"phone": "+5513999999999"},
                "lead_state": {"tipo_servico": "manutencao", "appointment": {}},
                "messages": [],
            }
        )
    )
    assert "sync_lead_sheet" in result["executed_side_effects"]


def test_sheet_failure_does_not_break_dispatch(monkeypatch):
    monkeypatch.setenv("LEADS_SHEET_ENABLED", "1")

    async def fake_sync(state):
        del state
        raise RuntimeError("sheet down")

    async def fake_redis_get(key):
        del key
        return None

    async def fake_redis_set(key, value, ex=None):
        del key, value, ex
        return None

    dispatcher_module = importlib.import_module("agent_graph.nodes.dispatch_side_effects")

    monkeypatch.setattr(dispatcher_module, "sync_lead_sheet", fake_sync)
    monkeypatch.setattr(dispatcher_module, "redis_get", fake_redis_get)
    monkeypatch.setattr(dispatcher_module, "redis_set", fake_redis_set)

    result = run(
        dispatch_side_effects(
            {
                "next_action": {"type": "offer_technical_visit", "side_effects": [{"type": "sync_lead_sheet", "payload": {}}]},
                "customer_data": {"phone": "+5513999999999"},
                "lead_state": {"tipo_servico": "manutencao", "appointment": {}},
                "messages": [],
            }
        )
    )
    assert result["executed_side_effects"] == ["sync_lead_sheet"]
