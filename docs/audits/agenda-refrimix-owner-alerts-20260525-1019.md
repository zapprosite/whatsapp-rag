# Auditoria — Agenda Refrimix e alertas do owner

Data: 2026-05-25 10:19

## Estado atual de OWNER_PHONE

- `OWNER_PHONE` existe no contrato de ambiente e é usado como canal do gerente.
- `app/worker.py` envia alertas para o owner via `notify_owner()` e `maybe_notify_owner_from_result()`.
- O owner recebe hoje alertas de handoff humano, reclamação/risco, revisão humana, cliente ativo, lead pronto para agenda e alto valor genérico.

## Como alertas são enviados hoje

- `app/worker.py` possui `send_whatsapp_message()` com chamada direta para Evolution API em `/message/sendText/{instance}`.
- `agent_graph/services/alerts.py` duplica a chamada HTTP e envia `send_appointment_alert()` diretamente para `OWNER_PHONE`.
- Não há serviço único de WhatsApp para texto individual, grupo e listagem de grupos.
- Deduplicação de alerta soft existe no worker com chave `handoff_alert:{phone}:{reason}` e TTL `HANDOFF_ALERT_TTL_SECONDS`.

## Como CustomerService representa agenda hoje

- `CustomerService` tem `phone`, `service`, `status`, `address`, `scheduled_window`, `notes`, `created_at` e `updated_at`.
- A janela de agenda é textual em `scheduled_window`.
- Não há `scheduled_start`/`scheduled_end` estruturados, nome do cliente, cidade/bairro, prioridade, tipo de serviço ou camada de valor.

## Presença de group JID

- Não há `AGENDA_GROUP_JID` no contrato atual.
- Não há envio operacional para grupo.
- Não há discovery de grupos da Evolution API.

## Plano de mudança

1. Adicionar variáveis de ambiente para owner, grupo operacional, horários, TTLs e limites.
2. Expandir `CustomerService` com campos opcionais e índices sem remover `scheduled_window`.
3. Criar `agent_graph/services/whatsapp.py` para centralizar envio e discovery.
4. Refatorar `alerts.py` e `worker.py` para usar o serviço único.
5. Criar `agenda_digest.py` para buscar `CustomerService`, formatar e enviar resumo ao grupo por JID.
6. Criar scheduler interno com Redis lock/dedup para 07:00 e 20:00 em `America/Sao_Paulo`.
7. Adicionar rotas e scripts para preview/envio manual e discovery do grupo.
8. Reforçar detecção de lead de alto valor e manter resposta consultiva ao lead.
9. Cobrir com testes focados em digest, owner alert, dedup e takeover.
10. Atualizar README.

## Riscos

- Banco de produção precisa receber novos campos antes do digest estruturado usar `scheduled_start`.
- Evolution API pode variar endpoint de listagem de grupos; o script deve reportar falha sem enviar mensagem.
- Envio para grupo depende de `AGENDA_GROUP_JID`; com JID vazio deve apenas logar warning e não enviar.
- Mudança em `agent_graph/nodes/nodes.py` exige rebuild/restart do container para produção.

## Rollback

- Reverter commit da branch e executar `prisma db push`/migration reversa se os campos forem aplicados e precisarem ser removidos.
- Para rollback operacional rápido, definir `AGENDA_GROUP_ENABLED=0`, `OWNER_HIGH_VALUE_ALERTS_ENABLED=0` ou `OWNER_ALERTS_ENABLED=0`.
- O fluxo legado de `scheduled_window` permanece compatível, então serviços já cadastrados não dependem dos novos campos.
