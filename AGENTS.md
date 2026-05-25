# Obrigatório Para Agentes

Antes de qualquer alteração neste repositório, leia primeiro:

[docs/mapa-pc1-pc2-refinamento.md](docs/mapa-pc1-pc2-refinamento.md)

Esse mapa é a referência obrigatória para entender PC1, PC2, dependências do WhatsApp RAG, falas prontas, semântico, RAG e fluxo de refinamento.

## Regras De Trabalho

- Não altere `.env` sem rodar `scripts/env-vault.sh sync` depois.
- Não versionar segredos, tokens, telefones sensíveis ou chaves reais.
- Testes de atendimento devem usar `/test/chat?...&send=false` para não enviar WhatsApp real.
- Mudanças em `agent_graph/nodes/nodes.py` exigem rebuild/restart do container para produção.
- Mudanças em `qdrant/seed_hvac.py` exigem re-seed do Qdrant.
- Antes de finalizar alterações de código, rode `.venv/bin/python -m pytest`.
