# SUPER BLUEPRINT v2.2 — Refrimix HVAC-R Bot
## Arquitetura Completa: Evolution + FastAPI + LangGraph + Qdrant + PostgreSQL

**Data:** 26/05/2026
**Autor:** Socrates / William (Refrimix)
**Versão:** 2.2 (refatorado com base em arquitetura Evolution/FastAPI/LangGraph)
**Repo:** `/home/will/workspace/whatsapp-rag-clean`

---

## DIAGRAMA DE ARQUITETURA (CANONICAL)

```
WhatsApp
  ↓
Evolution API (WhatsApp Channel — NÃO É CERÉBRO)
  ├─ recebe msgs
  ├─ envia respostas
  └─ webhook POST MESSAGES_UPSERT
         ↓
FastAPI /webhook/evolution (PORTA DE ENTRADA)
  ├─ valida X-Webhook-Secret
  ├─ valida instance (RefrimixLead)
  ├─ extrai message_id
  ├─ verifica idempotência no PostgreSQL
  ├─ salva mensagem bruta em PostgreSQL
  └─ 200 OK IMEDIATO (não processa aqui)
         ↓
Redis: lead:{phone}:buffer (junta msgs fragmentadas por 5s)
Redis: lead:{phone}:debounce_lock (impede double-process)
Redis: queue:refrimix_leads (RQ/Redis native queue)
         ↓
Worker Python (processo separado — NÃO FastAPI BackgroundTask)
  ├─ consome Redis queue
  ├─ carrega lead context do PostgreSQL
  └─ executa LangGraph
         ↓
  ┌────────────────────────────────────────────────────┐
  │                 LANGGRAPH                          │
  │                                                  │
  │  [receive_message]                               │
  │        ↓                                         │
  │  [normalize_message]  ← normaliza msg brut       │
  │        ↓                                         │
  │  [load_lead_context]  ← Mongo/Postgres summary  │
  │        ↓                                         │
  │  [detect_intent]      ← regex HVAC + intent key │
  │        ↓                                         │
  │  [detect_risk]        ← disjuntor/cheiro/risco   │
  │        ↓                                         │
  │  [retrieve_qdrant]    ← só se INTENDED           │
  │        ↓                                         │
  │  [decide_next_action] ← commercial_router v2    │
  │        ↓                                         │
  │  [generate_response]  ← canonical OR LLM        │
  │        ↓                                         │
  │  [guardrail_check]    ← bloqeia preço inventado │
  │        ↓                                         │
  │  [save_decision]      ← PostgreSQL bot_decisions │
  │        ↓                                         │
  │  [send_whatsapp]      ← Evolution sendText       │
  └────────────────────────────────────────────────────┘
         ↓
PostgreSQL: messages + lead_states + bot_decisions
Evolution API: WhatsApp response
```

---

## PARTE 1 — Papel de Cada Peça (CANONICO)

### 1.1 Evolution API = Canal WhatsApp

**Função:**
- Receber mensagens do WhatsApp
- Enviar respostas via `sendText`
- Gerenciar instância/conexão WhatsApp
- QR Code e handshakes Baileys/Meta API
- Webhook para eventos (`MESSAGES_UPSERT`)

**O que NÃO é:**
- Não é cérebro
- Não decide caminho comercial
- Não gera resposta
- Não consulta histórico

**Regra de Ouro:**
> Evolution = carteiro. Não peça para o carteiro vender ar-condicionado com diagnóstico elétrico.

---

### 1.2 FastAPI = Porta de Entrada

**Função:**
- Receber webhook `/webhook/evolution`
- Validar `X-Webhook-Secret` header
- Validar `instance` do payload
- Verificar idempotência (`message_id` no PostgreSQL)
- Salvar mensagem bruta no PostgreSQL
- Despachar para Redis queue
- Responder `200 OK` IMEDIATAMENTE

**O que NÃO é:**
- Não é worker de processamento
- Não roda LangGraph
- Não chama LLM no request HTTP
- Não usa `BackgroundTasks` para lógica crítica

**Regra de Ouro:**
> FastAPI = porteiro. Recebe, registra, entrega para o worker, volta para o próximo访客.

---

### 1.3 Redis = Fila, Debounce, Cache, Lock

**Função:**
- `queue:refrimix_leads` — fila de trabalho (não é só cache)
- `lead:{phone}:buffer` — junta mensagens fragmentadas (5s window)
- `lead:{phone}:debounce_lock` — lock de process duplicado
- `lead:{phone}:state` — estado curto do lead (TTL 72h)
- `lead:{phone}:handoff_required` — flag para humano

**O que NÃO é:**
- Não é fonte da verdade operacional (PostgreSQL é)
- Não substitui PostgreSQL para histórico permanente

---

### 1.4 PostgreSQL = Fonte da Verdade

**Função:**
- `messages` — todas mensagens (inbound + outbound)
- `lead_states` — estado atual de cada lead (JSONB)
- `bot_decisions` — log de decisões (intent, action, response, handoff)
- `leads` — cadastro básico (telefone, nome, created_at)
- `message_idempotency` — deduplicação (`message_id`, `payload_hash`, `created_at`)
- `quote_requests` — orçamentos solicitados
- `appointments` — agendamentos

**O que NÃO é:**
- Não é vetor semântico (Qdrant é)
- Não é cache de sessão curta (Redis é)

---

### 1.5 Qdrant = Busca Técnica/Comercial (quando RAG enabled)

**Função:**
- Busca知識 base de climatização HVAC-R
- Filtros: `intent`, `risk`, `service`, `categoria`
- Retorna contexto para LLM

**O que NÃO é:**
- Não decide nada
- Não é fonte da verdade operacional
- Não substitui PostgreSQL

---

### 1.6 LangGraph = Fluxo, Estado, Decisão, Handoff

**Função:**
- Fluxo de atendimento multi-turn com memória
- Classificação de intent + risk
- Decisão de próximo passo
- Geração de resposta (canonical ou LLM)
- Validação de guardrail
- Handoff para humano quando risco alto

**Quando USA:**
- Multi-turn conversations
- Decisions com estado
- Risco técnico
- Human-in-the-loop approval
- Follow-up

**Quando NÃO USA:**
- FAQ simples
- Resposta única sem estado
- Mensagens isoladas sem contexto

---

## PARTE 2 — Fluxo Detalhado (Passo a Passo)

### Passo 0 — Evolution API recebe mensagem

```json
{
  "event": "MESSAGES_UPSERT",
  "instance": "RefrimixLead",
  "data": {
    "key": {
      "id": "XYZ123",
      "remoteJid": "5513996659382@s.whatsapp.net",
      "fromMe": false
    },
    "message": {
      "conversation": "meu ar não gela"
    },
    "pushName": "Will"
  }
}
```

**Evolution NÃO vai para o worker ainda.** Só dispara webhook.

---

### Passo 1 — FastAPI recebe webhook

```
POST /webhook/evolution
Headers:
  X-Webhook-Secret: {WEBHOOK_SECRET}
Content-Type: application/json
```

**Validações em ordem:**
1. Header `X-Webhook-Secret` presente e válido
2. `instance` == `RefrimixLead`
3. `fromMe == false` (ignora mensagens do próprio bot)
4. `message_id` não existe em `message_idempotency` (idempotência)

**Se qualquer falha:**
- `401` / `403` → reject
- `fromMe == true` → 200 OK, não processa (log pra analytics)
- `message_id` duplicado → 200 OK, não processa (log "duplicate ignored")

**Se válido:**
1. Salva mensagem em `messages`
2. Registra em `message_idempotency`
3. Salva em `lead:{phone}:buffer` no Redis (5s TTL)
4. Retorna `200 OK` IMEDIATO

**Código mínimo do webhook:**

```python
@router.post("/webhook/evolution")
async def evolution_webhook(request: Request, payload: dict):
    # 1. Validar secret
    secret = request.headers.get("X-Webhook-Secret")
    if secret != settings.WEBHOOK_SECRET:
        raise HTTPException(401, "Invalid secret")

    # 2. fromMe = ignore
    if payload.get("data", {}).get("key", {}).get("fromMe"):
        return {"status": "ok", "reason": "fromMe"}

    # 3. Idempotência
    message_id = payload.get("data", {}).get("key", {}).get("id")
    if(await check_idempotency(message_id)):
        return {"status": "ok", "reason": "duplicate"}

    # 4. Salvar mensagem
    await save_message_to_postgres(payload)
    await register_idempotency(message_id, payload)

    # 5._buff + queue
    phone = extract_phone(payload)
    await redis.rpush(f"queue:refrimix_leads", json.dumps({
        "message_id": message_id,
        "phone": phone,
        "payload": payload
    }))

    return {"status": "ok"}
```

---

### Passo 2 — Redis Debounce (juntar mensagens fragmentadas)

**Problema real:**
```
Cliente envia:
"Oi"
"Meu ar"
"Não gela"
"Quanto fica"
"Sou de Santos"
```

Sem debounce: 5 respostas separadas = monstro.

**Solução:**
```python
async def buffer_message(phone: str, payload: dict, window_seconds: int = 5):
    key = f"lead:{phone}:buffer"
    lock_key = f"lead:{phone}:debounce_lock"

    # Se já existe lock, rejeita (está processando)
    if await redis.exists(lock_key):
        return  # ignora, worker vai processar

    # Adiciona msg ao buffer
    await redis.rpush(key, json.dumps({
        "text": payload["message"]["conversation"],
        "timestamp": payload["timestamp"]
    }))
    await redis.expire(key, window_seconds + 2)

    # Agenda process após window
    await redis.set(lock_key, "1", nx=True, ex=window_seconds + 1)
    await redis.rpush("queue:refrimix_leads", json.dumps({
        "phone": phone,
        "trigger": "debounce",
        "buffer_window": window_seconds
    }))
```

**Resultado após 5s:**
```
Buffer: ["Oi", "Meu ar", "Não gela", "Quanto fica", "Sou de Santos"]
→ Join: "Oi meu ar não gela quanto fica sou de Santos"
→ Worker processa texto completo
```

---

### Passo 3 — Worker consome Redis queue

```
BLPOP queue:refrimix_leads  (blocking pop, 30s timeout)
```

**Para cada job:**

```python
job = redis.lpop("queue:refrimix_leads")
data = json.loads(job)

phone = data["phone"]

# Carrega estado do lead do Redis (prioridade) ou PostgreSQL
lead_state = await redis.get(f"lead:{phone}:state")
if not lead_state:
    lead_state = await load_from_postgres(phone)

# Carrega buffer se existir
buffered_msgs = await redis.lrange(f"lead:{phone}:buffer", 0, -1)
if buffered_msgs:
    combined_text = " ".join([json.loads(m)["text"] for m in buffered_msgs])
    # Limpa buffer
    await redis.delete(f"lead:{phone}:buffer")

# Executa LangGraph
result = await langgraph_agent.run({
    "user_message": combined_text or raw_message,
    "lead_state": lead_state,
    "phone": phone
})
```

---

### Passo 4 — LangGraph Nodes (detalhado)

```
[receive_message]
      ↓
[normalize_message]
  - Limpa texto (espaços, pontuação)
  - Detecta idioma (PT-BR obrigatório)
  - Extrai entidades básicas (telefone, nome)
      ↓
[load_lead_context]
  - Carrega lead_state do PostgreSQL (resumo)
  - Resgata histórico de intents
  - Resgata campos já coletados
      ↓
[detect_intent]
  - Regex classifier → kind (JÁ EXISTE em understand_message.py)
  - Mapeia para intent_key (nao_gela, disjuntor_cai, etc)
  - Confiança da classificação
      ↓
[detect_risk]
  - Se intent em ["disjuntor_cai","fio_esquenta","cheiro_queimado"]
    → risk = ALTO, human_handoff = true
  - Se intent em ["nao_gela","barulho"]
    → risk = MEDIO
  - Caso contrário
    → risk = BAIXO
      ↓
[retrieve_qdrant]  (só se RAG_ENABLED e intent != generic)
  - Filtra por intent_key + risk + service
  - Máximo 3 chunks
  - Contexto retornado para LLM
      ↓
[decide_next_action]  (commercial_router.py — DETERMINÍSTICO)
  - action_type: offer_technical_visit, fixed_installation, etc
  - next_node: ask_symptoms | give_quote | transfer_human
      ↓
[generate_response]
  - Se action tem canonical_response:
    → canonical_response_block[action_type]
  - Se action é generic/complex:
    → llm_response(MiniMax, system_prompt, few_shot)
      ↓
[guardrail_check]
  - Bloqeia: preço inventado, diagnóstico definitivo, frases proibidas
  - Se violou → regera com canonical ou fallback
      ↓
[save_decision]
  - PostgreSQL: bot_decisions (intent_key, action_type, response, llm_called, handoff)
  - PostgreSQL: lead_states (novo estado)
  - Redis: lead:{phone}:state (cache 72h)
      ↓
[send_whatsapp]
  - Evolution sendText API
  - Salva mensagem outbound em messages
```

---

### Passo 5 — Resposta Canonical vs LLM

**Regra:**
- 80% das situações → canonical response block
- 20% (generic/complex) → LLM MiniMax com persona

**Canonical Response Blocks (intent_blocks.json):**

```json
{
  "nao_gela": {
    "canonical_response": "Entendi. Quando o ar liga mas não gela, pode ser coisa simples como condensadora suja ou falta de gás, mas também pode envolver placa ou sensor. Pra eu te passar uma orientação sem errar, me confirma: ele liga normal, a condensadora funciona e aparece algum código no visor?",
    "risk": "medio",
    "next_action_hint": "collect_symptoms"
  },
  "disjuntor_cai": {
    "canonical_response": "Entendi. Quando o disjuntor cai ou o fio esquenta, o melhor é manter o equipamento desligado até avaliar, porque pode ser sobrecarga, mau contato ou circuito fora do padrão. Me manda uma foto do disjuntor e do aparelho, e me fala o bairro pra eu verificar o melhor caminho.",
    "risk": "alto",
    "human_handoff": true
  }
}
```

**LLM fallback (quando canonical não existe):**

```python
async def llm_response(user_message: str, lead_state: dict, context: dict) -> str:
    system_prompt = load_prompt("persona_ptbr_vendas.md")

    few_shot = """
    Cliente: meu ar faz um barulho estranho
    Resposta: Entendi. Barulho anormal pode ser vibração da evaporadora, turbinacom sujeira, peça solta ou até problema no compressor. Me descreve que tipo de barulho é e se acontece o tempo todo ou só em determinadas situações.

    Cliente: preciso instalar 3 split
    Resposta: Perfeito. Pra instalação, o valor correto depende de alguns detalhes. Me fala: qual bairro fica? Os aparelho já estão comprados? E sabe quantos BTUs precisa pro ambiente?
    """

    messages = [
        {"role": "system", "content": system_prompt + few_shot},
        {"role": "user", "content": user_message}
    ]

    response = await minimax.chat(messages)
    return response["choices"][0]["message"]["content"]
```

---

## PARTE 3 — Idempotência (PostgreSQL)

### Tabela

```sql
CREATE TABLE message_idempotency (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(100) UNIQUE NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    phone VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_message_idempotency_message_id ON message_idempotency(message_id);
```

**Verificação:**
```python
async def check_idempotency(message_id: str) -> bool:
    result = await db.fetch_one(
        "SELECT 1 FROM message_idempotency WHERE message_id = $1",
        message_id
    )
    return result is not None
```

---

## PARTE 4 — Redis Keys (Completo)

| Key | Conteúdo | TTL | Propósito |
|-----|----------|-----|----------|
| `queue:refrimix_leads` | Lista de jobs aguardando | — | Fila principal |
| `lead:{phone}:buffer` | Msgs fragmentadas juntas | 7s | Juntar msgs quebradas |
| `lead:{phone}:debounce_lock` | "1" enquanto processa | 6s | Impede duplicado |
| `lead:{phone}:state` | JSON do lead state | 72h | MemóriaCurta |
| `lead:{phone}:handoff_required` | "true" | 24h | Flag p/ humano |
| `lead:{phone}:last_intent` | `nao_gela` | 72h | Analytics |
| `rate_limit:{phone}` | Contador | 60s | Anti-spam |

---

## PARTE 5 — Guardrails (NÃO NEGOCIÁVEIS)

```python
FORBIDDEN_PATTERNS = [
    (r"\bfalta de gás com certeza\b", "Diagnóstico definitivo"),
    (r"\bcompressor queimou\b", "Diagnóstico definitivo"),
    (r"\bvalor fechado\b", "Preço inventado"),
    (r"\btenho disponibilidade\b", "Promessa não confirmada"),
    (r"\bpromoÇÃO\b", "Linguagem enganosa"),
    (r"^\\s*então,?", "Português europeu"),
    (r"\bprecisa de ajuda\\?\b", "Formalidade errada"),
    (r"¿", "Espanhol"),
]

REQUIRED_CONDITIONS = [
    lambda r: len(r) <= 500,
    lambda r: r.count("?") <= 2,
    lambda r: not any(p.match(r.lower()) for p, _ in FORBIDDEN_PATTERNS),
]

async def guardrail_check(response: str, lead_state: dict, action_type: str):
    violations = []
    for pattern, reason in FORBIDDEN_PATTERNS:
        if pattern.search(response):
            violations.append(reason)

    for condition in REQUIRED_CONDITIONS:
        if not condition(response):
            violations.append("Condição violated")

    if violations:
        # Fallback forçado para canonical response
        return get_canonical_fallback(action_type, lead_state)

    return response
```

---

## PARTE 6 — Respostas Canônicas ((intent_blocks.json))

### disjun tor_cai / fio_esquenta / cheiro_queimado
```
Entendi. Quando o disjuntor cai ou o fio esquenta, o melhor é manter o equipamento desligado até avaliar, porque pode ser sobrecarga, mau contato ou circuito fora do padrão. Me manda uma foto do disjuntor e do aparelho, e me fala o bairro pra eu verificar o melhor caminho.
```
⚠️ **Risk ALTO — human_handoff = true**

### nao_gela
```
Entendi. Quando o ar liga mas não gela, pode ser coisa simples como condensadora suja ou falta de gás, mas também pode envolver placa ou sensor. Pra eu te passar uma orientação sem errar, me confirma: ele liga normal, a condensadora funciona e aparece algum código no visor?
```

### pinga_agua
```
Entendi. Pingamento pode ser dreno obstruído, sujeira na bandeja, desnível ou até instalação. Dá pra resolver, mas precisa avaliar certinho. Me manda uma foto do aparelho e me fala se pinga logo que liga ou depois de um tempo.
```

### cheiro_ruim / rinite
```
Entendi. Quando o ar fica com cheiro ruim ou sensação de ar pesado, normalmente a higienização técnica resolve, principalmente se faz tempo sem manutenção. Me fala o bairro e, se souber, a marca e capacidade do aparelho.
```

### barulho
```
Entendi. Barulho anormal pode ser vibração da evaporadora, turbina com sujeira, peça solta ou até problema no compressor. Me descreve que tipo de barulho é e se acontece o tempo todo ou só em determinadas situações.
```

### instalacao
```
Perfeito. Pra instalação, o valor correto depende de alguns detalhes. Me fala: qual bairro fica? O aparelho já está comprado? E sabe quantos BTUs precisa pro ambiente?
```

### higienizacao
```
Higienização de split padrão fica R$200 por aparelho — o trabalho inclui limpeza das partes internas, filtro e bandeja. Se o aparelho não estiver climatizando, vira análise de manutenção por R$50. Quantos aparelhos são?
```

### servicos
```
Trabalhamos com instalação, manutenção, higienização e visita técnica para ar-condicionado. Também atendemos casos maiores como projeto, infraestrutura elétrica e equipamentos comerciais.

Os serviços mais comuns:
1. Instalação simples: a partir de R$850
2. Higienização: R$200/aparelho
3. Manutenção/conserto: visita R$50
4. Visita técnica de análise

Me fala qual você precisa hoje.
```

### welcome
```
Bom dia, tudo joia? Pra mim te ajudar, me conta o que você precisa — instalação, manutenção, higienizaçãoconserto ou alguma coisa específica com o aparelho.
```

### orcamento (sem dados)
```
Entendi que você quer orçamento. Pra eu passar um valor que faça sentido, preciso de alguns dados: qual bairro fica? O aparelho você já tem ou vai comprar? E sabe quantos BTUs大致?
```

---

## PARTE 7 — PostgreSQL Schema (Minimal)

```sql
-- Mensagens (inbound + outbound)
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) NOT NULL,
    message_id VARCHAR(100) UNIQUE NOT NULL,
    direction VARCHAR(10) NOT NULL, -- 'inbound' | 'outbound'
    content TEXT,
    raw_payload JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Estado do lead (resumo, não histórico completo)
CREATE TABLE lead_states (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) UNIQUE NOT NULL,
    state JSONB NOT NULL, -- intent_key, collected_fields, action_path, etc
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Decisões do bot (para analytics e qualidade)
CREATE TABLE bot_decisions (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    intent_key VARCHAR(50),
    action_type VARCHAR(50),
    risk_level VARCHAR(10),
    response_used TEXT,
    llm_called BOOLEAN DEFAULT false,
    handoff_triggered BOOLEAN DEFAULT false,
    human_response TEXT, -- NULL se não foi necessário
    quality_score DECIMAL(3,2), -- NULL por enquanto
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Idempotência
CREATE TABLE message_idempotency (
    id SERIAL PRIMARY KEY,
    message_id VARCHAR(100) UNIQUE NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    phone VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Agendamentos
CREATE TABLE appointments (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20) NOT NULL,
    service_type VARCHAR(50),
    scheduled_at TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'pending', -- pending/confirmed/completed/cancelled
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

**Estado de lead (`lead_states.state`):**
```json
{
  "lead_id": "123",
  "name": "Will",
  "phone": "5513996659382",
  "intent_key": "nao_gela",
  "risk_level": "medio",
  "collected_fields": ["bairro", "condensadora_funciona"],
  "missing_fields": ["codigo_erro", "tempo_problema"],
  "last_user_message": "meu ar não gela",
  "conversation_summary": "Cliente relata split não gela. Foi perguntado se condensadora funciona e se há código de erro.",
  "action_path": "tech_visit_flow",
  "last_action_type": "collect_symptoms"
}
```

---

## PARTE 8 — LangGraph Checkpointing (PERSISTENTE)

**NÃO use `InMemorySaver` em produção.**

```python
from langgraph.checkpoint.postgres import AsyncPostgresSaver

# Setup
checkpointer = AsyncPostgresSaver.from_conn_string(DATABASE_URL)
await checkpointer.setup()  # cria tabelas se não existirem

# Thread por conversa = phone + instance_id
thread_id = f"evolution:refrimix:{phone}"

# Agente
agent = Graph.from_graph(checkpointer=checkpointer)

# Runnable com checkpoint
graph_agent = agent.compile(thread={"configurable": {"thread_id": thread_id}})

# Execução
result = await graph_agent.invoke({
    "user_message": combined_text,
    "lead_state": lead_state
})
```

**Benefícios:**
- Memória entre mensagens (resume após restart)
- Replay/debug de conversas
- Recuperação de falha
- Human-in-the-loop com aprovação

---

## PARTE 9 — Arquivos: Criar / Modificar / Deletar

### CRIAR

| Arquivo | Prior | Descrição |
|---------|-------|-----------|
| `refrimix_core/domain/intent_blocks.json` | 🔴 | Intent blocks + canonical responses |
| `refrimix_core/domain/canonical_response.py` | 🔴 | build_response() + canonical hit |
| `refrimix_core/domain/risk_detector.py` | 🔴 | detect_risk() + handoff flags |
| `refrimix_core/prompts/persona_ptbr_vendas.md` | 🔴 | System prompt completo |
| `refrimix_core/domain/llm_response.py` | 🟡 | MiniMax fallback generator |
| `refrimix_core/domain/guardrail_validator.py` | 🟡 | Post-response guardrails |
| `refrimix_core/graph/nodes/` | 🔴 | 11 nodes do LangGraph |
| `refrimix_core/graph/agent.py` | 🔴 | LangGraph agent completo |
| `refrimix_core/db/idempotency.py` | 🟡 | Check + register idempotência |
| `scripts/migrate_idempotency.sql` | 🟡 | Migration PostgreSQL |

### MODIFICAR

| Arquivo | Mudança |
|---------|---------|
| `docker-compose.yml` | Adicionar `AsyncPostgresSaver` config |
| `refrimix_core/domain/pipeline.py` | Wire `build_response()` |
| `.env.example` | Adicionar `WEBHOOK_SECRET`, `LANGGRAPH_CHECKPOINTER_URL` |

### DELETAR

| Arquivo | Por quê |
|---------|---------|
| `app/mvp_attendance.py` | Legacy LangGraph, duplica pipeline v2 |
| `agent_graph/` | Legacy LangGraph, não usado |

---

## PARTE 10 — Teste de Integração (快速 smoke)

```python
# tests/integration/test_full_flow.py

async def test_message_flow_evolution_to_whatsapp():
    """
    1. Manda 'bom dia' via webhook
    2. Verifica salva em PostgreSQL messages
    3. Verifica job na Redis queue
    4. Worker processa
    5. Verifica bot_decisions preenchido
    6. NÃO verifica se WhatsApp recebeu ( Evolution sendText pode falhar em dev)
    """
    payload = {
        "event": "MESSAGES_UPSERT",
        "instance": "RefrimixLead",
        "data": {
            "key": {
                "id": "test_dev_123",
                "remoteJid": "5513996659382@s.whatsapp.net",
                "fromMe": False
            },
            "message": {"conversation": "bom dia"},
            "pushName": "Will Dev"
        }
    }

    # POST webhook
    response = await client.post("/webhook/evolution", json=payload)
    assert response.status_code == 200

    # PostgreSQL: mensagem salva
    msg = await db.fetch_one(
        "SELECT * FROM messages WHERE message_id = $1",
        "test_dev_123"
    )
    assert msg is not None

    # Redis: job na queue
    job = await redis.lpop("queue:refrimix_leads")
    assert job is not None

    # bot_decisions após worker processar
    decision = await db.fetch_one(
        "SELECT * FROM bot_decisions WHERE phone = $1 ORDER BY created_at DESC LIMIT 1",
        "5513996659382"
    )
    assert decision is not None
    assert decision["intent_key"] == "welcome"
```

---

## PARTE 11 — Métricas (Dashboard pós-implementação)

```sql
-- Volume de msgs por dia
SELECT DATE(created_at), COUNT(*) FROM messages GROUP BY 1;

-- Intent distribution
SELECT intent_key, COUNT(*) FROM bot_decisions GROUP BY 1;

-- Taxa de handoff
SELECT
    COUNT(*) FILTER (WHERE handoff_triggered) * 100.0 / NULLIF(COUNT(*), 0)
FROM bot_decisions;

-- Leads em funnel
SELECT
    state->>'action_path' as path,
    COUNT(DISTINCT phone)
FROM lead_states
GROUP BY 1;

-- Tempo médio de resposta (inbound → outbound)
WITH diff AS (
    SELECT
        m1.phone,
        m1.created_at as inbound,
        m2.created_at as outbound,
        EXTRACT(EPOCH FROM (m2.created_at - m1.created_at)) as seconds
    FROM messages m1
    JOIN messages m2 ON m1.phone = m2.phone
        AND m2.direction = 'outbound'
        AND m2.created_at > m1.created_at
    WHERE m1.direction = 'inbound'
)
SELECT AVG(seconds) FROM diff WHERE seconds < 300; -- só respostas < 5min
```

---

## PARTE 12 — Checklist de Implementação

### Fase 1 — Core (1-2 dias)
- [ ] `intent_blocks.json` com 12 intents
- [ ] `canonical_response.py` (build_response)
- [ ] `risk_detector.py`
- [ ] `guardrail_validator.py`
- [ ] Modificar `pipeline.py` → usar `build_response()`
- [ ] Teste: mensagem "meu ar não gela" → canonical_response
- [ ] Teste: mensagem "oi" → welcome canônica

### Fase 2 — LangGraph (2-3 dias)
- [ ] 11 nodes do grafo
- [ ] `agent.py` com checkpointer Postgres
- [ ] Wire `detect_intent` → `refrimix_core/nodes/understand_message.py`
- [ ] Wire `decide_next_action` → `commercial_router.py`
- [ ] Teste: fluxo completo `bom dia` → `nao_gela` → canonical
- [ ] Teste: fluxo `disjuntor cai` → handoff flag

### Fase 3 — Debounce + Idempotência (1 dia)
- [ ] Schema PostgreSQL `message_idempotency`
- [ ] Redis buffer + debounce lock
- [ ] FastAPI idempotency check
- [ ] Teste: msgs fragmentadas juntas
- [ ] Teste: duplicate rejected

### Fase 4 — LLM Fallback (1 dia)
- [ ] `persona_ptbr_vendas.md` system prompt
- [ ] `llm_response.py` (MiniMax call)
- [ ] Teste: intent "generic" → LLM response
- [ ] Guardrail block price invented

### Fase 5 — Observabilidade (1 dia)
- [ ] Dashboard básico (intent distribution, handoff rate)
- [ ] Bot decisions logging completo
- [ ] Smoke test automatizado
- [ ] Runbook de rollback

---

## PARTE 13 — Evolution API: Versões e Compatibilidade

### Estrategia de Versões (REGRADE OURO)

| Ambiente | Versão Evolution | Status |
|----------|-----------------|--------|
| **Produção** | **2.3.7** | Estável, sem licença obrigatória |
| **Laboratório/Staging** | **2.4.0-rc2** | Testar interativos, validar licença, webhooks |

### Por que 2.3.7 em produção?

- Sem licenciamento obrigatório (não dá `503 LICENSE_REQUIRED`)
- Estável para webhook + sendText + MESSAGES_UPSERT + reconnect
- Não arriscar bloqueio de endpoints de negócio

### Por que 2.4.0-rc2 em staging?

- Manager v2 (console melhorado)
- Interactive messages: `sendList`, `sendButtons`, `sendCarousel`, `sendCTA`
- PIX integration
- `@lid` handling (mapeamento de identificadores ocultos do WhatsApp)
- Audio chain (corrige envio encadeado)
- Histórico sync completion event

### Validação em staging ANTES de ir para produção:

```bash
# health
curl http://172.22.0.1:8080/health

# license status
curl http://172.22.0.1:8080/license/status

# manager
curl http://172.22.0.1:8080/manager

# webhook send
curl -X POST http://172.22.0.1:8080/message/sendText/RefrimixLead \
  -H "Content-Type: application/json" \
  -d "{\"number\":\"5513996659382\",\"text\":\"teste interativo\"}"

# list message (Evolution 2.4)
curl -X POST http://172.22.0.1:8080/message/sendList/RefrimixLead \
  -H "Content-Type: application/json" \
  -d '{"number":"5513996659382","title":"Como posso ajudar?","buttonText":"Escolha uma opção","sections":[{"title":"Serviços","rows":[{"title":"Instalação","rowId":"instalacao"},{"title":"Higienização","rowId":"higienizacao"},{"title":"Manutenção","rowId":"manutencao"}]}]}'

# MESSAGES_UPSERT event
curl -X POST http://172.22.0.1:8080/webhook/set \
  -H "Content-Type: application/json" \
  -d '{"webhook":{"url":"http://127.0.0.1:8000/webhook/evolution","events":["MESSAGES_UPSERT","CONNECTION_UPDATE"]}}'

# reconnect test
curl -X DELETE http://172.22.0.1:8080/instance/RefrimixLead/logout
curl -X POST http://172.22.0.1:8080/instance/RefrimixLead/connect
```

---

## PARTE 14 — Evolution 2.4: Interactive Messages (Ouro Comercial)

### Por que interativo muda conversion

```
Lead frio sem contexto:
  ❌ "Como posso ajudar?"                    → cliente não sabe o que digitar
  ✅ Lista com 6 opções clicáveis            → cliente escolhe e bot conduce

Lead com problema:
  ❌ "Me conta mais sobre o problema"        → cliente digita description errada
  ✅ Botão "Tirar foto do aparelho"          → dado estruturado, não textual

Lead de elétrica:
  ❌ "Entendi, qual é o bairro?"            → cliente continua usando equipo com risco
  ✅ "Manter desligado" + "Falar com atendente" → segurança + human handoff
```

### Tipos de Interactive Messages

#### 1. List Message (melhor para menu inicial)

```json
{
  "number": "5513996659382",
  "title": "Bem-vindo à Refrimix! 👋",
  "body": "Escolhe uma opção pra eu te ajudar:",
  "buttonText": "Ver opções",
  "sections": [
    {
      "title": "Serviços",
      "rows": [
        {"title": "Instalação de ar-condicionado", "rowId": "instalacao", "description": "Split, piso-teto, cassete"},
        {"title": "Higienização", "rowId": "higienizacao", "description": "R$200/aparelho"},
        {"title": "Manutenção e reparo", "rowId": "manutencao", "description": "Visita R$50"},
        {"title": "Projeto / Infraestrutura", "rowId": "projeto", "description": "Orçamento sob medida"}
      ]
    },
    {
      "title": "Problemas",
      "rows": [
        {"title": "Ar não gela", "rowId": "nao_gela", "description": "Split não climatiza"},
        {"title": "Pingando água", "rowId": "pinga_agua", "description": "Gotejamento ou dreno"},
        {"title": "Disjuntor cai / Fio aquece", "rowId": "disjuntor_cai", "description": "⚠️ Risco elétrico"},
        {"title": "Outro problema", "rowId": "outro", "description": "Me conta o que acontece"}
      ]
    }
  ]
}
```

**Renderização WhatsApp:**
```
┌─────────────────────────────┐
│ Bem-vindo à Refrimix! 👋    │
│                             │
│ Escolhe uma opção pra       │
│ eu te ajudar:               │
│                             │
│ [ Ver opções ]             │
│                             │
│ ── Serviços ──              │
│  📦 Instalação              │
│  🧹 Higienização            │
│  🔧 Manutenção              │
│  📋 Projeto                 │
│                             │
│ ── Problemas ──             │
│  ❄️ Ar não gela             │
│  💧 Pingando água           │
│  ⚡ Disjuntor cai           │
│  ❓ Outro problema          │
└─────────────────────────────┘
```

#### 2. Buttons (melhor para ação única confirmada)

```json
{
  "number": "5513996659382",
  "text": "Entendi. Pra avançar, me confirma:",
  "buttons": [
    {"type": "quickreply", "text": "📸 Tirar foto do aparelho"},
    {"type": "quickreply", "text": "🏠 Informar bairro"},
    {"type": "quickreply", "text": "📞 Falar com atendente"}
  ]
}
```

#### 3. CTA Button (para ação direta)

```json
{
  "number": "5513996659382",
  "text": "Perfeito. Pra agendar a visitatécnica:",
  "buttons": [
    {"type": "url", "text": "👉Verificar disponibilidade", "url": "https://refrimix.com.br/agenda"}
  ]
}
```

#### 4. Carousel ( Evolution 2.4+ apenas — staging)

```json
{
  "number": "5513996659382",
  "title": "Nossos serviços",
  "description": "Escolha um pra saber mais:",
  "cards": [
    {
      "title": "Instalação",
      "description": "Split，简单 a partir de R$850",
      "imageUrl": "https://refrimix.com.br/img/instalacao.jpg",
      "buttons": [
        {"type": "quickreply", "text": "Quero orçamento"},
        {"type": "url", "text": "Ver detalhes", "url": "https://refrimix.com.br/instalacao"}
      ]
    },
    {
      "title": "Higienização",
      "description": "R$200/aparelho. Banho técnico completo.",
      "imageUrl": "https://refrimix.com.br/img/higienizacao.jpg",
      "buttons": [
        {"type": "quickreply", "text": "Quero agendar"},
        {"type": "url", "text": "Ver detalhes", "url": "https://refrimix.com.br/higienizacao"}
      ]
    }
  ]
}
```

### Fluxo Interativo por Estágio do Funil

| Estágio | Lead | Interativo | Retorno |
|---------|------|------------|---------|
| **Entrada fria** | Sem contexto | List Message com 8 opções | Intent classificada |
| **Problema leve** | `nao_gela` ou `pinga_agua` | Buttons: coletar bairro + foto | Dados estruturados |
| **Problema elétrico** | `disjuntor_cai`, `cheiro_queimado` | Alerta segurança + "Falar com atendente" | Handoff humano |
| **Higienização** | `higienizacao` | CTA: "Verificar disponibilidade" | Agendamento |
| **Instalação** | `instalacao` | List: coletar dados + botões bairro | Orçamento |
| **Confirmação** | Dados completos | PIX ou link de sinal | Fechamento |

### Implementação do Envio Interativo

```python
async def send_interactive_list(phone: str, title: str, body: str, sections: list):
    """Evolution sendList Message"""
    url = f"{settings.EVOLUTION_API_URL}/message/sendList/{settings.EVOLUTION_INSTANCE}"
    payload = {
        "number": phone,
        "title": title,
        "body": body,
        "buttonText": "Ver opções",
        "sections": sections
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers={
            "Content-Type": "application/json",
            "apikey": settings.EVOLUTION_API_KEY
        })
    return response.json()

async def send_interactive_buttons(phone: str, text: str, buttons: list):
    """Evolution sendButtons Message"""
    url = f"{settings.EVOLUTION_API_URL}/message/sendButtons/{settings.EVOLUTION_INSTANCE}"
    payload = {
        "number": phone,
        "text": text,
        "buttons": buttons
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, json=payload, headers={
            "Content-Type": "application/json",
            "apikey": settings.EVOLUTION_API_KEY
        })
    return response.json()
```

### Trade-off: List vs Buttons vs Carousel

| Tipo | Quando usar | Limitações |
|------|------------|-----------|
| **List Message** | Menu inicial, múltiplas opções | 1 botão "Ver opções" + até 10 sections x 10 rows |
| **Buttons** | Ação única, confirmação | Máximo 3 botões (quickreply ou URL) |
| **CTA** | Link externo (agenda, site) | Só 1 botão URL |
| **Carousel** | Showcase serviços | Evolution 2.4+ apenas, staging primeiro |

---

## PARTE 15 — WhatsApp Business Solution Terms: Conformidade

### O que é permitido (agora claro)

```
✅ "Bot de atendimento da Refrimix que orienta, coleta dados e agenda visita."
✅ "Proveedor de IA como suporte ao negócio."
✅ Fine-tune com dados exclusivos (não públicos).
✅ Usar dados para IA aplicada exclusively ao serviço.
✅ Coletar dados operacionais em PostgreSQL.
✅ Respostas canônicas determinísticas + LLM para texto.
✅ Human handoff quando necessário.
✅ Dados reais para avaliação e otimização interna.
```

### O que é proibido

```
❌ "ChatGPT genérico dentro do WhatsApp Respondendo qualquer coisa."
❌ IA como funcionalidad principal do produto de IA.
❌ Treinar modelo público com dados de conversas.
❌ Vender "IA de atendimento" como produto independente.
❌ Mandarlogs para serviços de observabilidade públicos sem anonimização.
```

### Regras de Dados

```python
# Quando salvar conversa (PostgreSQL)
# - Anonimizar: não salvar número real em plaintext se não for necessário
# - phone mascara: 5513****9382 em logs / analytics
# - phone completo: só em tabelas operacionais (leads, appointments)
#
# Quando usar conversas para otimizar
# - Dados sintéticos: gerar exemplos artificias basés em padrões reais
# - Não enviar transcrições reais para APIs de fine-tuning externas
# - Se precisar treinar: fine-tune interno com modelo dedicado
```

---

## PARTE 16 — LID e Identificação de Contato (Evolution 2.4)

### O problema

WhatsApp adicionou `@lid` — identificador opaco/oculto que muda com o tempo. Número de telefone pode não ser надежным para Rastreamento de contato.

### Campos de identificação

| Campo | Onde vem | Uso |
|------|----------|-----|
| `phone` | Extrado doremoteJid | Identificação primária |
| `remoteJid` | payload.data.key.remoteJid | Canonical JID do WhatsApp |
| `lidJid` | Evolution 2.4 novo campo | Identificador oculto (alternativo) |
| `pushName` | payload.pushName | Nome display do contato |
| `instance` | RefrimixLead | Instância da Evolution |
| `messageId` | payload.data.key.id | Idempotência |

### Schema PostgreSQL atualizado

```sql
CREATE TABLE contacts (
    id SERIAL PRIMARY KEY,
    phone VARCHAR(20), -- mascarado em analytics
    remote_jid VARCHAR(100) UNIQUE NOT NULL,
    lid_jid VARCHAR(100), -- Evolution 2.4, pode ser NULL
    push_name VARCHAR(100),
    instance VARCHAR(50),
    first_seen_at TIMESTAMPTZ DEFAULT now(),
    last_seen_at TIMESTAMPTZ DEFAULT now(),
    opted_out BOOLEAN DEFAULT false
);

-- msgs com LID
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20),
    message_id VARCHAR(100) UNIQUE NOT NULL,
    remote_jid VARCHAR(100),
    lid_jid VARCHAR(100),
    direction VARCHAR(10) NOT NULL,
    content TEXT,
    raw_payload JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_messages_remote_jid ON messages(remote_jid);
CREATE INDEX idx_messages_lid_jid ON messages(lid_jid);
```

### Mapeamento de resposta interativa

Quando cliente clica em `rowId` da List Message, o payload recebido contém:

```json
{
  "event": "MESSAGES_UPSERT",
  "data": {
    "key": {
      "id": "XYZ789",
      "remoteJid": "5513996659382@s.whatsapp.net",
      "fromMe": false
    },
    "message": {
      "listResponseMessage": {
        "title": "Instalação de ar-condicionado",
        "listType": 1,
        "single-response": {
          "title": "Instalação",
          "rowId": "instalacao"
        }
      }
    }
  }
}
```

**Detectar click na List:**

```python
def extract_interactive_response(payload: dict) -> str | None:
    msg = payload.get("data", {}).get("message", {})
    # List Response
    if "listResponseMessage" in msg:
        return msg["listResponseMessage"]["single_response"]["rowId"]
    # Button Response
    if "buttonsResponseMessage" in msg:
        return msg["buttonsResponseMessage"]["selectedButtonId"]
    return None

# No webhook:
intent_key = extract_interactive_response(payload) or extract_text_from_conversation(payload)
```

---

## PARTE 17 — Eventos de Histórico (MESSAGES_SET)

### O problema

Evolution 2.4 dispara `MESSAGES_SET` quando histórico é sincronizado. Isso não é mensagem de lead — ésync.

### Filtro no webhook

```python
ALLOWED_EVENTS = {"MESSAGES_UPSERT"}  # ONLY user messages
SYNC_EVENTS = {"MESSAGES_SET", "MESSAGES_UPDATE", "MESSAGES_DELETE"}

@router.post("/webhook/evolution")
async def evolution_webhook(request: Request, payload: dict):
    event = payload.get("event")

    # Rejeitar eventos que não são mensagem de usuário
    if event not in ALLOWED_EVENTS:
        return {"status": "ok", "reason": f"event_{event}_ignored"}

    # Histórico sync: salvar apenas para analytics, não responder
    if event == "MESSAGES_SET":
        await save_historical_sync_to_analytics(payload)
        return {"status": "ok", "reason": "historical_sync_not_answered"}

    # fromMe: ignorar completamente
    if payload.get("data", {}).get("key", {}).get("fromMe"):
        return {"status": "ok", "reason": "fromMe"}

    # ... resto do fluxo
```

---

## PARTE 18 — Fluxo Interativo Completo (danstagrafico)

```
╔═══════════════════════════════════════════════════════════════╗
║                     ENTRADA (Evolution)                       ║
║  WhatsApp → MESSAGES_UPSERT → FastAPI webhook               ║
╚═══════════════════════════════════════════════════════════════╝
                              ↓
                    fromMe == true? → IGNORAR
                    event != MESSAGES_UPSERT? → IGNORAR
                    duplicate messageId? → IGNORAR
                              ↓
╔═══════════════════════════════════════════════════════════════╗
║                    DEBOUNCE (Redis, 5s)                        ║
║  Buffer: lead:{phone}:buffer — junta msgs quebradas          ║
║  Lock: lead:{phone}:debounce_lock — impede duplicado         ║
╚═══════════════════════════════════════════════════════════════╝
                              ↓
╔═══════════════════════════════════════════════════════════════╗
║                   LANGGRAPH (Worker isolado)                  ║
║                                                               ║
║  [normalize_message]                                          ║
║        ↓                                                       ║
║  [load_lead_context] (Redis cache优先级, Postgres fallback)    ║
║        ↓                                                       ║
║  [detect_intent]                                              ║
║    ├─ listResponseMessage.click → intent = rowId               ║
║    └─ conversation text → regex → intent_key                  ║
║        ↓                                                       ║
║  [detect_risk]                                                ║
║    ├─ disjuntor_cai / cheiro_queimado → ALTO → handoff        ║
║    └─ demais → BAIXO/MÉDIO                                    ║
║        ↓                                                       ║
║  [decide_action] (commercial_router determinístico)            ║
║        ↓                                                       ║
║  [generate_response]                                           ║
║    ├─ canonical_response (intent_blocks.json)                  ║
║    └─ llm_response (MiniMax, fallback)                         ║
║        ↓                                                       ║
║  [guardrail_check] → valida resposta                          ║
║        ↓                                                       ║
║  [send_whatsapp]                                               ║
║    ├─ texto simples → sendText                                ║
║    └─ interativo → sendList / sendButtons                      ║
╚═══════════════════════════════════════════════════════════════╝
                              ↓
╔═══════════════════════════════════════════════════════════════╗
║              INTERACTIVE RESPONSE (Evolution 2.4)            ║
║                                                               ║
║  ESTÁGIO 1 — LEAD FRIO                                        ║
║    └─ List Message: "Escolha uma opção"                       ║
║        → 8 rowId: instalacao, higienizacao, etc               ║
║                                                               ║
║  ESTÁGIO 2 — LEAD COM PROBLEMA                                ║
║    ├─ nao_gela → "Leva foto + bairro" (Buttons)              ║
║    ├─ pinga_agua → "Tirar foto + bairro" (Buttons)           ║
║    └─ barulho → "Descreve tipo barulho" (texto)              ║
║                                                               ║
║  ESTÁGIO 3 — RISCO ELÉTRICO ⚠️                                 ║
║    └─ "Manter desligado" + CTA "Falar com atendente"         ║
║       → handoff_required = true (Redis + Postgres)           ║
║                                                               ║
║  ESTÁGIO 4 — DADOS COMPLETOS                                  ║
║    └─ CTA "Verificar disponibilidade" (link agenda)          ║
║                                                               ║
║  ESTÁGIO 5 — CONVERSÃO                                        ║
║    └─ PIX payment link / signal request / appointment         ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## PARTE 19 — Arquivos Atualizados: Criar / Modificar / Deletar

### CRIAR (novos)

| Arquivo | Prior | Descrição |
|---------|-------|-----------|
| `refrimix_core/domain/intent_blocks.json` | 🔴 | Intent blocks + canonical + interativo |
| `refrimix_core/domain/canonical_response.py` | 🔴 | build_response() + interactive selector |
| `refrimix_core/domain/interactive_sender.py` | 🔴 | sendList, sendButtons, sendCarousel |
| `refrimix_core/domain/risk_detector.py` | 🔴 | detect_risk() + handoff flags |
| `refrimix_core/prompts/persona_ptbr_vendas.md` | 🔴 | System prompt completo |
| `refrimix_core/domain/llm_response.py` | 🟡 | MiniMax fallback + guardrails |
| `refrimix_core/domain/guardrail_validator.py` | 🟡 | Post-response validator |
| `refrimix_core/graph/nodes/` | 🔴 | 11 nodes do LangGraph |
| `refrimix_core/graph/agent.py` | 🔴 | LangGraph agent com Postgres checkpointer |
| `refrimix_core/db/idempotency.py` | 🟡 | Check + register idempotência |
| `scripts/migrate_contact_lid.sql` | 🟡 | Migration: contacts + messages com LID |
| `tests/integration/test_interactive_flow.py` | 🟡 | Smoke test interativo |

### MODIFICAR

| Arquivo | Mudança |
|---------|---------|
| `docker-compose.yml` | Adicionar `AsyncPostgresSaver` config; isolar Evolution version |
| `refrimix_core/domain/pipeline.py` | Wire `build_response()` + interactive selector |
| `.env.example` | Adicionar `WEBHOOK_SECRET`, `LANGGRAPH_CHECKPOINTER_URL`, `EvOLUTION_VERSION` |
| `app/api/webhook.py` | Adicionar `X-Webhook-Secret` validation + event filter (only MESSAGES_UPSERT) |
| `requirements.txt` | Documentar `httpx`, `langgraph`, `asyncpg` |

### DELETAR

| Arquivo | Por quê |
|---------|---------|
| `app/mvp_attendance.py` | Legacy LangGraph, duplica pipeline v2 |
| `agent_graph/` | Legacy LangGraph, não usado |

---

## PARTE 20 — Stack Final Recomendada

```
Evolution API:
  produção → 2.3.7 (sem licença, estável)
  staging  → 2.4.0-rc2 (interativos, LID, Manager v2)

FastAPI:
  webhook gateway
  idempotência
  validação de event + instance + secret
  salvar raw events em PostgreSQL
  enfileirar para Redis
  retorna 200 IMEDIATO

Redis:
  queue:refrimix_leads (fila de trabalho)
  lead:{phone}:buffer (5s debounce)
  lead:{phone}:debounce_lock (anti-duplicado)
  lead:{phone}:state (72h cache)
  lead:{phone}:handoff_required (24h flag)

PostgreSQL:
  contacts (phone, remoteJid, LID, pushName, instance)
  messages (idempotência, raw_payload, direction)
  lead_states (state JSONB)
  bot_decisions (intent_key, action_type, risk, handoff)
  appointments, quote_requests

LangGraph:
  Postgres checkpointer persistence
  thread_id = evolution:refrimix:{phone}
  11 nodes modulares
  idempotent effects (sendWhatsapp validation)

Qdrant (RAG_ENABLED=1):
  hybrid retrieval: dense + sparse + payload filters + rerank
  coleção: kb_hvac_br (intent, risk, service, categoria)
  só consulta quando intent != generic

LLM:
  MiniMax M2.7 (cloud) — texto natural
  Qwen2.5 7B — domain knowledge (staging)
  ambos via LiteLLM proxy

Interactive (Evolution 2.4):
  List Message — menu inicial
  Buttons — coleta de dado único
  CTA — link direto
  Carousel — showcase serviços (staging only)
```

---

## REGRA DE OURO FINAL
