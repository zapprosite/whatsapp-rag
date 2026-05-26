from __future__ import annotations

import asyncio
import logging
import os
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from agent_graph.services.agenda_digest import send_agenda_digest

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _enabled() -> bool:
    return os.getenv("AGENDA_GROUP_ENABLED", "1") == "1"


def _timezone() -> ZoneInfo:
    return ZoneInfo(os.getenv("AGENDA_GROUP_DIGEST_TIMEZONE", "America/Sao_Paulo"))


async def try_send_digest(kind: str, target_date, r: Any) -> dict[str, Any]:
    key = f"agenda_digest_lock:{kind}:{target_date.isoformat()}"
    ttl = _env_int("AGENDA_DIGEST_DEDUP_TTL_SECONDS", 90000)
    acquired = await r.set(key, "1", nx=True, ex=ttl)
    if not acquired:
        logger.info("Digest já processado: %s", key)
        return {"sent": False, "deduped": True, "kind": kind, "target_date": target_date.isoformat()}

    result = await send_agenda_digest(target_date, kind, force=True)
    if not result.get("sent"):
        with suppress(Exception):
            await r.delete(key)
    return result


def _next_run(now: datetime) -> tuple[str, datetime]:
    morning = now.replace(
        hour=_env_int("AGENDA_GROUP_MORNING_DIGEST_HOUR", 7),
        minute=_env_int("AGENDA_GROUP_MORNING_DIGEST_MINUTE", 0),
        second=0,
        microsecond=0,
    )
    night = now.replace(
        hour=_env_int("AGENDA_GROUP_NIGHT_DIGEST_HOUR", 20),
        minute=_env_int("AGENDA_GROUP_NIGHT_DIGEST_MINUTE", 0),
        second=0,
        microsecond=0,
    )
    candidates = [
        ("morning_today", morning if morning > now else morning + timedelta(days=1)),
        ("night_tomorrow", night if night > now else night + timedelta(days=1)),
    ]
    return min(candidates, key=lambda item: item[1])


async def maybe_send_scheduled_digest(r: Any) -> dict[str, Any] | None:
    if not _enabled():
        return None
    now = datetime.now(_timezone())
    kind, run_at = _next_run(now - timedelta(seconds=1))
    if abs((run_at - now).total_seconds()) > 35:
        return None
    target_date = now.date() if kind == "morning_today" else now.date() + timedelta(days=1)
    return await try_send_digest(kind, target_date, r)


async def agenda_digest_loop(worker_id: int = 0, redis_getter=None) -> None:
    if not _enabled():
        logger.info("AGENDA_GROUP_ENABLED=0; scheduler de agenda não iniciado")
        return

    while True:
        try:
            now = datetime.now(_timezone())
            kind, run_at = _next_run(now)
            sleep_seconds = max(1.0, min((run_at - now).total_seconds(), 3600.0))
            await asyncio.sleep(sleep_seconds)

            r = await redis_getter() if redis_getter is not None else None
            if r is None:
                continue
            target_date = run_at.date() if kind == "morning_today" else run_at.date() + timedelta(days=1)
            await try_send_digest(kind, target_date, r)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Scheduler de agenda falhou: %s", exc)
            await asyncio.sleep(30)
