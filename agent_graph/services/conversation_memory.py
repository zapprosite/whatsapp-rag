from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def _json_value(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value


def _iso(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if value is not None else None


def _message_text(message: BaseMessage) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(part) for part in content)
    return str(content or "")


def _role(message: BaseMessage) -> str:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    return getattr(message, "type", "unknown")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


async def load_lead_profile(phone: str) -> dict[str, Any] | None:
    from prisma import Prisma

    db = Prisma()
    await db.connect()
    try:
        lead = await db.lead.find_unique(where={"phone": phone})
        if not lead:
            return None
        return {
            "lead_id": lead.id,
            "phone": lead.phone,
            "service_type": lead.service_type,
            "pipeline_stage": lead.pipeline_stage,
            "city_bairro": lead.city_bairro,
            "lead_state": _json_value(lead.lead_state, {}),
            "conversation_summary": lead.conversation_summary or "",
            "already_asked_fields": _json_value(lead.already_asked_fields, []),
            "missing_fields": _json_value(lead.missing_fields, []),
            "do_not_ask": _json_value(lead.do_not_ask, []),
            "last_user_message_at": _iso(lead.last_user_message_at),
            "created_at": _iso(lead.created_at),
            "updated_at": _iso(lead.updated_at),
        }
    finally:
        await db.disconnect()


async def load_recent_lead_events(phone: str, limit: int = 12) -> list[BaseMessage]:
    from prisma import Prisma

    db = Prisma()
    await db.connect()
    try:
        lead = await db.lead.find_unique(where={"phone": phone})
        if not lead:
            return []
        events = await db.leadevent.find_many(
            where={"lead_id": lead.id},
            order={"created_at": "desc"},
            take=limit,
        )
        messages: list[BaseMessage] = []
        for event in reversed(events):
            text = str(event.message or "").strip()
            if not text:
                continue
            if event.role == "user":
                messages.append(HumanMessage(content=text))
            elif event.role == "assistant":
                messages.append(AIMessage(content=text))
        return messages
    finally:
        await db.disconnect()


def _dedupe_merge(messages: list[BaseMessage]) -> list[BaseMessage]:
    merged: list[BaseMessage] = []
    seen: set[tuple[str, str]] = set()
    for message in messages:
        text = _message_text(message).strip()
        if not text:
            continue
        key = (_role(message), _norm(text))
        if key in seen:
            continue
        seen.add(key)
        merged.append(message)
    return merged


def _has_lead_state(profile: dict[str, Any] | None) -> bool:
    if not profile:
        return False
    lead_state = profile.get("lead_state") or {}
    return bool(
        lead_state
        or profile.get("service_type")
        or profile.get("conversation_summary")
        or profile.get("city_bairro")
    )


async def build_canonical_history(
    phone: str,
    redis_history: list[BaseMessage],
) -> tuple[list[BaseMessage], dict[str, Any]]:
    profile = await load_lead_profile(phone)
    postgres_history = await load_recent_lead_events(phone)
    postgres_count = len(postgres_history)
    has_persistent_lead = _has_lead_state(profile) or postgres_count > 0

    if redis_history and not postgres_history:
        history = redis_history
        source = "redis"
    elif not redis_history and postgres_history:
        history = postgres_history
        source = "postgres"
    elif redis_history and postgres_history:
        if len(postgres_history) > len(redis_history):
            history = _dedupe_merge(postgres_history + redis_history)
            source = "merged"
        else:
            history = _dedupe_merge(redis_history + postgres_history)
            source = "merged" if len(history) != len(redis_history) else "redis"
    else:
        history = []
        source = "none"

    metadata = {
        "history_source": source,
        "is_conversation_started": bool(history) or has_persistent_lead,
        "has_persistent_lead": has_persistent_lead,
        "postgres_event_count": postgres_count,
    }
    return history, metadata
