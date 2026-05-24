---
source: CLAUDE.md
type: generic
---

# WhatsApp RAG Lead — Refrimix

## Contexto

Projeto: bot WhatsApp para onboarding e atendimento a leads da Refrimix Tecnologia.
Stack: Evolution API v2.3.7 Docker (8080) + FastAPI + LangGraph (8000) + Qdrant staging (6333) + Redis PC1 (6379).
Seis serviços KB: instalacao, consultoria, manutencao, pmoc, projeto-central, higienizacao.
Coleção Qdrant: `hermes_hvac_rag_service_staging` — 768 dimensões, cosine, 55 pontos.
Redis PC1: 192.168.15.83:6379.
PostgreSQL whatsapp_rag: 192.168.15.83:5432.

## Arquitetura

```
[WhatsApp] → [Evolution API Docker :8080]
                  ↓ webhook POST
            [FastAPI + LangGraph :8000]
              ↓ Redis queue     ↓ worker_loop
         [Redis PC1:6379]   [LangGraph 7 nós]
                                  ↓
                 [Qdrant :6333] + [MiniMax/Groq]
```

## LangGraph — 7 Nós

```
preprocess_input → classify_service → retrieve_knowledge → generate_response
→ language_guard_check → format_whatsapp → decide_response_modality
→ tts_voice_clone | dispatch_appointment_alert → save_interaction
```

## Routing LLM

- `onboarding`, `manutencao`, `instalacao`, `higienizacao` → Groq llama-3.1-8b-instant (~1s)
- `pmoc`, `consultoria`, `projeto-central` → MiniMax M2.7 (~7-15s, raciocínio)
- `classify_service` LLM override → Groq llama-3.3-70b-versatile (~1-2s)

## Regras de Código

1. `from __future__ import annotations` + type hints em todo arquivo Python
2. Nenhum segredo no código — só `os.getenv`
3. Redis usa `redis.asyncio`
4. LangGraph: `messages: Annotated[list[BaseMessage], add_messages]`
5. Não modificar Evolution API docker-compose
6. Histórico de conversa: sliding window 6 turnos, TTL 30min, chave `conv_history:{phone}`
7. Salvar histórico limpo: `messages_with_history + [AIMessage(ai_message)]` — não `messages_out`
