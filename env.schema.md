# Schema de Ambiente

Este arquivo documenta o contrato operacional de ambiente sem valores reais. O `.env.example` deve continuar mascarado com `{SECRET}` quando a variavel puder revelar token, chave, telefone, host interno, URL operacional ou detalhe sensivel.

Categorias usadas: `placeholder_intencional_seguro`, `exemplo_seguro`, `valor_real_local_ignorado`, `possivel_segredo_versionado`, `valor_operacional_sensivel`, `config_obsoleta`, `config_sem_documentacao`.

| Variavel | Tipo | Obrigatoria | Default seguro | Origem | Categoria |
|---|---|---:|---|---|---|
| `ACTIVE_SERVICE_STATUSES` | lista CSV | nao | statuses internos | `.env` ou codigo | config_sem_documentacao |
| `AGENDA_DIGEST_DEDUP_TTL_SECONDS` | inteiro | nao | `90000` | `.env.example` | exemplo_seguro |
| `AGENDA_DIGEST_MAX_ITEMS` | inteiro | nao | `20` | `.env.example` | exemplo_seguro |
| `AGENDA_GROUP_DIGEST_TIMEZONE` | timezone | nao | `America/Sao_Paulo` | `.env.example` | exemplo_seguro |
| `AGENDA_GROUP_ENABLED` | booleano `0/1` | nao | `1` | `.env.example` | exemplo_seguro |
| `AGENDA_GROUP_JID` | identificador WhatsApp | nao | vazio | vault/config local | valor_operacional_sensivel |
| `AGENDA_GROUP_MORNING_DIGEST_HOUR` | inteiro | nao | `7` | `.env.example` | exemplo_seguro |
| `AGENDA_GROUP_MORNING_DIGEST_MINUTE` | inteiro | nao | `0` | `.env.example` | exemplo_seguro |
| `AGENDA_GROUP_NAME` | texto | nao | `Agenda Refrimix` | `.env.example` | exemplo_seguro |
| `AGENDA_GROUP_NIGHT_DIGEST_HOUR` | inteiro | nao | `20` | `.env.example` | exemplo_seguro |
| `AGENDA_GROUP_NIGHT_DIGEST_MINUTE` | inteiro | nao | `0` | `.env.example` | exemplo_seguro |
| `AGENDA_LOOKAHEAD_DAYS` | inteiro | nao | `7` | `.env.example` | exemplo_seguro |
| `AUTHENTICATION_API_KEY` | segredo | sim | nenhum | vault/config local | placeholder_intencional_seguro |
| `BOT_OFF_MESSAGE` | texto pt-BR | nao | mensagem padrao | `.env` ou codigo | config_sem_documentacao |
| `CHATTERBOX_URL` | URL operacional | nao | `http://127.0.0.1:8200` | vault/config local | valor_operacional_sensivel |
| `COMPLETED_SERVICE_STATUSES` | lista CSV | nao | statuses internos | `.env` ou codigo | config_sem_documentacao |
| `CONV_LOCK_REQUEUE_DELAY_SECONDS` | decimal | nao | `0.4` | codigo | config_sem_documentacao |
| `CONV_LOCK_TTL_SECONDS` | inteiro | nao | `240` | codigo | config_sem_documentacao |
| `CONV_LOCK_WAIT_SECONDS` | decimal | nao | `20` | codigo | config_sem_documentacao |
| `CONV_MAX_TURNS` | inteiro | nao | `6` | codigo | config_sem_documentacao |
| `CONV_TTL_SECONDS` | inteiro | nao | `1800` | codigo | config_sem_documentacao |
| `DATABASE_PROVIDER` | enum | nao | `postgresql` | `.env.example`/Compose | exemplo_seguro |
| `DATABASE_URL` | URL com possivel credencial | sim para Prisma/servicos DB | nenhum | vault/config local | placeholder_intencional_seguro |
| `ENVIRONMENT` | enum | nao | `local` | codigo | config_sem_documentacao |
| `EVOLUTION_API_KEY` | segredo | sim | nenhum | vault/config local | placeholder_intencional_seguro |
| `EVOLUTION_API_URL` | URL operacional | sim | `http://localhost:8080` | vault/config local | placeholder_intencional_seguro |
| `EVOLUTION_DATABASE_URL` | URL com credencial | sim para Evolution API no Compose | nenhum | vault/config local | valor_real_local_ignorado |
| `EVOLUTION_INSTANCE` | texto operacional | sim | nenhum | vault/config local | placeholder_intencional_seguro |
| `GH_TOKEN` | segredo | nao | nenhum | vault/config local | placeholder_intencional_seguro |
| `GITHUB_TOKEN` | segredo | nao | nenhum | vault/config local | placeholder_intencional_seguro |
| `GOOGLE_CALENDAR_ENABLED` | booleano `0/1` | nao | `0` | vault/config local | placeholder_intencional_seguro |
| `GOOGLE_CALENDAR_ID` | identificador | se agenda Google ativa | `primary` | vault/config local | placeholder_intencional_seguro |
| `GOOGLE_CALENDAR_TIMEZONE` | timezone | nao | `America/Sao_Paulo` | vault/config local | placeholder_intencional_seguro |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | caminho local | se agenda Google ativa | vazio | vault/config local | placeholder_intencional_seguro |
| `GRAPH_RESPONSE_TIMEOUT_SECONDS` | decimal | nao | `45` | `.env.example` | placeholder_intencional_seguro |
| `GROQ_API_KEY` | segredo | recomendado | nenhum | vault/config local | placeholder_intencional_seguro |
| `GROQ_BASE_URL` | URL | nao | endpoint oficial Groq | vault/config local | placeholder_intencional_seguro |
| `GROQ_FALLBACK_MODEL` | texto | nao | modelo em codigo/docs | vault/config local | placeholder_intencional_seguro |
| `GROQ_MODEL` | texto | nao | `llama-3.1-8b-instant` | vault/config local | placeholder_intencional_seguro |
| `HANDOFF_ALERT_TTL_SECONDS` | inteiro | nao | `21600` | `.env.example` | placeholder_intencional_seguro |
| `HANDOFF_STATE_TTL_SECONDS` | inteiro | nao | nenhum documentado | `.env.example` | placeholder_intencional_seguro |
| `HF_TOKEN` | segredo | nao | nenhum | vault/config local | placeholder_intencional_seguro |
| `HOST` | host bind | nao | nenhum | vault/config local | placeholder_intencional_seguro |
| `LOCAL_PTBR_BASE_URL` | URL operacional | se polimento ativo | vazio | vault/config local | placeholder_intencional_seguro |
| `LOCAL_PTBR_MODEL` | texto | se polimento ativo | modelo local | vault/config local | placeholder_intencional_seguro |
| `LOCAL_QWEN_BASE_URL` | URL operacional | nao | URL local | vault/config local | placeholder_intencional_seguro |
| `LOCAL_QWEN_MODEL` | texto | nao | modelo local | vault/config local | placeholder_intencional_seguro |
| `LOG_LEVEL` | enum | nao | nenhum | vault/config local | placeholder_intencional_seguro |
| `MANUAL_TAKEOVER_TTL_SECONDS` | inteiro | nao | `86400` | codigo/README | config_sem_documentacao |
| `MINIMAX_API_KEY` | segredo | recomendado | nenhum | vault/config local | placeholder_intencional_seguro |
| `MINIMAX_BASE_URL` | URL | nao | endpoint MiniMax | vault/config local | placeholder_intencional_seguro |
| `MINIMAX_MODEL` | texto | nao | `MiniMax-M2.7` | vault/config local | placeholder_intencional_seguro |
| `OMNIVOICE_URL` | URL operacional | nao | `http://127.0.0.1:8202` | vault/config local | valor_operacional_sensivel |
| `OWNER_ALERTS_ENABLED` | booleano `0/1` | nao | `1` | `.env.example` | exemplo_seguro |
| `OWNER_ALERT_DEDUP_TTL_SECONDS` | inteiro | nao | `21600` | `.env.example` | exemplo_seguro |
| `OWNER_HIGH_VALUE_ALERTS_ENABLED` | booleano `0/1` | nao | `1` | `.env.example` | exemplo_seguro |
| `OWNER_PHONE` | telefone | sim para alertas | nenhum | vault/config local | valor_operacional_sensivel |
| `OWNER_RECEIVE_AGENDA_DIGEST` | booleano `0/1` | nao | `0` | `.env.example` | exemplo_seguro |
| `PORT` | inteiro | nao | nenhum | vault/config local | placeholder_intencional_seguro |
| `PTBR_POLISH_ENABLED` | booleano `0/1` | nao | `0` | vault/config local | placeholder_intencional_seguro |
| `QDRANT_COLLECTION` | texto | sim | colecao staging | vault/config local | placeholder_intencional_seguro |
| `QDRANT_URL` | URL operacional | sim | `http://localhost:6333` | vault/config local | placeholder_intencional_seguro |
| `RAG_MIN_SCORE` | decimal | nao | `0.35` | vault/config local | placeholder_intencional_seguro |
| `RAG_TIMEOUT_SECONDS` | decimal | nao | nenhum documentado | `.env.example` | placeholder_intencional_seguro |
| `REDIS_URL` | URL operacional | sim | `redis://localhost:6379` | vault/config local | placeholder_intencional_seguro |
| `REFINAR_BASE_URL` | URL local | nao | `http://localhost:8000` | codigo | config_sem_documentacao |
| `REFINAR_GIT_MIRROR` | booleano `0/1` | nao | `1` | codigo | config_sem_documentacao |
| `REFINAR_MAX_QUESTIONS` | inteiro | nao | `2` | codigo | config_sem_documentacao |
| `REFINAR_MAX_RESPONSE_CHARS` | inteiro | nao | `650` | codigo | config_sem_documentacao |
| `REFINAR_TIMEOUT_SECONDS` | decimal | nao | `90` | codigo | config_sem_documentacao |
| `SALES_CACHE_TTL_SECONDS` | inteiro | nao | `2592000` | vault/config local | placeholder_intencional_seguro |
| `SRE_AUDIO_URL` | URL de teste | nao | URL publica de exemplo | codigo | config_sem_documentacao |
| `SRE_FASTAPI_URL` | URL local | nao | `http://localhost:8000` | codigo | config_sem_documentacao |
| `SRE_IMAGE_URL` | URL de teste | nao | URL publica de exemplo | codigo | config_sem_documentacao |
| `SRE_TEST_PHONE` | telefone de teste | nao | `OWNER_PHONE`/placeholder | vault/config local | config_sem_documentacao |
| `SRE_WEBHOOK_URL` | URL local | nao | webhook local | codigo | config_sem_documentacao |
| `SSH_HOST_PC1` | usuario/host SSH | nao | host PC1 | vault/config local | placeholder_intencional_seguro |
| `TTS_ALLOW_CHATTERBOX_PTBR` | booleano `0/1` | nao | `0` no codigo, `1` em producao | vault/config local | placeholder_intencional_seguro |
| `TTS_CHATTERBOX_CFG_WEIGHT` | decimal | nao | `0.50` | vault/config local | placeholder_intencional_seguro |
| `TTS_CHATTERBOX_CHUNK_SIZE` | inteiro | nao | `400` | vault/config local | placeholder_intencional_seguro |
| `TTS_CHATTERBOX_EXAGGERATION` | decimal | nao | `0.42` | vault/config local | placeholder_intencional_seguro |
| `TTS_CHATTERBOX_LANGUAGE` | texto | nao | `pt` | vault/config local | placeholder_intencional_seguro |
| `TTS_CHATTERBOX_SPEED_FACTOR` | decimal | nao | `1.0` | vault/config local | placeholder_intencional_seguro |
| `TTS_CHATTERBOX_TEMPERATURE` | decimal | nao | `0.55` | vault/config local | placeholder_intencional_seguro |
| `TTS_ENGINE` | enum | nao | `chatterbox` | vault/config local | placeholder_intencional_seguro |
| `TTS_LOCALE` | locale | nao | `pt-BR` | vault/config local | placeholder_intencional_seguro |
| `TTS_MAX_CHARS` | inteiro | nao | `420` | vault/config local | placeholder_intencional_seguro |
| `TTS_OMNIVOICE_SPEED` | decimal | nao | vazio | vault/config local | placeholder_intencional_seguro |
| `VALIDATED_REPLY_MIN_SCORE` | decimal | nao | `9.0` | vault/config local | placeholder_intencional_seguro |
| `WEBHOOK_REDIS_TIMEOUT_SECONDS` | decimal | nao | `3.0` | vault/config local | placeholder_intencional_seguro |
| `WHATSAPP_DLQ_KEY` | Redis key | nao | `whatsapp_rag:dead_letter` | codigo | config_sem_documentacao |
| `WHATSAPP_PROCESSING_QUEUE_KEY` | Redis key | nao | `whatsapp_rag:processing` | codigo | config_sem_documentacao |
| `WHATSAPP_QUEUE_KEY` | Redis key | nao | `whatsapp_rag:queue` | vault/config local | placeholder_intencional_seguro |
| `WORKER_CONCURRENCY` | inteiro | nao | `4` | codigo | config_sem_documentacao |
| `WORKER_MAX_ATTEMPTS` | inteiro | nao | `3` | codigo | config_sem_documentacao |
| `WORKER_MESSAGE_TIMEOUT_SECONDS` | decimal | nao | `180` | codigo | config_sem_documentacao |
| `WORKER_QUEUE_POP_TIMEOUT_SECONDS` | inteiro | nao | `5` | codigo | config_sem_documentacao |

## Arquivos

| Arquivo | Categoria | Observacao |
|---|---|---|
| `.env.example` | placeholder_intencional_seguro | Contrato mascarado. Nao trocar `{SECRET}` por exemplo realista. |
| `prisma/.env.example` | exemplo_seguro | Usa placeholders genericos de Prisma, sem credencial real. |
| `.gitignore` | exemplo_seguro | Mantem `.env` e `.env.local` ignorados e permite `.env.example`. |
| `docker-compose.yml` | possivel_segredo_versionado | Foi corrigido para usar `${AUTHENTICATION_API_KEY}` e `${EVOLUTION_DATABASE_URL}`. Segredos antigos devem ser rotacionados. |
| `app/Dockerfile` | exemplo_seguro | `DATABASE_URL=postgresql://x:x@localhost:5432/x` e apenas dummy para `prisma generate`. |
| `README.md` | exemplo_seguro | Deve documentar fluxo seguro sem segredos reais. |
| `sync.sh` | exemplo_seguro | Usa variaveis operacionais de Git e nao imprime segredos. |
| `bot.sh` | exemplo_seguro | Usa apenas `BOT_API_URL` e status sem segredos. |
| `git.sh` | exemplo_seguro | Wrapper operacional de Git sem segredos. |
| `scripts/env-vault.sh` | placeholder_intencional_seguro | Gera `.env.example` mascarado a partir do `.env`. |
| `scripts/validate-env.py` | exemplo_seguro | Valida presenca de nomes e nunca mostra valores. |
| `scripts/send-agenda-digest.py` | valor_operacional_sensivel | Carrega `.env` local ignorado para envio real. |
| `scripts/find-whatsapp-group.py` | valor_operacional_sensivel | Usa Evolution API local e nomes/JIDs operacionais. |
| `scripts/customer-service.py` | exemplo_seguro | Sem leitura direta de segredo no inventario auditado. |
| `app/config/settings.py` | config_obsoleta | BaseSettings legado com defaults antigos; app atual usa `os.getenv` direto. |
| Arquivos com `os.getenv` | valor_operacional_sensivel | Leem ambiente em runtime; relatorios devem listar nomes, nunca valores. |

## Validacao Sem Revelar Valores

Use:

```bash
.venv/bin/python scripts/validate-env.py --env-file .env
```

A saida lista apenas nomes ausentes ou mascarados. Ela nao imprime tokens, senhas, URLs completas nem telefones.
