# Google Integration Runbook — Refrimix

Guia operacional para testes de integração Google Drive + Calendar.

---

## 1. Visão Geral

Este runbook cobre:
- Autenticação OAuth (credenciais + token)
- Smoke test dry-run (padrão)
- Smoke test live (execução real)
- Cleanup de artefatos de teste
- Diagnóstico de erros comuns

**Arquivos principais:**
```
refrimix_core/tools/google_auth.py                    ← OAuth loading
refrimix_core/tools/google_drive_tool.py              ← Drive API v3
refrimix_core/tools/google_calendar_tool.py           ← Calendar API v3
refrimix_core/tools/google_integration_smoke.py       ← Smoke helpers
scripts/smoke_google_drive_calendar.py               ← Script standalone
tests/integration/test_google_drive_live_dry_run.py
tests/integration/test_google_calendar_live_dry_run.py
tests/integration/test_pdf_skill_drive_contract.py
```

---

## 2. Autenticação OAuth

### Arquivos necessários

| Arquivo | Variável | Padrão |
|---|---|---|
| Token de acesso | `GOOGLE_OAUTH_TOKEN_PATH` | `/srv/infra/google/refrimix/token.json` |
| Credentials | `GOOGLE_OAUTH_CREDENTIALS_PATH` | `/srv/infra/google/refrimix/oauth_client.json` |

### Setup inicial

1. Criar projeto Google Cloud em https://console.cloud.google.com/
2. Habilitar Google Drive API e Google Calendar API
3. Criar OAuth Client ID (Desktop app ou Web application)
4. Baixar o JSON de credentials como `oauth_client.json`
5. Gerar o token inicial (primeiro acesso interativo)
6. Guardar ambos arquivos em `/srv/infra/google/refrimix/` com permissões restritivas:

```bash
mkdir -p /srv/infra/google/refrimix
chmod 700 /srv/infra/google/refrimix
chmod 600 /srv/infra/google/refrimix/oauth_client.json
chmod 600 /srv/infra/google/refrimix/token.json
```

### Validação rápida

```bash
python3 -c "
from refrimix_core.tools.google_auth import auth_summary, check_credentials
print('Credentials:', check_credentials())
print('Auth:', auth_summary())
"
```

**Nunca exponha os arquivos reais em logs, screenshots ou commits.**

---

## 3. Variáveis de Ambiente

```env
# Drive
GOOGLE_DRIVE_ROOT_FOLDER_ID=0AF2hQ71kEgWWUk9PVA
GOOGLE_DRIVE_ROOT_NAME=refrimix Tecnologia
GOOGLE_DRIVE_FOLDER_PROPOSTAS_TECNICAS=
GOOGLE_DRIVE_FOLDER_CONTRATOS_SLA=
GOOGLE_DRIVE_FOLDER_ORDENS_SERVICO=
GOOGLE_DRIVE_FOLDER_PMOC_LAUDOS=
GOOGLE_DRIVE_FOLDER_ORCAMENTOS=
GOOGLE_DRIVE_FOLDER_MIDIAS_REDES_SOCIAIS=
GOOGLE_OAUTH_TOKEN_PATH=/srv/infra/google/refrimix/token.json
GOOGLE_OAUTH_CREDENTIALS_PATH=/srv/infra/google/refrimix/oauth_client.json

# Calendar
GOOGLE_CALENDAR_ID=refrimixtecnologia@gmail.com
GOOGLE_CALENDAR_TIMEZONE=America/Sao_Paulo
REFRIMIX_VISIT_DURATION_MIN=60
REFRIMIX_HYGIENIZATION_DURATION_MIN=90
REFRIMIX_INSTALLATION_DURATION_MIN=180

# Smoke test
GOOGLE_INTEGRATION_DRY_RUN=1
GOOGLE_DRIVE_SANDBOX_FOLDER_ID=
GOOGLE_CALENDAR_TEST_PREFIX=[TESTE HERMES]
GOOGLE_SMOKE_CLEANUP=0
```

---

## 4. Smoke Test — DRY-RUN (padrão)

```bash
python scripts/smoke_google_drive_calendar.py
```

Saída esperada:
```
╔═══════════════════════════════════════════════════════════╗
║  Google Drive + Calendar Smoke Test                      ║
╚═══════════════════════════════════════════════════════════╝

┌ Modo: DRY-RUN (simulação, sem chamadas reais à API) ─────────┐
│  GOOGLE_INTEGRATION_DRY_RUN=1                               │
└──────────────────────────────────────────────────────────────┘

  DRY_RUN:        True
  LIVE_CONFIRMED: False
  Lead ID:        smoke_a1b2c3d4e5f6
  Phone:          55999999999999

--- DRIVE ---
  Success:        True
  Sandbox ID:     dry_run_sandbox_id
  Job Folder ID:  dry_run_job_folder_...
  metadata.json:  dry_run_metadata_id
  resumo_lead.md: dry_run_resumo_id
  PDF file ID:    dry_run_pdf_id

--- CALENDAR ---
  Success:        True
  Event ID:      dry_run_event_...
  FreeBusy slots: 2

OVERALL: PASS
```

---

## 5. Smoke Test — LIVE

### 5.1 Pré-requisitos

1. `GOOGLE_INTEGRATION_DRY_RUN=0`
2. `CONFIRM_GOOGLE_LIVE_TEST=1`
3. Pasta `99_SANDBOX_HERMES_TESTES` criada (ou deja criado)

### 5.2 Identificar a pasta sandbox

Se `GOOGLE_DRIVE_SANDBOX_FOLDER_ID` não estiver configurado, o script vai buscar/criar a pasta `99_SANDBOX_HERMES_TESTES` dentro da raiz do Drive.

Para saber o ID antes:
1. Abrir Google Drive no navegador
2. Navegar até `refrimix Tecnologia`
3. Criar (se não existir) uma pasta chamada `99_SANDBOX_HERMES_TESTES`
4. Copiar o ID da URL: `drive.google.com/drive/folders/{AQUI}`
5. Colocar em `GOOGLE_DRIVE_SANDBOX_FOLDER_ID` no `.env`

### 5.3 Executar

```bash
GOOGLE_INTEGRATION_DRY_RUN=0 \
CONFIRM_GOOGLE_LIVE_TEST=1 \
python scripts/smoke_google_drive_calendar.py
```

O script pede confirmação digitando `SIM`.

### 5.4 Saída esperada

```
--- DRIVE ---
  Success:        True
  Sandbox ID:     1X2Y3Z4W5...
  Job Folder ID:  7A8B9C0D1...
  metadata.json:  file_abc123
  resumo_lead.md: file_def456
  PDF file ID:   file_ghi789

--- CALENDAR ---
  Success:        True
  Event ID:       abc123_event_id
  Event Link:     https://calendar.google.com/calendar/...

OVERALL: PASS
```

---

## 6. Cleanup

### Automático

```bash
GOOGLE_INTEGRATION_DRY_RUN=0 \
CONFIRM_GOOGLE_LIVE_TEST=1 \
GOOGLE_SMOKE_CLEANUP=1 \
python scripts/smoke_google_drive_calendar.py
```

Remove automaticamente a pasta de teste e o evento do Calendar.

### Manual

1. Acessar Google Drive → `refrimix Tecnologia` → `99_SANDBOX_HERMES_TESTES`
2. Deletar a pasta com nome `2026-MM-DD_5599999999999_Fulano...`
3. Acessar Google Calendar → excluir evento `[TESTE HERMES]`

---

## 7. Erros Comuns

### `Token OAuth não encontrado`

```python
RuntimeError: Token OAuth não encontrado: token.json. Rode o fluxo de OAuth primeiro.
```

**Solução:** Verificar se `GOOGLE_OAUTH_TOKEN_PATH` aponta para arquivo existente.

### `access_token ausente no token`

O arquivo token.json existe mas não tem campo `access_token`. Provavelmente o token foi sobrescrito por um arquivo inválido. Regenerar o token.

### `Token OAuth expirado`

```python
RuntimeError: Token OAuth expirado em token.json. Rode o refresh OAuth.
```

**Solução:** Renovar o token OAuth (refresh).

### Pasta sandbox não encontrada

Se o script falhar ao criar `99_SANDBOX_HERMES_TESTES`:
1. Verificar se `GOOGLE_DRIVE_ROOT_FOLDER_ID` está correto
2. Criar manualmente a pasta no Google Drive
3. Copiar o ID e colar em `GOOGLE_DRIVE_SANDBOX_FOLDER_ID`

### `HTTP 401: Unauthorized`

Token inválido ou revogado. Regenerar OAuth.

### `HTTP 403: Forbidden`

Scopes insuficientes. Verificar se o token tem `drive.file` e `calendar` scopes.

---

## 8. Regras de Segurança

1. **Nunca commitar** `token.json`, `oauth_client.json` ou `.env` real
2. **Nunca usar** `google-drive://` no backend — é só para navegação manual no Linux
3. **Nunca enviar** PDF de smoke por WhatsApp
4. **Logs** nunca exibem `access_token`, `refresh_token` ou payload completo
5. **Sandbox** `99_SANDBOX_HERMES_TESTES` é a única pasta onde testes live podem escrever
6. **Evento de teste** deve começar com `[TESTE HERMES]` para identificação fácil

---

## 9. Pytest — Testes de Integração

```bash
# Rodar todos os testes de integração
MINIMAL_MVP_ENABLED=0 python -m pytest tests/integration/ -v

# Verificar que são skipped quando DRY_RUN=1 (padrão)
MINIMAL_MVP_ENABLED=0 GOOGLE_INTEGRATION_DRY_RUN=1 python -m pytest tests/integration/ -v

# Live test (dry-run)
MINIMAL_MVP_ENABLED=0 GOOGLE_INTEGRATION_DRY_RUN=0 python -m pytest tests/integration/ -v
```

**Nota:** Testes de integração ficam em `tests/integration/` e são filtrados pelo gate `MINIMAL_MVP_ENABLED`.
