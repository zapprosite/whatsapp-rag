# Audit — Evolution Network Fix & WhatsApp Real Test

**Data:** 2026-05-26
**Hora:** 13:51
**Repo:** `/home/will/workspace/whatsapp-rag-clean`
**Commit:** `ee5ea2713a73b40e69237147e3f481580d8920bf`

---

## 1. Problema Identificado

### Webhook 127.0.0.1 — Hipótese Inicial Incorreta

**Hipótese errada:** "127.0.0.1 dentro do container da Evolution aponta para o próprio container da Evolution".

**Correção:** A Evolution API está rodando com `network_mode: host`. Nesse modo, o container **não recebe namespace de rede isolado** — ele compartilha a pilha de rede do host Linux diretamente. Isso significa que `127.0.0.1` dentro do container Evolution é o mesmo `127.0.0.1` do host. Logo, `http://127.0.0.1:8000/webhook/evolution` é **válido e funcional** neste cenário específico.

**Fonte:** [Docker Documentation — Host network driver](https://docs.docker.com/engine/network/drivers/host/)

### Problema Real: Redis

**Sintoma:** Health mostrava `redis: down` com erro `Error 111 connecting to 100.66.232.72:6379`.

**Causa:** `REDIS_URL=redis://100.66.232.72:6379` — IP de máquina que mudou de subrede.

**Correção:** `REDIS_URL=redis://redis:6379/0` — Redis local como serviço Docker Compose no repo clean. Serviços no mesmo Docker Compose se resolvem pelo nome do serviço na rede padrão do projeto.

**Fonte:** [Docker Documentation — Networking in Compose](https://docs.docker.com/compose/how-tos/networking/)

---

## 2. Configuração de Rede Atual

### Evolution API
- **Container:** `evoapicloud/evolution-api:v2.3.7`
- **Modo de rede:** `network_mode: host`
- **Websocket/Webhook:** `http://127.0.0.1:8000/webhook/evolution` ✅ válido

### FastAPI (repo clean)
- **Modo de rede:** bridge (redes: `default` + `evolution_net`)
- **Porta exposta:** `127.0.0.1:8000:8000`
- **Redis:** serviço local `redis:7-alpine` na rede `default`
- **Webhook URL:** `http://127.0.0.1:8000/webhook/evolution` ✅ funcional

### Por que funciona

```
Evolution (host networking)
  └── 127.0.0.1:8000
        ↓ mesmo namespace de rede do host
  HOST (mesma máquina)
  └── 127.0.0.1:8000 → Docker bridge → container fastapi-rag:8000
```

---

## 3. Health Antes / Depois

### Antes
```json
{
  "status": "ok",
  "core_version": "v2",
  "redis": "down",
  "worker": "running"
}
```

### Depois
```json
{
  "status": "ok",
  "core_version": "v2",
  "redis": "up",
  "postgres": "up",
  "refrimix_core": "up",
  "legacy_core": "available",
  "langgraph": "legacy_available",
  "worker": "running",
  "evolution": "up",
  "rag": "disabled",
  "tts": "disabled",
  "vision": "disabled"
}
```

---

## 4. Teste de Conectividade Evolution → FastAPI

```bash
docker exec evolution_api sh -lc \
  'wget --post-data={"event":"test"} http://127.0.0.1:8000/webhook/evolution'
```

**Resultado:**
```json
{"status":"ok","skipped":"ignored event: test"}
```
✅ Sucesso — Evolution alcança FastAPI via `127.0.0.1:8000`

---

## 5. Dead Letter

**Antes:** nenhum
**Depois:** nenhum
**Comando verificado:**
```bash
docker compose exec -T redis redis-cli --scan --pattern "*dead_letter*" | sort
```
✅ Zero dead letters

---

## 6. Variáveis Corrigidas

| Variável | Valor Antigo | Valor Novo |
|---|---|---|
| `REDIS_URL` | `redis://100.66.232.72:6379` | `redis://redis:6379/0` |
| `EVOLUTION_WEBHOOK_URL` | `http://127.0.0.1:8000/webhook/evolution` | `http://127.0.0.1:8000/webhook/evolution` (mantido ✅) |

---

## 7. Commit

```
fix: networking docker evolution e redis no repo clean

4 files changed, 127 insertions, 11 deletions
Commit: ee5ea2713a73b40e69237147e3f481580d8920bf
```

---

## 8. Próximo Passo — Teste WhatsApp Real

### Sequência de mensagens a testar
1. `bom dia`
2. `quais serviços vocês fazem?`
3. `preciso fazer uma higienização no meu ar`
4. `1`
5. `meu ar não gela`

### Critério de vitória
- Webhook recebe `MESSAGES_UPSERT`
- Worker processa sem crash
- Redis continua `up`
- `sendText` sai pela Evolution
- `LeadEvent` salva
- `dead_letter` continua zero
- Resposta chega no WhatsApp

### Em caso de falha
- Registrar erro completo
- Não fazer `docker system prune`
- Não criar GitHub PR ainda
- Não ativar TTS/RAG/Vision