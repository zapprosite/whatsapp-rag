# Auditoria — onboarding, política comercial e planilha de leads

Data: 2026-05-26 03:47
Branch: `fix/onboarding-commercial-policy-leads-sheet`

## Objetivo

Refatorar o atendimento para:

- cumprimentar uma vez, sem reiniciar conversa;
- coletar nome de forma leve;
- usar política comercial first;
- avançar para visita técnica ou agenda quando houver caminho claro;
- registrar leads no PostgreSQL;
- exportar planilha operacional sem virar fonte da verdade.

## Prints de regressão

- `tests/test_onboarding_lead_identity.py`: onboarding com saudação única, telefone automático e nome leve.
- `tests/test_commercial_policy_first.py`: instalação R$850, higienização R$200, visita técnica R$50 e projeto fora do escopo fixo.
- `tests/test_leads_export.py`: CSV com headers corretos, sync opcional e falha de planilha sem quebrar runtime.
- `tests/test_action_planner.py`: pedido de agenda sem dados completos agora pode virar visita técnica, sem loop de formulário.

## Causa raiz

- O planner antigo priorizava `missing_fields` cedo demais e tratava foto, BTU, bairro e outros campos úteis como quase bloqueantes.
- O onboarding dependia mais do estado incidental da conversa do que de histórico persistido, o que permitia saudação repetida e reinício artificial.
- A camada comercial ainda misturava decisão determinística com resposta aberta, deixando RAG/LLM influenciar demais o próximo passo.
- Não existia serviço operacional claro para exportar leads do PostgreSQL sem acoplar isso ao fluxo crítico do WhatsApp.

## Arquivos alterados

- `.context/docs/playbook_vendas.md`
- `.gitignore`
- `agent_graph/domain/actions.py`
- `agent_graph/domain/field_policy.py`
- `agent_graph/domain/onboarding.py`
- `agent_graph/guards/response_guard.py`
- `agent_graph/nodes/compose_response.py`
- `agent_graph/nodes/dispatch_side_effects.py`
- `agent_graph/nodes/nodes.py`
- `agent_graph/nodes/plan_next_action.py`
- `agent_graph/nodes/reduce_lead_state.py`
- `agent_graph/nodes/sync_lead_sheet.py`
- `agent_graph/nodes/understand_message.py`
- `agent_graph/services/google_sheets.py`
- `agent_graph/services/leads_export.py`
- `docs/audits/onboarding-commercial-policy-leads-sheet-20260526-0347.md`
- `prisma/schema.prisma`
- `scripts/export-leads.py`
- `tests/test_action_planner.py`
- `tests/test_commercial_policy_first.py`
- `tests/test_leads_export.py`
- `tests/test_onboarding_lead_identity.py`

## Testes criados

- `tests/test_onboarding_lead_identity.py`
- `tests/test_leads_export.py`
- `tests/test_commercial_policy_first.py`

## Comandos rodados

- `git checkout -b fix/onboarding-commercial-policy-leads-sheet`
- `.venv/bin/python -m pytest tests/test_onboarding_lead_identity.py -vv`
- `.venv/bin/python -m pytest tests/test_leads_export.py -vv`
- `.venv/bin/python -m pytest tests/test_commercial_policy_first.py -vv`
- `.venv/bin/python -m pytest tests/test_action_planner.py::test_calendar_request_with_missing_requirements_asks_missing_field -vv`
- `.venv/bin/python -m pytest tests/test_action_planner.py::test_calendar_request_with_requirements_offers_slots -vv`
- `.venv/bin/python -m pytest tests/test_commercial_router.py::test_nao_consegue_horario_calls_calendar_when_schedule_allowed -vv`
- `.venv/bin/python -m pytest tests/test_handoff_policy.py::test_graph_unknown_retrieves_and_generates_recovery -vv`
- `.venv/bin/python -m pytest`

## Rollback

Se necessário, reverter este branch por commit ou remover o branch e manter a base anterior intacta:

- `git revert <commit_fix>`
- `git revert <commit_docs>`
- Se a branch ainda não tiver sido mesclada: `git checkout <branch-anterior>` e `git branch -D fix/onboarding-commercial-policy-leads-sheet`
