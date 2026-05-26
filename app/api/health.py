from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Response

try:
    from runtime import get_redis, postgres_status, worker_heartbeat_status
except ModuleNotFoundError:
    from app.runtime import get_redis, postgres_status, worker_heartbeat_status

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(response: Response) -> dict[str, Any]:
    status: dict[str, Any] = {"status": "ok"}
    failed = False

    try:
        r = await get_redis()
        await r.ping()
        status["redis"] = "up"
    except Exception as e:
        status["redis"] = f"down: {e}"
        failed = True

    try:
        status.update(await postgres_status())
    except Exception as e:
        status["postgres"] = f"down: {e}"
        status["prisma"] = "down"
        failed = True

    try:
        r = await get_redis()
        heartbeat = await worker_heartbeat_status(r)
        status["worker"] = heartbeat
        if heartbeat.get("status") != "up":
            failed = True
    except Exception as e:
        status["worker"] = {"status": "down", "reason": str(e)}
        failed = True

    status["langgraph"] = "disabled" if os.getenv("MINIMAL_MVP_ENABLED", "0") == "1" else "up"
    if failed:
        status["status"] = "degraded"
        response.status_code = 503
    return status


@router.get("/")
async def root() -> dict[str, str]:
    return {"service": "Refrimix WhatsApp RAG", "version": "1.0.0"}
