from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from prisma import Prisma

from agent_graph.nodes.nodes import _lead_state_copy, sanitize_lead_state

_COLUMN_CACHE: dict[str, set[str]] = {}
_JSONB_COLUMNS = {"lead_state", "already_asked_fields", "missing_fields", "do_not_ask", "extracted_data", "metadata"}
_TIMESTAMP_COLUMNS = {"created_at", "updated_at", "last_user_message_at"}


def _placeholder(index: int, column: str) -> str:
    if column in _JSONB_COLUMNS:
        return f"${index}::jsonb"
    if column in _TIMESTAMP_COLUMNS:
        return f"${index}::timestamp"
    return f"${index}"


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _table_columns(db: Prisma, table_name: str) -> set[str]:
    cached = _COLUMN_CACHE.get(table_name)
    if cached is not None:
        return cached

    rows = await db.query_raw(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = $1
        """,
        table_name,
    )
    columns = {str(row.get("column_name")) for row in rows or [] if row.get("column_name")}
    _COLUMN_CACHE[table_name] = columns
    return columns


def _default_lead_state(phone: str, name: str | None = None) -> dict[str, Any]:
    lead_state = sanitize_lead_state(_lead_state_copy())
    identity = lead_state.setdefault("lead_identity", {})
    identity["phone"] = phone
    if name:
        parts = name.split()
        lead_state["nome"] = name
        identity["full_name"] = name
        identity["first_name"] = parts[0] if parts else None
        identity["last_name"] = " ".join(parts[1:]) if len(parts) > 1 else None
        identity["identity_status"] = "identified"
    else:
        identity["identity_status"] = "missing_name"
    return lead_state


def _normalize_loaded_lead(row: dict[str, Any], columns: set[str], phone: str) -> dict[str, Any]:
    raw_name = row.get("name")
    lead_state = _json_value(row.get("lead_state"), _default_lead_state(phone, raw_name))
    if not isinstance(lead_state, dict) or not lead_state:
        lead_state = _default_lead_state(phone, raw_name)
    lead_state = sanitize_lead_state(lead_state)
    identity = lead_state.setdefault("lead_identity", {})
    identity["phone"] = phone
    if raw_name and not lead_state.get("nome"):
        lead_state["nome"] = raw_name
    if raw_name and not identity.get("full_name"):
        parts = str(raw_name).split()
        identity["full_name"] = raw_name
        identity["first_name"] = parts[0] if parts else None
        identity["last_name"] = " ".join(parts[1:]) if len(parts) > 1 else None
    identity["identity_status"] = "identified" if identity.get("full_name") else "missing_name"
    return {
        "id": str(row.get("id") or ""),
        "phone": str(row.get("phone") or phone),
        "name": raw_name,
        "service_type": row.get("service_type") or row.get("service"),
        "pipeline_stage": row.get("pipeline_stage") or "new",
        "city_bairro": row.get("city_bairro"),
        "lead_state": lead_state,
        "event_count": int(row.get("event_count") or 0),
        "available_columns": columns,
    }


async def prisma_healthcheck() -> dict[str, str]:
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL ausente")

    db = Prisma()
    await db.connect()
    try:
        await db.query_raw("SELECT 1 AS ok")
        await _table_columns(db, "leads")
    finally:
        await db.disconnect()
    return {"postgres": "up", "prisma": "up"}


async def load_or_create_lead(phone: str, name: str | None = None) -> dict[str, Any]:
    db = Prisma()
    await db.connect()
    try:
        return await _load_or_create_lead_with_db(db, phone, name=name)
    finally:
        await db.disconnect()


async def _load_or_create_lead_with_db(db: Prisma, phone: str, name: str | None = None) -> dict[str, Any]:
    columns = await _table_columns(db, "leads")
    select_columns = [
        column
        for column in ("id", "phone", "name", "service", "service_type", "pipeline_stage", "city_bairro", "lead_state")
        if column in columns
    ]
    if "id" not in select_columns or "phone" not in select_columns:
        raise RuntimeError("Tabela leads sem colunas mínimas esperadas")

    rows = await db.query_raw(
        f"SELECT {', '.join(select_columns)} FROM leads WHERE phone = $1 LIMIT 1",
        phone,
    )
    row = rows[0] if rows else None
    if not row:
        now = _utcnow()
        insert_columns: list[str] = ["id", "phone"]
        insert_values: list[Any] = [str(uuid.uuid4()), phone]
        lead_state = _default_lead_state(phone, name)
        defaults: dict[str, Any] = {
            "name": name,
            "source": "whatsapp",
            "service": None,
            "service_type": None,
            "pipeline_stage": "new",
            "city_bairro": None,
            "lead_status": "open",
            "lead_state": json.dumps(lead_state, ensure_ascii=False),
            "already_asked_fields": json.dumps([], ensure_ascii=False),
            "missing_fields": json.dumps(["tipo_servico"], ensure_ascii=False),
            "do_not_ask": json.dumps([], ensure_ascii=False),
            "conversation_summary": None,
            "last_user_message_at": None,
            "created_at": now,
            "updated_at": now,
        }
        for column, value in defaults.items():
            if column in columns:
                insert_columns.append(column)
                insert_values.append(value)

        placeholders = ", ".join(_placeholder(index, column) for index, column in enumerate(insert_columns, start=1))
        rows = await db.query_raw(
            f"INSERT INTO leads ({', '.join(insert_columns)}) VALUES ({placeholders}) RETURNING {', '.join(select_columns)}",
            *insert_values,
        )
        row = rows[0]

    event_count = 0
    event_columns = await _table_columns(db, "lead_events")
    if event_columns >= {"id", "lead_id"}:
        count_rows = await db.query_raw(
            "SELECT COUNT(*)::int AS count FROM lead_events WHERE lead_id = $1",
            str(row.get("id") or ""),
        )
        event_count = int((count_rows or [{}])[0].get("count") or 0)

    normalized = _normalize_loaded_lead({**row, "event_count": event_count}, columns, phone)
    if name and not normalized["name"]:
        normalized["name"] = name
    return normalized


async def update_lead_state(
    phone: str,
    lead_state: dict[str, Any],
    *,
    pipeline_stage: str,
    service_type: str | None,
    city_bairro: str | None = None,
) -> None:
    db = Prisma()
    await db.connect()
    try:
        await _load_or_create_lead_with_db(db, phone)
        columns = await _table_columns(db, "leads")
        now = _utcnow()
        updates: dict[str, Any] = {
            "lead_state": json.dumps(sanitize_lead_state(lead_state), ensure_ascii=False),
            "name": lead_state.get("nome"),
            "service": service_type,
            "service_type": service_type,
            "pipeline_stage": pipeline_stage,
            "city_bairro": city_bairro or lead_state.get("cidade_bairro"),
            "already_asked_fields": json.dumps([], ensure_ascii=False),
            "missing_fields": json.dumps([], ensure_ascii=False),
            "do_not_ask": json.dumps([], ensure_ascii=False),
            "last_user_message_at": now,
            "updated_at": now,
        }
        set_parts: list[str] = []
        values: list[Any] = []
        next_index = 1
        for column, value in updates.items():
            if column not in columns:
                continue
            set_parts.append(f"{column} = {_placeholder(next_index, column)}")
            values.append(value)
            next_index += 1

        if not set_parts:
            return

        values.append(phone)
        await db.execute_raw(
            f"UPDATE leads SET {', '.join(set_parts)} WHERE phone = ${next_index}",
            *values,
        )
    finally:
        await db.disconnect()


async def create_lead_event(phone: str, role: str, message: str, extracted_data: dict[str, Any] | None = None) -> None:
    db = Prisma()
    await db.connect()
    try:
        lead = await _load_or_create_lead_with_db(db, phone)
        columns = await _table_columns(db, "lead_events")
        if not {"id", "lead_id", "role", "message"}.issubset(columns):
            return

        insert_columns = ["id", "lead_id", "role", "message"]
        insert_values: list[Any] = [str(uuid.uuid4()), lead["id"], role, message]
        if "extracted_data" in columns:
            insert_columns.append("extracted_data")
            insert_values.append(json.dumps(extracted_data or {}, ensure_ascii=False))
        if "created_at" in columns:
            insert_columns.append("created_at")
            insert_values.append(_utcnow())
        placeholders = ", ".join(_placeholder(index, column) for index, column in enumerate(insert_columns, start=1))
        await db.query_raw(
            f"INSERT INTO lead_events ({', '.join(insert_columns)}) VALUES ({placeholders}) RETURNING id",
            *insert_values,
        )
    finally:
        await db.disconnect()
