from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agent_graph.services.alerts import send_agenda_group_message, send_owner_alert

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = (
    "scheduled",
    "in_progress",
    "approved",
    "active",
    "awaiting_parts",
    "awaiting_customer",
)
_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _tz() -> ZoneInfo:
    return ZoneInfo(os.getenv("AGENDA_GROUP_DIGEST_TIMEZONE", "America/Sao_Paulo"))


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _target_day_patterns(target_date: date) -> tuple[str, ...]:
    return (
        target_date.isoformat(),
        target_date.strftime("%d/%m/%Y"),
        target_date.strftime("%d/%m"),
        target_date.strftime("%d-%m-%Y"),
    )


def _row_to_service(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _as_text(row.get("id")),
        "phone": _as_text(row.get("phone")),
        "customer_name": _as_text(row.get("customer_name")),
        "service": _as_text(row.get("service")),
        "job_type": _as_text(row.get("job_type")),
        "status": _as_text(row.get("status")),
        "address": _as_text(row.get("address")),
        "city_bairro": _as_text(row.get("city_bairro")),
        "scheduled_start": _as_text(row.get("scheduled_start")),
        "scheduled_end": _as_text(row.get("scheduled_end")),
        "scheduled_window": _as_text(row.get("scheduled_window")),
        "notes": _as_text(row.get("notes")),
        "priority": _as_text(row.get("priority") or "normal"),
        "value_tier": _as_text(row.get("value_tier") or "standard"),
    }


async def get_services_for_day(target_date: date) -> list[dict[str, Any]]:
    if not os.getenv("DATABASE_URL"):
        return []

    from prisma import Prisma

    tz = _tz()
    day_start = datetime.combine(target_date, time.min, tzinfo=tz)
    day_end = day_start + timedelta(days=1)
    placeholders = ", ".join(f"${idx}" for idx in range(3, len(_ACTIVE_STATUSES) + 3))

    db = Prisma()
    await db.connect()
    try:
        rows = await db.query_raw(
            f"""
            SELECT id, phone, service, status, address, scheduled_window, notes,
                   scheduled_start, scheduled_end, city_bairro, customer_name,
                   source, priority, value_tier, job_type, owner_alerted_at, agenda_alerted_at
            FROM customer_services
            WHERE status IN ({placeholders})
              AND (
                (scheduled_start >= $1 AND scheduled_start < $2)
                OR scheduled_start IS NULL
              )
            ORDER BY scheduled_start ASC NULLS LAST, updated_at ASC
            """,
            day_start,
            day_end,
            *_ACTIVE_STATUSES,
        )
    except Exception as exc:
        logger.warning("Falha ao consultar agenda estruturada: %s", exc)
        legacy_placeholders = ", ".join(f"${idx}" for idx in range(1, len(_ACTIVE_STATUSES) + 1))
        rows = await db.query_raw(
            f"""
            SELECT id, phone, service, status, address, scheduled_window, notes
            FROM customer_services
            WHERE status IN ({legacy_placeholders})
            ORDER BY updated_at ASC
            """,
            *_ACTIVE_STATUSES,
        )
    finally:
        await db.disconnect()

    patterns = _target_day_patterns(target_date)
    services: list[dict[str, Any]] = []
    for row in rows:
        service = _row_to_service(row)
        if service["scheduled_start"]:
            services.append(service)
            continue
        window = service["scheduled_window"].lower()
        if window and any(pattern.lower() in window for pattern in patterns):
            services.append(service)
    return sorted(services, key=_sort_key)


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _sort_key(service: dict[str, Any]) -> tuple[int, str]:
    dt = _parse_dt(str(service.get("scheduled_start") or ""))
    if dt:
        return (0, dt.isoformat())
    return (1, str(service.get("scheduled_window") or service.get("customer_name") or service.get("phone") or ""))


def _date_title(target_date: date, kind: str) -> str:
    weekday = _WEEKDAYS[target_date.weekday()]
    label = "Amanhã" if kind == "night_tomorrow" else "Hoje" if kind == "morning_today" else target_date.strftime("%d/%m")
    return f"*Agenda Refrimix — {label} ({weekday}, {target_date.strftime('%d/%m')})*"


def _time_label(service: dict[str, Any]) -> str:
    start = _parse_dt(str(service.get("scheduled_start") or ""))
    end = _parse_dt(str(service.get("scheduled_end") or ""))
    if start and end:
        return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"
    if start:
        return start.strftime("%H:%M")
    return str(service.get("scheduled_window") or "Sem horário definido")


def _service_label(service: dict[str, Any]) -> str:
    return str(service.get("job_type") or service.get("service") or "Atendimento").replace("_", " ").strip().capitalize()


def _place_label(service: dict[str, Any]) -> str:
    city = str(service.get("city_bairro") or "").strip()
    address = str(service.get("address") or "").strip()
    if city and address:
        return f"{city} / {address}"
    return city or address or "não informado"


def _pending_items(services: list[dict[str, Any]]) -> list[str]:
    pending: list[str] = []
    for service in services:
        name = service.get("customer_name") or service.get("phone") or "cliente"
        if not service.get("scheduled_start"):
            pending.append(f"confirmar horário de {name}")
        if not service.get("address") and not service.get("city_bairro"):
            pending.append(f"confirmar endereço de {name}")
        notes = str(service.get("notes") or "").strip()
        if notes and re.search(r"\b(confirmar|levar|revisar|pendente|aguard)", notes, re.I):
            pending.append(notes[:120])
    return pending[:6]


def format_agenda_digest(target_date: date, services: list[dict[str, Any]], kind: str) -> str:
    title = _date_title(target_date, kind)
    if not services:
        label = "hoje" if kind == "morning_today" else "amanhã" if kind == "night_tomorrow" else "na data"
        return f"{title}\nNenhum atendimento estruturado para {label} no sistema."

    max_items = _env_int("AGENDA_DIGEST_MAX_ITEMS", 20)
    ordered = sorted(services, key=_sort_key)
    limited = ordered[:max_items]
    high_value_count = sum(1 for item in services if item.get("value_tier") == "high_ticket" or item.get("priority") in {"high", "urgent"})
    unscheduled_count = sum(1 for item in services if not item.get("scheduled_start"))
    pending = _pending_items(services)
    first = next((_time_label(item) for item in ordered if item.get("scheduled_start")), "a confirmar")

    if kind == "night_tomorrow":
        lines = [
            title,
            "Resumo para organizar antes de dormir:",
            "",
            f"• Atendimentos: {len(services)}",
            f"• Alto valor: {high_value_count}",
            f"• Sem horário definido: {unscheduled_count}",
            "",
        ]
    else:
        lines = [
            title,
            "Bom dia. Agenda operacional de hoje:",
            "",
            f"• Atendimentos: {len(services)}",
            f"• Primeiro horário: {first}",
            f"• Pendências: {len(pending)}",
            "",
        ]

    for idx, service in enumerate(limited, start=1):
        lines.extend(
            [
                f"{idx}) {_time_label(service)} — {_service_label(service)}",
                f"Cliente: {service.get('customer_name') or service.get('phone') or 'não informado'}",
                f"Local: {_place_label(service)}",
                f"Contato: {service.get('phone') or 'não informado'}",
                f"Status: {service.get('status') or 'não informado'}",
            ]
        )
        if service.get("priority") in {"high", "urgent"} or service.get("value_tier") == "high_ticket":
            lines.append("Prioridade: ALTA")
        if service.get("notes"):
            lines.append(f"Obs: {str(service['notes'])[:180]}")
        lines.append("")

    if len(services) > max_items:
        lines.append(f"Mais {len(services) - max_items} atendimento(s) não listados por limite do resumo.")
        lines.append("")

    footer_title = "Pendências:" if kind == "night_tomorrow" else "Antes de sair:"
    lines.append(footer_title)
    lines.extend([f"• {item}" for item in pending] or ["• Sem pendências registradas."])
    if high_value_count:
        lines.append("")
        lines.append("Atenção: lead alto valor separado foi enviado no privado do gerente quando aplicável.")

    message = "\n".join(lines).strip()
    if len(message) <= 3500:
        return message
    return message[:3400].rstrip() + "\n\nResumo limitado para caber no WhatsApp."


async def build_agenda_digest(target_date: date, kind: str) -> str:
    return format_agenda_digest(target_date, await get_services_for_day(target_date), kind)


async def send_agenda_digest(
    target_date: date,
    kind: str,
    force: bool = False,
    *,
    redis_client: Any | None = None,
    target: str = "group",
) -> dict[str, Any]:
    services = await get_services_for_day(target_date)
    message = format_agenda_digest(target_date, services, kind)
    group_jid = os.getenv("AGENDA_GROUP_JID", "").strip()
    group_enabled = os.getenv("AGENDA_GROUP_ENABLED", "1") == "1"

    lock_key = f"agenda_digest_sent:{kind}:{target_date.isoformat()}"
    if redis_client is not None and not force:
        ttl = _env_int("AGENDA_DIGEST_DEDUP_TTL_SECONDS", 90000)
        acquired = await redis_client.set(lock_key, "1", nx=True, ex=ttl)
        if not acquired:
            return {
                "sent": False,
                "deduped": True,
                "kind": kind,
                "target_date": target_date.isoformat(),
                "count": len(services),
                "group_jid_configured": bool(group_jid),
                "message": message,
            }

    sent = False
    if target == "preview":
        sent = False
    elif target == "owner":
        if os.getenv("OWNER_RECEIVE_AGENDA_DIGEST", "0") == "1":
            sent = await send_owner_alert({"title": "AGENDA REFRIMIX", "summary": message, "reason": "agenda_digest"})
    else:
        if not group_enabled:
            logger.info("AGENDA_GROUP_ENABLED=0; digest não enviado")
        elif not group_jid:
            logger.warning("AGENDA_GROUP_ENABLED=1, mas AGENDA_GROUP_JID está vazio; digest não enviado")
        else:
            sent = await send_agenda_group_message(message)

    if redis_client is not None and not sent and target != "preview":
        try:
            await redis_client.delete(lock_key)
        except Exception:
            pass

    return {
        "sent": sent,
        "kind": kind,
        "target_date": target_date.isoformat(),
        "count": len(services),
        "group_jid_configured": bool(group_jid),
        "message": message,
    }
