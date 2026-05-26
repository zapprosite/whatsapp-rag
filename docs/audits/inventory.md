# CLEAN REPO EXTRACTION INVENTORY
Generated: 2026-05-26T12:47:17.806219

## SOURCE
Branch: feature/proxima-tarefa-20260526
Commit: 952c24e1
Message: reversa: fase0 20260526-124506

## CORE_KEEP
### Obrigatórios
- refrimix_core/ (todo)
- app/main.py, app/runtime.py, app/worker.py
- app/api/webhook.py, app/api/health.py, app/api/test_routes.py
- prisma/schema.prisma
- docker-compose.yml, app/Dockerfile
- requirements.txt ou pyproject.toml

### Estrutura app/
- app/agenda_scheduler.py
- app/api/bot.py
- app/api/health.py
- app/api/__init__.py
- app/api/test_routes.py
- app/api/webhook.py
- app/config/__init__.py
- app/config/settings.py
- app/__init__.py
- app/lead_repository.py
- app/main.py
- app/mvp_attendance.py
- app/runtime.py
- app/worker.py

### Estrutura refrimix_core/
- refrimix_core/config/__init__.py
- refrimix_core/config/settings.py
- refrimix_core/domain/commercial_router.py
- refrimix_core/domain/__init__.py
- refrimix_core/domain/pipeline.py
- refrimix_core/domain/response_catalog.py
- refrimix_core/domain/text_normalizer.py
- refrimix_core/domain/types.py
- refrimix_core/guards/__init__.py
- refrimix_core/guards/language_guard.py
- refrimix_core/__init__.py
- refrimix_core/integrations/__init__.py
- refrimix_core/nodes/__init__.py
- refrimix_core/nodes/plan_next_action.py
- refrimix_core/nodes/reduce_lead_state.py
- refrimix_core/nodes/understand_message.py

## COPY_OPTIONAL
- scripts/reset-lead.py
- scripts/smoke-v2.sh
- scripts/env-vault.sh
- docs/reversa/
- .context/docs/

## DO_NOT_COPY
- agent_graph/ (LEGAcy DEBT)
- orcamento_teste.pdf (LEGAcy DEBT)

## Docker services
evolution-api
fastapi-rag
evolution_instances
evolution-data

## Key imports

app/main.py:
  from __future__ import annotations
  import logging
  from pathlib import Path
  from dotenv import load_dotenv
  from fastapi import FastAPI
  from runtime import lifespan
  from api.bot import router as bot_router
  from api.health import router as health_router
  from api.test_routes import router as test_router
  from api.webhook import router as webhook_router

app/worker.py:
  from __future__ import annotations
  import asyncio
  import json
  import logging
  import os
  import random
  import re
  import uuid
  from contextlib import asynccontextmanager, suppress
  from datetime import datetime
  from typing import Any
  import httpx
  import redis.asyncio as redis
  from fastapi import FastAPI
  from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

app/api/webhook.py:
  from __future__ import annotations
  import asyncio
  import json
  import logging
  import os
  import re
  from dataclasses import dataclass
  from typing import Any
  from fastapi import APIRouter, HTTPException, Request
  from fastapi.responses import JSONResponse
  from runtime import get_redis, normalize_whatsapp_number, queue_key, send_whatsapp_message, set_manual_takeover
  from app.runtime import get_redis, normalize_whatsapp_number, queue_key, send_whatsapp_message, set_manual_takeover

app/api/health.py:
  from __future__ import annotations
  import os
  from typing import Any
  from fastapi import APIRouter
  from runtime import get_redis
  from app.runtime import get_redis
  from runtime import get_redis
  from app.runtime import get_redis

refrimix_core/domain/pipeline.py:
  from __future__ import annotations
  import hashlib
  import logging
  from typing import Any
  from refrimix_core.domain.commercial_router import decide_commercial_path
  from refrimix_core.domain.response_catalog import get_response
  from refrimix_core.domain.text_normalizer import fold
  from refrimix_core.nodes.understand_message import understand_message
  from refrimix_core.nodes.reduce_lead_state import reduce_lead_state
  from refrimix_core.nodes.plan_next_action import plan_next_action
  from refrimix_core.guards.language_guard import guard, validate

## Env vars used
- DATABASE_URL: str = ""
- EVOLUTION_API_KEY: str = ""
- EVOLUTION_API_URL: str = "http://localhost:8080"
- EVOLUTION_INSTANCE: str = "default"
- _ADMIN_TEST_PHONE = normalize_whatsapp_number(os.getenv("OWNER_PHONE", "")) or normalize_whatsapp_nu
- _BOT_OFF_MSG = os.getenv(
- _CONV_MAX_TURNS = int(os.getenv("CONV_MAX_TURNS", "6"))
- _CONV_TTL = int(os.getenv("CONV_TTL_SECONDS", "1800"))
- _DLQ_KEY = os.getenv("WHATSAPP_DLQ_KEY", "whatsapp_rag:dead_letter")
- _GRAPH_TIMEOUT = float(os.getenv("GRAPH_RESPONSE_TIMEOUT_SECONDS", "45"))
- _HANDOFF_ALERT_TTL = int(os.getenv("HANDOFF_ALERT_TTL_SECONDS", "21600"))
- _LOCK_REQUEUE_DELAY = float(os.getenv("CONV_LOCK_REQUEUE_DELAY_SECONDS", "0.4"))
- _LOCK_TTL = int(os.getenv("CONV_LOCK_TTL_SECONDS", "240"))
- _LOCK_WAIT = float(os.getenv("CONV_LOCK_WAIT_SECONDS", "20"))
- _MANUAL_TAKEOVER_TTL = int(os.getenv("MANUAL_TAKEOVER_TTL_SECONDS", "86400"))
- _MAX_ATTEMPTS = max(1, int(os.getenv("WORKER_MAX_ATTEMPTS", "3")))
- _MESSAGE_TIMEOUT = float(os.getenv("WORKER_MESSAGE_TIMEOUT_SECONDS", "180"))
- _OWNER_ALERT_TTL = int(os.getenv("OWNER_ALERT_DEDUP_TTL_SECONDS", "21600"))
- _PROCESSING_KEY = os.getenv("WHATSAPP_PROCESSING_QUEUE_KEY", "whatsapp_rag:processing")
- _QUEUE_KEY = os.getenv("WHATSAPP_QUEUE_KEY", "whatsapp_rag:queue")
- _QUEUE_POP_TIMEOUT = int(os.getenv("WORKER_QUEUE_POP_TIMEOUT_SECONDS", "5"))
- _REFRIMIX_CORE_VERSION = os.getenv("REFRIMIX_CORE_VERSION", "legacy")
- _WEBHOOK_REDIS_TIMEOUT = float(os.getenv("WEBHOOK_REDIS_TIMEOUT_SECONDS", "3.0"))
- _WORKER_COUNT = max(1, int(os.getenv("WORKER_CONCURRENCY", "4")))
- _WORKER_HEARTBEAT_TTL = max(30, int(os.getenv("WORKER_HEARTBEAT_TTL_SECONDS", "30")))

## Rollback
- SOURCE intacto
- evolution_api banco intocado
- voice_embeddings Qdrant preservado
- Evolution token/URL inalterado
