---
source: GUIDE_REFINAMENTO.md
type: generic
---

# Refinamento — Refrimix WhatsApp RAG

## Os 4 Níveis

```
Nível 1 — Tom e persona     →  WILL_SYSTEM_PROMPT  (agent_graph/nodes/nodes.py)
Nível 2 — Conhecimento RAG  →  chunks no Qdrant    (qdrant/seed_hvac.py)
Nível 3 — Classificação     →  SCORE_MAP           (classify_service em nodes.py)
Nível 4 — Modelo LLM        →  .env MINIMAX_MODEL / GROQ_FALLBACK_MODEL
```

Regra: refine no nível mais baixo que resolve o problema.

## Testar sem WhatsApp

```bash
curl -X POST "http://localhost:8000/test/chat?message=MENSAGEM+AQUI&send=false"
curl -X POST "http://localhost:8000/test/e2e?start=0&limit=35&delay=0"
```

## Git rápido

```bash
./git.sh save "refina: mensagem do que mudou"
./git.sh merge   # joga para main quando aprovado
```

## Container

```bash
# Rebuild após mudança em nodes.py
docker compose build fastapi-rag && \
docker rm -f whatsapp-rag-fastapi-rag-1 && \
docker run -d --name whatsapp-rag-fastapi-rag-1 --network host --restart unless-stopped \
  --env-file /home/will/whatsapp-rag/.env \
  -e QDRANT_URL=http://127.0.0.1:6333 \
  -e QDRANT_COLLECTION=hermes_hvac_rag_service_staging \
  whatsapp-rag-fastapi-rag:latest

# Logs ao vivo
docker logs -f whatsapp-rag-fastapi-rag-1 2>&1 | grep -E "INFO|ERROR|WARNING" | grep -v "HTTP Request"
```
