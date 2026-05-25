# Obrigatório Para Agentes

## Fechamento Obrigatório Da Tarefa

No fim de qualquer tarefa com alteração de arquivo:

1. Rode a validação necessária, no mínimo `.venv/bin/python -m pytest` quando houver código Python.
2. Rode `./sync.sh --message "tipo: resumo objetivo"` para gerar `CLAUDE.md`, commitar, publicar no Gitea e espelhar no GitHub.
3. Se a mudança já estiver no Gitea e só faltar espelho, rode `./sync.sh --mirror-only`.
4. Confirme `git status --short` limpo antes da resposta final.

`origin` é o Gitea primário. `github` é apenas espelho.

Antes de qualquer alteração neste repositório, leia primeiro:

[docs/mapa-pc1-pc2-refinamento.md](docs/mapa-pc1-pc2-refinamento.md)

Esse mapa é a referência obrigatória para entender PC1, PC2, dependências do WhatsApp RAG, falas prontas, semântico, RAG e fluxo de refinamento.

## Regras De Trabalho

- Não altere `.env` sem rodar `scripts/env-vault.sh sync` depois.
- Não versionar segredos, tokens, telefones sensíveis ou chaves reais.
- Testes de atendimento devem usar `/test/chat?...&send=false` para não enviar WhatsApp real.
- Auditoria de voz/PC1/PC2 deve usar `.venv/bin/python -m sre.probes tts-audit`; para gerar sample local sem WhatsApp real, use `--synthesize`.
- Mudanças em `agent_graph/nodes/nodes.py` exigem rebuild/restart do container para produção.
- Mudanças em `qdrant/seed_hvac.py` exigem re-seed do Qdrant.
- Antes de finalizar alterações de código, rode `.venv/bin/python -m pytest`.
