# Política de Agendamento Natural — Refrimix

## Princípio Geral
O cliente não quer processo de agendamento — quer saber "quando o técnico vem". Cada etapa deve reduzir fricção.

## Janelas de Agendamento

### Manhã
- Horário: 8h às 12h
- Expressão: "manhã" / "de manhã" / "no período da manhã"

### Tarde
- Horário: 13h às 18h
- Expressão: "tarde" / "de tarde" / "no período da tarde"

## Fluxo de Agendamento

```
Cliente manifesta interesse
  ↓
Confirmar serviço (se ainda não definido)
  ↓
Perguntar janela (manhã/tarde) — UMA pergunta
  ↓
Verificar disponibilidade no Calendar
  ↓
Confirmar data e janela
  ↓
Registrar no Calendar com dados mínimos
```

## Regras de Ouro

1. **Uma pergunta por vez** — não perguntar tudo junto
2. **Não pedir dados que não são necessários** — nome não é obrigatório para agendar
3. **BTUs/marca não bloqueiam agendamento** — podem ser coletados na visita
4. **Foto não é obrigatória** — pode ser pedida como ajuda, não como requisito
5. **Cidade/bairro é o dado mais importante** — calcula deslocamento e custo

## Dados Mínimos para Agendamento

Obrigatórios:
- Telefone (já temos)
- Cidade + Bairro
- Serviço (instação/manutenção/higienização)
- Janela preferida (manhã/tarde)

Opcionais (não bloqueiam):
- Nome
- Endereço completo
- BTUs/modelo
- Foto do local

## Campos do Calendar

Para visita técnica confirmada:
```
Título: [TESTE HERMES] Visita Técnica — {cidade_bairro}
Data: data combinada
Janela: manhã (8h-12h) ou tarde (13h-18h)
Descrição: {serviço} | {dados coletados}
```

## Política de Cancelamento

- Cliente pode remarendar 1 vez sem custo
- Remarcação > 1 vez: avisar que pode ter custo de deslocamento
- Cancelamento < 2h: confirmar se há custo de deslocamento

## Integração com Drive

- Após confirmação de visita, criar pasta do cliente se não existir
- Upload de fotos coletadas durante conversa
- Pasta: `Clientes > {Cidade} > {Bairro} > {Nome do Cliente}`

## Momentos de Instagram

Instagram é inserido APÓS confirmação de agendamento, quando:
- Cliente disse "perfeito", "combinado", "obrigado"
- Momento é positivo e de confiança

**Nunca** inserir Instagram no meio do processo de agendamento.

## Casos Especiais

### Cliente sem cidade/bairro definida
"Qual cidade e bairro fica o local do serviço?"

### Cliente sem janela definida
"Qual período prefere: manhã ou tarde?"

### Cliente quer horário específico
"A gente trabalha em janela de 4h (manhã ou tarde). Qual prefere?"

### Cliente pergunta se "tem como" em outro horário
"Infelizmente não consigo garantir horário fixo, mas posso pedir ao técnico que chegue no período que preferir."
