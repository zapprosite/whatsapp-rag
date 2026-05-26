from __future__ import annotations

import csv
import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any


LEAD_EXPORT_HEADERS = [
    "created_at",
    "updated_at",
    "phone",
    "name",
    "email",
    "service_type",
    "commercial_path",
    "pipeline_stage",
    "cidade_bairro",
    "address",
    "appointment_window",
    "appointment_slot_start",
    "appointment_slot_end",
    "google_event_id",
    "lead_status",
    "source",
    "last_user_message",
    "last_bot_message",
    "owner_alert_reason",
    "notes",
]


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def build_lead_row(lead: Any, latest_event: dict[str, Any] | None = None) -> dict[str, str]:
    lead_state = _json_value(getattr(lead, "lead_state", None), {})
    identity = lead_state.get("lead_identity") or {}
    appointment = lead_state.get("appointment") or {}
    commercial_decision = lead_state.get("commercial_decision") or {}
    last_messages = lead_state.get("last_messages") or {}
    latest_event = latest_event or {}
    return {
        "created_at": _iso(getattr(lead, "created_at", "")),
        "updated_at": _iso(getattr(lead, "updated_at", "")),
        "phone": str(getattr(lead, "phone", "") or ""),
        "name": str(getattr(lead, "name", None) or identity.get("full_name") or ""),
        "email": str(getattr(lead, "email", None) or identity.get("email") or ""),
        "service_type": str(getattr(lead, "service_type", None) or getattr(lead, "service", None) or lead_state.get("tipo_servico") or ""),
        "commercial_path": str(getattr(lead, "commercial_path", None) or commercial_decision.get("path") or ""),
        "pipeline_stage": str(getattr(lead, "pipeline_stage", None) or lead_state.get("pipeline_stage") or ""),
        "cidade_bairro": str(getattr(lead, "city_bairro", None) or lead_state.get("cidade_bairro") or ""),
        "address": str(getattr(lead, "address", None) or identity.get("address") or ""),
        "appointment_window": str(getattr(lead, "appointment_window", None) or appointment.get("preferred_window") or ""),
        "appointment_slot_start": _iso(getattr(lead, "appointment_slot_start", None) or appointment.get("slot_start") or ""),
        "appointment_slot_end": _iso(getattr(lead, "appointment_slot_end", None) or appointment.get("slot_end") or ""),
        "google_event_id": str(getattr(lead, "google_event_id", None) or appointment.get("google_event_id") or ""),
        "lead_status": str(getattr(lead, "lead_status", None) or "open"),
        "source": str(getattr(lead, "source", None) or "whatsapp"),
        "last_user_message": str(last_messages.get("user") or latest_event.get("last_user_message") or ""),
        "last_bot_message": str(last_messages.get("assistant") or latest_event.get("last_bot_message") or ""),
        "owner_alert_reason": str(commercial_decision.get("owner_alert_reason") or latest_event.get("owner_alert_reason") or ""),
        "notes": str(latest_event.get("notes") or lead_state.get("conversation_summary") or ""),
    }


async def export_leads_csv(
    start_date: date | None = None,
    end_date: date | None = None,
    path: str | None = None,
) -> str:
    from prisma import Prisma

    db = Prisma()
    await db.connect()
    try:
        where: dict[str, Any] = {}
        if start_date or end_date:
            created_filter: dict[str, Any] = {}
            if start_date:
                created_filter["gte"] = datetime.combine(start_date, time.min)
            if end_date:
                created_filter["lte"] = datetime.combine(end_date, time.max)
            where["created_at"] = created_filter

        leads = await db.lead.find_many(where=where or None, order={"created_at": "asc"})
        output_path = Path(path or f"exports/leads-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LEAD_EXPORT_HEADERS)
            writer.writeheader()
            for lead in leads:
                writer.writerow(build_lead_row(lead))
        return str(output_path)
    finally:
        await db.disconnect()
