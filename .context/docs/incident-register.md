# Incident Register — Refrimix WhatsApp Bot

> Registro canônico de incidentes conhecidos, sintomas, remediação determinística e critérios de escalation.  
> Versão: 1.0 — mai/2026  
> Mantido em: `.context/docs/incident-register.md` (fonte), distribuído via `./sync.sh`.

---

## Como Ler Este Documento (Para LLMs e Operadores)

### Estrutura de Cada Entrada
Cada incidente segue o formato:

```
## [ID] NOME_DO_INCIDENTE
Severity: P1 | P2 | P3 | P4
Class: service_down | data_corruption | performance | business_logic
First Signal: <como identificar que este incidente começou>
Root Cause: <causa raiz típica>
Remediation (executar nesta ordem):
  1. <comando ou ação>
  2. <comando ou ação>
  3. <comando ou ação>
Escalation If: <condição que exige humano>
Prevention: <o que fazer para reducir probabiliance>
State of Health: <sintomas de resolucombe>
```

### Severity Definitions
| Level | Meaning | Response Time | Autonomous? |
|-------|---------|--------------|-------------|
| P1 | Serviço completamente offline — zero mensagens processadas | < 5 min | Partial — restart first, escalate if 2nd cycle |
| P2 | Funcionalidade crítica degradada — mensagens em fila mas sem resposta | < 15 min | Yes — execute remediation steps 1-3 |
| P3 | Degradação parcial — tipo de mensagem específico falhando | < 60 min | Yes — isolate and fix |
| P4 | Cosmetic/inconveniência menor — não afeta conversa | Best effort | No — document only |

### Autonomy Rules (Para LLMs)
- **P1+P2 → autonomous remediation primeiro, avise depois**
- **P3 → remediation autonomous, documente o resultado**
- **P4 → apenas registre, não intervenha automaticamente**
- **Se ostituto não reconhecer o incidente → STOP, pergunte ao Will**

---

## P1 — Bot Parou de Responder

**Severity:** P1  
**Class:** service_down  
**First Signal:** `/health` retorna 503 ou timeout (> 5s) na porta 8000. evolution API segue respondendo mas cliente não recebe mensagem.

```
Root Cause: FastAPI crash (OOM kill, excessões não capturadas) ou worker-RAG parado.
Remediation:
  1. docker ps | grep -E "fastapi|worker|redis|postgres"        # diagnóstico rápido
  2. docker compose restart fastapi-rag worker-rag              # restart dos containers impacto
  3. curl -f http://localhost:8000/health                      # verify back online
  4. Se ainda 503: docker logs fastapi-rag --tail=50           # ler logs
  5. Se OOM: docker compose up --no-cache fastapi-rag          # rebuild
Escalation If: 2 restart cycles sem melhora, ou Redis + Postgres caíram juntos.
Prevention: hermes-watchdog.sh a cada 5min + healthcheck CronHealth endpoint.
```

---

##  P2 — Redis Queue Estoura (Mensagens Acumuladas / Loop)

**Severity:** P2  
**Class:** performance  
**First Signal:** `docker exec redis-rag redis-cli LLEN queue:messages` > 50 mensagens, ou mensagens com `delay > 60s` no watchdog.

```
Root Cause: Worker não está consumindo a fila — crash, deadlock Python, ou mensagem corrompida.
Remediation:
  1. docker exec redis-rag redis-cli LLEN queue:messages       # validar tamanho da fila
  2. docker exec redis-rag redis-cli LRANGE queue:messages 0 5  # inspecionar primeiras entradas
  3. docker compose restart worker-rag                         # restart worker
  4. sleep 5 && docker exec redis-rag redis-cli LLEN queue:messages  # verificar se consumiu
  5. Se fila continuar crescendo: docker logs worker-rag --tail=30  # identificar mensagem problemática
  6. docker exec redis-rag redis-cli LTRIM queue:messages 0 49  # purgar se necessário
     ⚠️  ATENÇÃO: LTRIM remove as primeiras entradas; se outras mensagens legítimas
          estiverem na fila, usar LPOP em loop até_REMOVE só a corrompida.
     Safer: LREM queue:messages 1 "<msg_id>"  # remove uma ocorrência específica
Escalation If: Fila volta a crescer após restart em menos de 10min.
Prevention: Worker com heartbeat para watchdog; mensagems com TTLmax de 300s.
```

---

## P3 — Evolution API Timeout (Webhook Response > 30s)

**Severity:** P3  
**Class:** service_down  
**First Signal:** `curl -w "%{time_total}" -X POST http://localhost:8080/...` > 30s ou HTTP 504.

```
Root Cause: Instância da Evolution API travada, QR code não regerado, conexão WhatsApp instável.
Remediation:
  1. curl -sf http://localhost:8080/instance/connect/{EVOLUTION_INSTANCE} --max-time 10  # healthcheck
  2. Se falhar: scripts/evolution-safe-up.sh                      # restart seguro Evolution
  3. Verificar logs: docker compose logs evolution-api --tail=20
  4. Se instance off: POST /instance/connect para reconectar WhatsApp
Escalation If: Evolution API retorna 401/403 (api key inválida ou instância deletada).
Prevention: evolution-preflight.py antes de cada deployment;monitorar QR code state.
```

---

## P4 — Evolution API Instance Off-line (QR Code Expired)

**Severity:** P3  
**Class:** business_logic  
**First Signal:** Envio de mensagem retorna `{"key": {"id": "", "invalid": true}}` ou similar.

```
Root Cause: Sessão WhatsApp da Evolution expirou — telefone desconectado ou QR não escaneado.
Remediation:
  1. curl -sf http://localhost:8080/instance/connectionState/{EVOLUTION_INSTANCE}
  2. Se "close" | "disconnected": POST /instance/connect para regerar QR
  3. Will recebe QR code via UI da Evolution ou logs: docker compose logs evolution-api 2>&1 | grep "qrcode"
  4. Will escaneia QR com WhatsApp; instance volta a "connected".
Escalation If: Instância foi deletada da Evolution (não existe mais).
Prevention: Manter sessão ativa; Evolution com reconnect automático ativado.
```

---

## P5 — PostgreSQL: Conexão Exausta ou Query Timeout

**Severity:** P2  
**Class:** data_corruption  
**First Signal:** Erro `FATAL: remaining connection slots reserved` ou query > 10s no bot.

```
Root Cause: Connection pool exhaust (muitas conexões simultâneas, conexão não fecha).
Remediation:
  1. docker exec postgres-rag psql -U postgres -d refrimix -c "SELECT count(*) FROM pg_stat_activity WHERE datname='refrimix'"  # conexões ativas
  2. docker exec postgres-rag psql -U postgres -d refrimix -c "SELECT pid, query FROM pg_stat_activity ORDER BY query_start"  # queries em execução
  3. Se > 80 conexões: docker compose restart fastapi-rag  # reinicia pool
  4. Se query lenta: IDENTIFICAR a query mais lenta e kill pelo pid
  5. docker exec postgres-rag psql -U postgres -d refrimix -c "SELECT pg_terminate_backend(pid) WHERE pg_stat_activity.query ~~ '%long_query%'"  # matar query problemática
Escalation If: Problema recorrente — pool constantemente em 80%+.
Prevention: Conexões com context manager (autoclose); pool max 20 no Prisma.
```

---

## P6 — Lead Preso em Loop Conversacional (State Machine Deadlock)

**Severity:** P3  
**Class:** business_logic  
**First Signal:** Mesmo lead enviando N mensagens similares sem avançuo de estado. `lead_state` não atualiza.

```
Root Cause: Intent classification repetida retornando mesmo valor, plan_next_action repetindo ação, ou resposta do catálogo fazendo loop (prompt → resposta → prompt).
Remediation:
  1. .venv/bin/python scripts/reset-lead.py <phone>           # reset cirúrgico do lead
  2. Verificar motivo: docker logs worker-rag --tail=20 2>&1 | grep "<phone>"
  3. Se é bug de intent: registar o texto da mensagem em bug报告 e fechar issue
  4. Se é resposta do catálogo em loop: corrigir response_catalog para o intent específico
Escalation If: Reset não resolve (problema no intent router).
Prevention: Limite de 3 mensajeers por intent por sessão; watchdog detecta loop.
```

---

## P7 — Mensagem Enviada Duas Vezes (Duplicate Send)

**Severity:** P3  
**Class:** business_logic  
**First Signal:** Cliente responde "já mandei de novo" ou收到 mensagem duplicada no WhatsApp.

```
Root Cause: Worker consumindo a mesma mensagem 2x (RabbitMQ consumer offset não committing) ouevolution API retry sem idempotência.
Remediation:
  1. Verificar logs: docker logs worker-rag 2>&1 | grep "<msg_id>"   # identificar duplicata
  2. Se duplicate do worker: verificar Redis message dedup (set NX com msg_id).
  3. Se duplicate do evolution: idempotency key no evolution API.
  4. Desabilitar retry temporário se habilitado.
Escalation If: Mais de 3 duplicatas em 1h — voltar ao básico.
Prevention: Message deduplication via Redis SET NX com TTL.
```

---

## P8 — .env com Placeholder Vazio em Produção (CONFIGURATION ERROR)

**Severity:** P2  
**Class:** data_corruption  
**First Signal:** Container com healthcheck failing no ar; `docker ps` showing `Restarting`.

```
Root Cause: .env com ${VAR} não expandido (deploy sem `scripts/env-vault.sh sync`).
Remediation:
  1. docker ps --format "{{.Names}} {{.Status}}" | grep -i restart  # listar containers em loop
  2. scripts/env-vault.sh sync                                    # restaurar .env do vault
  3. docker compose up -d                                         # reopen containers
  4. docker logs <container> --tail=10 2>&1 | grep "required"     # identificar var ausente
Escalation If: Variável é ${EVOLUTION_DATABASE_URL} — não sincronizar sem backup.
Prevention: Regra em .rules/secrets-env.md; CI bloqueia deploy sem validate-env.py.
```

---

## P9 — Gitea Não Espelha para GitHub (Mirror Failed)

**Severity:** P4  
**Class:** service_down  
**First Signal:** `./sync.sh --mirror-only` rejeita por `non-fast-forward` ou `authentication failed`.

```
Root Cause:** (a) Histórico divergente entre Gitea e GitHub; (b) Token do GitHub expirado.

Remediation (caso a):
  1. cd /home/will/whatsapp-rag
  2. git fetch origin && git log --oneline origin/main -3      # ver estado do Gitea
  3. git fetch github && git log --oneline github/main -3      # ver estado do GitHub
  4. git push github refs/remotes/origin/main:main --force     # forçar espelho ⚠️ reescreve histórico
  OU (mais seguro): git push github origin/main:github/main --force-with-lease
Escalation If:** Não sabe se é seguro descartar changes do GitHub.
Prevention: Sempre usar --mirror-after-commit no sync.sh; revisar divergent branches antes de mirror.

Remediation (caso b):**
  1. gh auth status                                             # verificar token
  GitHub**
  2. gh auth refresh                                            # re-autenticar
  3. cat ~/.git-credentials | grep github                      # verificar credencial armazenada
  Se expired: gh auth logout && gh auth login --with-token
Escalation If: Org-level PAT sem access scope para repo.
```

---

##  Template: Registrar Novo Incidente

> LLMs: ao detectar um incidente que **não está na lista acima**, use este template para criar uma entrada provisória antes de escalar. Depois submeta via PR para aprovação.

```markdown
## [PI-NEW] NOME_DO_INCIDENTE
**Severity:** P?
**Detected At:** YYYY-MM-DD HH:MM
**First Signal:** <comando ou sintoma que identificou>
**Root Cause (hipótese):** <causa mais provável>
**Remediation (executada):**
  1. <passo 1 — comando>
  2. <passo 2 — comando>
**Result:** <sucesso | falha | parcialmente resolvido>
**Escalation Needed:** <sim | não, porque>
**Prevention (sugerida):** <o que recomendaria para evitar>
```

Instructions: after filling in, create a GitHub issue labeled `incident` and assign to `zapprosite`. Do NOT attempt autonomous fix for unknown incidents without approval.

---

## Referências Cruzadas

- Playbook de rollback: `.context/docs/playbook.md`
- SOTA LLM+RPA+Incidents: `.context/docs/state-of-the-art-llm-rpa-incidents.md`
- Evolution API config: `.context/docs/evolution.md`
- Scripts utilitários: `scripts/reset-lead.py`, `scripts/evolution-safe-up.sh`, `scripts/hermes-watchdog.sh`
- SRE probes: `sre/probes.py`
