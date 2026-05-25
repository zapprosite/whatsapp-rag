# WhatsApp RAG Lead — Refrimix

Bot WhatsApp para onboarding e atendimento a leads da Refrimix Tecnologia.
O Will responde leads automaticamente, coleta dados de agendamento e escala para humano quando necessário.

---

## Arquitetura

```
[WhatsApp] → [Evolution API Docker :8080]
                  ↓ webhook POST
            [FastAPI + LangGraph :8000]
                  ↓ Redis queue
            [worker_loop]
              ↓ classify    ↓ RAG         ↓ gera resposta
         [Groq 70b]   [Qdrant :6333]  [Groq 8b / MiniMax M2.7]
                                          ↓
                              [Redis histórico] + [PostgreSQL leads]
```

Mapa operacional detalhado de PC1/PC2, dependências e refinamento:
[docs/mapa-pc1-pc2-refinamento.md](docs/mapa-pc1-pc2-refinamento.md).

Regra de copy e atendimento:
[.rules/pt-br.md](.rules/pt-br.md). Tudo que chega ao cliente deve nascer em português brasileiro; inglês fica restrito a termos técnicos inevitáveis.

### LangGraph — 8 nós em sequência

```
preprocess_input → classify_service → retrieve_knowledge → generate_response
→ language_guard_check → format_whatsapp → decide_response_modality
→ tts_voice_clone | dispatch_appointment_alert → save_interaction
```

### Routing de modelo LLM

| Intent | Modelo | Latência |
|--------|--------|----------|
| `onboarding`, `manutencao`, `instalacao`, `higienizacao` | Groq llama-3.1-8b-instant | ~1s |
| `pmoc`, `consultoria`, `projeto-central` | MiniMax M2.7 | ~7-15s |
| Classificação (LLM override) | Groq llama-3.3-70b-versatile | ~2s |

---

## Estrutura de Pastas

```
whatsapp-rag/
├── .env                          # segredos — nunca versionar
├── .env.example                  # contrato de variáveis (versionar)
├── .gitignore
├── docker-compose.yml            # Evolution API + FastAPI
│
├── bot.sh                        # liga/desliga IA em tempo real
├── git.sh                        # save / push / merge rápido
├── refinar.py                    # loop interativo de refinamento
├── sync.sh                       # gera CLAUDE.md e espelha Gitea -> GitHub
├── scripts/customer-service.py    # marca cliente com serviço em andamento
│
├── sre/
│   └── probes.py                 # smoke, stress e probes Evolution sem coleta pytest
│
├── agent_graph/
│   ├── graph/
│   │   └── graph.py              # StateGraph + edges + routing
│   ├── guards/
│   │   └── language_guard.py     # anti-CJK/cirílico dual-layer
│   ├── nodes/
│   │   └── nodes.py              # 8 nós + WILL_SYSTEM_PROMPT + SCORE_MAP
│   └── services/
│       ├── alerts.py             # alerta WhatsApp dono + upsert lead Prisma
│       ├── stt.py                # Groq Whisper (transcrição de áudio)
│       ├── tts.py                # Chatterbox Multilingual primário + OmniVoice fallback
│       └── vision.py             # Groq Vision (análise de imagens)
│
├── app/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                   # FastAPI composition root
│   ├── runtime.py                # ponte com worker, Redis e envio WhatsApp
│   ├── api/
│   │   ├── webhook.py            # entrada Evolution API → Redis queue
│   │   ├── bot.py                # controle operacional /bot
│   │   ├── health.py             # saúde e root
│   │   └── test_routes.py        # diagnósticos /test/*
│   └── worker.py                 # worker_loop: Redis queue → LangGraph
│
├── prisma/
│   └── schema.prisma             # Interaction + Lead models
│
├── qdrant/
│   ├── hvac_top100.py            # top100 FAQ pt-BR/SP para RAG
│   └── seed_hvac.py              # recria coleção RAG e remove legado/sandbox
│
└── .context/
    └── docs/
        ├── project-rules.md      # regras do projeto → gera CLAUDE.md
        └── refinamento.md        # guia de refinamento → gera CLAUDE.md
```

**Regra de ouro:** só edite `.env` e `WILL_SYSTEM_PROMPT` sem rebuild. Todo o resto exige `docker compose build fastapi-rag`.

---

## Variáveis de Ambiente (`.env`)

```env
# Evolution API
AUTHENTICATION_API_KEY=sua_chave
SERVER_URL=https://seu-servidor.com
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_INSTANCE=RefrimixLead

# LLM
MINIMAX_API_KEY=sk-...
MINIMAX_MODEL=MiniMax-M2.7
GROQ_API_KEY=gsk_...

# Infraestrutura
REDIS_URL=redis://192.168.15.83:6379
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=hermes_hvac_rag_service_staging
DATABASE_URL=postgresql://USER:PASS@192.168.15.83:5432/whatsapp_rag

# Alertas
OWNER_PHONE=5513996659382

# Agenda opcional
GOOGLE_CALENDAR_ENABLED=0
GOOGLE_CALENDAR_ID=
GOOGLE_SERVICE_ACCOUNT_FILE=
GOOGLE_CALENDAR_TIMEZONE=America/Sao_Paulo

# Bot (opcional)
BOT_OFF_MESSAGE=Oi! Estou em atendimento agora, te respondo em breve 🙂

# Voz / TTS PC1
TTS_ENGINE=chatterbox
TTS_LOCALE=pt-BR
OMNIVOICE_URL=http://127.0.0.1:8202
CHATTERBOX_URL=http://127.0.0.1:8200
TTS_CHATTERBOX_LANGUAGE=pt
TTS_ALLOW_CHATTERBOX_PTBR=1
SSH_HOST_PC1=will-zappro@192.168.15.83
```

---

## Voz PT-BR / PC1

O TTS de produção é `Chatterbox Multilingual` no PC1, acessado via SSH porque a API roda em `127.0.0.1:8200` naquela máquina. O texto passa por normalização de fala brasileira antes da síntese: moeda, `3x`, `PMOC`, `ART`, `CREA`, `BTU`, links e markdown são convertidos para áudio mais natural.

`OmniVoice` fica como fallback seguro. `XTTS` foi removido do caminho de produção para não reintroduzir português genérico/locale errado. Só mantenha Chatterbox como primário se a auditoria confirmar modelo multilíngue/português:

```bash
.venv/bin/python -m sre.probes tts-audit
.venv/bin/python -m sre.probes tts-audit --synthesize
```

Para testar sem mandar WhatsApp real:

```bash
curl -X POST "http://localhost:8000/test/chat?message=Opa,+tudo+bem?&send=false"
```

---

## Subir / Atualizar o Container

```bash
# Build e sobe (primeira vez ou após mudança em nodes.py)
docker compose build fastapi-rag
docker rm -f whatsapp-rag-fastapi-rag-1
docker run -d --name whatsapp-rag-fastapi-rag-1 --network host --restart unless-stopped \
  --env-file .env \
  -e QDRANT_URL=http://127.0.0.1:6333 \
  -e QDRANT_COLLECTION=hermes_hvac_rag_service_staging \
  whatsapp-rag-fastapi-rag:latest

# Confirma saúde
curl -s http://localhost:8000/health
```

---

## Ligar e Desligar o Bot

Controle instantâneo sem restart. A rota `/bot/on` grava `whatsapp_rag:bot_enabled=1` no Redis, `/bot/off` grava `0`, e `/bot/toggle` alterna o estado atual. O painel e a API também gravam metadados em `whatsapp_rag:bot_state_meta`.

O worker consulta essa chave antes de chamar o LangGraph. Quando está pausado, a IA não conduz o atendimento no WhatsApp; se `BOT_OFF_MESSAGE` estiver preenchida, o cliente recebe essa mensagem de ausência.

```bash
./bot.sh on      # liga a IA no WhatsApp
./bot.sh off     # pausa a IA no WhatsApp
./bot.sh toggle  # alterna o estado atual
./bot.sh status  # confirma o estado real lido da API/Redis
```

**Painel visual** (celular ou browser):
```
http://localhost:8000/bot
```
Interruptor visual acessível, sem recarregar página, com atualização automática a cada 5s.

Se a API estiver em outra porta:

```bash
BOT_API_URL=http://localhost:8015 ./bot.sh status
```

**Mensagem de ausência** quando bot está off:
```env
BOT_OFF_MESSAGE=Oi! No momento estou em atendimento. Te retorno em breve 🙂
```
Se a variável não existir, o worker usa uma mensagem padrão. Defina `BOT_OFF_MESSAGE=` vazio para silêncio total.

**Validação operacional:**

```bash
curl -s http://localhost:8000/bot/status
./bot.sh off && ./bot.sh status
./bot.sh on && ./bot.sh status
```

Com o bot pausado, o log do worker deve mostrar `Bot PAUSADO; mensagem ... ignorada pela IA` quando chegar mensagem real.

---

## Refinar as Respostas

O ciclo de refinamento tem 4 níveis. **Sempre refine no nível mais baixo que resolve o problema.**

```
Nível 1 — Tom e persona    →  WILL_SYSTEM_PROMPT  (nodes.py)
Nível 2 — Conhecimento RAG →  chunks no Qdrant    (seed_hvac.py)
Nível 3 — Classificação    →  SCORE_MAP           (nodes.py)
Nível 4 — Modelo LLM       →  .env MINIMAX_MODEL
```

### Loop interativo — `refinar.py`

```bash
# Inicia o loop de refinamento
python3 refinar.py

# Ou já passa uma mensagem direto
python3 refinar.py "O ar tá fazendo barulho"

# Bateria semântica sem interação: 50 mensagens pt-BR/SP
python3 refinar.py --loop 50

# Mesma bateria reprovando também avisos de linguagem PT-BR/SP
python3 refinar.py --loop 50 --strict-ptbr
```

O script mostra a resposta do Will + intent + RAG hits e pergunta o que ficou errado:

| Opção | O que corrige | Onde mexe |
|-------|--------------|-----------|
| `1` Tom errado | Você digita como o Will deveria ter dito → vira exemplo no `WILL_SYSTEM_PROMPT` | `nodes.py` |
| `2` Regra nova | "NUNCA diga X" → vai para REGRAS ABSOLUTAS | `nodes.py` |
| `3` Intent errado | Você diz o serviço certo + keyword → `SCORE_MAP` | `nodes.py` |
| `4` Info faltando | Texto correto → chunk no Qdrant (re-indexa na hora) | `seed_hvac.py` |
| `5` Ver 3 variações | Mostra 3 respostas seguidas para checar consistência | — |

Depois de refinar, ainda no loop:
```
> rebuild       ← aplica tudo (faz build + restart do container)
> commit        ← salva na feature branch sem rebuild
> sair          ← pergunta se quer rebuild antes de sair
```

### Cliente com serviço em andamento

Quando o cliente já fechou e voltar no WhatsApp, cadastre o serviço para o bot responder como acompanhamento, não como lead novo:

```bash
.venv/bin/python scripts/customer-service.py upsert \
  --phone 5513999999999 \
  --service instalacao \
  --status scheduled \
  --address "Santos" \
  --window "terça à tarde" \
  --notes "instalação high-wall aprovada"
```

Para encerrar:

```bash
.venv/bin/python scripts/customer-service.py close --phone 5513999999999
```

### Testar sem WhatsApp

```bash
# Suíte automatizada local
.venv/bin/python -m pytest

# Resposta única
curl -X POST "http://localhost:8000/test/chat?message=O+ar+tá+com+barulho&send=false"

# 3 variações da mesma mensagem (checa consistência)
curl -X POST "http://localhost:8000/test/refine?message=Quero+instalar+split"

# Acurácia dos 34 cenários E2E
curl -X POST "http://localhost:8000/test/e2e?start=0&limit=34&delay=0"
```

### Probes SRE

Os antigos scripts soltos da raiz foram consolidados em `sre.probes`. Eles são checks operacionais manuais e não rodam durante o pytest.

```bash
# Smoke do webhook: texto, audio e imagem
.venv/bin/python -m sre.probes webhook-smoke

# Carga concorrente do webhook
.venv/bin/python -m sre.probes webhook-stress --requests 30 --concurrency 10

# Endpoints de audio da Evolution API
EVOLUTION_API_KEY=... .venv/bin/python -m sre.probes evolution-audio --phone 5513996659382

# Auditoria PC2 + TTS PC1 (OmniVoice/Chatterbox/vozes)
.venv/bin/python -m sre.probes tts-audit
```

### Vault Local

O `.env` deste projeto segue o mesmo padrão do Hermes: valores reais ficam só em `.env`, e o contrato versionado fica em `.env.example` com segredos mascarados.

```bash
scripts/env-vault.sh edit
scripts/env-vault.sh sync
```

### Nível 1 — Tom e persona (sem rebuild)

Edite `agent_graph/nodes/nodes.py` → `WILL_SYSTEM_PROMPT`.  
Adicione exemplos na seção `EXEMPLOS_VALIDADOS_START`:

```python
# EXEMPLOS_VALIDADOS_START
Lead: "Oi"
Will: "Ei! Sou o Will da Refrimix — cuida do seu ar aqui no Guarujá e região. O que tá precisando?"
# EXEMPLOS_VALIDADOS_END
```

Ou adicione/remova regras na seção `REGRAS ABSOLUTAS`.  
**Exige rebuild.**

### Nível 2 — Conhecimento RAG top100 (sem rebuild)

Edite `qdrant/hvac_top100.py` → lista `TOP100_FAQ`. Depois re-indexe:

```bash
source .venv/bin/activate
python3 qdrant/seed_hvac.py --prune-legacy
```

O Qdrant é consultado em runtime — não precisa rebuildar o container. O `--prune-legacy` remove coleções antigas/sandbox que não são usadas pelo runtime.

### Nível 3 — Classificação de intent

Edite `agent_graph/nodes/nodes.py` → `SCORE_MAP` dentro de `classify_service`.

```python
("laudo técnico", 4): "pmoc",    # adiciona keyword nova
("pmoc", 5): "pmoc",             # aumenta peso de keyword existente
```

**Exige rebuild.**

### Nível 4 — Modelo LLM

Edite `.env`:

```bash
MINIMAX_MODEL=MiniMax-M2.7   # versão mais recente, melhor raciocínio
GROQ_FALLBACK_MODEL=llama-3.3-70b-versatile  # Groq mais preciso
```

Reinicie o container sem rebuild (só lê `.env`):

```bash
docker rm -f whatsapp-rag-fastapi-rag-1 && \
docker run -d --name whatsapp-rag-fastapi-rag-1 --network host --restart unless-stopped \
  --env-file .env \
  -e QDRANT_URL=http://127.0.0.1:6333 \
  -e QDRANT_COLLECTION=hermes_hvac_rag_service_staging \
  whatsapp-rag-fastapi-rag:latest
```

---

## Como Não Quebrar

### O que pode editar com segurança

| Arquivo | Impacto | Precisa de rebuild? |
|---------|---------|---------------------|
| `.env` | Configs e chaves | Não (reinicia container) |
| `WILL_SYSTEM_PROMPT` em `nodes.py` | Tom do Will | Sim |
| `SCORE_MAP` em `nodes.py` | Classificação de intent | Sim |
| `qdrant/seed_hvac.py` | Conhecimento RAG | Não (re-seed via Python) |
| `docker-compose.yml` da Evolution API | **NÃO MEXA** | — |

### Antes de qualquer mudança grande

```bash
# Veja o estado atual
git status --short

# Cria um ponto de retorno
./sync.sh --message "backup: antes de refatorar X"
```

### Depois de uma mudança

```bash
# 1. Rebuilda sem recriar Evolution
docker compose up -d --build --no-deps fastapi-rag

# 2. Confirma que não quebrou nada
curl -X POST "http://localhost:8000/test/e2e?start=0&limit=34&delay=0" | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Acerto: {d[\"correct\"]}/{len(d[\"results\"])}')"

# 3. Salva se passou
./sync.sh --message "refina: descreve o que mudou"
```

### Para voltar uma mudança que quebrou

```bash
git log --oneline -10      # vê o histórico
git checkout <hash> -- agent_graph/nodes/nodes.py   # restaura arquivo específico
./sync.sh --message "revert: voltou nodes.py para versão estável"
```

---

## Git — Fluxo de Trabalho

```bash
./sync.sh --message "mensagem"  # gera CLAUDE.md, publica no Gitea e espelha no GitHub
./sync.sh --mirror-only         # espelha origin/main -> github/main sem commit local
git status --short              # arquivos modificados
git log --oneline -5            # últimos commits
```

Fonte primária: Gitea remoto `origin`.
Espelho: GitHub remoto `github` (`https://github.com/zapprosite/whatsapp-rag.git`).

---

## Monitorar em Tempo Real

```bash
# Logs ao vivo (filtra só o relevante)
docker logs -f whatsapp-rag-fastapi-rag-1 2>&1 | grep -E "INFO|ERROR|WARNING" | grep -v "HTTP Request"

# Ver leads salvos no PostgreSQL
ssh will-zappro@192.168.15.83 \
  "sudo -u postgres psql -d whatsapp_rag -c \
  'SELECT phone, service, address, window FROM leads ORDER BY created_at DESC LIMIT 10;'"

# Ver interações
ssh will-zappro@192.168.15.83 \
  "sudo -u postgres psql -d whatsapp_rag -c \
  'SELECT phone, intent, LEFT(response,80) FROM interactions ORDER BY created_at DESC LIMIT 5;'"
```
