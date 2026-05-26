# Mapeamento do Core vs Inflado — 26/05/2026

Este documento organiza a árvore de arquivos e diretórios do repositório em categorias de utilidade e define o destino operacional de cada um para o MVP mínimo viável.

---

## 1. CORE_KEEP (Mantidos no Caminho Crítico)
Estes arquivos são essenciais para o pipeline principal do bot (webhook -> worker -> lead_repository -> understand_message -> commercial_router -> response_catalog -> sendText -> save LeadEvent).

- `app/main.py` (FastAPI)
- `app/api/webhook.py` (Ingestão de mensagens)
- `app/api/health.py` (Health Check honesto)
- `app/worker.py` (Consumidor assíncrono de filas Redis)
- `app/mvp_attendance.py` (Cérebro do fluxo MVP determinístico)
- `agent_graph/domain/commercial_router.py` (Regras de roteamento financeiro/visita)
- `agent_graph/domain/response_catalog.py` (Fonte única de textos e cópias)
- `agent_graph/nodes/understand_message.py` (Detecção de intenções)
- `agent_graph/nodes/plan_next_action.py` (Orquestrador básico)
- `agent_graph/nodes/compose_response.py` (Formatador de respostas)
- `agent_graph/services/whatsapp.py` (Envio de dados via API)
- `agent_graph/services/alerts.py` (Alertas administrativos)
- `agent_graph/services/conversation_memory.py` (Histórico de conversações)
- `prisma/schema.prisma` (Contrato do banco de dados)
- `scripts/reset-lead.py` & `scripts/reset_lead.py` (Reset de leads)
- `scripts/export-leads.py` (Exportação opcional em CSV)

---

## 2. KEEP_DISABLED (Mantidos, mas fora do caminho crítico do MVP)
Módulos persistentes para infraestrutura complementar que estão **desativados** por flags de ambiente e não impactam a performance do fluxo básico.

- `qdrant/*` (Banco de vetores/busca RAG - RAG_ENABLED=0)
- `knowledge/*` (Material técnico de suporte - RAG_ENABLED=0)
- `agent_graph/services/tts.py` (Clonagem de voz Chatterbox/OmniVoice - TTS_ENABLED=0)
- `agent_graph/services/stt.py` (Transcrição de voz Groq - STT_ENABLED=0)
- `agent_graph/services/vision.py` (Visão Qwen-VL - VISION_ENABLED=0)
- `agent_graph/services/calendar.py` (Google Calendar - GOOGLE_CALENDAR_ENABLED=0)

---

## 3. CANDIDATE_REMOVE_OR_ARCHIVE (Movidos para `_archive/minimal-mvp-disabled/`)
Estes arquivos e scripts são obsoletos, experimentais ou duplicados e serão movidos de forma limpa para a pasta de arquivos arquivados.

- **Scripts de Otimização e Refinamento**:
  - `refinar.py` -> Mover
  - `refinar_llm.py` -> Mover
  - `refinar_tts.py` -> Mover
- **Documentação Duplicada**:
  - `GUIDE_REFINAMENTO.md` -> Mover
  - `BLUEPRINT.md` -> Mover
- **Testes Antigos/Loops Complexos**:
  - `tests/test_compose_response_by_action.py` -> Marcar com `@pytest.mark.skip` ou Mover
  - `tests/test_appointment_state_machine.py` -> Marcar com `@pytest.mark.skip` ou Mover
  - `tests/test_handoff_policy.py` -> Marcar com `@pytest.mark.skip` ou Mover
  - `tests/test_response_guard.py` -> Marcar com `@pytest.mark.skip` ou Mover
  - `tests/test_refinar_llm_parsing.py` -> Marcar com `@pytest.mark.skip` ou Mover
  - `tests/test_refinar_ptbr_quality.py` -> Marcar com `@pytest.mark.skip` ou Mover
