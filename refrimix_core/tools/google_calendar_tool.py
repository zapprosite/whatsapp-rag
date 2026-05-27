"""
Google Calendar Tool — Refrimix
Consulta disponibilidade e cria eventos no Google Calendar da Refrimix.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, time, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
TOKEN_PATH = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", "/srv/infra/google/refrimix/token.json")
CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "refrimixtecnologia@gmail.com")
REFRIMIX_TIMEZONE = os.getenv("REFRIMIX_TIMEZONE", "America/Sao_Paulo")

# Duração padrão por tipo de serviço (minutos)
SERVICE_DURATION = {
    "higienizacao": int(os.getenv("REFRIMIX_HYGIENIZATION_DURATION_MIN", "90")),
    "instalacao": int(os.getenv("REFRIMIX_INSTALLATION_DURATION_MIN", "180")),
    "manutencao": int(os.getenv("REFRIMIX_VISIT_DURATION_MIN", "60")),
    "conserto": int(os.getenv("REFRIMIX_VISIT_DURATION_MIN", "60")),
    "vrf": int(os.getenv("REFRIMIX_INSTALLATION_DURATION_MIN", "180")),
    "outro": int(os.getenv("REFRIMIX_VISIT_DURATION_MIN", "60")),
}

# Horário comercial
BUSINESS_START = time(8, 0)
BUSINESS_END = time(18, 0)
BUSINESS_DAYS = [1, 2, 3, 4, 5]  # Seg-Sex


def _get_access_token() -> str:
    token_file = Path(TOKEN_PATH)
    if not token_file.exists():
        raise RuntimeError(f"Token OAuth não encontrado em {TOKEN_PATH}")
    with open(token_file) as f:
        token_data = json.load(f)
    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError(f"access_token ausente em {TOKEN_PATH}")
    return access_token


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_access_token()}"}


def _tz_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def list_available_slots(
    service_type: str,
    preferred_window: str | None = None,
    city_bairro: str | None = None,
    days_ahead: int = 7,
) -> list[dict[str, Any]]:
    """
    Lista horários disponíveis para agendamento.

    Usa FreeBusy para descobrir horários ocupados e deriva os livres.
    Retorna lista de slots no formato:
    {
        "date": "2026-05-28",
        "start": "09:00",
        "end": "10:00",
        "day_label": "Quinta-feira",
        "slot_index": 1,
    }
    """
    from datetime import date

    duration = SERVICE_DURATION.get(service_type, 60)

    # Janela de dias úteis
    slots = []
    current_date = _tz_now().date()
    day_labels = [
        "Segunda-feira", "Terça-feira", "Quarta-feira",
        "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"
    ]

    days_checked = 0
    day_cursor = current_date

    while days_checked < days_ahead:
        day_cursor += timedelta(days=1)
        weekday = day_cursor.weekday()

        # Pula sábado e domingo
        if weekday not in BUSINESS_DAYS:
            continue

        # Monta timeMin/timeMax do dia
        day_start = datetime.combine(day_cursor, BUSINESS_START, tzinfo=timezone.utc)
        day_end = datetime.combine(day_cursor, BUSINESS_END, tzinfo=timezone.utc)

        # Consulta FreeBusy
        freebusy_url = f"{CALENDAR_API_BASE}/freeBusy"
        payload = {
            "timeMin": day_start.isoformat(),
            "timeMax": day_end.isoformat(),
            "items": [{"id": CALENDAR_ID}],
            "timeZone": REFRIMIX_TIMEZONE,
        }

        try:
            with httpx.Client() as client:
                resp = client.post(
                    freebusy_url,
                    headers=_headers(),
                    json=payload,
                    timeout=30,
                )
            resp.raise_for_status()
            busy_periods = resp.json().get("calendars", {}).get(CALENDAR_ID, {}).get("busy", [])
        except Exception as exc:
            logger.warning("FreeBusy falhou para %s: %s", day_cursor, exc)
            busy_periods = []

        # Converte busy periods para set de minutos do dia
        busy_minutes = set()
        for bp in busy_periods:
            bp_start = datetime.fromisoformat(bp["start"].replace("Z", "+00:00"))
            bp_end = datetime.fromisoformat(bp["end"].replace("Z", "+00:00"))
            # Normaliza para o dia
            start_min = (bp_start.hour * 60 + bp_start.minute) - (8 * 60)
            end_min = (bp_end.hour * 60 + bp_end.minute) - (8 * 60)
            for m in range(max(0, start_min), min(10 * 60, end_min)):
                busy_minutes.add(m)

        # Gera slots disponíveis
        day_slots = []
        slot_start = 8 * 60  # 08:00 em minutos
        business_minutes = (18 - 8) * 60  # 10h = 600 min

        slot_count = 0
        while slot_start + duration <= 18 * 60:
            slot_minutes = set(
                m for m in range(slot_start, slot_start + duration)
            )
            if not slot_minutes & busy_minutes:
                hour = slot_start // 60
                minute = slot_start % 60
                end_hour = (slot_start + duration) // 60
                end_minute = (slot_start + duration) % 60
                slot_count += 1
                day_slots.append({
                    "date": day_cursor.isoformat(),
                    "start": f"{hour:02d}:{minute:02d}",
                    "end": f"{end_hour:02d}:{end_minute:02d}",
                    "day_label": day_labels[weekday],
                    "slot_index": slot_count,
                })
            slot_start += 30  # slots a cada 30 min

        slots.extend(day_slots)
        days_checked += 1

        if len(slots) >= 12:  # Máximo 12 opções
            break

    return slots[:12]


def format_slots_for_whatsapp(slots: list[dict[str, Any]]) -> str:
    """
    Formata slots como opções numeradas para WhatsApp.

    Exemplo:
    1. Quinta-feira 28/05 às 09:00
    2. Quinta-feira 28/05 às 10:00
    """
    if not slots:
        return "Nenhum horário disponível neste período. Me avise outro dia."

    lines = []
    for slot in slots:
        date_obj = datetime.fromisoformat(slot["date"])
        date_str = date_obj.strftime("%d/%m")
        day = slot["day_label"]
        start = slot["start"]
        lines.append(f"{slot['slot_index']}. {day} {date_str} às {start}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Event creation
# ---------------------------------------------------------------------------

def create_service_event(
    lead_id: str,
    phone: str,
    client_name: str | None,
    service_type: str,
    city_bairro: str,
    start_iso: str,  # ISO datetime
    duration_minutes: int | None = None,
    drive_folder_url: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """
    Cria evento de serviço no Google Calendar.

    O evento inclui:
    - Cliente e telefone
    - Tipo de serviço e bairro
    - Link da pasta do Drive (se disponível)
    - Notas do atendimento
    """
    if duration_minutes is None:
        duration_minutes = SERVICE_DURATION.get(service_type, 60)

    start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    # Descrição com link do Drive
    description_parts = [
        f"Lead ID: {lead_id}",
        f"Telefone: {phone}",
        f"Tipo: {service_type}",
    ]
    if client_name:
        description_parts.insert(0, f"Cliente: {client_name}")
    if drive_folder_url:
        description_parts.append(f"Drive: {drive_folder_url}")
    if notes:
        description_parts.append(f"\nResumo: {notes}")

    event_payload = {
        "summary": f"[{service_type.upper()}] {client_name or phone} — {city_bairro}",
        "location": city_bairro,
        "description": "\n".join(description_parts),
        "start": {
            "dateTime": start_iso,
            "timeZone": REFRIMIX_TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": REFRIMIX_TIMEZONE,
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ],
        },
    }

    url = f"{CALENDAR_API_BASE}/calendars/{CALENDAR_ID}/events"
    with httpx.Client() as client:
        resp = client.post(url, headers=_headers(), json=event_payload, timeout=30)
    resp.raise_for_status()
    result = resp.json()

    logger.info("Evento criado: %s (%s)", result.get("summary"), result.get("id"))
    return {
        "id": result.get("id"),
        "summary": result.get("summary"),
        "start": result.get("start", {}).get("dateTime"),
        "end": result.get("end", {}).get("dateTime"),
        "html_link": result.get("htmlLink"),
        "meet_link": result.get("conferenceData", {}).get("entryPoints", [{}])[0].get("uri"),
    }
