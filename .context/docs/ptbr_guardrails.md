---
source: .rules/pt-br.md
type: generic
---

# Guardrails PT-BR

## Regra Principal

Todo atendimento, prompt, documento, PDF, copy e instrução para LLM deve ser produzido em português brasileiro moderno. Inglês só é permitido para nomes técnicos inevitáveis de APIs, bibliotecas, comandos, variáveis, classes, modelos ou protocolos.

## Copy De Cliente

- WhatsApp: natural, curto, com jeito brasileiro de atendimento.
- PDF comercial: português técnico claro, formal o suficiente, sem inglês decorativo.
- Evitar termos como `Breakdown`, `budget`, `labor`, `client-ready`, `Must` e `Required` em qualquer copy final.
- Usar `detalhamento`, `orçamento`, `mão de obra`, `pronto para o cliente final`, `deve` e `obrigatório`.

## Números Fixos

- `5513974139382`: linha Refrimix Tecnologia, QR code lido na Evolution API.
- `5513996659382`: gerente, usado para receber crons e alertas.
- Eventos `fromMe=true` desses números são mensagens enviadas pela operação e devem ser ignorados pelo bot.

## Validação

Antes de finalizar mudança de copy ou documento:

```bash
.venv/bin/python -m pytest
```
