from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

try:
    from runtime import get_redis
except ModuleNotFoundError:
    from app.runtime import get_redis

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, Any]:
    status: dict[str, str] = {"status": "ok"}

    try:
        r = await get_redis()
        await r.ping()
        status["redis"] = "up"
    except Exception as e:
        status["redis"] = f"down: {e}"

    try:
        from qdrant_client import QdrantClient

        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        qc = QdrantClient(url=qdrant_url)
        qc.get_collections()
        status["qdrant"] = "up"
    except Exception as e:
        status["qdrant"] = f"down: {e}"

    status["langgraph"] = "up"
    status["worker"] = "running"
    return status


@router.get("/")
async def root() -> dict[str, str]:
    return {"service": "Refrimix WhatsApp RAG", "version": "1.0.0"}
