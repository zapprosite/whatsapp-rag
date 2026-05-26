# Auditoria de Redução ao MVP Mínimo — 26/05/2026

Este documento registra a Fase 0 do processo de transformação do projeto em um MVP mínimo viável, estável e livre de código inflado.

---

## Metadados Operacionais Baseline
- **Data/Hora**: 26/05/2026 06:05 (Horário Local)
- **Branch Atual**: `feature/proxima-tarefa-20260526`
- **Commit Atual (HEAD)**: `9a03a6325da8cffdbb4e72793efcb0eee66b7844`
- **Objetivo**: Reduzir a base de código ao fluxo MVP mínimo estritamente determinístico no WhatsApp para a Refrimix, eliminando inteligência experimental e perguntas infinitas.

---

## Lista de Arquivos Analisados e Categorizados

### 1. CORE_KEEP (Arquivos de Produção & Testes MVP)
- `app/main.py` — Inicialização do FastAPI
- `app/api/webhook.py` — Ingestão de webhooks do WhatsApp/Evolution
- `app/api/health.py` — Monitoramento honesto de saúde do sistema
- `app/worker.py` — Loop de processamento de mensagens assíncronas do Redis
- `app/mvp_attendance.py` — Fluxo simplificado e determinístico do MVP
- `agent_graph/domain/commercial_router.py` — Lógica e regras comerciais centrais
- `agent_graph/domain/response_catalog.py` — Fonte única de verdade de cópias e textos
- `agent_graph/nodes/understand_message.py` — Detecção de intents determinística
- `agent_graph/nodes/plan_next_action.py` — Planejador de ações
- `agent_graph/nodes/compose_response.py` — Gerenciador de resposta
- `agent_graph/services/whatsapp.py` — Integração de envio via Evolution API
- `agent_graph/services/alerts.py` — Envio mínimo de alertas
- `agent_graph/services/conversation_memory.py` — Histórico de conversa
- `prisma/schema.prisma` — Estrutura de dados compatível com o banco atual
- `scripts/reset-lead.py` — Utility script para desenvolvimento
- `scripts/reset_lead.py` — Surgical reset de estado no Redis e DB
- `scripts/export-leads.py` — Exportação de leads em CSV

### 2. KEEP_DISABLED (Arquivos Existentes Desativados do Caminho Crítico)
- `qdrant/*` — Motor e seeds de busca semântica RAG (Desativado)
- `knowledge/*` — Base de dados estática do HVAC (Desativado)
- `agent_graph/services/tts.py` — Módulo de síntese de voz (Desativado)
- `agent_graph/services/stt.py` — Módulo de áudio-transcrição (Desativado)
- `agent_graph/services/vision.py` — Inferência do Qwen2.5-VL de imagens (Desativado)
- `agent_graph/services/calendar.py` — Lógica de agendamento no Google Calendar (Desativado)

### 3. CANDIDATE_REMOVE_OR_ARCHIVE (Arquivos inflados/obsoletos a serem movidos para `_archive/minimal-mvp-disabled/`)
- Testes antigos do LangGraph completo que validam fluxos redundantes/loops
- Scripts antigos de refinamento de prompts e seeds RAG não utilizados no MVP
- Documentações duplicadas fora do diretório `.context/`

---

## Ações de Segurança e Rollback
- Toda remoção/arquivamento será validada localmente por meio de ferramentas de análise estática (`grep`/`rg`) e execução imediata de `pytest`.
- Em caso de quebra de dependências ou imports inesperados, os arquivos arquivados serão imediatamente restaurados.
