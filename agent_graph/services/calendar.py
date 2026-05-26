from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


def _enabled() -> bool:
    return os.getenv("GOOGLE_CALENDAR_ENABLED", "0") == "1"


def _create_events_enabled() -> bool:
    return os.getenv("GOOGLE_CALENDAR_CREATE_EVENTS", "0") == "1"


def _timezone_name() -> str:
    return os.getenv("GOOGLE_CALENDAR_TIMEZONE", "America/Sao_Paulo")


def _timezone() -> ZoneInfo:
    return ZoneInfo(_timezone_name())


def _duration_minutes() -> int:
    try:
        return max(30, int(os.getenv("GOOGLE_CALENDAR_DEFAULT_DURATION_MINUTES", "120")))
    except ValueError:
        return 120


def _calendar_id() -> str:
    return os.getenv("GOOGLE_CALENDAR_ID", "primary")


def _credentials_file() -> str:
    return os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")


def _now() -> datetime:
    return datetime.now(_timezone())


def _build_calendar_service(scope: str):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    credentials_file = _credentials_file()
    if not credentials_file:
        raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_FILE ausente")
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=[scope],
    )
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _candidate_hours(period: str | None) -> tuple[int, ...]:
    period = (period or "").strip().lower()
    if period == "manhã":
        return (9, 11)
    if period == "tarde":
        return (14, 16)
    if period == "noite":
        return (18, 20)
    return (9, 11, 14, 16)


def _slot_label(start: datetime) -> str:
    now = _now().date()
    if start.date() == now:
        day_label = "Hoje"
    elif start.date() == now + timedelta(days=1):
        day_label = "Amanhã"
    else:
        weekday_map = {
            0: "Segunda",
            1: "Terça",
            2: "Quarta",
            3: "Quinta",
            4: "Sexta",
            5: "Sábado",
            6: "Domingo",
        }
        day_label = weekday_map[start.weekday()]
    return f"{day_label} {start.strftime('%H:%M')}"


def _iter_business_slots(start: datetime, days: int, period: str | None) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    hours = _candidate_hours(period)
    duration = timedelta(minutes=_duration_minutes())
    for day_offset in range(days):
        day = start.date() + timedelta(days=day_offset)
        if day.weekday() >= 5:
            continue
        for hour in hours:
            begin = datetime.combine(day, datetime.min.time(), tzinfo=start.tzinfo).replace(hour=hour)
            end = begin + duration
            if begin <= start:
                continue
            slots.append(
                {
                    "start": begin.isoformat(),
                    "end": end.isoformat(),
                    "label": _slot_label(begin),
                }
            )
    return slots


def _overlaps(slot: dict[str, Any], busy: list[dict[str, Any]]) -> bool:
    slot_start = datetime.fromisoformat(slot["start"])
    slot_end = datetime.fromisoformat(slot["end"])
    for item in busy:
        busy_start = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
        busy_end = datetime.fromisoformat(item["end"].replace("Z", "+00:00"))
        if slot_start < busy_end and slot_end > busy_start:
            return True
    return False


def _freebusy_sync(period: str | None, days: int, max_slots: int) -> list[dict[str, Any]]:
    if not _enabled():
        return []

    service = _build_calendar_service("https://www.googleapis.com/auth/calendar.freebusy")
    now = _now()
    end = now + timedelta(days=days)
    calendar_id = _calendar_id()
    body = {
        "timeMin": now.isoformat(),
        "timeMax": end.isoformat(),
        "timeZone": _timezone_name(),
        "items": [{"id": calendar_id}],
    }
    result = service.freebusy().query(body=body).execute()
    busy = result.get("calendars", {}).get(calendar_id, {}).get("busy", [])

    free_slots: list[dict[str, Any]] = []
    for slot in _iter_business_slots(now, days, period):
        if _overlaps(slot, busy):
            continue
        free_slots.append(slot)
        if len(free_slots) >= max_slots:
            break
    return free_slots


async def suggest_slots(period: str | None, lead_state: dict[str, Any], days: int = 7, max_slots: int = 3) -> list[dict[str, Any]]:
    del lead_state
    if not _enabled():
        return []
    try:
        return await asyncio.to_thread(_freebusy_sync, period, days, max_slots)
    except Exception:
        return []


async def create_service_event(lead_state: dict[str, Any], selected_slot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not _enabled() or not _create_events_enabled() or not selected_slot:
        return None

    def _insert_sync() -> dict[str, Any]:
        service = _build_calendar_service("https://www.googleapis.com/auth/calendar.events")
        service_name = lead_state.get("tipo_servico") or "atendimento"
        customer_name = lead_state.get("nome") or "Cliente Refrimix"
        description_parts = [
            f"Serviço: {service_name}",
            f"Local: {lead_state.get('cidade_bairro') or 'não informado'}",
        ]
        event = {
            "summary": f"Refrimix - {customer_name}",
            "description": "\n".join(description_parts),
            "start": {"dateTime": selected_slot["start"], "timeZone": _timezone_name()},
            "end": {"dateTime": selected_slot["end"], "timeZone": _timezone_name()},
        }
        return service.events().insert(calendarId=_calendar_id(), body=event).execute()

    try:
        return await asyncio.to_thread(_insert_sync)
    except Exception:
        return None


def format_slots_for_whatsapp(slots: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for index, slot in enumerate(slots[:3], start=1):
        lines.append(f"{index}. {slot.get('label')}")
    return "\n".join(lines)


async def get_availability_summary(days: int = 7, max_slots: int = 3) -> str:
    if not _enabled():
        return ""
    slots = await suggest_slots(None, {}, days=days, max_slots=max_slots)
    if not slots:
        return "Agenda conectada, mas sem janela livre nos próximos dias úteis."
    labels = ", ".join(slot["label"] for slot in slots)
    return f"Próximas janelas livres na agenda: {labels}."
