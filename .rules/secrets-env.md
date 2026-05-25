# Regra Obrigatória: Secrets, Env e Vault

Este repositório trata `.env.example` como contrato mascarado. `{SECRET}` é proteção intencional contra vazamento por agentes, assistentes e automações.

## P0 Para Qualquer Agente

- Não remover `{SECRET}` do `.env.example`.
- Não transformar `.env.example` em arquivo com exemplos realistas de segredo.
- Não copiar valor real de `.env`, `.env.local`, terminal, vault, Docker, histórico Git ou painel externo para arquivo versionado.
- Não pedir segredo real em chat quando a tarefa puder ser resolvida por nome de variável, placeholder ou validação local.
- Não imprimir token, senha, telefone sensível, URL com senha, API key, chave SSH, service account ou credencial em resposta, log, doc, teste ou commit.

## Como Configurar Com Segurança

- Valores reais ficam só em `.env`, `.env.local`, vault ou configuração local ignorada pelo Git.
- O contrato operacional fica em `env.schema.md`.
- Para atualizar o contrato mascarado, use `scripts/env-vault.sh sync`.
- Para validar ambiente, use `.venv/bin/python scripts/validate-env.py --env-file .env`.
- A validação deve listar apenas nomes ausentes ou mascarados, nunca valores.

## Se Encontrar Segredo Versionado

1. Não repita o valor em relatório, commit, issue ou resposta.
2. Remova o valor do arquivo versionado.
3. Troque por `${NOME_DA_VARIAVEL}` ou `{SECRET}`, conforme o arquivo.
4. Documente a variável em `env.schema.md`.
5. Registre a ocorrência como `possivel_segredo_versionado`, mascarando no máximo como `abcd...wxyz` se for inevitável.
6. Recomende rotação do segredo sem reproduzir o segredo.

## Classificação Padrão

- `.env.example`: `placeholder_intencional_seguro`.
- `prisma/.env.example`: `exemplo_seguro` quando só tiver placeholders genéricos.
- `.env` e `.env.local`: `valor_real_local_ignorado`.
- Tokens, senhas e URLs com credencial em arquivos versionados: `possivel_segredo_versionado`.
- Telefones, hosts internos, JIDs, nomes de instância e URLs operacionais reais: `valor_operacional_sensivel`.
