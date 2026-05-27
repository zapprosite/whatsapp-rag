# Phase 2.10 — Clean State + Long PT-BR Refinement Runbook

## Objetivo

Limpar estado operacional (Redis + PostgreSQL + Qdrant), reindexar RAG e rodar loop longo de refinamento até eliminar o fallback genérico repetido.

## Problema

O bot está repetindo:
```
Entendi.
Isso é instalação, manutenção, higienização ou conserto?
```

Isso indica estado/caches velhos, fila/Review pendente, ou classifier caindo sempre em `ask_basic_service`.

---

## Etapa 0 — Congelar envio

```bash
export BOT_RUNTIME_MODE=shadow
export BOT_CANARY_PERCENT=0
```

Confirmar que shadow mode está ativo antes de continuar.

---

## Etapa 1 — Backup

```bash
.venv/bin/python scripts/backup_before_clean_state.py
```

**Saída esperada:** `backup_report.json` em `/tmp/refrimix-backups/refrimix-clean-state-YYYYMMDD-HHMMSS/`

**Exit code 0** = backup criado. **Exit code 1** = falha — NÃO prosseguir.

---

## Etapa 2 — Dry-run da limpeza

```bash
.venv/bin/python scripts/clean_operational_state.py
```

Mostra o que seria deletado sem apagar nada.

---

## Etapa 3 — Aplicar limpeza (com confirmação)

```bash
CONFIRM_RESET_OPERATIONAL_STATE=1 .venv/bin/python scripts/clean_operational_state.py
```

**Relatório:** `reports/clean_state_YYYYMMDD-HHMMSS.md`

---

## Etapa 4 — Reindex RAG (dry-run primeiro)

```bash
.venv/bin/python scripts/reindex_refrimix_rag.py  # dry-run
.venv/bin/python scripts/reindex_refrimix_rag.py --clean-rebuild  # aplica
```

**Relatório:** `reports/reindex_rag_YYYYMMDD-HHMMSS.md`

---

## Etapa 5 — Teste de regressão do fallback

```bash
.venv/bin/python -m pytest tests/test_no_repeated_generic_fallback.py -v
```

SeSkipped = fixture needs `conversation_simulator` — veja pytest fixtures em `tests/conftest.py`.

---

## Etapa 6 — Loop longo (dry-run)

```bash
.venv/bin/python scripts/run_long_ptbr_refinement_loop.py --hours 1 --batch-size 50 --seed 42
```

Teste rápido de 1h antes de rodar as 3h full.

---

## Etapa 7 — Loop longo (aplicar)

```bash
APPLY_REFINEMENTS=1 .venv/bin/python scripts/run_long_ptbr_refinement_loop.py --hours 3 --batch-size 100
```

**Relatório:** `reports/long_ptbr_refinement_YYYYMMDD-HHMMSS.md`

---

## Critérios de aceite

- `repeated_generic_fallback_count = 0`
- `ask_basic_service` indevido = 0
- `agenda_friction_failures = 0`
- `missing_electrical_shutdown_count = 0`
- Score médio final >= 4.6
- Zero falhas críticas

---

## Arquivos criados

| Arquivo | Descrição |
|---------|-----------|
| `scripts/backup_before_clean_state.py` | Backup PostgreSQL + Redis + Qdrant |
| `scripts/clean_operational_state.py` | Limpeza Redis (prefixos) + Postgres (operacional) |
| `scripts/reindex_refrimix_rag.py` | Reindex playbooks em Qdrant |
| `scripts/run_long_ptbr_refinement_loop.py` | Loop longo 3h com métricas |
| `tests/test_no_repeated_generic_fallback.py` | Teste regressivo contra fallback repetido |

---

## Regras inegociáveis

- **NUNCA** `FLUSHALL` ou `FLUSHDB` sem confirmar Redis exclusivo
- **NUNCA** apagar tabelas comerciais (clients, quotes, service_orders, proposals, contracts)
- **NUNCA** aplicar sem backup feito
- **NUNCA** alterar `risk_detector.py` ou `guardrail_validator.py` automaticamente
- Reset operacional: só com `CONFIRM_RESET_OPERATIONAL_STATE=1`