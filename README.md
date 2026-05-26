# WhatsApp RAG — Refrimix Core v2 (Clean)

Repositório limpo do bot WhatsApp da Refrimix HVAC-R Brasil.
Pipeline determinístico v2 (sem LLM no caminho crítico).

## Arquitetura

```
User → WhatsApp → Evolution API → FastAPI (refrimix_core v2) → Redis Queue → Worker → Prisma/Postgres
                              ↓
                    Evolution API (sendText)
                              ↓
                         WhatsApp User
```

## Stack

- **FastAPI** — API server
- **Refrimix Core v2** — deterministic pipeline (intent → routing → response)
- **Prisma** — ORM Postgres
- **Redis** — fila assíncrona
- **Evolution API** — integração WhatsApp
- **PostgreSQL** — banco de leads e interações

## Flags de Feature

| Flag | Default | Descrição |
|------|---------|-----------|
| `REFRIMIX_CORE_VERSION=v2` | ✅ v2 | Usa pipeline determinístico |
| `MINIMAL_MVP_ENABLED=1` | ✅ 1 | Desabilita LangGraph do path crítico |
| `RAG_ENABLED=0` | ✅ 0 | Qdrant desabilitado por padrão |
| `TTS_ENABLED=0` | ✅ 0 | TTS desabilitado por padrão |
| `VISION_ENABLED=0` | ✅ 0 | Vision desabilitado por padrão |

## Quick Start

```bash
# 1. Copiar .env
cp .env.example .env
# Preencher .env com valores reais

# 2. Build
docker compose build

# 3. Up
docker compose up -d

# 4. Health
curl http://localhost:8000/health | python3 -m json.tool
```

## Health Endpoint

```json
{
  "status": "ok",
  "core_version": "v2",
  "redis": "up",
  "postgres": "up",
  "refrimix_core": "up",
  "legacy_core": "available",
  "langgraph": "legacy_available",
  "worker": "running",
  "evolution": "up",
  "rag": "disabled",
  "tts": "disabled",
  "vision": "disabled"
}
```

## Smoke Tests

```bash
# Testar intent classification
curl -X POST "http://localhost:8000/test/chat?message=Bom+dia&send=false"
curl -X POST "http://localhost:8000/test/chat?message=Quais+serviços+oferecem%3F&send=false"
curl -X POST "http://localhost:8000/test/chat?message=Preciso+higienização&send=false"
curl -X POST "http://localhost:8000/test/chat?message=Meu+ar+não+gela&send=false"
curl -X POST "http://localhost:8000/test/chat?message=Preciso+VRF+restaurante&send=false"
```

Esperado: intent correto, sem CJK/árabe, R$ preservado, rag=0.

## Estrutura

```
app/
  main.py          — FastAPI app
  runtime.py       — lifespan (Redis, Postgres, Worker)
  worker.py        — background queue processor
  mvp_attendance.py — MINIMAL_MVP path (v2 core)
  lead_repository.py — Prisma ORM
  api/
    webhook.py     — Evolution webhook receiver
    health.py      — health endpoint
    test_routes.py — smoke test endpoint
refrimix_core/     — v2 deterministic pipeline
  domain/
    pipeline.py    — intent → routing → response
    commercial_router.py — R$850/R$200/R$50 rules
    response_catalog.py — response templates
    text_normalizer.py — PT-BR normalization
  nodes/
    understand_message.py
    reduce_lead_state.py
    plan_next_action.py
  guards/
    language_guard.py — block CJK/árabe/cirílico
prisma/schema.prisma — DB schema
agent_graph/       — legacy LangGraph (para MINIMAL_MVP=0)
```

## Rollback

```bash
# Parar clean
docker compose down

# Voltar pro antigo (se repo antigo existir)
cd /home/will/whatsapp-rag
docker compose up -d
```

## Prune do Repo Antigo

Ver `docs/operations/prune-old-repo.md` — só fazer quando clean estiver
respondendo WhatsApp real há 24-72h sem incidentes.