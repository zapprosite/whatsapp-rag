# WhatsApp RAG Lead — Refrimix

## Contexto

Projeto: bot WhatsApp para onboarding e atendimento a leads da Refrimix Tecnologia.
Stack: Evolution API v2.3.7 Docker (8080) + FastAPI + LangGraph (8000) + Qdrant staging (6333) + Redis PC1 (6379).
Seis serviços KB: instalacao, consultoria, manutencao, pmoc, projeto-central, higienizacao.
Coleção Qdrant: `hermes_hvac_rag_service_staging` — 768 dimensões, cosine, 55 pontos (seed OK).
Redis PC1: 192.168.15.83:6379.
PostgreSQL Evolution API: 192.168.15.83:5432/evolution_api.

## Arquitetura Alvo

```
[WhatsApp] → [Evolution API Docker :8080]
                  ↓ webhook POST
            [FastAPI + LangGraph :8000]
                  ↓                    ↓
           [Redis PC1:6379]      [Qdrant :6333]
```

## O QUE FAZER

Criar em `/home/will/whatsapp-rag/` o projeto completo:

### 1. Guardrail de Idioma (MiniMax)

Problema: o modelo às vezes responde em espanhol, cirílico, CJK.
Arquitetura: **dual-layer** — system prompt injetado + guardrail de detecção pós-resposta.

**Arquivo: `langgraph/guards/language_guard.py`**
- Classe `LanguageGuard` com método `validate_and_fix(response: str, expected_lang: str = "pt-BR") -> str`
- Detecta scripts não-latinos: Cirílico, CJK, Hangul, árabe, etc.
- Detecta frases que sãoMajority não-pt-BR (threshold > 50% de tokens não-latinos)
- Usa `langdetect` se disponível, fallback regex
- Se detectar desvio: faz retry no LLM pedindo resposta em pt-BR com o mesmo prompt
- Max retries: 2
- Raise `LanguageViolation` se falhar

**Arquivo: `langgraph/guards/__init__.py`**

### 2. LangGraph 7 Nodes

**Arquivo: `langgraph/nodes/nodes.py`**

```
nodes:
  1. classify_service      — classifica intent do lead entre 6 serviços KB
  2. retrieve_knowledge    — busca top-5 no Qdrant por service_name
  3. generate_response    — monta resposta com contexto RAG + tom comercial Refrimix
  4. language_guard_check  — valida saída em pt-BR antes de enviar
  5. format_whatsapp       — formata mensagem para WhatsApp (textos curtos, emojis)
  6. save_interaction     — persiste no PostgreSQL via Prisma
  7. route_human          — se intent == "human" ou confidence < 0.6, escala para humano
```

Cada node retorna dict com `{"messages": [...], "metadata": {...}}`.

**Arquivo: `langgraph/graph/graph.py`**
- Estado: `{"messages": [], "intent": None, "service": None, "rag_context": [], "customer_data": {}}`
- Borda condicional: classify_service → [retrieve_knowledge | route_human]
- Borda: language_guard_check ← generate_response → format_whatsapp

### 3. FastAPI Application

**Arquivo: `app/main.py`**

```python
from fastapi import FastAPI, Request, HTTPException
from langgraph.graph import StateGraph
import redis, json

app = FastAPI(title="Refrimix WhatsApp RAG")

# POST /webhook/evolution — recebe webhook da Evolution API
@app.post("/webhook/evolution")
async def receive_webhook(request: Request):
    body = await request.json()
    # ekstrai phone, message, instanceName
    # publicadores para LangGraph
    # responde 200 OK imediatamente (Evolution exige)
    return {"status": "ok"}

# GET /health
@app.get("/health")
async def health():
    return {"status": "ok", "langgraph": "up", "qdrant": "up", "redis": "up"}
```

### 4. Prisma Schema

**Arquivo: `prisma/schema.prisma`**

```prisma
datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

generator client {
  provider = "prisma-client-py"
}

model Interaction {
  id          String   @id @default(uuid())
  phone       String
  message     String
  intent      String?
  service     String?
  response    String?
  is_human    Boolean  @default(false)
  created_at  DateTime @default(now())
  metadata    Json?
}
```

### 5. Configurações

**Arquivo: `config/settings.py`** — Pydantic BaseSettings com:
- `evolution_api_key`
- `redis_url`
- `qdrant_url`
- `database_url`
- `llm_model` = "mini-max"
- `llm_api_base` = "https://api.minimax.chat"

### 6. Docker Compose Atualizado

**Arquivo: `docker-compose.yml`** — incluir FastAPI + LangGraph + Redis (se não subir no PC1):

```yaml
version: '3.8'
services:
  whatsapp-api:
    image: atendai/evolution-api:v2.3.7
    # ... já existe, não mexer

  fastapi-rag:
    build: ./app
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://192.168.15.83:6379
      - QDRANT_URL=http://192.168.15.83:6333
      - DATABASE_URL=postgresql://evo_user:changeme@192.168.15.83:5432/evolution_api
    depends_on:
      - whatsapp-api
```

**Arquivo: `app/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Arquivo: `app/requirements.txt`**
```
fastapi
uvicorn
langgraph
langchain-core
redis
prisma
pydantic-settings
python-dotenv
httpx
langdetect
```

### 7. Estrutura de Diretórios

```
whatsapp-rag/
├── .env                          # AUTHENTICATION_API_KEY, SERVER_URL, etc.
├── docker-compose.yml           # Evolution API + FastAPI
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                  # FastAPI app
│   └── config/
│       └── settings.py
├── langgraph/
│   ├── __init__.py
│   ├── graph/
│   │   └── graph.py             # StateGraph + 7 nodes
│   └── guards/
│       ├── __init__.py
│       └── language_guard.py     # Guardrail idioma pt-BR
├── prisma/
│   └── schema.prisma
├── qdrant/
│   └── seed_qdrant.py           # já existe
└── README.md
```

### 8. README.md

Criar `/home/will/whatsapp-rag/README.md` com:
- Descrição do projeto
- Stack
- Variáveis de ambiente
- Como rodar localmente
- Como rodar com Docker Compose
- Diagrama da arquitetura em ASCII

## REGRAS

1. Todos os arquivos Python usam `from __future__ import annotations` + type hints completos
2. Nenhum valor real de credentials no código — usar `os.getenv` + .env
3. Redis usa `redis.asyncio` para operações assíncronas
4. Qdrant usa `qdrant-client` com busca por service_name metadata
5. LangGraph usa schema `messages: list[BaseMessage]` compatível com langchain-core 0.3.x
6. Testar import de cada módulo antes de declarar pronto
7. Avisar se encontrar incompatibilidade de versão entre langchain-core e langgraph

## O QUE NÃO FAZER

- Não modificar o docker-compose.yml da Evolution API (ele já funciona)
- Não mexer em seed_qdrant.py (já está correto)
- Não implementar autenticação extra no webhook (Evolution API já autentica por API key)

## VERIFICAÇÃO

Ao finalizar, rodar:
```bash
cd /home/will/whatsapp-rag
python -c "from langgraph.guards.language_guard import LanguageGuard; print('language_guard: OK')"
python -c "from langgraph.graph.graph import build_graph; print('graph: OK')"
python -c "from app.main import app; print('fastapi: OK')"
```