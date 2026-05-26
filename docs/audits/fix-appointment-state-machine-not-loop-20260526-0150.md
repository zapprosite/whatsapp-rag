# Auditoria: fix appointment state machine not loop

Data: 2026-05-26 01:50
Branch: `fix/appointment-state-machine-not-loop`

## Print do bug

Reprodução textual informada pelo operador, sem anexar print com telefone, JID, QR code ou payload real:

1. Bot pediu foto da condensadora.
2. Cliente mandou foto.
3. Bot registrou `tarde`.
4. Cliente perguntou: "Como funciona?"
5. Bot respondeu novamente: "Perfeito, deixei o período da tarde registrado. Vou encaminhar..."

Resultado esperado: depois de registrar uma janela, a resposta deve seguir a intenção atual do cliente. Para "Como funciona?", o bot deve explicar o processo e continuar pedindo o requisito pendente, sem repetir confirmação de período.

## Causa raiz

O estado `appointment_ready` estava sendo usado como decisão global de resposta. Quando ele ficava verdadeiro, caminhos determinísticos como `generate_response`, `_continuation_response` e `response_guard_check` podiam priorizar agenda/confirmar período mesmo quando a mensagem atual era uma pergunta de processo.

Também havia dois riscos relacionados:

- janela informada antes dos requisitos mínimos podia ser tratada como confirmação, em vez de preferência anotada;
- alerta operacional poderia cair no fallback de owner e precisava suprimir envio quando o telefone do owner fosse igual ao telefone do lead.

## Arquivos alterados

- `agent_graph/nodes/nodes.py`
- `agent_graph/guards/response_guard.py`
- `agent_graph/services/alerts.py`
- `tests/test_appointment_state_machine.py`
- `tests/test_process_question_after_window.py`
- `tests/test_image_expected_field_mismatch.py`
- `tests/test_owner_alert_same_phone.py`
- `tests/test_no_double_appointment_alert.py`
- `tests/test_current_print_regression.py`
- `tests/test_response_guard.py`

## Correção

- Criada máquina explícita de estágio de agendamento em `appointment.appointment_stage`.
- `appointment_ready` passou a ser recalculado por `refresh_appointment_state`.
- "Tarde" antes dos requisitos mínimos vira preferência anotada.
- "Tarde" com requisitos mínimos confirma a janela uma vez.
- Perguntas de processo, como "Como funciona?", respondem processo e próximo requisito.
- Foto interna recebida quando a pendência era foto externa não satisfaz a foto da condensadora.
- `response_guard` bloqueia confirmação repetida de janela e pergunta de agenda antes dos requisitos mínimos.
- Alerta para owner é suprimido quando `OWNER_PHONE` e telefone do lead são iguais, sem imprimir o telefone em log.
- `dispatch_appointment_alert` exige janela confirmada ou `handoff_reason=appointment_confirmed` e respeita deduplicação por `appointment_alert_sent`.

## Testes criados

- `tests/test_appointment_state_machine.py`
- `tests/test_process_question_after_window.py`
- `tests/test_image_expected_field_mismatch.py`
- `tests/test_owner_alert_same_phone.py`
- `tests/test_no_double_appointment_alert.py`
- `tests/test_current_print_regression.py`

## Validação

Comandos executados:

```bash
.venv/bin/python -m pytest tests/test_appointment_state_machine.py -vv
.venv/bin/python -m pytest tests/test_process_question_after_window.py -vv
.venv/bin/python -m pytest tests/test_image_expected_field_mismatch.py -vv
.venv/bin/python -m pytest tests/test_owner_alert_same_phone.py -vv
.venv/bin/python -m pytest tests/test_no_double_appointment_alert.py -vv
.venv/bin/python -m pytest tests/test_current_print_regression.py -vv
.venv/bin/python -m pytest tests/test_response_guard.py -vv
```

Resultado: todos passaram.

## Rollback

Reverter o commit desta branch no Gitea:

```bash
git revert <commit>
```

Após rollback, reiniciar o container do bot se a mudança já tiver sido aplicada em produção, porque `agent_graph/nodes/nodes.py` participa do grafo de atendimento.
