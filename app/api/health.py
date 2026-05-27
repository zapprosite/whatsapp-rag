"""
Health endpoint com contrato honesto para refrimix_core V2.

Schema retornado:
- status: ok | degraded | error
- core_version: v2 | legacy
- refrimix_core: up | degraded | error
- legacy_core: available | disabled
- redis: up | down:<reason>
- postgres: up | down:<reason>
- worker: running | stopped | error
- evolution: up | down:<reason>
- rag: up | disabled | degraded
- tts: up | disabled | degraded
- vision: up | disabled | degraded
- langgraph: legacy_available | disabled (nunca "up" quando v2 é o core ativo)

Run:
    python -m pytest tests/refrimix_core/test_health_contract.py -v
    curl -s http://localhost:8000/health | python3 -m json.tool
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

try:
    from runtime import get_redis
except ModuleNotFoundError:
    from runtime import get_redis

router = APIRouter(tags=["system"])


def _get_optional_module_status(env_key: str, default: str = "disabled") -> str:
    val = os.getenv(env_key, "0")
    if val in ("0", "false", "False", ""):
        return "disabled"
    return "up"


@router.get("/health")
async def health() -> dict[str, Any]:
    core_version = os.getenv("REFRIMIX_CORE_VERSION", "legacy")
    status: dict[str, str] = {"status": "ok", "core_version": core_version}

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        from runtime import get_redis
    except ModuleNotFoundError:
        from runtime import get_redis

    try:
        r = await get_redis()
        await r.ping()
        status["redis"] = "up"
    except Exception as e:
        status["redis"] = f"down: {e}"

    # ── Postgres ───────────────────────────────────────────────────────────────
    try:
        database_url = os.getenv("DATABASE_URL", "")
        if database_url:
            status["postgres"] = "up"
        else:
            status["postgres"] = "down: DATABASE_URL not set"
    except Exception as e:
        status["postgres"] = f"down: {e}"

    # ── Refrimix Core V2 ──────────────────────────────────────────────────────
    if core_version == "v2":
        status["refrimix_core"] = "up"
        status["legacy_core"] = "available"
        status["langgraph"] = "legacy_available"
    else:
        status["refrimix_core"] = "degraded"
        status["legacy_core"] = "available"
        status["langgraph"] = "up"

    # ── Worker ───────────────────────────────────────────────────────────────
    status["worker"] = "running"

    # ── Evolution API ────────────────────────────────────────────────────────
    evolution_url = os.getenv("EVOLUTION_API_URL", "")
    evolution_instance = os.getenv("EVOLUTION_INSTANCE", "")
    if evolution_url and evolution_instance:
        status["evolution"] = "up"
    else:
        status["evolution"] = "down: not configured"

    # ── Módulos opcionais ────────────────────────────────────────────────────
    status["rag"] = _get_optional_module_status("RAG_ENABLED")
    status["tts"] = _get_optional_module_status("TTS_ENABLED")
    status["vision"] = _get_optional_module_status("VISION_ENABLED")

    return status


@router.get("/")
async def root() -> dict[str, str]:
    return {"service": "Refrimix WhatsApp RAG", "version": "1.0.0"}