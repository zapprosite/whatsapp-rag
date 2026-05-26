# Rollback — Core V2 → Legacy

## Quando usar

Este documento cobre como reverter para o core legado (`langgraph`) caso o `refrimix_core` apresente falhas em produção.

## Critérios de ativação

- Smoke tests falhando após 3 tentativas.
- Health mostrando `core_version=v2` com `status:degraded`.
- Atendimento respondendo texto vazio ou action `fallback_recover_context` em sequência.
- LeadEvent não sendo salvo.
- Evolution sendText retornando erro 5xx.

## Procedimento de Rollback

### Passo 1 — Identificar versão atual

```bash
# Verificar flag atual
grep REFRIMIX_CORE_VERSION .env
```

### Passo 2 — Reverter flag para legacy

```bash
# Opção A: editar .env direto (não recomendado se vault sincroniza)
sed -i 's/REFRIMIX_CORE_VERSION=v2/REFRIMIX_CORE_VERSION=legacy/' .env

# Opção B: via env-vault
./scripts/env-vault.sh set REFRIMIX_CORE_VERSION=legacy
```

### Passo 3 — Rebuild do container/serviço

```bash
# Se usando Docker
docker compose down && docker compose up -d

# Se usando Python diretamente
pkill -f "uvicorn app.main:app" || true
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

### Passo 4 — Verificar health

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
# Esperado: core_version não aparece ou aparece como "legacy"
```

### Passo 5 — Verificar atendimento

```bash
curl -s "http://localhost:8000/test/chat?message=Bom+dia&send=false" | python3 -m json.tool
# Esperado: response com saudação old core (schema diferente do V2)
```

## Arquivos que garantem reversão

| Arquivo | O que faz |
|---|---|
| `app/main.py` | Entry point — sempre aponta para `app.worker` |
| `app/worker.py` | Worker LangGraph legado — não foi modificado |
| `app/api/webhook.py` | Webhook Evolution — não foi modificado |
| `app/api/test_routes.py` | Test route — não foi modificado |
| `refrimix_core/` | Novo core — criado em paralelo, nunca chamado por padrão |
| `docs/reversa/` | Documentação — não afeta runtime |

## Como confirmar que rollback funcionou

```bash
# Old core schema é diferente — input(intent), response, send_requested
curl -s "http://localhost:8000/test/chat?message=oi&send=false" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('has intent:', 'intent' in d)
print('has response:', 'response' in d)
print('schema:', list(d.keys()))
"
# Se mostrar "has intent: True" → legacy ok
# Se mostrar "has action: True" → V2 ainda ativo
```

## Commit history de rollback

Se rollback for necessário, fazer commit com mensagem:
```
fix: rollback para core legacy — reverta REFRIMIX_CORE_VERSION=v2

Razão: <descrever problema>
Data: <data>
```

Nunca fazer merge de V2 para main sem antes confirmar rollback funcional.

## Contato de emergência

Se não conseguir fazer rollback:
1. Parar container: `docker stop $(docker ps -q --filter name=whatsapp)`
2. Restaurar branch: `git checkout main && git reset --hard <last-known-good-commit>`
3. Subir old core: `git cherry-pick <commit-do-working-old-core>`
4. Notificar equipe pelo canal de.ops.

## Logs para diagnóstico

```bash
# Logs do worker
docker logs -f whatsapp-rag-worker 2>&1 | grep -E "pipeline|action|response_text|error" | tail -100

# Logs do FastAPI
docker logs -f whatsapp-rag-api 2>&1 | grep -E "pipeline|action|error|warning" | tail -50
```

## Prevenção

- Nunca fazer merge de V2 para main sem smoke tests passando.
- Nunca remover branch `main` ou commit history.
- Sempre manter `_archive/` com estado anterior.
- Health honesto (`/health`) detecta degradação antes do cliente.