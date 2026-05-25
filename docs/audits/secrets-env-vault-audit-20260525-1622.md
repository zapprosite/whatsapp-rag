# Auditoria de Secrets, Env e Vault

Data: 2026-05-25 16:22 BRT.

Escopo auditado: `.env.example`, `prisma/.env.example`, `.gitignore`, `docker-compose.yml`, `app/Dockerfile`, `README.md`, `sync.sh`, `bot.sh`, `git.sh`, `scripts/`, `app/config/settings.py` e arquivos com `os.getenv`.

## Resultado Executivo

- `.env.example` usa `{SECRET}` de forma proposital. Classificacao: `placeholder_intencional_seguro`.
- `.env` e `.env.local` seguem ignorados pelo Git. Classificacao esperada: `valor_real_local_ignorado`.
- `docker-compose.yml` continha uma chave da Evolution API e duas URLs PostgreSQL com credenciais versionadas. Classificacao: `possivel_segredo_versionado`.
- O Compose foi ajustado para ler `AUTHENTICATION_API_KEY` e `EVOLUTION_DATABASE_URL` do ambiente local/vault, sem publicar valores.
- Recomenda-se rotacionar qualquer segredo que tenha sido commitado antes desta auditoria.

## Correcoes Aplicadas

| Arquivo | Antes | Depois | Categoria |
|---|---|---|---|
| `docker-compose.yml` | API key da Evolution versionada | `AUTHENTICATION_API_KEY=${AUTHENTICATION_API_KEY}` | possivel_segredo_versionado |
| `docker-compose.yml` | URL PostgreSQL da Evolution com credencial | `DATABASE_URL=${EVOLUTION_DATABASE_URL}` | possivel_segredo_versionado |
| `docker-compose.yml` | URI PostgreSQL duplicada com credencial | `DATABASE_CONNECTION_URI=${EVOLUTION_DATABASE_URL}` | possivel_segredo_versionado |
| `README.md` | exemplos realistas de segredo | fluxo seguro e validacao sem valores | exemplo_seguro |
| `env.schema.md` | inexistente | schema operacional de variaveis | exemplo_seguro |
| `scripts/validate-env.py` | inexistente | validador que lista apenas nomes | exemplo_seguro |

## Variaveis Por Categoria

### placeholder_intencional_seguro

`AUTHENTICATION_API_KEY`, `DATABASE_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_API_URL`, `EVOLUTION_INSTANCE`, `GH_TOKEN`, `GITHUB_TOKEN`, `GOOGLE_CALENDAR_ENABLED`, `GOOGLE_CALENDAR_ID`, `GOOGLE_CALENDAR_TIMEZONE`, `GOOGLE_SERVICE_ACCOUNT_FILE`, `GRAPH_RESPONSE_TIMEOUT_SECONDS`, `GROQ_API_KEY`, `GROQ_BASE_URL`, `GROQ_FALLBACK_MODEL`, `GROQ_MODEL`, `HANDOFF_ALERT_TTL_SECONDS`, `HANDOFF_STATE_TTL_SECONDS`, `HF_TOKEN`, `HOST`, `LOCAL_PTBR_BASE_URL`, `LOCAL_PTBR_MODEL`, `LOCAL_QWEN_BASE_URL`, `LOCAL_QWEN_MODEL`, `LOG_LEVEL`, `MINIMAX_API_KEY`, `MINIMAX_BASE_URL`, `MINIMAX_MODEL`, `PORT`, `PTBR_POLISH_ENABLED`, `QDRANT_COLLECTION`, `QDRANT_URL`, `RAG_MIN_SCORE`, `RAG_TIMEOUT_SECONDS`, `REDIS_URL`, `SALES_CACHE_TTL_SECONDS`, `SSH_HOST_PC1`, `TTS_ALLOW_CHATTERBOX_PTBR`, `TTS_CHATTERBOX_CFG_WEIGHT`, `TTS_CHATTERBOX_CHUNK_SIZE`, `TTS_CHATTERBOX_EXAGGERATION`, `TTS_CHATTERBOX_LANGUAGE`, `TTS_CHATTERBOX_SPEED_FACTOR`, `TTS_CHATTERBOX_TEMPERATURE`, `TTS_ENGINE`, `TTS_LOCALE`, `TTS_MAX_CHARS`, `TTS_OMNIVOICE_SPEED`, `VALIDATED_REPLY_MIN_SCORE`, `WEBHOOK_REDIS_TIMEOUT_SECONDS`, `WHATSAPP_QUEUE_KEY`.

### exemplo_seguro

`AGENDA_DIGEST_DEDUP_TTL_SECONDS`, `AGENDA_DIGEST_MAX_ITEMS`, `AGENDA_GROUP_DIGEST_TIMEZONE`, `AGENDA_GROUP_ENABLED`, `AGENDA_GROUP_MORNING_DIGEST_HOUR`, `AGENDA_GROUP_MORNING_DIGEST_MINUTE`, `AGENDA_GROUP_NAME`, `AGENDA_GROUP_NIGHT_DIGEST_HOUR`, `AGENDA_GROUP_NIGHT_DIGEST_MINUTE`, `AGENDA_LOOKAHEAD_DAYS`, `DATABASE_PROVIDER`, `OWNER_ALERTS_ENABLED`, `OWNER_ALERT_DEDUP_TTL_SECONDS`, `OWNER_HIGH_VALUE_ALERTS_ENABLED`, `OWNER_RECEIVE_AGENDA_DIGEST`.

### valor_real_local_ignorado

`.env`, `.env.local` e `EVOLUTION_DATABASE_URL` quando definido localmente. Esses valores nao foram lidos nem impressos.

### possivel_segredo_versionado

`docker-compose.yml` tinha tres ocorrencias sensiveis versionadas. Os valores nao sao reproduzidos aqui; devem ser considerados comprometidos e rotacionados.

### valor_operacional_sensivel

`AGENDA_GROUP_JID`, `CHATTERBOX_URL`, `EVOLUTION_DATABASE_URL`, `OMNIVOICE_URL`, `OWNER_PHONE`, `SRE_TEST_PHONE` e qualquer URL/telefone/host real carregado por runtime.

### config_obsoleta

`app/config/settings.py` aparenta ser legado: define `BaseSettings`, mas o caminho principal usa `os.getenv` nos modulos de runtime. Nao foi removido nesta auditoria.

### config_sem_documentacao

`ACTIVE_SERVICE_STATUSES`, `BOT_OFF_MESSAGE`, `COMPLETED_SERVICE_STATUSES`, `CONV_LOCK_REQUEUE_DELAY_SECONDS`, `CONV_LOCK_TTL_SECONDS`, `CONV_LOCK_WAIT_SECONDS`, `CONV_MAX_TURNS`, `CONV_TTL_SECONDS`, `ENVIRONMENT`, `MANUAL_TAKEOVER_TTL_SECONDS`, `REFINAR_BASE_URL`, `REFINAR_GIT_MIRROR`, `REFINAR_MAX_QUESTIONS`, `REFINAR_MAX_RESPONSE_CHARS`, `REFINAR_TIMEOUT_SECONDS`, `SRE_AUDIO_URL`, `SRE_FASTAPI_URL`, `SRE_IMAGE_URL`, `SRE_WEBHOOK_URL`, `WHATSAPP_DLQ_KEY`, `WHATSAPP_PROCESSING_QUEUE_KEY`, `WORKER_CONCURRENCY`, `WORKER_MAX_ATTEMPTS`, `WORKER_MESSAGE_TIMEOUT_SECONDS`, `WORKER_QUEUE_POP_TIMEOUT_SECONDS`.

## Arquivos Auditados

| Arquivo | Categoria | Observacao |
|---|---|---|
| `.env.example` | placeholder_intencional_seguro | `{SECRET}` e intencional e deve permanecer. |
| `prisma/.env.example` | exemplo_seguro | Usa placeholders genericos. |
| `.gitignore` | exemplo_seguro | Ignora `.env` e `.env.local`; permite `.env.example`. |
| `docker-compose.yml` | possivel_segredo_versionado | Corrigido para variaveis `${...}`; rotacao recomendada. |
| `app/Dockerfile` | exemplo_seguro | Usa URL dummy para gerar Prisma client. |
| `README.md` | exemplo_seguro | Atualizado para fluxo seguro. |
| `sync.sh` | exemplo_seguro | Gera docs e publica Git sem segredos. |
| `bot.sh` | exemplo_seguro | Nao imprime segredo. |
| `git.sh` | exemplo_seguro | Nao imprime segredo. |
| `scripts/env-vault.sh` | placeholder_intencional_seguro | Mantem contrato mascarado. |
| `scripts/validate-env.py` | exemplo_seguro | Valida nomes faltantes sem valores. |
| `scripts/send-agenda-digest.py` | valor_operacional_sensivel | Usa `.env` local para envio real. |
| `scripts/find-whatsapp-group.py` | valor_operacional_sensivel | Usa configuracao local da Evolution. |
| `scripts/customer-service.py` | exemplo_seguro | Sem segredo direto identificado. |
| `app/config/settings.py` | config_obsoleta | Legado aparente. |
| Arquivos com `os.getenv` | valor_operacional_sensivel | Devem tratar valores como runtime sensivel. |

## Validacao Segura

Comando:

```bash
.venv/bin/python scripts/validate-env.py --env-file .env
```

Comportamento esperado: listar apenas nomes faltantes ou mascarados, nunca valores.

## Regras Para Agentes

- Nao remover `{SECRET}` do `.env.example`.
- Nao transformar `.env.example` em exemplos realistas de token, senha, telefone ou URL com credencial.
- Nao pedir, imprimir, copiar ou commitar segredo real.
- Nao buscar segredo em vault real durante auditoria.
- Ao diagnosticar ambiente, mostrar somente nomes de variaveis ausentes.
