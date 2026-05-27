# Phase 2.9 — Assisted Pilot Runbook

## Objetivo

Operar o bot em modo ASSISTED durante o piloto com 30 conversas reais, sem enviar nada automaticamente. Toda resposta sugerida pelo bot vira um `ReviewItem` pendente na inbox humana. O painel de revisão aprova, edita, rejeita ou expira cada item.

## Configuração Obrigatória

```bash
export BOT_RUNTIME_MODE=assisted
export BOT_CANARY_PERCENT=0
export BOT_AUTO_REPLY_ALLOWED_INTENTS=welcome,higienizacao,visita_tecnica,servicos,agenda
export BOT_HUMAN_REVIEW_REQUIRED_INTENTS=risco_eletrico,projeto,pmoc,laudo,contrato,reclamacao
```

## Regras de Operação

### Antes do Piloto

1. Verificar que todos os serviços estão rodando:
   ```bash
   curl -s http://localhost:3000/health | jq .core_version  # Evolution API
   curl -s http://localhost:8000/health | jq .status        # FastAPI
   ```

2. Confirmar que a inbox está vazia:
   ```bash
   curl -s http://localhost:8000/review/stats | jq .
   ```

3. Limpar dados de pilots anteriores:
   ```bash
   curl -X POST http://localhost:8000/review/expire-all -H "Authorization: Bearer $REVIEW_API_TOKEN"
   ```

### Durante o Piloto

**Regra 1 — Nada de autoenvio.** O bot nunca envia WhatsApp direto em ASSISTED_MODE. Isso vale para texto, áudio e documento.

**Regra 2 — Risco elétrico, projeto, PMOC, laudo, contrato e reclamação exigem atenção.** Esses intents têm prioridade URGENT ou HIGH. Priorize esses itens primeiro.

**Regra 3 — Áudio só com policy.** Qualquer resposta marcada como `audio` precisa passar por `tts_policy` e `audio_delivery_policy` antes de ser enviada. O painel exibe o resultado da avaliação de policy.

**Regra 4 — PDF e documento nunca.envio automático.** Sempre requer aprovaçãomanual. O painel mostra `PROPOSTA` ou `PDF` com canal bloqueado indicado.

### Workflow de Revisão

```
Cliente envia msg → Bot classifica intent → Cria ReviewItem pending → Humano revisa → Aprova/Edita/Rejeita/Expir
```

#### Passos do Humano

1. Listar inbox:
   ```bash
   curl -s "http://localhost:8000/review/inbox?filter_mode=pending&limit=20"
   ```

2. Ver detalhes de um item:
   ```bash
   curl -s "http://localhost:8000/review/items/{review_id}"
   ```

3. Para cada item, uma das seguintes ações:
   - **Aprovar** (sem edição):
     ```bash
     curl -X POST http://localhost:8000/review/items/{review_id}/approve \
       -H "Authorization: Bearer $REVIEW_API_TOKEN"
     ```
   - **Aprovar com edição**:
     ```bash
     curl -X POST http://localhost:8000/review/items/{review_id}/approve \
       -H "Authorization: Bearer $REVIEW_API_TOKEN" \
       -H "Content-Type: application/json" \
       -d '{"edited_response": "Nova resposta edited pelo humano"}'
     ```
   - **Editar** (marca como EDITED):
     ```bash
     curl -X POST http://localhost:8000/review/items/{review_id}/edit \
       -H "Authorization: Bearer $REVIEW_API_TOKEN" \
       -H "Content-Type: application/json" \
       -d '{"new_response": "Resposta editada", "edited_by": "atendente_01"}'
     ```
   - **Rejeitar** (não envía nada):
     ```bash
     curl -X POST http://localhost:8000/review/items/{review_id}/reject \
       -H "Authorization: Bearer $REVIEW_API_TOKEN" \
       -H "Content-Type: application/json" \
       -d '{"reason": "Tom inadequado, cliente irritado"}'
     ```
   - **Enviar** (após aprovação):
     ```bash
     curl -X POST http://localhost:8000/review/items/{review_id}/send \
       -H "Authorization: Bearer $REVIEW_API_TOKEN"
     ```
   - **Expirar manualmente:**
     ```bash
     curl -X POST http://localhost:8000/review/items/{review_id}/mark-expired \
       -H "Authorization: Bearer $REVIEW_API_TOKEN"
     ```

### Gerar Relatório

Ao final do piloto (mínimo 30 conversas avaliadas):

```bash
python scripts/run_assisted_pilot_report.py --min-conversations 30
python scripts/run_assisted_pilot_report.py --min-conversations 30 --output reports/assisted_pilot_YYYYMMDD.json
```

Saída esperada: relatório JSON com taxa de aprovação, edição, rejeição, expirados e recomendação.

### Exportar Casos Reais para Refinement Loop

```bash
python scripts/export_real_cases_to_refinement_loop.py --min-cases 30 --output reports/real_cases_pilot_YYYYMMDD.jsonl
```

Verificar que dados foram anonimizados (sem telefone, nome ou endereço expostos).

### Rodar Refinement Loop com Casos Reais

```bash
# Dry-run primeiro
python scripts/run_response_refinement_loop.py --count 30 --seed 42 --dry-run

# Aplicar se score >= 4.3
APPLY_REFINEMENTS=1 python scripts/run_response_refinement_loop.py --count 30 --seed 42
```

## Critérios de Recomendação

### Liberar CANARY_PERCENT=10 se:

| Critério | Limiar |
|----------|--------|
| Conversas reais avaliadas | >= 30 |
| approval_without_edit_rate | >= 70% |
| reject_rate | <= 10% |
| critical_guardrail_blocks | 0 |
| risco_eletrico autoenviado | 0 |
| PDF/documentos autoenviados | 0 |
| refinement loop executado | SIM |

### Metas por intent simples:

| Intent | approval_without_edit_rate |
|--------|---------------------------|
| welcome | >= 90% |
| servicos | >= 90% |
| visita_tecnica | >= 75% |
| Higienização | >= 80% |

### Permanecer em ASSISTED se:

- approval_without_edit_rate < 70%
- reject_rate > 10%
- Qualquer falha crítica senza tratamento
- risk_eletrico foi autoenviado

### Voltar para SHADOW se:

- Falhas críticas constantes
- Humann override > 50% das respostas
- Nenhum intent simples atingir 70% de aprovação sem edição

## Status Webhook

O webhook `/webhook/evolution/status` atualiza o rastreador de status mas **nunca gera resposta nova**. Status válidos: `sent`, `delivered`, `read`, `failed`.

O WhatsApp pode entregar `read` sem `delivered` explícito — o tracker aceita qualquer ordem.

## Posições do Inbox

```
filter_mode=pending       # Itens aguardando revisão
filter_mode=urgent       # Itens URGENT (risco elétrico, reclamação)
filter_mode=risco_eletrico # Only risco_eletrico
filter_mode=projetos      # HIGH + URGENT (projeto, PMOC, laudo, contrato)
filter_mode=pdf_documentos # Itens com PDF/documento
filter_mode=edited       # Já editados pelo humano
filter_mode=rejected     # Rejeitados
filter_mode=sent         # Já enviados ao cliente
```

## Alertas

-Items pendentes há mais de 2h com prioridade URGENT: escalate manualmente
- Items pending há mais de 24h: expirar
- Taxa de rejeição > 20%: interromper piloto, voltar para shadow
- Qualquer risco_eletrico nunca revisado: abortar piloto

## Equipe

 piloto é supervisionado por um técnico sênior da Refrimix. Não é fully autonomous.
