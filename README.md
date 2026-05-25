# WhatsApp RAG Lead — Refrimix

> Regra P0 de segurança: `.env.example` é propositalmente mascarado com `{SECRET}`. Nenhum agente deve substituir placeholders por valores reais, pedir/imprimir segredos ou diagnosticar ambiente exibindo valores. Veja [.rules/secrets-env.md](.rules/secrets-env.md) e [env.schema.md](env.schema.md).

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

## Variáveis de Ambiente e Vault

O `.env.example` é propositalmente mascarado com `{SECRET}`. Esse placeholder é uma defesa contra vazamento por assistentes, agentes e revisões apressadas; não substitua por exemplos realistas de token, senha, telefone, host interno ou URL com credencial.

Valores reais ficam somente em `.env`, `.env.local`, vault ou configuração local do operador. Esses arquivos são ignorados pelo Git. O contrato operacional fica em [env.schema.md](env.schema.md), com tipo, obrigatoriedade, default seguro, origem e categoria de cada variável.

Fluxo seguro:

```bash
scripts/env-vault.sh edit
scripts/env-vault.sh sync
.venv/bin/python scripts/validate-env.py --env-file .env
```

`scripts/env-vault.sh sync` atualiza o `.env.example` mantendo valores mascarados. A validação mostra apenas nomes ausentes ou mascarados; ela nunca imprime tokens, senhas, URLs completas, telefones ou chaves.

Regras para agentes:

- Não remover `{SECRET}` do `.env.example`.
- Não transformar `.env.example` em arquivo com segredos realistas.
- Não pedir segredo real ao operador em chat quando a validação por nome for suficiente.
- Não imprimir `.env`, `.env.local`, token, senha, URL com senha, API key ou chave SSH.
- Em diagnósticos, listar somente nomes de variáveis faltantes.

No Compose, segredos da Evolution API devem vir do ambiente:

```env
AUTHENTICATION_API_KEY={SECRET}
EVOLUTION_DATABASE_URL={SECRET}
```

---

## Atendimento, Agenda e Intervenção Humana

O bot diferencia três situações antes de responder:

- `new_lead`: contato sem serviço anterior identificado. O fluxo coleta serviço, cidade/bairro e dados mínimos para orçamento ou agenda.
- `active_customer`: existe registro em `customer_services` com status ativo (`scheduled`, `in_progress`, `awaiting_parts`, `awaiting_customer`, `approved`, `active`). O bot trata como acompanhamento de serviço, não como lead novo, e alerta o `OWNER_PHONE`.
- `past_customer`: existe último serviço concluído/encerrado, mas nenhum serviço ativo. O bot pergunta se é dúvida do atendimento anterior ou novo atendimento.

### Pausa por atendimento humano

Quando um humano assumir um contato, pause a IA só para aquele telefone:

```bash
curl -X POST http://localhost:8000/bot/takeover/{TELEFONE_TESTE}
curl http://localhost:8000/bot/takeover/{TELEFONE_TESTE}
curl -X POST http://localhost:8000/bot/release/{TELEFONE_TESTE}
```

Contrato Redis equivalente:

```bash
redis-cli SETEX manual_takeover:{TELEFONE_TESTE} 86400 1
redis-cli GET manual_takeover:{TELEFONE_TESTE}
redis-cli DEL manual_takeover:{TELEFONE_TESTE}
```

Enquanto `manual_takeover:{phone}=1`, o worker registra `Humano assumiu; IA pausada para este contato` e não chama o LangGraph nem envia resposta automática.

### Pontuação de agendamento

`appointment_score` mede quando já há dados suficientes para focar em agenda:

- `+2` tipo de serviço.
- `+2` cidade/bairro.
- `+2` intenção de agendar, visita ou técnico.
- `+1` nome.
- `+1` foto ou contexto técnico.
- `+1` janela preferida.

Com `appointment_score >= 5`, o estado vira `appointment_ready`, `pipeline_stage=ready_to_schedule`, `handoff_mode=soft_alert` e `handoff_reason=appointment_ready`.

### Alertas para OWNER_PHONE

O `OWNER_PHONE` é canal de decisão gerencial. Ele recebe alerta com telefone, motivo, última mensagem, resumo curto e próximo passo recomendado quando houver:

- `appointment_ready`: lead pronto para confirmar agenda.
- `no_context_needs_human_review`: segunda tentativa sem contexto suficiente.
- `active_service_followup`: cliente com serviço ativo pedindo acompanhamento.
- `complaint_or_risk`: reclamação forte, risco comercial ou jurídico.
- `explicit_handoff`: cliente pediu humano/atendente.
- `high_value_*`: VRF/VRV, dutos, splitão, piso-teto, cassete, sistema central, PMOC, laudo, ART, contrato, empresa, condomínio, restaurante, clínica, galpão ou múltiplos aparelhos.

Fora preço fixo de instalação simples e higienização de split, o bot não inventa valor: conduz para análise técnica de R$50 abatível se o orçamento for aprovado.

### Grupo Agenda Refrimix

O grupo operacional recebe apenas resumo de agenda. Ele não recebe alerta comercial de alto valor nem intervenção humana por padrão.

- 07:00 `America/Sao_Paulo`: agenda de hoje.
- 20:00 `America/Sao_Paulo`: agenda de amanhã.
- O envio usa `AGENDA_GROUP_JID`, não o nome do grupo.
- Se `AGENDA_GROUP_ENABLED=1` e `AGENDA_GROUP_JID` estiver vazio, o sistema registra warning e não envia.

Para descobrir o JID:

```bash
python scripts/find-whatsapp-group.py --name "Agenda Refrimix"
```

Depois copie o valor exibido para o `.env`:

```env
AGENDA_GROUP_JID=120363000000000000@g.us
```

Preview e envio manual:

```bash
python scripts/send-agenda-digest.py today --preview
python scripts/send-agenda-digest.py tomorrow --send
curl -s http://localhost:8000/bot/agenda/today
curl -s http://localhost:8000/bot/agenda/tomorrow
curl -X POST "http://localhost:8000/bot/agenda/send/tomorrow?send=false"
curl -X POST "http://localhost:8000/bot/agenda/send/tomorrow?send=true"
```

Rotas úteis:

- `GET /bot/agenda/today`
- `GET /bot/agenda/tomorrow`
- `POST /bot/agenda/send/today?send=false`
- `POST /bot/agenda/send/tomorrow?send=false`
- `POST /bot/agenda/send/date/{yyyy_mm_dd}?send=false`
- `GET /bot/groups` em ambiente local/dev para debug.

Testes focados:

```bash
.venv/bin/python -m pytest tests/test_agenda_digest.py tests/test_owner_high_value_alerts.py tests/test_manual_takeover.py
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
  --phone {TELEFONE_TESTE} \
  --service instalacao \
  --status scheduled \
  --address "Santos" \
  --window "terça à tarde" \
  --notes "instalação high-wall aprovada"
```

Para encerrar:

```bash
.venv/bin/python scripts/customer-service.py close --phone {TELEFONE_TESTE}
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
EVOLUTION_API_KEY={SECRET} .venv/bin/python -m sre.probes evolution-audio --phone {TELEFONE_TESTE}

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
