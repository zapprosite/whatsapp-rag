# Política de Documentos Drive — Refrimix

A pasta Google Drive da Refrimix é o **arquivo operacional** da empresa.

## Regras de Organização

- O bot usa o Drive para salvar: propostas técnicas, contratos, SLA, ordens de serviço, PMOC, laudos, orçamentos e materiais de redes sociais.
- O bot **não depende** do caminho `google-drive://` do GNOME. Esse caminho é apenas para navegação manual no Linux.
- O backend usa **Google Drive API** com `folder_id` via `.env`.
- Estrutura por ano/mês/atendimento dentro de cada pasta operacional.

## Estrutura de Pasta por Atendimento

Cada lead/atendimento gera uma pasta com:

```
{YYYY-MM-DD}_{telefone}_{cliente_ou_sem_nome}_{cidade}_{servico}/
  resumo_lead.md
  metadata.json
  fotos/
  *.pdf
```

## Contrato de Geração de Documentos

```
Hermes skill   → gera PDF localmente
google_drive_tool → salva no Drive
Postgres       → registra file_id e status
Qdrant/RAG     → indexa resumo e metadados
WhatsApp       → envia link/PDF quando aprovado
```

**Não misturar responsabilidades.** O Drive tool não gera PDF. O PDF skill não sobe para o Drive.

## Revisões Humanas Obrigatórias

Documentos com risco técnico alto, contrato, SLA, PMOC ou laudo **exigem revisão humana antes do envio**.

## Nomenclatura de Arquivos

```
ORCAMENTO_{cliente}_{servico}_{cidade}_{YYYYMMDD}_{status}.pdf
OS_{cliente}_{servico}_{cidade}_{YYYYMMDD}_{status}.pdf
LAUDO_{cliente}_{tipo}_{cidade}_{YYYYMMDD}.pdf
PROPOSTA_TECNICA_{cliente}_{servico}_{cidade}_{YYYYMMDD}.pdf
CONTRATO_{cliente}_{tipo}_{YYYYMMDD}.pdf
PMOC_{cliente}_{local}_{YYYYMMDD}.pdf
```

## Mapa: Tipo de Documento → Pasta

| Documento | Pasta |
|---|---|
| technical_proposal_pdf | 01_PROPOSTAS_TECNICAS |
| contract_pdf, sla_pdf | 02_CONTRATOS_E_SLA |
| service_order_pdf | 03_ORDENS_DE_SERVICO |
| pmoc_pdf, technical_report_pdf | 04_PMOC_E_LAUDOS |
| quote_pdf | 05_ORCAMENTOS |
| instagram_media_brief | 06_MIDIAS_E_REDES_SOCIAIS |

## RAG — O que Indexar

O RAG indexa: `metadata.json`, `resumo_lead.md`, texto extraído, tipo de documento, status comercial, serviço, cidade, risco, data, cliente.

O RAG **não expõe dados de outro cliente** em resposta. Busca por cliente exige phone/lead_id atual.

## Variáveis de Ambiente Obrigatórias

```env
GOOGLE_DRIVE_ROOT_FOLDER_ID={SECRET}
GOOGLE_DRIVE_FOLDER_PROPOSTAS_TECNICAS={SECRET}
GOOGLE_DRIVE_FOLDER_CONTRATOS_SLA={SECRET}
GOOGLE_DRIVE_FOLDER_ORDENS_SERVICO={SECRET}
GOOGLE_DRIVE_FOLDER_PMOC_LAUDOS={SECRET}
GOOGLE_DRIVE_FOLDER_ORCAMENTOS={SECRET}
GOOGLE_DRIVE_FOLDER_MIDIAS_REDES_SOCIAIS={SECRET}
GOOGLE_OAUTH_TOKEN_PATH={SECRET}
GOOGLE_OAUTH_CREDENTIALS_PATH={SECRET}
```

## Segurança

- Nunca commitar token OAuth, credentials, client_secret ou .env real.
- Pasta raiz (`google-drive://...`) é para uso humano local, não backend.
- Credenciais Google nunca versionadas.
