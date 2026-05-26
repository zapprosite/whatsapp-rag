# Auditoria FASE 0 — Reversa Rebuild WhatsApp-RAG
**Data:** 2026-05-26
**Hora:** ~09:00 BRT
**Branch:** `feature/proxima-tarefa-20260526` (HEAD: 9e6a80e4cb9ffa030a0986161d4e8b26379f072b)
**Git Status:** limpo (nada pendente)

---

## Visão Geral

Este documento registra o estado do repositório no início do processo de reconstrução Reversa.
O objetivo é criar um core novo, paralelo ao atual, que seja determinístico, rastreável e operável.
Nada é apagado no início. O core atual permanece funcional até que o novo core passe nos testes de paridade.

---

## Inventário de Entrada

### Filesystem Principal

```
whatsapp-rag/
├── agent_graph/
│   ├── domain/
│   │   ├── actions.py          # NextActionType enum (20 actions)
│   │   ├── commercial_router.py # decide_commercial_path (5 paths)
│   │   ├── field_policy.py
│   │   ├── lead_mind.py
│   │   ├── onboarding.py        # greeting_by_time
│   │   ├── stage_engine.py
│   │   └── stages.py
│   ├── graph/
│   │   └── graph.py            # LangGraph StateGraph, 15 nós
│   ├── guards/
│   │   ├── language_guard.py   # CJK/Arabic/Cyrillic block + pt-BR validation
│   │   ├── response_guard.py
│   │   └── security_guard.py
│   ├── nodes/
│   │   ├── nodes.py            # 4380 linhas - LLM calls, response helpers, classify_service
│   │   ├── understand_message.py  # 151 linhas - message understanding
│   │   ├── reduce_lead_state.py    # 184 linhas - lead state reducer
│   │   ├── compose_response.py     # 264 linhas - action → response composer
│   │   ├── plan_next_action.py
│   │   └── dispatch_side_effects.py
│   ├── services/
│   │   ├── alerts.py
│   │   ├── calendar.py
│   │   ├── conversation_memory.py
│   │   ├── google_sheets.py
│   │   ├── leads_export.py
│   │   ├── playbook_loader.py
│   │   ├── speech_adapter.py
│   │   ├── stt.py
│   │   ├── tts.py
│   │   ├── vision.py
│   │   └── whatsapp.py
│   └── utils/
│       ├── context_window.py
│       ├── llm_output.py
│       └── resilience.py
├── app/
│   ├── api/
│   │   ├── webhook.py          # Evolution webhook parser
│   │   ├── health.py
│   │   ├── test_routes.py
│   │   └── bot.py
│   ├── config/
│   ├── services/
│   ├── worker.py               # 932 linhas - Redis queue consumer
│   ├── runtime.py
│   ├── main.py
│   └── agenda_scheduler.py
├── prisma/
│   └── (schema com Lead, LeadEvent, CustomerServices)
├── qdrant/
│   ├── hvac_top100.py
│   ├── seed_hvac.py
│   └── rag_documents.py
├── docs/
│   └── mapa-pc1-pc2-refinamento.md
├── .env                        # valores reais (não versionar)
├── .env.example               # contrato mascarado
├── env.schema.md
├── docker-compose.yml
├── sync.sh
└── tests/
    ├── test_bot_control.py
    ├── test_manual_takeover.py
    ├── test_ptbr_guardrails.py
    ├── test_sre_probes.py
    └── test_tts_ptbr.py
```

### Tamanho do Código Principal

| Arquivo | Linhas | Responsibility |
|---|---|---|
| agent_graph/nodes/nodes.py | 4380 | LLM calls, response helpers, classify_service, system prompt |
| app/worker.py | 932 | Redis queue consumer, lock, dedup, sendWhatsApp |
| agent_graph/nodes/nodes.py (continuação) | — | Tudo que não coube nos outros nodes |
| agent_graph/graph/graph.py | 160 | LangGraph StateGraph |
| agent_graph/nodes/compose_response.py | 264 | Action → response composer |
| agent_graph/domain/commercial_router.py | 196 | 5 commercial paths |
| agent_graph/guards/language_guard.py | 209 | CJK/Arabic/Cyrillic + pt-BR guard |
| agent_graph/nodes/reduce_lead_state.py | 184 | Lead state reducer |
| agent_graph/nodes/understand_message.py | 151 | Message understanding |
| app/api/webhook.py | 349 | Evolution webhook parser |

**Problema identificado:** `nodes.py` com 4380 linhas acumula LLM calls, response helpers, classify_service, system prompt e dezenas de funções soltas. Isso viola o princípio de separação de concerns.

### Contratos Operacionais Existentes

#### Commercial Router (5 paths)

```
fixed_installation_simple  → R$850 (validate all fields)
fixed_hygienization        → R$200/aparelho (validate cooling)
technical_visit_50         → R$50 (default for missing info)
project_quote              → R$50 + owner_alert (VRF/cassete/etc)
ask_basic_service          → ask which service
```

#### Actions (20 types)

```
welcome_onboarding
ask_lead_name
ask_basic_service
ask_optional_contact_info
offer_fixed_installation    → R$850 + ask window
offer_fixed_hygienization   → R$200 + ask quantity
offer_technical_visit       → R$50 + ask window
offer_project_visit         → R$50 + ask city/bairro
answer_question
explain_process
answer_capability_question
ask_missing_field
save_preferred_window
offer_calendar_slots
confirm_calendar_slot
handoff_human
reject_security
active_service_followup
fallback_recover_context
```

#### Language Guard

- Block: CJK, Arabic, Cyrillic, Korean, Japanese, Chinese
- Block: Portuguese from Portugal terms (telemóvel, contactar, morada, marcação)
- Block: Spanish terms (presupuesto, mantenimiento, instalación, aire acondicionado)
- Fallback: sanitize_hard → fallback determinístico
- Retry cascade: LLM retry → Groq repair → sanitize → fallback determinístico

#### Modality Policy

- text input → text output
- audio input + TTS_ENABLED=1 → audio output (Chatterbox PC1)
- audio input + TTS_ENABLED=0 → text output
- image input → text output (Vision only if VISION_ENABLED=1)
- typing presence before text
- recording presence only before actual audio

### Lacunas Identificadas

1. **`response_catalog.py` não existe** — as respostas determinísticas estão embutidas em `compose_response.py` e `nodes.py`. O usuário exige que seja um arquivo separado e determinístico.

2. **`lead_state.py` não existe** — o schema do LeadState está disperso em múltiplos arquivos. O usuário exige schema explícito.

3. **`field_policy.py` existe** mas a lógica de quando perguntar está parcialmente em `nodes.py`.

4. **`text_normalizer.py` não existe** — normalização de texto ("1" → quantidade, "um" do STT → quantity) está em `reduce_lead_state.py`.

5. **Sistema de prompt gigante no `nodes.py`** — o WILL_SYSTEM_PROMPT tem ~4000 caracteres e mora no mesmo arquivo das funções de LLM. Deve ser isolado.

6. **Pipeline LangGraph faz demais** — o grafo atual tem 15 nós; o novo pipeline exige apenas ~10 nós seguindo o fluxo:
   ```
   webhook → redis queue → worker → load/create lead
   → understand_message → reduce_lead_state → commercial_router
   → plan_next_action → response_catalog → sendText → save LeadEvent
   ```

7. **Higienização com quantidade** — o fluxo "pergunta quantidade → cliente responde '1' → salvar → agendar" depende de `short_answer` no `understand_message` e `_apply_short_answer` no `reduce_lead_state`. Precisa ser explicitado como regra.

8. **Audio/STT pipeline** — Groq/Grok STT transcreve áudio, transcript entra como texto no mesmo pipeline. Se STT falhar, fallback text determinístico.

9. **Vision** — Qwen2.5 7B Vision no PC2 analisa imagem só quando `message_type == imageMessage` e `VISION_ENABLED=1`. Não chamar Vision para texto.

10. **Modelo policy** — Qwen 3B no PC1 para classificação rápida, saudação e normalização. MiniMax-M2.7 para reasoning aberto. Nunca usar 3B para decisão comercial final.

---

## Estado do Git

```
HEAD: 9e6a80e4cb9ffa030a0986161d4e8b26379f072b
Branch: feature/proxima-tarefa-20260526
Status: limpo
Main: main (9 branches ahead, 4 behind)
```

---

## Configuração de Ambiente

O `.env` real está preservado e não versionado. O `.env.example` mantém o contrato mascarado com `{SECRET}` placeholders.

Variáveis críticas para o rebuild:
- `MINIMAX_API_KEY`, `MINIMAX_MODEL`, `MINIMAX_BASE_URL`
- `GROQ_API_KEY`, `GROQ_MODEL`
- `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`, `EVOLUTION_API_URL`
- `REDIS_URL`, `WHATSAPP_QUEUE_KEY`
- `DATABASE_URL` (Prisma)
- `LOCAL_QWEN_BASE_URL`, `LOCAL_QWEN_MODEL` (PC1)
- `TTS_ENGINE=chatterbox`, `CHATTERBOX_URL`, `TTS_ALLOW_CHATTERBOX_PTBR=1`

---

## Estratégia de Rollback

Se algo sair errado durante o rebuild:
1. Não tocar no `.env` ou vault
2. Não apagar volumes da Evolution
3. Manter `REFRIMIX_CORE_VERSION=legacy` como fallback
4. Commits do rebuild são todos no branch de feature — nunca no main diretamente
5. Health endpoint deve ser honesto sobre qual core está rodando

---

## Próximo Passo

Gerar `docs/reversa/inventory.md` (FASE 1 Reversa Inventory) com:
- arquivos mapeados
- regras extraídas com origem, arquivo, função, confiança
- gaps documentados
- risk map