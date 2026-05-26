# Auditoria: fix/install-photo-stage-and-alert-dedup

**Data:** 2026-05-26 00:40  
**Branch:** fix/install-photo-stage-and-alert-dedup

## Bugs Identificados

1. **Vision classifica foto de parede como etiqueta** — `_HVAC_VISION_PROMPT` foca só em etiqueta/equipamento; foto de parede vira "não contém etiqueta técnica".
2. **`fotos["local_interno"]` nunca marcado** — `preprocess_input` não atualiza `lead_state` com tipo de foto; `foto_local_interno` nunca sai de `missing_fields`; bot repete o pedido.
3. **`appointment_ready` true com dados insuficientes** — `has_minimum_real_data_for_appointment` para instalação aceita só `local_interno` sem `local_externo`.
4. **Agendamento confirmado sem dados mínimos** — `generate_response` confirma `appointment_confirmed` quando cliente fala "Tarde" mesmo sem appointment_ready real.
5. **Alerta duplicado** — `maybe_notify_owner_from_result` + `dispatch_appointment_alert` disparam os dois para `appointment_confirmed`.
6. **Alerta vai para OWNER_PHONE em vez do grupo de agenda** — `send_appointment_alert` chama `send_owner_alert`; deveria usar grupo.
7. **Resumo do alerta usa histórico repetido** — `_summarize_conversation` cola falas de forma redundante.
8. **Owner alert vai para o mesmo número do lead** — sem guarda em `send_owner_alert`.
9. **"instalacao" sem acento nas respostas ao cliente** — falta `_human_service_label`.
10. **`_continuation_response` pede as duas fotos mesmo quando interno já recebido** — ramificação `foto_local_interno ou foto_local_externo` não diferencia.

## Arquivos Alterados

| Arquivo | Fases |
|---|---|
| `agent_graph/services/vision.py` | 1 |
| `agent_graph/nodes/nodes.py` | 2, 4, 5, 6, 7, 12 |
| `agent_graph/services/alerts.py` | 9, 10, 11 |
| `app/worker.py` | 8 |

## Testes Criados

- `tests/test_installation_image_stage.py`
- `tests/test_schedule_window_gate.py`
- `tests/test_appointment_alert_dedup.py`
- `tests/test_vision_image_type.py`
- `tests/test_owner_alert_not_to_lead.py`
- `tests/test_print_installation_photo_regression.py`
