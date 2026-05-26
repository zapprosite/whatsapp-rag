# docs/architecture.md

# Arquitetura — WhatsApp RAG Clean (Refrimix Core v2)

## Visão Geral

```
WhatsApp User
     ↓
Evolution API (webhook POST /webhook)
     ↓
FastAPI (app/api/webhook.py) — recebe payload
     ↓
Redis Queue (LPUSH whatsapp_rag:queue)
     ↓
Worker (app/worker.py) — processa em background
     ↓
Pipeline v2 (refrimix_core/domain/pipeline.py)
     ↓ (se MINIMAL_MVP_ENABLED=1)
     ↓ (se MINIMAL_MVP_ENABLED=0)
     ↓
Lead Repository (Prisma → Postgres whatsapp_rag)
     ↓
Send Message (Evolution API sendText)
     ↓
WhatsApp User
```

## Pipeline v2 (Determinístico)

### Fluxo

1. **Understand Message** (`refrimix_core/nodes/understand_message.py`)
   - Classifica intent via regex patterns
   - Extrai phone, text, history

2. **Reduce Lead State** (`refrimix_core/nodes/reduce_lead_state.py`)
   - Atualiza lead_state com extracted data
   - Mantém pipeline_stage

3. **Plan Next Action** (`refrimix_core/nodes/plan_next_action.py`)
   - Decide próximo estado do pipeline
   - Avalia campos faltantes

4. **Commercial Router** (`refrimix_core/domain/commercial_router.py`)
   - Determina pricing
   - Aplica regras R$850/R$200/R$50

5. **Response Catalog** (`refrimix_core/domain/response_catalog.py`)
   - Gera resposta em PT-BR
   - Blinda contra CJK/árabe/cirílico

### Intent Mapping

| Mensagem | Intent |
|----------|--------|
| "bom dia" / "ola" | `welcome_onboarding` |
| "quais serviços" | `answer_services_list` |
| "instalação" / "instalar" | `offer_fixed_installation` |
| "higienização" | `offer_fixed_hygienization` |
| "manutenção" / "não gela" | `offer_technical_visit_maintenance` |
| "VRF" / "restaurante" / "alto padrão" | `offer_project_visit` |
| "1" (resposta numérica) | `respond_service_quantity` |
| nome válido | `onboarding_name_collected` |

### Preços (Commercial Router)

- **R$850** — instalação simples (até 3m, acesso fácil, com material)
- **R$200** — higienização por aparelho
- **R$50** — visita técnica/análise (abativel no orçamento)
- **Custom** — VRF, projeto, alto padrão → `offer_project_visit`

## Estrutura de Diretórios

```
whatsapp-rag-clean/
├── app/
│   ├── main.py              # FastAPI app entrypoint
│   ├── runtime.py           # Lifespan manager (Redis, Postgres, Worker)
│   ├── worker.py           # Background queue processor
│   ├── mvp_attendance.py   # MINIMAL_MVP path (v2 core)
│   ├── lead_repository.py   # Prisma ORM
│   ├── agenda_scheduler.py  # (desabilitado por padrão)
│   ├── api/
│   │   ├── webhook.py      # Evolution webhook receiver
│   │   ├── health.py       # Health endpoint
│   │   ├── test_routes.py  # Smoke test endpoint
│   │   └── bot.py          # Bot router
│   └── config/
│       └── settings.py     # Pydantic settings
│
├── refrimix_core/           # v2 deterministic pipeline
│   ├── domain/
│   │   ├── pipeline.py     # Orchestrator (intent → response)
│   │   ├── commercial_router.py  # Pricing rules
│   │   ├── response_catalog.py  # Response templates
│   │   ├── text_normalizer.py   # PT-BR normalization
│   │   └── types.py        # Pydantic models
│   ├── nodes/
│   │   ├── understand_message.py  # Intent classification
│   │   ├── reduce_lead_state.py   # State update
│   │   └── plan_next_action.py    # Next action planning
│   ├── guards/
│   │   └── language_guard.py  # Block CJK/árabe/cirílico
│   └── config/
│       └── settings.py     # Core settings
│
├── prisma/
│   └── schema.prisma       # DB schema (leads, interactions, lead_events)
│
├── agent_graph/            # LEGACY (LangGraph) — só ativo se MINIMAL_MVP_ENABLED=0
│   ├── nodes/             # _lead_state_copy, sanitize_lead_state
│   ├── domain/           # onboarding, commercial_router (v1)
│   ├── graph/graph.py    # build_graph()
│   └── services/
│       ├── whatsapp.py   # Evolution API client
│       └── alerts.py     # Owner alerts
│
├── knowledge/             # RAG knowledge base (desabilitado por padrão)
│   └── refrimix/
│       └── docs/         # Markdown docs
│
├── qdrant/                # Qdrant seeding (desabilitado por padrão)
│   └── refrimix_ambiguity_cases.jsonl
│
└── tests/
    └── refrimix_core/     # Core v2 tests
```

## Variáveis de Ambiente

Ver `.env.schema.md` para documentação completa.

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `REFRIMIX_CORE_VERSION` | `v2` | Pipeline v2 vs legacy |
| `MINIMAL_MVP_ENABLED` | `1` | Desabilita LangGraph |
| `DATABASE_URL` | — | Postgres connection |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `RAG_ENABLED` | `0` | Qdrant RAG |
| `TTS_ENABLED` | `0` | TTS |
| `VISION_ENABLED` | `0` | Vision |
| `EVOLUTION_API_URL` | — | Evolution API base |
| `EVOLUTION_INSTANCE` | — | Instance name |
| `EVOLUTION_API_KEY` | — | API key |

## Fluxo de Dados

### Mensagem Recebida (Webhook)

```
Evolution API → POST /webhook
  → webhook.py: parse_message()
  → worker.py: enqueue()
  → Redis: LPUSH whatsapp_rag:queue

Worker (background):
  → BRPOP whatsapp_rag:queue
  → MINIMAL_MVP_ENABLED=1 → process_mvp_message()
  → pipeline.understand_message()
  → pipeline.reduce_lead_state()
  → pipeline.plan_next_action()
  → commercial_router.decide_commercial_path()
  → response_catalog.get_response()
  → Prisma: update_lead(), create_lead_event()
  → Evolution API: sendText()
```

### Lead State

```json
{
  "phone": "5511999999999",
  "tipo_servico": "higienizacao",
  "nome": "João",
  "cidade_bairro": "São Paulo, Pinheiros",
  "pipeline_stage": "qualified",
  "last_messages": {
    "assistant": "Higienização de split padrão...",
    "user": "Preciso fazer uma higienização"
  },
  "event_count": 5
}
```

## Integrações Externas

| Serviço | Connection | Purpose |
|---------|------------|---------|
| Evolution API | `EVOLUTION_API_URL` | WhatsApp webhook + sendText |
| PostgreSQL | `DATABASE_URL` | Leads, interactions |
| Redis | `REDIS_URL` | Queue, manual_takeover |
| Qdrant | `QDRANT_URL` | RAG embeddings (disabled) |

## Security

- `.env` nunca commitado
- `EVOLUTION_API_KEY` em vault
- `MINIMAX_API_KEY` em vault
- Hardcoded IPs proibidos (100.66.x.x, 192.168.x.x)