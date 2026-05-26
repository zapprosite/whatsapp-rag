# Auditoria de Respostas — MVP Refrimix
**Data:** 2026-05-26  
**Caminho:** `docs/audits/rewrite-response-catalog-mvp-20260526-0525.md`

Tabela de mapeamento das respostas existentes em `agent_graph/nodes/compose_response.py`, `agent_graph/nodes/nodes.py` e `agent_graph/guards/response_guard.py`.

## Tabela de Mapeamento de Respostas

| Arquivo | Função / Bloco | Tipo de Resposta | Decisão (manter/remover/substituir) | Raciocínio |
| :--- | :--- | :--- | :--- | :--- |
| `nodes.py` | `_unknown_recovery_response` | Fallback / Ambiguidade | **Substituir** | Será substituída pela resposta catálogo `fallback_recover_context` e desambiguação direta. |
| `nodes.py` | `_direct_price_response` | Resposta direta de preço | **Substituir** | Será substituída pelos templates determinísticos de preço e visita técnica no catálogo. |
| `nodes.py` | `_appointment_ready_response` | Confirmação de período pré-agendamento | **Substituir** | O fluxo de confirmação e janela será gerido pelas mensagens unificadas do catálogo. |
| `nodes.py` | `_appointment_window_confirmed_response` | Confirmação final da janela | **Substituir** | Substituída pelas mensagens de agendamento/janela no catálogo. |
| `nodes.py` | `_window_preference_saved_but_not_ready_response` | Preferência registrada com pendência | **Substituir** | Unificada no catálogo sob o tipo de ação correspondente. |
| `nodes.py` | `_process_question_response` | Explicação de processo | **Substituir** | Substituída por `explain_process_installation` ou visita genérica. |
| `nodes.py` | `_handoff_initial_response` | Inicial do atendimento humano | **Substituir** | Substituída por mensagem estruturada de handoff no catálogo. |
| `nodes.py` | `_light_complaint_response` | Reclamação leve | **Substituir** | Substituída por template uniforme de handoff/sinalização humana do catálogo. |
| `compose_response.py` | `_commercial_response` | Resposta determinística de caminho | **Remover / Substituir** | Toda lógica de texto grande foi movida para o catálogo de acordo com o `commercial_path`. |
| `compose_response.py` | `action_type == "welcome_onboarding"` | Saudação inicial | **Substituir** | Mapeada como `welcome_onboarding` no catálogo. |
| `compose_response.py` | `action_type == "ask_lead_name"` | Pergunta sobre o nome | **Substituir** | Mapeada como `ask_lead_name` no catálogo. |
| `compose_response.py` | `action_type == "ask_basic_service"` | Pergunta do tipo de serviço | **Substituir** | Mapeada como `ask_basic_service` no catálogo. |
| `compose_response.py` | `action_type == "offer_fixed_installation"` | Proposta de instalação fixa | **Substituir** | Mapeada como `offer_fixed_installation` no catálogo. |
| `compose_response.py` | `action_type == "offer_fixed_hygienization"` | Proposta de higienização fixa | **Substituir** | Mapeada como `offer_fixed_hygienization` no catálogo. |
| `compose_response.py` | `action_type == "offer_technical_visit"` | Proposta de visita de R$50 | **Substituir** | Mapeada como `offer_technical_visit_installation`, `_maintenance` ou `_generic` no catálogo. |
| `compose_response.py` | `action_type == "offer_project_visit"` | Proposta de projeto complexo | **Substituir** | Mapeada como `offer_project_visit` no catálogo. |
| `compose_response.py` | `action_type == "answer_capability_question"` | Capacidades do catálogo | **Substituir** | Mapeada como `answer_capability_hygienization` no catálogo. |
| `compose_response.py` | `action_type == "save_preferred_window"` | Anotação de período preferido | **Substituir** | Mapeada como `save_preferred_window` no catálogo. |
| `response_guard.py` | `_validate_next_action_contract` | Validação de guardrails | **Manter & Ajustar** | Ajustada para validar contra as novas strings do catálogo e banir frases antigas que causam loops. |

## Resumo da Auditoria

1. **Eliminação de Frases Antigas e Loops:** As strings redundantes e frases que confundem o cliente quando ele diz "não entendi" foram completamente listadas.
2. **Catalogação Estrita:** Toda resposta legível por cliente agora reside em `agent_graph/domain/response_catalog.py`, tornando fácil a auditoria de copy e a internacionalização futura se necessário (mantendo sempre a Regra Zero de Português Brasileiro).
3. **Decisão Inteligente por Serviço:** A renderização separa dinamicamente a resposta de visita técnica baseada no tipo de serviço (`instalacao`, `manutencao` ou genérico).
