# Regra Obrigatória: Evolution API, QR Code e Sessão

Este projeto usa a Evolution API como ponte WhatsApp. A sessão/QR code já pareada é estado operacional sensível.

## P0 Para Evolution API

- Não trocar tag da imagem, rodar upgrade/downgrade, usar `latest`, limpar volumes, apagar instância, chamar `/instance/logout`, recriar instância ou alterar `EVOLUTION_INSTANCE` sem estudar releases/issues oficiais da Evolution API e registrar a razão.
- Não usar `DATABASE_URL` do WhatsApp RAG como `EVOLUTION_DATABASE_URL`. A Evolution API precisa de banco/schema próprio. Reaproveitar o banco do app pode quebrar migrations com `P3005` ou misturar tabelas operacionais.
- Não imprimir `EVOLUTION_DATABASE_URL`, `DATABASE_URL`, `DATABASE_CONNECTION_URI`, API key, JID, telefone real, QR code ou payload de cliente em logs, respostas, commits ou docs.
- Se `EVOLUTION_DATABASE_URL` estiver ausente, pare e peça/restaure o valor correto do vault/local. Não invente URL, não copie outra variável e não rode migrations em banco desconhecido.
- Para preservar QR/sessão, nunca remova os volumes `evolution_instances` e `evolution-data` sem backup e janela planejada de novo pareamento.

## Versão e Issues Oficiais

- Em 2026-05-25/26, a linha `v2.4.0-rc*` é pre-release e não deve ser promovida direto para produção do `whatsapp-rag`.
- A linha `v2.4.0` introduz risco operacional de licença obrigatória; valide antes de qualquer upgrade.
- A versão local deve ficar pinada por tag exata em `docker-compose.yml`. Não usar `evoapicloud/evolution-api:latest`.
- Antes de mexer em versão ou sessão, consulte:
  - releases oficiais: `https://github.com/evolution-foundation/evolution-api/releases`
  - issues oficiais de QR/pairing, `@lid`, webhook e reconexão.

## Guardrails De Webhook

- Eventos `fromMe=true` nunca devem virar lead, mesmo se `fromMe` vier em `data.key`, `data` ou raiz do payload.
- Para payloads com `@lid`, prefira `remoteJidAlt`/`participantAlt` somente quando apontarem para `@s.whatsapp.net`. Se o `Alt` também for `@lid`, procure outro campo com JID telefônico antes de normalizar.
- Testes de atendimento devem usar `/test/chat?...&send=false`.
- Testes reais de webhook devem validar `MESSAGES_UPSERT`, `CONNECTION_UPDATE`, áudio/imagem e `@lid` sem enviar WhatsApp real quando houver rota de teste.

## Diagnóstico Seguro

- Para ambiente, use `.venv/bin/python scripts/validate-env.py --env-file .env`; ele deve listar só nomes de variáveis.
- Para logs, filtre e redija identificadores antes de compartilhar. Se um log local expôs URL com credencial, não repita o valor e recomende rotação do segredo.
- Se a Evolution estiver em loop de restart por banco vazio/incorreto, pare o container antes de continuar para reduzir vazamento em logs locais.
