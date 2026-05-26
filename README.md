# WhatsApp RAG Lead — Refrimix

> Regra P0 de segurança: `.env.example` é propositalmente mascarado com `{SECRET}`. Nenhum agente deve substituir placeholders por valores reais, pedir/imprimir segredos ou diagnosticar ambiente exibindo valores. Veja [.rules/secrets-env.md](.rules/secrets-env.md).

Bot WhatsApp para pré-atendimento e agendamento da Refrimix Tecnologia.
O Will responde leads automaticamente, coleta dados e direciona para instalação simples (R$850) ou visita técnica (R$50).

---

## Arquitetura

```
[WhatsApp] → [Evolution API Docker]
                  ↓ webhook POST
            [FastAPI :8000]
                  ↓ Redis queue
            [worker — MVP determinístico]
                  ↓
            [PostgreSQL leads]
```

O pipeline MVP é **determinístico**: intent por regex + catálogo de respostas + árvore de decisão comercial. Nenhum LLM no caminho crítico quando `MINIMAL_MVP_ENABLED=1`.

Feature flags em `docker-compose.yml`:
- `MINIMAL_MVP_ENABLED=1` — pipeline determinístico ativo
- `RAG_ENABLED=0` — Qdrant desabilitado
- `TTS_ENABLED=0` — Chatterbox desabilitado
- `VISION_ENABLED=0` — análise de imagem desabilitada
- `GOOGLE_CALENDAR_ENABLED=0` — Google Calendar desabilitado

---

## Estrutura de Pastas

```
whatsapp-rag/
├── .env                          # segredos — nunca versionar
├── .env.example                  # contrato de variáveis (versionar)
├── docker-compose.yml            # Evolution API + FastAPI + Redis + PostgreSQL
│
├── bot.sh                        # liga/desliga IA em tempo real
├── git.sh                        # save / push rápido
├── sync.sh                       # gera CLAUDE.md e espelha Gitea → GitHub
│
├── scripts/
│   ├── reset-lead.py             # reset cirúrgico de lead para teste
│   ├── customer-service.py       # upsert/close de cliente em atendimento
│   ├── send-agenda-digest.py     # digest manual de agenda
│   ├── find-whatsapp-group.py    # descobre JID do grupo agenda
│   ├── env-vault.sh              # edição segura do .env
│   └── validate-env.py          # validação de variáveis
│
├── agent_graph/
│   ├── domain/
│   │   ├── response_catalog.py   # catálogo central de respostas MVP
│   │   ├── commercial_router.py  # decisão comercial determinística
│   │   ├── onboarding.py        # detecção de saudação
│   │   ├── field_policy.py       # política de coleta de campos
│   │   └── stage_engine.py      # engine de estágios e agenda
│   ├── nodes/
│   │   ├── understand_message.py # intent determinística (regex)
│   │   ├── plan_next_action.py   # planner determinístico
│   │   ├── reduce_lead_state.py  # reducer de estado
│   │   └── nodes.py             # 4390 linhas — dívida técnica
│   └── services/
│       ├── whatsapp.py           # sendText + presença Evolution
│       ├── conversation_memory.py # histórico canônico Redis
│       └── alerts.py            # alerta owner via WhatsApp
│
├── app/
│   ├── mvp_attendance.py         # pipeline MVP determinístico
│   ├── lead_repository.py       # CRUD Lead/LeadEvent Prisma
│   ├── main.py                   # FastAPI composition root
│   ├── runtime.py                # ponte worker ↔ API
│   ├── worker.py                 # worker Redis queue → resposta
│   ├── api/
│   │   ├── webhook.py            # entrada Evolution API → Redis
│   │   ├── bot.py               # controle on/off/takeover
│   │   ├── health.py            # saúde honesto
│   │   └── test_routes.py       # diagnósticos /test/*
│   ├── Dockerfile
│   └── requirements.txt
│
├── prisma/
│   └── schema.prisma             # leads + lead_events
│
└── tests/                        # 155 testes (filtrados por conftest)
    ├── conftest.py              # filtra legacy quando MINIMAL_MVP_ENABLED=1
    └── test_*.py                # testes MVP determinístico
```

**Regra de ouro:** só edite `.env` sem rebuild. Todo o resto exige `docker compose build fastapi-rag`.

---

## Variáveis de Ambiente e Vault

O `.env.example` é propositalmente mascarado com `{SECRET}`. Valores reais ficam em `.env` (gitignored).

```bash
scripts/env-vault.sh edit
scripts/env-vault.sh sync
.venv/bin/python scripts/validate-env.py --env-file .env
```

---

## Operações

### Subir a stack

```bash
docker compose up -d
curl -s http://localhost:8000/health
```

### Ligar e Desligar o Bot

```bash
./bot.sh on      # liga a IA
./bot.sh off     # pausa a IA
./bot.sh toggle  # alterna o estado
./bot.sh status  # confirma o estado
```

Painel visual: `http://localhost:8000/bot`

### Reset de lead para teste

```bash
.venv/bin/python scripts/reset-lead.py 5513996659382
```

### Cadastrar cliente em atendimento

```bash
.venv/bin/python scripts/customer-service.py upsert \
  --phone 5513996659382 \
  --service instalacao \
  --status scheduled \
  --address "Guarujá" \
  --window "terça à tarde"
```

### Testar sem WhatsApp

```bash
# Resposta única
curl -X POST "http://localhost:8000/test/chat?message=Bom+dia&send=false"

# Suite de testes
.venv/bin/python -m pytest -vv
```

### Agenda de grupo

```bash
# Descobrir JID do grupo
python scripts/find-whatsapp-group.py --name "Agenda Refrimix"

# Digest manual
python scripts/send-agenda-digest.py today --preview
python scripts/send-agenda-digest.py tomorrow --send
```

---

## Git — Fluxo de Trabalho

```bash
./sync.sh --message "mensagem"  # gera CLAUDE.md, publica Gitea, espelha GitHub
git status --short
```

Fonte primária: Gitea remoto `origin`.
Espelho: GitHub remoto `github`.

---

## Monitoramento

```bash
# Logs ao vivo
docker logs -f whatsapp-rag-fastapi-rag-1 2>&1 | grep -E "INFO|ERROR"

# Health check
curl -s http://localhost:8000/health
```

---

## Dívida Técnica

- `agent_graph/nodes/nodes.py` (4390 linhas) — mantido como está. É usado pelo caminho LangGraph fallback (`MINIMAL_MVP_ENABLED=0`) e importa utilitários no caminho MVP. Não refatorar agora.
- `knowledge/refrimix/` (23 arquivos) — KEEP_DISABLED. O `playbook_loader.py` ainda importa YAMLs daqui para o caminho LangGraph fallback.
- Módulos desabilitados por feature flag: TTS, STT, Vision, Calendar, Google Sheets, RAG — mantidos no repo para preservação.

---

## Preços Oficiais (codificados em `commercial_router.py`)

| Serviço | Preço | Condição |
|---------|-------|----------|
| Instalação simples | R$ 850 | Até 3m tubulação, ponto elétrico pronto, acesso fácil |
| Higienização | R$ 200/aparelho | Split padrão, funcionando |
| Visita técnica | R$ 50 | Abatido do orçamento se aprovado |

Regra: **foto não é bloqueadora** — se o cliente não tiver ou não souber tirar, avança para Visita Técnica de R$50.
