# Constitution — Refrimix HVAC-R Bot v2.2

**Data:** 2026-05-26
**Branch:** agent/refrimix-core-v2
**Repo:** /home/will/workspace/whatsapp-rag-clean

---

## Princípios Invioláveis

- Peças no quadrado: cada componente faz UMA coisa — Evolution=canal, FastAPI=gateway, LangGraph=fluxo, Qdrant=knowledge, PostgreSQL=truth
- Não inventar preço: preços fixos do commercial_router (R$850, R$200, R$50) — LLM nunca decide valor
- Risco elétrico = handoff: disjuntor_cai, cheiro_queimado, fio_esquenta, tomada_derretida → "Manter equipamento desligado" + human_handoff flag
- PT-BR only: output, blocklist, prompts — tudo em português brasileiro
- commercial_router é autoridade: decisão comercial determinística, LLM nunca sobrepõe
- Sem latest em Docker: versões pinadas em todos os ambientes
- Sem FLUSHALL: nunca limpar Redis com flushall — usar deleção por key
- Sem vibe-coding: sem spec não se escreve código ( Constitution → PRD → Plan → Tasks → Implement)
- fromMe sempre ignorado: mensagens do próprio bot não são processadas

---

## Stack e Versões Pinadas

- **Evolution API:** 2.3.7 (produção), 2.4.0-rc2 (staging/lab)
- **Python:** 3.12+
- **FastAPI:** newest stable
- **PostgreSQL:** host-exposed (sem container)
- **Redis:** host 6379 (sem container)
- **LangGraph:** com AsyncPostgresSaver (nunca InMemorySaver em produção)
- **MiniMax M2.7** (produção), **Qwen2.5 7B** (staging)

---

## Regras de Segurança

- Secrets nunca versionados: .env no .gitignore, .env.example como contrato
- Secrets nunca em print/log: usar masking explícito
- Idempotência: message_id único no PostgreSQL (tabela message_idempotency)
- fromMe: sempre ignorar com 200 OK silencioso
- X-Webhook-Secret: validado no webhook antes de qualquer processamento
- MESSAGES_UPSERT only: outros eventos rejeitados no webhook (MESSAGES_SET, etc.)
- Forbidden patterns bloqueados: diagnóstico definitivo ("falta de gás com certeza"), preço inventado ("valor fechado"), PT europeu, espanhol, "¿"
- Response length: máximo 500 caracteres, máximo 2 perguntas

---

## Regras de Dados

- Phone mascarado em analytics: 5513****9382
- Phone completo: só em tabelas operacionais (contacts, messages, appointments)
- Dados para fine-tune: sintéticos, não reais — nunca alimentar modelo público com conversas reais
- Anonimização: logs/analytics não expõem phone real

---

## Convenções de Código

- `datetime.now(timezone.utc)` — NUNCA `datetime.utcnow()`
- Commits atômicos: 1 conceito por commit, reversível
- Branch: `agent/refrimix-core-v2`
- MINIMAL_MVP_ENABLED=1 mantido no path crítico
- Response catalog: canonical (intent_blocks.json) + LLM fallback — não mais strings em response_catalog.py
- Commercial router preserva preços: R$850 instalação, R$200 higienização, R$50 visita

---

## Fronteiras de Arquitetura (CANONICAL)

| Componente | Faz | NÃO faz |
|---|---|---|
| Evolution API | WhatsApp channel, send/receive | Decisão comercial, diagnóstico |
| FastAPI webhook | validate, idempotência, enfileira | Processa LLM, lógica crítica |
| Redis | Fila, debounce(5s), cache, lock | Verdade operacional |
| PostgreSQL | Leads SOURCE OF TRUTH, messages, bot_decisions | Busca vetorial |
| Qdrant | Hybrid search (dense+sparse+filter+rerank) | Decisão |
| LangGraph | Fluxo+estado+decisão+handoff | FAQ, resposta simples |
| interactive (EVO 2.4) | Menu inicial (List), coleta (Buttons), link (CTA) | Conversa longa |

---

## NÃO ESQUECER

- **Human handoff triggers:** disjuntor_cai, cheiro_queimado, fio_esquenta, tomada_derretida
- **Response para risco elétrico:** "Manter equipamento desligado" + handoff flag
- **Interactive messages:** List Message (menu), Buttons (ação), CTA (link)
- **Evolution 2.4 license:** só em staging, NUNCA production (2.3.7)
- **Checklist de implementação:** PARTE 12 do super-blueprint v2.2

---

## Anti-padrões BLOQUEADOS

- ❌ Implementar sem spec → exige PRD primeiro
- ❌ Commits monolíticos → exige atomicidade
- ❌ `latest` em produção → versões pinadas
- ❌ `datetime.utcnow()` → usar `datetime.now(timezone.utc)`
- ❌ `InMemorySaver` em produção → AsyncPostgresSaver
- ❌ FLUSHALL no Redis → deleção por key
- ❌ PT-PT termos na blocklist: `instalação`, `manutenção` são PT-BR legítimos — bloquear só `telemóvel`, `contactar`, `morada`, `marcação`
