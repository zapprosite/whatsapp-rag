# Obrigatório Para Agentes

## Regra P0: Segredos e `.env.example`

Antes de qualquer alteração envolvendo configuração, Docker, ambiente, README, scripts ou documentação operacional, leia [.rules/secrets-env.md](.rules/secrets-env.md).

- Não remover `{SECRET}` do `.env.example`.
- Não substituir placeholders por tokens, senhas, telefones, hosts internos, URLs com credencial, API keys ou chaves SSH reais.
- Não imprimir `.env`, `.env.local`, vault, token, senha, URL com senha, telefone sensível ou chave real em logs, docs, prompts, respostas ou commits.
- Diagnóstico de ambiente deve mostrar só nomes de variáveis ausentes, nunca valores. Use `.venv/bin/python scripts/validate-env.py --env-file .env`.
- Se encontrar segredo versionado, remova do arquivo, troque por `${VAR}`, documente o nome em `env.schema.md` e recomende rotação sem repetir o valor.

## Regra Zero: Português Brasileiro

Todo atendimento, prompt, documento, PDF, copy, log operacional legível por cliente e regra deste repositório deve ser pensado primeiro em português brasileiro moderno. Inglês só é permitido para nomes técnicos inevitáveis de APIs, bibliotecas, comandos, variáveis, classes, modelos ou protocolos.

Antes de criar ou alterar copy de cliente, leia [.rules/pt-br.md](.rules/pt-br.md).

## Regra P0: Evolution API, QR Code e Sessão

Antes de qualquer alteração envolvendo Evolution API, Docker Compose, QR code, sessão WhatsApp, webhook, versão da imagem, banco da Evolution ou variáveis `EVOLUTION_*`, leia [.rules/evolution-api.md](.rules/evolution-api.md).

- Não trocar tag da Evolution, usar `latest`, limpar volumes, recriar instância, chamar `/instance/logout` ou alterar `EVOLUTION_INSTANCE` sem estudar releases/issues oficiais e sem plano de rollback.
- Não usar `DATABASE_URL` do WhatsApp RAG como `EVOLUTION_DATABASE_URL`; a Evolution API precisa de banco/schema próprio.
- Se `EVOLUTION_DATABASE_URL` estiver ausente, restaure o valor correto do vault/local. Não copie outra URL e não rode migrations em banco desconhecido.
- Não imprimir QR code, JID, telefone real, payload de cliente, `EVOLUTION_DATABASE_URL`, `DATABASE_CONNECTION_URI` ou credenciais da Evolution.
- Payloads `@lid` devem preferir `remoteJidAlt`/`participantAlt` só quando apontarem para `@s.whatsapp.net`; `fromMe=true` nunca vira lead.
- Para subir a Evolution API, prefira `scripts/evolution-safe-up.sh`; ele roda preflight antes de `docker compose up -d evolution-api`.

## Fechamento Obrigatório Da Tarefa

No fim de qualquer tarefa com alteração de arquivo:

1. Rode a validação necessária, no mínimo `.venv/bin/python -m pytest` quando houver código Python.
2. Rode `./sync.sh --message "tipo: resumo objetivo"` para gerar `CLAUDE.md`, commitar, publicar no Gitea e espelhar no GitHub.
3. Se a mudança já estiver no Gitea e só faltar espelho, rode `./sync.sh --mirror-only`.
4. Confirme `git status --short` limpo antes da resposta final.

`origin` é o Gitea primário. `github` é apenas espelho.

Antes de qualquer alteração neste repositório, leia primeiro:

- [.context/docs/architecture.md](.context/docs/architecture.md) — arquitetura do MVP determinístico
- [.context/docs/context.md](.context/docs/context.md) — entendimento macro do MVP
- [.context/docs/decisions.md](.context/docs/decisions.md) — regras comerciais e preços
- [.context/docs/database.md](.context/docs/database.md) — schema de leads e lead_state
- [.context/docs/playbook.md](.context/docs/playbook.md) — playbook de incidentes
- [.context/docs/evolution.md](.context/docs/evolution.md) — Evolution API e sessão

Esses docs são a referência para contexto, não mais o mapa antigo de PC1/PC2.

## Regras De Trabalho

- Não altere `.env` sem rodar `scripts/env-vault.sh sync` depois.
- Não rode `scripts/env-vault.sh sync` se isso remover `EVOLUTION_DATABASE_URL={SECRET}` ou outros placeholders obrigatórios de `.env.example`; restaure o contrato mascarado antes de finalizar.
- Não versionar segredos, tokens, telefones sensíveis ou chaves reais.
- Testes de atendimento devem usar `/test/chat?...&send=false` para não enviar WhatsApp real.
- O pipeline MVP é determinístico: intent por regex, decisão comercial em `commercial_router.py`, respostas de `response_catalog.py`.
- **Não adicionar lógica nova em `agent_graph/nodes/nodes.py`** — é dívida técnica de 4390 linhas, legado LangGraph. Novo código vai para `app/mvp_attendance.py` ou `agent_graph/domain/`.
- Feature flags em `docker-compose.yml`: `MINIMAL_MVP_ENABLED=1`, `RAG_ENABLED=0`, `TTS_ENABLED=0`, `VISION_ENABLED=0`.
- Antes de finalizar alterações de código, rode `.venv/bin/python -m pytest`.
