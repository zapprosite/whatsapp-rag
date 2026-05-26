# AGENTS.md — Regras para Agentes de IA

## Contexto

Repositório limpo do WhatsApp Bot da Refrimix HVAC-R Brasil.
Pipeline oficial: **Refrimix Core v2** (determinístico, sem LLM no path crítico).

## Regras Obrigatórias

### 1. NÃO usar LangGraph como runtime principal
- `MINIMAL_MVP_ENABLED=1` desabilita LangGraph do path crítico
- Worker usa `process_mvp_message` do `app/mvp_attendance.py`
- LangGraph só entra se `MINIMAL_MVP_ENABLED=0` E `REFRIMIX_CORE_VERSION=legacy`

### 2. NÃO versionar secrets
- `.env` está no `.gitignore`
- `.env.example` é o template (sem valores reais)
- Variáveis reais vão para vault (Infisical/HashiCorp) não commitado

### 3. NÃO tocar no banco `evolution_api`
- Banco da Evolution API (`evolution_api`) é **intocável**
- Não rodar migrations, não limpar dados, não recriar schema
- Usar `DATABASE_URL` do whatsapp_rag (`whatsapp_rag`) apenas

### 4. NÃO mudar token/URL da Evolution API
- Credenciais da Evolution API não devem ser alteradas sem aprovação do dono

### 5. NÃO expor serviços em 0.0.0.0 sem necessidade
- Apenas `fastapi-rag` expuesto em `0.0.0.0:8000` via docker-compose
- Redis, Postgres, Qdrant são externos (localhost ou explicit hosts)

### 6. NÃO reintroduzir dívida técnica
- Não trazer `nodes.py` gigante (>4000 linhas)
- Não trazer `agent_graph/graph/graph.py` como core path
- Não adicionar RAG/Qdrant como dependência obrigatória

### 7. Core oficial é refrimix_core v2
- Intent → Service Routing → Commercial Decision → Response Catalog
- Sem LLM, sem LangChain, sem LangGraph no path crítico

### 8. Commercial Router preserva preços
- R$850 — instalação simples
- R$200 — higienização
- R$50 — visita técnica / manutenção
- VRF/Alto valor → projeto customizado

### 9. TTS/Vision/STT desligados por padrão
- `TTS_ENABLED=0`, `VISION_ENABLED=0`, `STT_ENABLED=0`
- Ativar só quando `CHATTERBOX_TTS_URL` ou Minimax API Key disponíveis

### 10. Não usar IP hardcoded
- `100.66.232.72`, `192.168.15.83`, `100.87.53.54` não devem aparecer no código
- Usar variáveis de ambiente (`REDIS_URL`, `DATABASE_URL`, etc.)

## Permissão para Mudanças

| Mudança | Precisa Aprovação |
|---------|-------------------|
| Mudar Evolution API token/URL | ❌ NÃO — risco de downtime |
| Alterar Commercial Router prices | ✅ SIM — envolve regras de negócio |
| Mudar `MINIMAL_MVP_ENABLED` default | ✅ SIM — muda comportamento |
| Adicionar LangGraph ao path | ❌ NÃO —违背 Princípio 1 |
| Criar novo serviço Docker | ✅ SIM — infraestrutura |
| Alterar schema Prisma | ✅ SIM — banco de dados |
| Modificar `evolution_api` database | ❌ NÃO — intocável |

## Import Archaeology

Se precisar importar algo novo, primeiro verificar se já existe em:

1. `refrimix_core/` — core v2 (não-LLM, determinístico)
2. `app/mvp_attendance.py` — attendance flow
3. `app/lead_repository.py` — Prisma ORM
4. `agent_graph/` — legacy (só via `MINIMAL_MVP_ENABLED=0`)

## Operações

### Subir
```bash
docker compose up -d
```

### Parar
```bash
docker compose down
```

### Logs
```bash
docker compose logs -f fastapi-rag
```

### Reset Lead
```bash
python scripts/reset-lead.py <phone>
```

### Health
```bash
curl http://localhost:8000/health
```

### Smoke Test
```bash
curl -X POST "http://localhost:8000/test/chat?message=Bom+dia&send=false"
```