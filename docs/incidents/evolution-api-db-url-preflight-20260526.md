# Incidente: Evolution API com `EVOLUTION_DATABASE_URL` ausente

Data do registro: 2026-05-26.

Status: resolvido e blindado.

## Resumo

A Evolution API entrou em loop de restart porque o Compose recebeu `EVOLUTION_DATABASE_URL` ausente, deixando `DATABASE_CONNECTION_URI` vazio dentro do container. Uma tentativa intermediária de reaproveitar o `DATABASE_URL` do WhatsApp RAG fez a Evolution tentar aplicar migrations em um schema já usado pelo app, resultando em erro Prisma `P3005`.

A restauração correta foi usar novamente o banco/schema próprio da Evolution API, preservar os volumes de sessão e manter a imagem pinada em `evoapicloud/evolution-api:v2.3.7`.

## Impacto

- Evolution API ficou indisponível na porta `8080` durante o loop de restart.
- Envio/recebimento WhatsApp via Evolution ficou indisponível enquanto o container não subia.
- FastAPI/LangGraph do RAG continuou saudável em `:8000`.
- QR code, instância e volumes foram preservados; não houve logout, recriação de instância nem limpeza de volumes.

## Causa Raiz

1. `EVOLUTION_DATABASE_URL` estava ausente no `.env` local.
2. `docker-compose.yml` injeta essa variável em `DATABASE_URL` e `DATABASE_CONNECTION_URI` do serviço `evolution-api`.
3. Com a variável vazia, a Evolution falhou com erro Prisma de URL obrigatória.
4. Reaproveitar `DATABASE_URL` do RAG não é seguro, porque o banco/schema do app já contém tabelas próprias e não deve receber migrations da Evolution.

## O Que Foi Preservado

- Tag pinada: `evoapicloud/evolution-api:v2.3.7`.
- Volumes Docker:
  - `whatsapp-rag_evolution_instances`
  - `whatsapp-rag_evolution-data`
- Instância `RefrimixLead`.
- Sessão WhatsApp pareada, validada depois como `state=open`.

## O Que Não Fazer Novamente

- Não usar `DATABASE_URL` do RAG como `EVOLUTION_DATABASE_URL`.
- Não subir Evolution sem preflight.
- Não usar tag `latest`.
- Não migrar direto para `v2.4.0-rc*` em produção.
- Não chamar `/instance/logout` para testar.
- Não remover volumes de sessão.
- Não recriar instância nem alterar `EVOLUTION_INSTANCE` sem plano de re-pareamento.
- Não imprimir URL de banco, API key, QR code, JID, telefone real ou payload de cliente em logs compartilhados.

## Ações Corretivas Aplicadas

- Restaurado `EVOLUTION_DATABASE_URL` correto da Evolution no `.env` local, sem imprimir o valor.
- Adicionado `scripts/evolution-preflight.py`.
- Adicionado `scripts/evolution-safe-up.sh`.
- `scripts/validate-env.py` passou a bloquear `EVOLUTION_DATABASE_URL == DATABASE_URL`.
- `scripts/env-vault.sh` passou a preservar placeholders versionados de `.env.example`.
- `.rules/evolution-api.md` passou a exigir consulta a docs/releases/issues oficiais na data atual antes de alterações.
- `AGENTS.md` passou a apontar para a regra Evolution.

## Comandos Seguros

Validar ambiente sem valores:

```bash
.venv/bin/python scripts/validate-env.py --env-file .env
```

Validar contrato específico da Evolution:

```bash
.venv/bin/python scripts/evolution-preflight.py --env-file .env
```

Subir Evolution com guardrail:

```bash
scripts/evolution-safe-up.sh
```

Checar API sem expor segredos:

```bash
curl -sS --max-time 15 http://localhost:8080/
```

Checar estado da instância deve ser feito com redaction de API key, QR code, token, JID e telefone.

## Validações Executadas

- `scripts/evolution-preflight.py --env-file .env`: OK.
- `scripts/validate-env.py --env-file .env`: OK.
- `curl http://localhost:8080/`: Evolution API respondeu `version=2.3.7`.
- Estado da instância: `RefrimixLead` com `state=open`.
- `curl http://localhost:8000/health`: Redis, Qdrant, LangGraph e worker OK.
- `.venv/bin/python -m pytest`: 149 testes passando.

## Fontes Oficiais Consultadas

Consulta feita em 2026-05-26.

- Releases oficiais da Evolution API: `https://github.com/evolution-foundation/evolution-api/releases`
- Docs oficiais da Evolution API: `https://docs.evolutionfoundation.com.br/evolution-api`
- Docs oficiais de webhooks: `https://docs.evolutionfoundation.com.br/evolution-api/configuration/webhooks`
- Issue oficial sobre QR/pairing e sintomas relacionados: `https://github.com/evolution-foundation/evolution-api/issues/2437`
- Issue oficial sobre licença obrigatória na linha 2.4: `https://github.com/evolution-foundation/evolution-api/issues/2534`
- Issue oficial sobre reconexão/QR após logout em 2.4 RC: `https://github.com/evolution-foundation/evolution-api/issues/2539`
- Issue oficial sobre `Bad MAC`/reconnect em 2.3.7: `https://github.com/evolution-foundation/evolution-api/issues/2518`
- Issue oficial sobre duplicidade/perda de `messages_upsert`: `https://github.com/evolution-foundation/evolution-api/issues/2110`
- Issue oficial sobre edição de mensagem em 2.3.7: `https://github.com/evolution-foundation/evolution-api/issues/2545`

## Decisão Operacional

Manter `v2.3.7` em produção neste repositório até haver razão objetiva para canário. Qualquer upgrade/downgrade precisa de:

1. consulta aos docs/releases/issues oficiais na data da mudança;
2. snapshot/backup de banco, Redis e volumes;
3. plano de rollback;
4. teste canário sem apagar sessão atual;
5. registro em `docs/incidents/` ou `docs/audits/`.
