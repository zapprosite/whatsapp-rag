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
# Gera CLAUDE.md, commita, publica no Gitea e espelha no GitHub
./sync.sh --message "refina: mensagem do que mudou"

# Se a mudança já está no Gitea e só falta atualizar o GitHub
./sync.sh --mirror-only
```

Regra de espelho: `origin` é o Gitea primário; `github` é espelho. Nunca trate o GitHub como fonte principal.

## Container

```bash
# Rebuild após mudança em nodes.py
docker compose up -d --build --no-deps fastapi-rag

# Logs ao vivo
docker logs -f whatsapp-rag-fastapi-rag-1 2>&1 | grep -E "INFO|ERROR|WARNING" | grep -v "HTTP Request"
```

## Loop 50x

```bash
python3 refinar.py --loop 50
```

O loop usa `/test/chat?send=false`; ele não envia WhatsApp real. Quando houver mudança aceita no refinamento, use o comando `commit` no `refinar.py` ou deixe o `refinar_llm.py` salvar no final do ciclo. Os dois fluxos chamam `sync.sh`, publicam no Gitea e espelham no GitHub.

## Voz PT-BR

```bash
.venv/bin/python -m sre.probes tts-audit
.venv/bin/python -m sre.probes tts-audit --synthesize
```

Se a voz soar portuguesa ou robótica, verifique primeiro se o Chatterbox está em modo multilíngue e se algum fallback genérico foi reintroduzido. Para produção, mantenha `TTS_ENGINE=chatterbox`, `TTS_LOCALE=pt-BR`, `TTS_CHATTERBOX_LANGUAGE=pt` e `TTS_ALLOW_CHATTERBOX_PTBR=1`. Se o probe Chatterbox falhar, volte temporariamente para `TTS_ENGINE=omnivoice`.
