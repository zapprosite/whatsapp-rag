# Política de Geração de PDF — Refrimix

## Princípio

PDF é gerado por **Hermes skill**, não pelo Drive tool ou Calendar tool.

```
Bot decide tipo de documento
→ Hermes PDF skill gera arquivo local
→ Drive tool salva no Drive
→ Postgres registra status
→ RAG indexa resumo
→ WhatsApp envia quando aprovado
```

## Skills de PDF Existentes

O Hermes já tem skills para gerar:
- Proposta comercial
- Orçamento
- Ordem de serviço
- Laudo técnico
- PMOC
- Contrato / SLA

## Fluxo Completo

```
Lead llega WhatsApp
  → Qwen 3B coleta dados
  → Bot identifica intent
  → Se orçamento → Hermes gera PDF local
              → Drive tool salva
              → Postgres marca rascunho
  → Se visita → Calendar tool verifica slots
             → Bot mostra opções
             → Cliente escolhe
             → Calendar tool cria evento
             → Calendar tool cria/linka pasta Drive
  → Se proposta técnica → Hermes gera PDF local
                      → Drive tool salva (requer revisão humana)
  → Se contrato/SLA/PMOC → Drive tool salva (requer revisão humana)
  → Humano aprova
  → WhatsApp envia link/PDF
```

## Quando NÃO Gerar PDF Automaticamente

- Contratos e SLA sem revisão humana
- Propostas técnicas com valor alto
- Laudos com risco elétrico, disjuntor, cheiro de queimado
- PMOC

## Status de Documento

```
rascunho      → PDF gerado localmente, não enviado
enviado       → PDF no Drive, enviado ao cliente
aprovado      → Cliente aprovou
perdido       → Cliente não respondeu ou recusou
revisar_humano → Aguarda revisão antes de enviar
```

## Nome de Arquivo

```
ORCAMENTO_{cliente}_{servico}_{cidade}_{YYYYMMDD}_{status}.pdf
OS_{cliente}_{servico}_{cidade}_{YYYYMMDD}_{status}.pdf
```
