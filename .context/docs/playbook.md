# Playbook de Incidentes e Rollback do MVP

Este documento serve como guia prático de referência para os administradores do sistema em caso de falhas operacionais, indisponibilidade ou necessidade de reversão de atualizações.

---

## 1. O Bot Parou de Responder (Triagem Rápida)

Em caso de parada total nas respostas do bot, siga a ordem estrita de diagnóstico:

### Passo 1: Verificar o Healthcheck
Acesse o endpoint de saúde `/health` do servidor executando no PC2:
```bash
curl -f http://localhost:8000/health
```
- Se responder status `503 Degraded` ou falhar, observe o payload de diagnóstico. Se o banco de dados PostgreSQL ou o Redis estiverem reportando status `down`, vá para o **Passo 2**.
- Se reportar que o worker está inativo ou com heartbeat atrasado, reinicie o worker.

### Passo 2: Reiniciar a Pilha de Serviços
Caso algum serviço esteja travado na máquina local, execute o restart seguro via Docker:
```bash
docker compose restart fastapi-rag redis-rag postgres-rag
```
Para reiniciar o worker de fila:
```bash
docker compose restart worker-rag
```

---

## 2. Falhas no Redis (Estouro de Fila)

Se o Redis cair ou acumular mensagens indevidamente:
1. **Limpar a fila acumulada**: Em caso de loop de mensagens ou travamentos gerados por uma mensagem corrompida, você pode purgar a fila Redis conectando ao CLI:
   ```bash
   docker exec -it redis-rag redis-cli FLUSHALL
   ```
2. **Reiniciar a escuta do Worker**:
   ```bash
   docker compose restart worker-rag
   ```

---

## 3. Resetes Cirúrgicos de Leads para Testes

Se um lead específico (ex: número do gerente Will ou do bot) entrar em um estado conversacional inválido ou precisar ser reiniciado para fins de homologação:
Rode o script utilitário de reset cirúrgico de leads:
```bash
.venv/bin/python scripts/reset-lead.py 5513996659382
```
Este script limpa o cache Redis do telefone e remove os campos de estado conversacional do lead no PostgreSQL, retornando-o ao estágio `"new"` como se fosse o primeiro contato.

---

## 4. Estratégia de Rollback de Código

Se uma atualização em produção gerar regressões inesperadas:
1. **Reverter a Branch**: Restaure o último commit estável conhecido da branch `feature/proxima-tarefa-20260526` ou faça checkout para a `main`.
2. **Sincronizar Repositório**: Rode o script de sincronização para commit e publicação imediata no Gitea:
   ```bash
   ./sync.sh --message "fix: rollback de emergencia para versao estavel X"
   ```
3. **Reconstruir Contêineres**: Force a reconstrução sem cache das imagens do RAG:
   ```bash
   docker compose build --no-cache fastapi-rag worker-rag
   docker compose up -d
   ```
