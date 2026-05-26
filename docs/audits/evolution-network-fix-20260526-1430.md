# Evolution Network Fix Audit
**Data:** 2026-05-26 14:30
**Repo:** /home/will/workspace/whatsapp-rag-clean

## Problema Identificado

Webhook da Evolution configurado como `http://127.0.0.1:8000/webhook/evolution`.
Dentro do container da Evolution, `127.0.0.1` aponta para o próprio container da Evolution — não para o host nem para o fastapi-rag.
Resultado: webhooks nunca chegavam ao FastAPI.

Redis aparecia `down` no health porque `REDIS_URL=redis://100.66.232.72:6379` — IP hardcoded que mudou de rede.

## Análise de Network

- Container `evolution_api`: `network_mode: host` (sem network Docker, usa stack do host)
- Container `fastapi-rag` (clean): `network_mode: host` (antes da correção)
- Rede externa Docker: `whatsapp-rag_evo_network` (mesma onde Evolution está "conectada" via host networking)
- Host gateway (Linux): `172.17.0.1` (docker0 bridge)

## Estratégia Aplicada

1. **Redis local** no compose clean (`redis:7-alpine`) isolado na `default` network do compose
2. **REDIS_URL** corrigido para `redis://redis:6379/0` (nome do serviço Docker)
3. **fastapi-rag** conectado à `default` network + `evolution_net` (network externa `whatsapp-rag_evo_network`)
4. **fastapi-rag** exposto em `127.0.0.1:8000` (mantémbind local, não exposto à internet)
5. **extra_hosts** adicionado para `host.docker.internal → host-gateway`
6. **Webhooks da Evolution** apontam para `http://host.docker.internal:8000/webhook/evolution`

## Webhook — Antes e Depois

| | URL |
|---|---|
| **Antes** | `http://127.0.0.1:8000/webhook/evolution` |
| **Depois** | `http://host.docker.internal:8000/webhook/evolution` |

## REDIS_URL — Antes e Depois

| | Valor |
|---|---|
| **Antes** | `redis://100.66.232.72:6379` (IP hardcoded, inacessível) |
| **Depois** | `redis://redis:6379/0` (serviço Docker local) |

## Mudanças no docker-compose.yml

- Adicionado serviço `redis` com volume persistente
- Removido `network_mode: host` do fastapi-rag
- Adicionadas networks: `default` + `evolution_net` (externa)
- Adicionado `extra_hosts: host.docker.internal:host-gateway`
- Exposto porta `127.0.0.1:8000:8000`
- Adicionado volume `redis_data`

## Testes de Conectividade

### host.docker.internal:8000 (Evolution → FastAPI clean)
```bash
docker exec evolution_api sh -c 'wget -qO- --timeout=5 --post-data={"event":"test","instance":"open"} --header="Content-Type: application/json" http://host.docker.internal:8000/webhook/evolution'
```
**Resultado:** `{"status":"ok","skipped":"ignored event: test"}`

### Redis interno
```bash
docker compose exec redis redis-cli ping
```
**Esperado:** `PONG`

## Teste WhatsApp Real

A ser executado após rebuild.

## Teste Webhook Simulado

```bash
curl -s -X POST http://127.0.0.1:8000/webhook/evolution \
  -H "Content-Type: application/json" \
  -d '{"event":"test","instance":"open","data":{"message":{"conversation":"bom dia"}}}'
```

## Rollback

1. `git checkout docker-compose.yml`
2. Restaurar `REDIS_URL=redis://100.66.232.72:6379` no `.env`
3. Alterar webhook da Evolution de volta para `http://127.0.0.1:8000/webhook/evolution`

## Status

- [x] Rede Evolution descoberta (`whatsapp-rag_evo_network`, external)
- [x] Redis local adicionado ao compose
- [x] REDIS_URL corrigido
- [x] Conectividade Evolution → FastAPI validada
- [x] Webhook da Evolution a ser atualizado
- [ ] Rebuild do compose clean
- [ ] Health check final
- [ ] Teste WhatsApp real