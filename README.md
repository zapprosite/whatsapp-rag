# WhatsApp RAG Lead — Refrimix

Bot WhatsApp para onboarding e atendimento a leads da Refrimix Tecnologia usando RAG (Retrieval-Augmented Generation).

## Arquitetura

```
[WhatsApp] → [Evolution API Docker :8080]
                  ↓ webhook POST
            [FastAPI + LangGraph :8000]
                  ↓                    ↓
           [Redis PC1:6379]      [Qdrant :6333]
                                          ↓
                              [PostgreSQL Evolution API :5432]
```

## Stack

- **Evolution API** v2.3.7 (WhatsApp gateway Docker)
- **FastAPI** (webhook receiver + health)
- **LangGraph** (stateful multi-node RAG pipeline)
- **Qdrant** (vector search, 768 dimensões, cosine)
- **Redis** (cache + queue)
- **PostgreSQL** (interaction storage via Prisma)
- **MiniMax LLM** (text generation)

## Variáveis de Ambiente

```env
# Evolution API
AUTHENTICATION_API_KEY=your_api_key_here
SERVER_URL=https://your-server.com

# Database
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE

# Redis
REDIS_URL=redis://192.168.15.83:6379

# Qdrant
QDRANT_URL=http://192.168.15.83:6333

# MiniMax LLM
MINIMAX_API_KEY=your_minimax_key
```

## Como Rodar

### Local (desenvolvimento)

```bash
# 1. Instalar dependências
cd app
pip install -r requirements.txt

# 2. Gerar Prisma Client
prisma generate

# 3. Aplicar migrations
prisma migrate dev --name init

# 4. Rodar FastAPI
uvicorn app.main:app --reload --port 8000
```

### Docker Compose

```bash
docker compose up --build
```

## Endpoints

| Método | Path | Descrição |
|--------|------|-----------|
| POST | `/webhook/evolution` | Webhook da Evolution API |
| GET | `/health` | Health check |
| GET | `/` | Info do serviço |

## LangGraph Pipeline (7 nós)

1. **classify_service** — Classifica intent entre 6 serviços KB
2. **retrieve_knowledge** — Busca top-5 no Qdrant por service_name
3. **generate_response** — Monta resposta com contexto RAG
4. **language_guard_check** — Valida saída em pt-BR (anti-CJK)
5. **format_whatsapp** — Formata mensagem para WhatsApp
6. **save_interaction** — Persiste no PostgreSQL via Prisma
7. **route_human** — Escalona para humano se intent=="human" ou confidence<0.6

## Guardrail de Idioma

Arquitetura dual-layer anti-CJK:
- **Layer 1**: System prompt instruindo resposta apenas em pt-BR
- **Layer 2**: Validação pós-resposta — detecta scripts CJK, Cirílico, Hangul, Árabe

Bloqueia: CJK (chinês/japonês), Cirílico, Hangul, Árabe, Hebraico, Thai, Devanagari, Tamil, Kannada, Malayalam.

## Verificação

```bash
cd /home/will/whatsapp-rag
python -c "from langgraph.guards.language_guard import LanguageGuard; print('language_guard: OK')"
python -c "from langgraph.graph.graph import build_graph; print('graph: OK')"
python -c "from app.main import app; print('fastapi: OK')"
```

## Estrutura de Diretórios

```
whatsapp-rag/
├── .env
├── docker-compose.yml
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   └── config/
│       └── settings.py
├── langgraph/
│   ├── __init__.py
│   ├── nodes/
│   │   ├── __init__.py
│   │   └── nodes.py
│   ├── graph/
│   │   ├── __init__.py
│   │   └── graph.py
│   └── guards/
│       ├── __init__.py
│       └── language_guard.py
├── prisma/
│   ├── schema.prisma
│   └── .env.example
├── qdrant/
│   └── seed_qdrant.py
└── README.md
```
