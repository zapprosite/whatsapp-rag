# Auditoria: Response Architecture Action Planner

Data: 2026-05-26 02:07
Branch: `refactor/response-architecture-action-planner`

## Fluxo atual

Hoje o fluxo principal ainda nasce assim:

`preprocess_input -> extract_lead_data -> classify_service -> retrieve_knowledge/generate_response -> guards -> format -> modality -> dispatch_appointment_alert -> save_interaction`

Os acoplamentos observados:

- `preprocess_input` já alterava `lead_state` com efeito de imagem.
- `extract_lead_data` já alterava preferência de janela.
- `classify_service` misturava intenção, risco, relacionamento e condução.
- `generate_response` concentrava recuperação de contexto, decisão de agenda, leitura de estado, cache, RAG e escrita final.
- `dispatch_appointment_alert` lia texto genérico em vez de um plano explícito.

## Bugs reproduzidos

Casos confirmados antes do refactor:

1. `Como funciona?` com `preferred_window=tarde` podia voltar como confirmação de período em vez de explicar processo.
2. `Sim` dependia de heurística tardia da resposta e nem sempre aplicava ao último campo perguntado.
3. `Vocês também trabalham com higienização?` podia reabrir roteamento do serviço principal.
4. `Tarde` podia avançar para confirmação operacional sem slot real.
5. Alertas operacionais dependiam de detecção textual ampla e podiam disparar fora do momento correto.

## Plano de refactor

Separação em quatro camadas:

1. `understand_message`
   - só entende a mensagem atual
   - não altera `lead_state`

2. `reduce_lead_state`
   - aplica a mensagem entendida ao estado
   - atualiza fotos, respostas curtas e preferência de janela

3. `stage_engine` + `plan_next_action`
   - calcula estágio conversacional e de agenda
   - define `next_action` como contrato único da resposta

4. `compose_response` + `dispatch_side_effects`
   - resposta nasce de `next_action`
   - efeitos colaterais passam a depender do plano

## Testes de regressão

Cobertura adicionada para:

- entendimento de processo, capacidade, resposta curta, janela, agenda e preço
- reducer de resposta curta e mismatch de imagem
- planner para processo, capability, agenda incompleta, agenda completa, janela e escolha de slot
- composição determinística por ação
- slots reais via `freebusy`
- `response_guard` validando `next_action`
- dispatcher sem alerta indevido em lead e com insert controlado de evento
- regressão do print de `Como funciona?` após `tarde`

## Rollback

Se o novo fluxo falhar em produção:

1. voltar a branch anterior estável
2. restaurar o grafo anterior com `generate_response`
3. manter os arquivos novos apenas fora do fluxo ou removê-los em commit de rollback
4. validar com `pytest` e rota `/test/chat?...&send=false` antes de religar o bot
