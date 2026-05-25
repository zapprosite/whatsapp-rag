from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def _enabled() -> bool:
    return os.getenv("GOOGLE_CALENDAR_ENABLED", "0") == "1"


def _business_slots(start: datetime, days: int) -> list[tuple[datetime, datetime]]:
    slots: list[tuple[datetime, datetime]] = []
    current = start
    for offset in range(days):
        day = current.date() + timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for hour in (9, 11, 14, 16):
            begin = datetime.combine(day, datetime.min.time(), tzinfo=start.tzinfo).replace(hour=hour)
            if begin <= start:
                continue
            slots.append((begin, begin + timedelta(hours=1)))
    return slots


def _overlaps(slot: tuple[datetime, datetime], busy: list[dict]) -> bool:
    slot_start, slot_end = slot
    for item in busy:
        busy_start = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
        busy_end = datetime.fromisoformat(item["end"].replace("Z", "+00:00"))
        if slot_start < busy_end and slot_end > busy_start:
            return True
    return False


def _freebusy_sync(days: int, max_slots: int) -> list[str]:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    credentials_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    timezone_name = os.getenv("GOOGLE_CALENDAR_TIMEZONE", "America/Sao_Paulo")

    if not credentials_file:
        return []

    tz = ZoneInfo(timezone_name)
    now = datetime.now(tz)
    end = now + timedelta(days=days)
    credentials = service_account.Credentials.from_service_account_file(
        credentials_file,
        scopes=["https://www.googleapis.com/auth/calendar.freebusy"],
    )
    service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
    body = {
        "timeMin": now.isoformat(),
        "timeMax": end.isoformat(),
        "timeZone": timezone_name,
        "items": [{"id": calendar_id}],
    }
    result = service.freebusy().query(body=body).execute()
    busy = result.get("calendars", {}).get(calendar_id, {}).get("busy", [])

    free: list[str] = []
    for slot in _business_slots(now, days):
        if _overlaps(slot, busy):
            continue
        free.append(slot[0].strftime("%d/%m %H:%M"))
        if len(free) >= max_slots:
            break
    return free


async def get_availability_summary(days: int = 7, max_slots: int = 3) -> str:
    """Retorna resumo curto de disponibilidade; vazio quando integração está inativa."""
    if not _enabled():
        return ""
    try:
        slots = await asyncio.to_thread(_freebusy_sync, days, max_slots)
    except Exception:
        return ""
    if not slots:
        return "Agenda conectada, mas sem janela livre nos próximos dias úteis."
    return "Próximas janelas livres na agenda: " + ", ".join(slots) + "."
