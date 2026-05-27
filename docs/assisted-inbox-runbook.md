# Assisted Inbox — Runbook Operacional

## Visão Geral

O painel de revisão humana (`ASSISTED_MODE`) permite que o humano aprove, edite ou rejeite respostas sugeridas pelo bot antes de qualquer envio ao cliente WhatsApp.

```
Cliente envia mensagem
    → Bot gera resposta candidata
    → Runtime detecta ASSISTED_MODE
    → ReviewItem criado com status PENDING
    → Humano acessa inbox
    → Humano aprova/edita/rejeita
    → Worker envia via Redis queue
    → Status webhook atualiza sent/delivered/read/failed
    → Feedback salva before/after
    → Real case exporter alimenta refinamento
```

## Modos de Runtime

| Modo | Comportamento |
|------|--------------|
| `SHADOW` | Gera resposta, salva métricas, NÃO envia |
| `ASSISTED` | Gera resposta, cria ReviewItem, NÃO envia até aprovação |
| `CANARY` | Autoenvia só intents permitidos + CANARY_PERCENT |
| `NORMAL` | Produção plena |

## Prioridades de ReviewItem

| Prioridade | Gatilho | Expiração |
|------------|---------|-----------|
| `URGENT` 🔴 | risco_eletrico, reclamação, cheiro queimado | 2h |
| `HIGH` 🟠 | projeto, PMOC, laudo, contrato, proposta | 8h |
| `NORMAL` 🟡 | manutenção, conserto, instalação | 24h |
| `LOW` 🟢 | saudação, higienização simples | 24h |

## API Endpoints

### GET /review/inbox
Lista items com filtro. Parâmetros:
- `filter_mode`: all | pending | urgent | risco_eletrico | projetos | pdf_documentos | edited | rejected | sent
- `limit`: default 50
- `offset`: paginação

### GET /review/items/{review_id}
Detalhes completos do item.

### POST /review/items/{review_id}/approve
Aprova sem editar. Body opcional: `{"edited_response": "..."}` para editar e já aprovar.

### POST /review/items/{review_id}/edit
Edita a resposta. Body: `{"new_response": "...", "edited_by": "human"}`

### POST /review/items/{review_id}/reject
Rejeita sem enviar. Body: `{"reason": "motivo obrigatório"}`

### POST /review/items/{review_id}/send
Envia resposta aprovada (approved_response) via WhatsApp. O item precisa estar com status APPROVED ou EDITED.

### POST /review/items/{review_id}/mark-expired
Marca manualmente como expirado.

### POST /review/expire-all
Expira todos os PENDING que ultrapassaram o expiry time.

### GET /review/stats
Estatísticas: total, by_status, by_priority, pending, urgent, risco_eletrico.

## Regras de Segurança

1. **PDF/documento**: NUNCA autoenvia. Sempre requer aprovação manual via drive.
2. **Áudio**: Passa por `evaluate_audio_policy` antes do envio. Texto > 300 chars ou < 50 chars bloqueia.
3. **Intent risco**: risco_eletrico, projeto, pmoc, laudo, contrato, reclamação SEMPRE vão para humano.
4. **fromMe=true**: ignorado no webhook — não cria ReviewItem.
5. **message_id duplicado**: ignorado — idempotência por Redis.
6. **Logs**: NUNCA expõem token, telefone completo, endereço completo, ou prompt interno.

## Fluxo de Envio

```
1. Humano aprova/editar → API retorna should_send=True + response_to_send
2. API enfileira payload na Redis queue (action=review_send, review_id, response)
3. Worker consome queue item
4. Worker resolve phone via msg_phone mapping ou conversation_id lookup
5. Worker envia via send_whatsapp_message
6. Status webhook atualiza sent/delivered/read/failed no tracker
```

## Histórico de Feedback

Toda edição humana salva before/after em `ProductionFeedbackStore`:
- `edited_response` vs `suggested_response`
- `intent`, `conversation_id`, `review_id`
- Usado pelo Phase 2.5 refinement loop

## Expiração

- Itens expiram automaticamente se ficarem PENDING além do tempo limite
- URGENT: 2h, HIGH: 8h, NORMAL/LOW: 24h
- Expired não envia automaticamente — humano precisa reavaliar
- Cron job recomendado: a cada 15min, chamar POST /review/expire-all

## Monitoramento

Métricas via `ConversationMetricsCollector`:
- `review_item_created` — novo item criado
- `review_item_approved` — aprovado sem edição
- `review_item_edited` — aprovado com edição
- `review_item_rejected` — rejeitado
- `review_item_sent` — enviado ao cliente

## Configuração ENV

```bash
BOT_RUNTIME_MODE=assisted
BOT_HUMAN_REVIEW_REQUIRED_INTENTS=risco_eletrico,projeto,pmoc,laudo,contrato,reclamacao
BOT_AUTO_REPLY_ALLOWED_INTENTS=welcome,higienizacao,visita_tecnica,servicos,agenda
REVIEW_DEFAULT_EXPIRY_HOURS=24
REVIEW_EXPIRY_HOURS_URGENT=2
REVIEW_EXPIRY_HOURS_HIGH=8
REVIEW_AUDIO_MAX_CHARS=300
REVIEW_API_TOKEN=  # opcional,空白 = sem auth
```

## Troubleshooting

| Problema | Solução |
|----------|--------|
| Item não aparece na inbox | Verificar se `BOT_RUNTIME_MODE=assisted` |
| Send falha | Verificar Redis queue e worker ativos |
| Áudio bloqueado | Texto muito longo (>300) ou muito curto (<50) — editar ou aprovar como texto |
| PDF não envia | Normal — PDF requer aprovação manual, não autoenvia |

## PRÓXIMO PASSO

Phase 2.9: Assisted Pilot com 30 conversas reais — medir approval rate, edit rate, tempo médio, intents problemáticos.