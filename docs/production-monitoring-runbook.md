# Runbook — Produção: Monitoramento de Conversas Phase 2.6

## Visão Geral

Phase 2.6 implementa 3 modos de runtime para o bot Refrimix:

| Modo | Comportamento | Quando usar |
|------|--------------|-------------|
| `shadow` | Gera resposta, salva, NÃO envia | Validação inicial, teste em produção |
| `assisted` | Gera resposta, mostra p/ humano aprovar | Primeiros leads reais, ajuste fino |
| `canary` | Envia automático só intents seguros | Operação autônoma limitada |

---

## Variáveis de Ambiente

```bash
BOT_RUNTIME_MODE=shadow              # shadow | assisted | canary
BOT_CANARY_PERCENT=10                 # % tráfego em modo canary
BOT_AUTO_REPLY_ALLOWED_INTENTS=welcome,higienizacao,visita_tecnica,servicos,agenda
BOT_HUMAN_REVIEW_REQUIRED_INTENTS=risco_eletrico,projeto,pmoc,laudo,contrato,reclamacao
BOT_FEEDBACK_EXPORT_MIN_CASES=30
```

---

## Modo SHADOW

### O que faz
1. Recebe mensagem do lead
2. Gera resposta via bot
3. Salva resposta no banco
4. **NÃO envia ao cliente**

### Como ativar
```bash
export BOT_RUNTIME_MODE=shadow
```

### Verificação
- Conferir que webhook do Evolution não envia resposta automaticamente
- Mensagens ficam pendentes em `whatsapp_status_tracker` com status `pending`
- Métricas `guardrail_blocked` e `human_handoff` são incrementadas corretamente

---

## Modo ASSISTED

### O que faz
1. Recebe mensagem do lead
2. Gera resposta via bot
3. **Mostra resposta para humano**
4. Humano edita ou aprova
5. Humana envia ao cliente

### Como ativar
```bash
export BOT_RUNTIME_MODE=assisted
```

### Fluxo
```
Lead → Bot gera resposta → Salva em production_feedback → Notifica humano →
Humano edita/aprova → Envia via Evolution API → Tracking
```

### Feedback
- Cada edição humana é salva em `production_feedback`
- Campos editados são registrados para análise
- Após 30 casos, pode exportar dataset para Phase 2.5

---

## Modo CANARY

### O que faz
- Envia automaticamente para intents **permitidos**
- Desvia para humano para intents **bloqueados**

### Intents Permitidos (auto-reply)
- `welcome` — Saudação inicial
- `higienizacao` — Solicitação de higienização
- `visita_tecnica` — Agendamento de visita
- `servicos` — Lista de serviços
- `agenda` — Solicitação de agendamento

### Intents Bloqueados (human review)
- `risco_eletrico` — Disjuntor, fio quente, cheiro de queimado
- `projeto` — VRF, cassete, piso-teto, duto
- `pmoc` — Plano de manutenção
- `laudo` — Laudo técnico
- `contrato` — Contrato de serviço
- `reclamacao` — Reclamação de cliente

### Como ativar
```bash
export BOT_RUNTIME_MODE=canary
export BOT_CANARY_PERCENT=10
```

### Percentual de Tráfego
- 10% do tráfego vai para modo canary (auto-reply)
- 90% vai para modo assisted (humano aprova)
- Gradually aumentar percentual conforme confiança

---

## Métricas Obrigatórias

### Status de Mensagem
| Métrica | Descrição |
|---------|-----------|
| `sent` | Mensagem enviada ao WhatsApp |
| `delivered` | Mensagem entregue ao cliente |
| `read` | Mensagem lida pelo cliente |
| `failed` | Falha no envio |
| `pending` | Mensagem pendente (shadow mode) |

### Engajamento
| Métrica | Descrição |
|---------|-----------|
| `user_replied` | Cliente respondeu após mensagem do bot |
| `appointment_offered` | Bot ofereceu agendamento |
| `appointment_scheduled` | Cliente confirmou agendamento |
| `human_handoff` | Transferência para humano |
| `guardrail_blocked` | Resposta bloqueada por guardrail |

### Áudio
| Métrica | Descrição |
|---------|-----------|
| `audio_sent` | Áudio enviado com sucesso |
| `audio_failed` | Falha ao gerar/enviar áudio |
| `text_fallback_sent` | Texto enviado como fallback |

---

## Regras de Segurança (NUNCA Violar)

### ✅ O que fazer
- Risco elétrico → sempre transferir para humano
- PDF/contrato/PMOC/laudo/proposta → sempre transferir para humano
- Cliente irritado → sempre transferir para humano

### ❌ O que NÃO fazer
- Resposta automática para risco elétrico
- Envio de áudio para texto longo (laudo, orçamento, contrato, PMOC)
- Mais de 2 perguntas por mensagem
- Bloquear agendamento por falta de nome ou foto
- Diagnóstico definitivo sem avaliação

---

## Webhook de Status

### Endpoint de callback
O Evolution API envia status via webhook para:
```
POST /webhook/whatsapp/status
```

### Payload
```json
{
  "message_id": "msg_123",
  "conversation_id": "conv_456",
  "status": "delivered",
  "timestamp": "2026-05-27T12:00:00Z"
}
```

### Atualização de métricas
- `track_message_status()` atualiza `whatsapp_status_tracker`
- Estatísticas de entrega disponíveis via `get_delivery_stats()`

---

## Detecção de Conversa Estagnada

### Regra
Após 30 minutos sem resposta do cliente, marcar como `stale`.

### Ação
- Notificar humano sobre conversa pendente
- Evitar envio de follow-up automático

### Configuração
```python
detect_stale_conversation("conv_001", threshold_minutes=30)
```

---

## Exportação de Casos Reais

### Script
```bash
python scripts/export_real_cases_to_refinement_loop.py
python scripts/export_real_cases_to_refinement_loop.py --min-cases 30 --output reports/real_cases_20260527.jsonl
```

### Anonimização
- Telefone → `MASCARA_TEL`
- Nome → `MASCARA_NOME`
- Endereço → `MASCARA_END`
- Conversation ID → `MASCARA_CONV_XXXX`

### Limite
Mínimo 30 casos para exportar (configurável via `BOT_FEEDBACK_EXPORT_MIN_CASES`)

---

## Análise de Abandono

### Onde o cliente parou
```python
tracker = LeadOutcomeTracker()
result = tracker.get_abandonment_rate()
# result["by_turning_point"] mostra pontos de abandono
```

### Taxa de Conversão por Intent
```python
result = tracker.get_conversion_by_intent()
# result["higienizacao"]["conversion_rate"]
```

---

## Relatório Semanal

### Métricas para incluir
1. Total de conversas
2. Taxa de abandono por turning point
3. Taxa de conversão por intent
4. Top 10 campos editados por humanos
5. Casos de guardrail bloqueados
6. Performance de áudio (sent vs failed)

### Geração
Executar ao final de cada semana:
```bash
python scripts/generate_weekly_monitoring_report.py
```

---

## Rollback

### Se bot começar a falhar
1. Mudar `BOT_RUNTIME_MODE=assisted` imediatamente
2. Todas as mensagens vão para humano aprovar
3. Investigar causa raiz
4. Corrigir e testar em shadow antes de voltar para canary

### Se métrica de falha disparar
1. Verificar `whatsapp_status_tracker` para identificar mensagens com `failed`
2. Verificar `guardrail_blocked` — pode indicar novo padrão não tratado
3. Adicionar novo guardrail se necessário (NÃO em `risk_detector.py` ou `guardrail_validator.py`)

---

## Checklist de Go-Live

- [ ] `BOT_RUNTIME_MODE=shadow` definido
- [ ] Webhook de status configurado
- [ ] Monitoramento de métricas ativo
- [ ] Comunicação com equipe sobre modo shadow
- [ ] Plano de rollback documentado
- [ ] Limite de 30 casos para exportação configurado