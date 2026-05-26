# PRD — Refrimix HVAC-R Bot v2.2

**Data:** 2026-05-26
**Branch:** agent/refrimix-core-v2
**Repo:** /home/will/workspace/whatsapp-rag-clean
**Fase:** Phase 3 SPECIFY (socrates-dev-kit)
**Stack:** Evolution API 2.3.7 + FastAPI + LangGraph + PostgreSQL + Redis + MiniMax M2.7

---

## Problema

A Refrimix precisa qualifier leads de HVAC-R no WhatsApp em São Paulo. O bot atual é robótico demais — responde o mesmo para todo mundo, não sabe guiar o lead, e perde conversōes. Leads frios não convertem porque o bot não consegue coletar informaçōes suficiente nem detectar urgência. Casos elétricos (disjuntor caindo, cheiro de queimado) não recebem o alerta de segurança nem sāo encaminhados para humano.

O bot precisa: (1) saudar com menu interativo, (2) coletar sintomas e dados comerciais, (3) dar respostas canônicas baseadas em intent, (4) usar LLM apenas como fallback, (5) detectar risco elétrico com handoff obrigatório, (6) manter resposta em < 5s, (7) nunca inventar preço.

---

## Usuário-alvo

**Primário:** Leads interessados em instalaçāo ou manutençāo de ar-condicionado na regiāo de São Paulo, que encontram a Refrimix via WhatsApp.āt
**Secundário:** Clientes existentes com problemas em equipamentos jā instalados.āt
**Canal:** WhatsApp (via Evolution API 2.3.7) — texto apenas, sem audio/video
**Idioma:** PT-BR exclusivo — nenhum PT-PT, ES ou EN em textōs para usuārio

---

## Requisitos Funcionais

1. **Webhook Evolution API MESSAGES_UPSERT**
   - POST /webhook/evolution com validaçāo X-Webhook-Secret
   - Ignora fromMe=true silenciosamente (200 OK)
   - Rejeita eventos que nāo sejam MESSAGES_UPSERT (401)

2. **Idempotência por message_id (PostgreSQL)**
   - Tabela message_idempotency com message_id UNIQUE
   - Duplicate message_id retorna 200 OK silencioso
   - Payload hash para auditoria

3. **Debounce 5s para mensagens fragmentadas**
   - Redis lead:{phone}:buffer com TTL 7s
   - Redis lead:{phone}:debounce_lock com TTL 6s (nx=True)
   - Job sō entra na fila após janela de 5s fechar

4. **Intent classification (regex — existente, wired to new flow)**
   - understand_message.py jā tem classify_intent() com regex
   - intent_keys: nao_gela, disjuntor_cai, cheiro_queimado, barulho, instalacao, higienizacao, visita_tecnica, generic
   - Confiança da classificaçāo salva em bot_decisions

5. **Risk detection (low/medium/high + human handoff triggers)**
   - ALTO: disjuntor_cai, cheiro_queimado, fio_esquenta, tomada_derretida → human_handoff=true, "Manter equipamento desligado"
   - MEDIO: nao_gela, barulho → collect_symptoms
   - BAIXO: instalacao, higienizacao, generic → commercial flow

6. **Commercial routing (determinístico — existing commercial_router.py)**
   - action_types: offer_technical_visit, fixed_installation, hygienization, quote_custom
   - Preços fixos: R$850 instalaçāo, R$200/higienizaçāo, R$50 visita técnica
   - LLM nunca sobrepōe commercial_router

7. **Response generation: canonical blocks + LLM fallback**
   - 80% das intents → intent_blocks.json canonical_response
   - 20% (generic/complex) → MiniMax M2.7 com persona PT-BR
   - Guardrail: bloqueia preço inventado, diagnóstico definitivo, PT-PT/ES/EN

8. **Interactive messages: List Message, Buttons, CTA (Evolution 2.4 staging)**
   - List Message: menu inicial de opçōes
   - Buttons: coleta de dados (bairro, sintoma)
   - CTA: link para agendamento
   - Evolution 2.4.0-rc2 em staging; 2.3.7 em produção

9. **Human handoff for electric risk cases**
   - Redis lead:{phone}:handoff_required = "true" (TTL 24h)
   - PostgreSQL bot_decisions.handoff = true
   - Responde "Manter equipamento desligado" + instruçōes de seguranca

10. **PostgreSQL persistence: messages, lead_states, bot_decisions**
    - messages: todas (inbound + outbound), key, remoteJid, text, timestamp
    - lead_states: JSONB com intent_history, collected_fields, current_node
    - bot_decisions: intent_key, action_type, risk_level, response_text, llm_called, handoff, created_at
    - leads: phone (completo), pushName, created_at
    - message_idempotency: message_id, payload_hash, created_at

11. **Redis: queue, buffer, debounce lock, state cache**
    - queue:refrimix_leads — BLPOP com timeout 30s
    - lead:{phone}:buffer — lista de mensagens fragmentadas (TTL 7s)
    - lead:{phone}:debounce_lock — "1" enquanto processa (TTL 6s)
    - lead:{phone}:state — JSONB cache (TTL 72h)
    - lead:{phone}:handoff_required — flag handoff (TTL 24h)

---

## Requisitos Não-Funcionais

- **Response time:** webhook 200 OK < 500ms (enfileira e retorna)
- **LLM fallback:** < 5s response time p95
- **Availability:** 24/7
- **PT-BR only:** sem PT-PT, ES ou EN em user-facing text; blocklist de palavras europeias
- **No data leakage:** phone mascarado em analytics (5513****9382); secrets nunca em log
- **Evolution 2.3.7 produção** (sem licenca requerida)
- **InMemorySaver BANNED:** usar AsyncPostgresSaver em producao
- **Sem FLUSHALL:** deleção por key especifica
- **Sem latest em Docker:** versões pinadas
- **Response length:** max 500 caracteres, max 2 perguntas por mensagem

---

## Critérios de Aceitação

- "oi" do lead → welcome List Message com opçōes de servico em < 5s
- "meu ar não gela" → canonical response "Entendi..." + coletando sintomas (condensadora? visor?)
- "disjuntor cai" → "Manter equipamento desligado" + alert + handoff_flag=true
- "limpeza" ou "higienizacao" → canonical response + R$200/aparelho
- duplicate message_id → silently ignored (200 OK, nada na fila)
- fromMe=true → silently ignored (200 OK, nāo processa)
- interativo click → intent=rowId (List Message selection vira intent, sem regex)
- PostgreSQL: bot_decisions populated após cada interaçao (intent_key, action_type, risk_level, handoff)
- Redis queue: job consumido dentro de 10s após webhook return
- lead com risco alto: handoff_flag em Redis + bot_decisions.handoff=true

---

## Fora de Escopo

- QR code management (Evolution API cuida)
- Audio/video messages (texto apenas)
- Multi-language (PT-BR only — blocklist de PT-PT, ES, EN)
- Fine-tuning com dados reais de clientes
- VRF/cassette complex project estimation (coleta dados apenas, sem preço)
- RAG/Qdrant para MVP (RAG_ENABLED=0 por enquanto; Qdrant é knowledge base, não decisão)
- TTS/Vision/STT para MVP (TTS_ENABLED=0, VISION_ENABLED=0, STT_ENABLED=0)

---

## Métricas de Sucesso

- **Intent classification accuracy:** > 85% (revisão manual de bot_decisions)
- **Lead conversion rate:** > 15% first interaction → scheduled visit
- **Handoff rate for electric risk:** 100% (todo caso elétrico recebe handoff_flag)
- **Response time p95:** < 3s (LLM fallback)
- **Zero false handoffs:** nenhum caso não-elétrico recebe risk=high
- **Duplicate tracking:** 0 respostas duplicadas para mesmo message_id

---

## Roadmap de Implementação

- **Phase 1:** canonical_response + risk_detector (sem LLM, intent_blocks.json)
- **Phase 2:** LangGraph com Postgres checkpointer + AsyncPostgresSaver
- **Phase 3:** debounce + idempotency infrastructure (Redis + PostgreSQL)
- **Phase 4:** LLM fallback (MiniMax M2.7) para generic intents
- **Phase 5:** interactive messages + Evolution 2.4.0-rc2 staging
- **Phase 6:** observability dashboard (metrics em bot_decisions)

---

## Arquitetura Simplificada (Canonical)

```
WhatsApp
  ↓ (MESSAGES_UPSERT webhook)
FastAPI /webhook/evolution
  ├─ X-Webhook-Secret validation
  ├─ fromMe check
  ├─ message_id idempotency (PostgreSQL)
  ├─ raw message → messages table
  └─ 200 OK < 500ms + Redis queue:refrimix_leads
        ↓ (BLPOP, 30s timeout)
Worker Python (separate process)
  ├─ Redis debounce (5s window)
  ├─ Load lead_state (Redis cache → PostgreSQL fallback)
  ├─ classify_intent (regex from understand_message.py)
  ├─ detect_risk (high/medium/low + handoff triggers)
  ├─ commercial_router (deterministic, prices from catalog)
  ├─ generate_response (canonical_blocks.json → LLM fallback)
  ├─ guardrail_check (forbidden patterns, price, language)
  ├─ save_decision (bot_decisions + lead_states in PostgreSQL)
  └─ send_whatsapp (Evolution sendText API)
        ↓
WhatsApp reply
```

---

## Anti-padrōes Bloqueados

- ❌ Implementar sem PRD primeiro
- ❌ InMemorySaver em producao
- ❌ datetime.utcnow() — usar datetime.now(timezone.utc)
- ❌ FLUSHALL no Redis
- ❌ latest tag em Docker
- ❌ Commits monolíticos
- ❌ LLM decidindo preço ou sobrepondo commercial_router
- ❌ PT-PT/ES/EN em user-facing text