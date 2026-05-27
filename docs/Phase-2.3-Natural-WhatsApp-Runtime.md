# Phase 2.3 — Natural WhatsApp Runtime

## Status: SPEC

## Objetivo
Implementar runtime de atendimento WhatsApp com duas velocidades (fast/slow lane), respeitando estilo conversacional brasileiro educado, sem FAQ engessado, e com guardrails.

## Contexto de Arquitetura

```
WhatsApp → Evolution API → FastAPI /webhook → Redis Queue → Worker
                                                                  ↓
                                                    whatsapp_orchestrator
                                                    /        |        \
                                          fast_lane    slow_lane    send
                                          (Qwen3B)   (MiniMax M2.7) (Evolution)
```

## Fast Lane — Qwen2.5 3B Local (PC1)
- Responde em < 2s
- Microcopy educada, acolhe
- Ignora mensagens técnicas/comerciais
- Não inventa preço, não diagnostica, não chama tools, não consulta agenda

## Slow Lane — MiniMax M2.7
- Interpreta intenção
- Consulta RAG se habilitado
- Usa risk_detector e guardrail_validator
- Consulta Calendar/Drive quando necessário
- Gera resposta final natural

## Regras de Negócio (invioláveis)

1. Saudação simples → responde rápido com Qwen2.5 3B
2. Mensagem técnica/comercial → microcopy curta + depois MiniMax M2.7
3. Se MiniMax demorar → ativar typing indicator
4. No máximo 1 microcopy antes da resposta final
5. Não usar "Como posso ajudar?" se cliente já explicou o problema
6. Não pedir checklist gigante
7. Máximo 2 perguntas por resposta
8. Nome, foto, marca, BTUs não bloqueiam visita
9. Dados técnicos incompletos → bloqueia preço fechado, não bloqueia visita técnica
10. Casos elétricos → orientar desligar equipamento
11. Instagram → só em momento útil (consulta agenda ou positivo), nunca como spam
12. Nenhuma resposta parece FAQ engessado
13. Toda resposta final passa por guardrail_validator
14. Toda mensagem recebida tem idempotência por message_id
15. Ignorar fromMe=true

## Fluxo de Processamento

1. Evolution webhook recebe mensagem
2. Validar event == MESSAGES_UPSERT
3. Ignorar fromMe=true
4. Idempotência por message_id (Redis deduplication)
5. Debounce 1.5s para juntar mensagens quebradas
6. model_router decide fast/slow
7. Qwen2.5 3B → microcopy se fast lane
8. Typing indicator ON se slow lane
9. MiniMax M2.7 interpreta e decide
10. guardrail_validator valida resposta
11. Envio via Evolution REST
12. Salvar decisão no Postgres

## Arquivos a Criar

### Domain
- `refrimix_core/domain/natural_microcopy.py` — templates de microcopy
- `refrimix_core/domain/conversation_style.py` — estilo conversacional BR
- `refrimix_core/domain/model_router.py` — routing fast/slow
- `refrimix_core/domain/typing_policy.py` — quando ativar typing
- `refrimix_core/domain/whatsapp_runtime_policy.py` — regras de negócio

### Runtime
- `refrimix_core/runtime/whatsapp_orchestrator.py` — orquestrador principal

### Adapters
- `refrimix_core/adapters/evolution_typing_adapter.py` — typing indicator

### Knowledge
- `knowledge/refrimix/playbooks/ptbr_whatsapp_style.md` — estilo WhatsApp BR
- `knowledge/refrimix/playbooks/natural_scheduling_policy.md` — política de agendamento natural

### Testes
- `tests/test_natural_microcopy.py`
- `tests/test_model_router.py`
- `tests/test_typing_policy.py`
- `tests/test_whatsapp_runtime_policy.py`
- `tests/test_whatsapp_orchestrator.py`

## Critérios de Aceitação

- [ ] Mensagem "Oi" ou "Olá" responde em < 2s via fast lane
- [ ] Mensagem técnica não recebe resposta do fast lane (forward para slow)
- [ ] Typing indicator ativa antes de slow lane responder
- [ ] Microcopy não repete antes da resposta final
- [ ] guardrail_validator bloqueia resposta com preço inventado
- [ ] Idempotência por message_id — mesma mensagem não processa 2x
- [ ] fromMe=true é ignorado
- [ ] Máximo 2 perguntas por resposta
- [ ] Instagram só aparece em momento útil
- [ ] 58+ testes existentes continuam passando
