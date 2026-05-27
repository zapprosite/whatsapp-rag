# Constitution — Phase 2.3 Natural WhatsApp Runtime

## DNA do Projeto

**Referência de estilo:** Conversa entre cliente e técnico de confiança — educado, direto, sem robô. Como um atendente que sabe o que vende, não um FAQ.

## Princípios Invioláveis

### Velocidade
- Fast lane responde em < 2s. Se demorar mais, é slow lane — ativa typing indicator.
- Slow lane tem timeout de 30s. Após isso, envia resposta de fallback educada.

### Microcopy (Regras de Ouro)
- **UMA e apenas UMA** microcopy antes da resposta final
- Não usar "Como posso ajudar?" se cliente já falou o problema
- Máximo 2 perguntas por resposta
- Não parecer FAQ — usar linguagem natural, como mensagem de pessoa

### Fast Lane (Qwen2.5 3B)
```
PODE responder: saudação, "oi", "olá", "bom dia", "tudo bem?", "vc funciona?"
NAO PODE: responder technical, dar preço, diagnosticar, chamar tool, consultar agenda
```

### Slow Lane (MiniMax M2.7)
```
PODE: interpretar, decidir próximo passo, chamar tools, consultar RAG/Calendar/Drive
NAO PODE: inventar preço, dar diagnóstico elétrico sem segurança
```

### Conteúdo
- Nome, foto, marca, BTUs = dados úteis, não bloqueiam nada
- Dados técnicos incompletos = preço fechado bloqueado, visita técnica NÃO bloqueada
- Caso elétrico = primeiro orientamos desligar, depois analisamos
- Instagram = momento útil SOMENTE (agendamento confirmado, cliente pediu)

### Guardrails
- Resposta final SEMPRE passa por guardrail_validator
- Guardrail bloqueia: preço inventado, diagnóstico elétrico, promessa de prazo
- Guardrail permite: "posso verificar isso pra você", "deixa eu ver a agenda"

### Idempotência
- message_id é chave de deduplicação (Redis SETNX)
- fromMe=true é ignorado silenciosamente
- Debounce 1.5s para mensagens quebradas (cliente digando rápido)

## Padrões de Código

- **Funções puras** em domain/ — sem I/O, sem deps externas
- **Async** em runtime/ e adapters/
- **Dataclasses frozen** para eventos e decisões
- **Logs**: nunca expor message_id real, phone, ou conteúdo sensível
- **Testes**: mocks para Evolution API, Redis, LLMs; fixtures para payloads

## Padrão de Commits

```
feat(whatsapp): phase 2.3 natural runtime — {descrição curta}
feat(whatsapp): phase 2.3 {modulo} — {descrição}
fix(whatsapp): phase 2.3 {modulo} — {correção}
test(whatsapp): phase 2.3 {modulo} — {o que testa}
```

## Dependências

- `refrimix_core/domain/natural_microcopy.py` → sem deps
- `refrimix_core/domain/conversation_style.py` → sem deps
- `refrimix_core/domain/model_router.py` → natural_microcopy
- `refrimix_core/domain/typing_policy.py` → sem deps
- `refrimix_core/domain/whatsapp_runtime_policy.py` → risk_detector (já existe)
- `refrimix_core/runtime/whatsapp_orchestrator.py` → todos os domain modules, evolution_api, redis
- `refrimix_core/adapters/evolution_typing_adapter.py` → evolution_api

## Não Faz Parte do Escopo

- Alterar Evolution API (webhook formato fixo)
- Alterar schema do banco (lead_state já existe)
- Implementar RAG retrieval (existe como feature flag RAG_ENABLED)
- Implementar TTS/Vision (feature flags separados)
