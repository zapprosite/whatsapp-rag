from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv(Path(__file__).parent.parent / ".env")

from runtime import lifespan
from api.bot import router as bot_router
from api.health import router as health_router
from api.test_routes import router as test_router
from api.webhook import router as webhook_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Refrimix WhatsApp RAG", version="1.0.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(bot_router)
app.include_router(webhook_router)
app.include_router(test_router)
