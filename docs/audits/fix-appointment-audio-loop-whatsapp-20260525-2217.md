# Auditoria — Fix: Loop de Agendamento e Placeholder de Áudio

**Data:** 2026-05-25 22:17  
**Branch:** `fix/appointment-audio-loop-whatsapp`

## Reprodução do Print (Sequência Real de Bug)

1. Cliente: "Boa noite. Gostaria de fazer um orçamento para o meu ar condicionado"
   - Bug: bot respondeu com mensagem de alto valor ("esse caso é mais técnico") sem sinal técnico
   - Causa: `_detect_high_value_reason` disparou `high_value_consultoria` apenas pelo intent
   
2. Cliente: "Manutenção" (via áudio — STT falhou)
   - Bug: `[áudio]` foi tratado como `cidade_bairro` no extractor
   - Bug: `appointment_ready=True` mesmo sem dado mínimo
   - Bug: resposta usou "agendamento de manutenção em [áudio]"
   
3. Cliente: "Tarde"
   - Bug: bot repetiu "manhã ou tarde?" em vez de confirmar o período
   - Bug: "Vou sinalizar o gerente agora" vazou para o cliente
   
4. Cliente: "Tarde" (novamente)
   - Bug: mesmo loop, mesma resposta, `appointment_ready` em loop infinito

## Causas Identificadas (Arquivos + Linhas)

| Bug | Arquivo | Linha(s) | Causa |
|-----|---------|----------|-------|
| `[áudio]` como city | `app/api/webhook.py` | 260,265 | `message = message or "[áudio]"` sem sanitização downstream |
| STT falha silenciosa | `nodes.py` | 3178-3179 | Apenas loga error, segue com `[áudio]` no fluxo |
| appointment_ready prematuro | `nodes.py` | 2873-2876 | score≥5 sem mínimo real por serviço |
| Copy com gerente e loop | `nodes.py` | 751-757 | `_appointment_ready_response` hardcodado |
| Pergunta janela em loop | `nodes.py` | 2547 | `response_guard_check` fallback pergunta "manhã ou tarde" sem verificar se já respondida |
| Janela não persiste | `nodes.py` | 2744-2800 | `DEFAULT_LEAD_STATE` sem chave `appointment` |
| high_value agressivo | `nodes.py` | 1465-1493 | intent consultoria → high_value sem sinal técnico |
| appointment_confirmed ausente | `app/worker.py` | 69-78 | `_OWNER_WORTHY_REASONS` sem "appointment_confirmed" |

## Arquivos Alterados

- `agent_graph/nodes/nodes.py` — utilidades de sanitização, STT flag, DEFAULT_LEAD_STATE, min_data, bare service, janela persistida, _appointment_ready_response, dispatch dedup, high_value, copy patches
- `agent_graph/guards/response_guard.py` — 4 novas violations
- `app/worker.py` — adiciona `appointment_confirmed` ao set de reasons

## Testes Criados

- `tests/test_audio_placeholder_bug.py`
- `tests/test_appointment_window_loop.py`
- `tests/test_appointment_ready_minimum_data.py`
- `tests/test_bare_service_selection.py`
- `tests/test_high_value_not_overtrigger.py`
- `tests/test_print_bug_regression.py`
- Casos adicionados em `tests/test_response_guard.py`

## Rollback

Cada fase tem commit isolado. Para reverter:
```bash
git log --oneline  # identificar hash do commit a reverter
git revert <hash>
```
O hook de commit também tira snapshot BTRFS automático a cada commit.
