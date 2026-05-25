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
Repositório primário: Gitea remoto `origin`.
Espelho público/externo: GitHub remoto `github` (`https://github.com/zapprosite/whatsapp-rag.git`).

## Arquitetura

```
[WhatsApp] → [Evolution API Docker :8080]
                  ↓ webhook POST
            [FastAPI + LangGraph :8000]
              ↓ Redis queue     ↓ worker_loop
         [Redis PC1:6379]   [LangGraph 8 nós]
                                  ↓
                 [Qdrant :6333] + [MiniMax/Groq]
```

## LangGraph — 8 Nós

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
8. Voz em produção deve ficar em `TTS_ENGINE=chatterbox` + `TTS_LOCALE=pt-BR` enquanto `.venv/bin/python -m sre.probes tts-audit --require-chatterbox-pt` estiver verde; `OmniVoice` é fallback seguro.
9. Antes de aceitar mudança de voz/PC1/PC2, rode `.venv/bin/python -m sre.probes tts-audit`; para sample local sem WhatsApp real, use `--synthesize`.
10. `5513974139382` é a linha Refrimix/QR lido; `5513996659382` é gerente/crons. Eventos `fromMe=true` desses números devem ser ignorados pelo bot.
11. Copy, PDF, prompts e mensagens de cliente devem seguir `.rules/pt-br.md`: português brasileiro por padrão; inglês só para termos técnicos inevitáveis.
12. Secrets/env seguem `.rules/secrets-env.md`: `{SECRET}` em `.env.example` é proteção intencional; nenhum agente deve trocar placeholders por valores reais, imprimir segredos ou diagnosticar ambiente mostrando valores.

## Guardrail P0 de Secrets

- `.env.example` deve continuar mascarado com `{SECRET}`.
- Valores reais ficam apenas em `.env`, `.env.local`, vault ou configuração local ignorada pelo Git.
- Diagnóstico de ambiente deve usar `.venv/bin/python scripts/validate-env.py --env-file .env` e listar somente nomes faltantes.
- Se aparecer segredo versionado, trocar por `${VAR}`, documentar em `env.schema.md` e recomendar rotação sem repetir o valor.

## Documentação e Espelho Git

- `AGENTS.md` é a primeira leitura obrigatória para qualquer agente.
- `CLAUDE.md` é arquivo gerado. A fonte canônica fica em `.context/docs/*.md`.
- Nunca edite `CLAUDE.md` manualmente. Edite `.context/docs/*.md` e rode `./sync.sh`.
- O fluxo correto de publicação é `origin` (Gitea) primeiro e `github` depois.
- Para publicar mudanças: `./sync.sh --message "sync: descreve a mudança"`.
- Para espelhar algo que já está no Gitea: `./sync.sh --mirror-only`.
- O GitHub não é fonte primária; ele é espelho do Gitea.
