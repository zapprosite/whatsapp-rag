# Estado da Arte: LLM + RPA + Incidents

> Pesquisa consolidada — mai/2026. Objetivo: dar a qualquer LLM o contexto necessário para entender o cenário atual antes de tratar incidentes.

---

## 1. RPA Tradicional vs Agentic AI

### RPA Tradicional (2019–2023)
- Bots executam scripts rígidos gravados por desenvolvedores.
- Alto custo de manutenção: qualquer mudança na UI quebra o bot.
-抄壮 — sem capacidade de raciocínio ou adaptação.
- Ideal para processos estáveis e de alto volume (e.g., faturamento, CRM).

### Agentic AI / LLM-based Automation (2024–2026)
- Agentes usam LLM para **raciocinar**, **decidir** e **executar** ações em ambiente.
- ReAct paradigm (Reason + Act): a cada langkah, o agente observa resultado e recalcula.
- **Problema do ReAct**: invocar LLM a cada passo é ineficiente em tarefas repetitivas → custo token explodes.
- **Solução SOTA**: AutoRPA — distillation do raciocínio ReAct em funções RPA robustas (arXiv:2605.21082v1, mai/2026).

---

## 2. SOTA em Incident Management + AI Agents

### Tendência Global (2025–2026)
1. **Runbooks viram código First-Class**: runbooks escritos como código versionado, testável, executável por agente (não mais markdown estático).
2. **On-call agent com runbook embutido**: o agente recebe o runbook como contexto RAG e executa steps determinísticos; quando não sabe, escala para humano com diagnóstico pronto.
3. **Autonomous incident response**: o agente ejecuta ações corretivas automaticamente — restart de container, rollout rollback, purga fila — sem aguard humans no loop crítico.
4. **SLO-aware triage**: severidade classificada não por regra fixa, mas por impacto real no SLO/SLA do cliente.

### Frameworks de Referência
- **AWS DevOps Agent**: agente autônomo que usa topology intelligence para remediação em ambiente AWS.
- **ServiceNow Virtual Agent**: ITSM integrado — o agente abre incidentes, pesquisa KB, executa change requests.
- **Cutover / iLert**: slack-first, humanos no loop com hand-off suave entre agente e on-call.
- **Digitate (Ignio)**: ML-driven pattern recognition sobre métricas históricas para predizer e auto-remediar antes de escalar.

### Padrões Comuns de Incident Types (SRE/SRE-like)
| Type | Trigger | Autonomous Action | Escalates When |
|------|---------|-------------------|----------------|
| Service Down | healthcheck 503 ou timeout | restart container, flip feature flag | 3 failures in a row |
| Redis Queue Explosion | queue depth > threshold | flush corrupted items, restart worker | user impact detected |
| Database Connection Pool | pool exausto | conexões ativas > 80% | query timeout ≥ 2s |
| Evolution API timeout | webhook response > 30s | retry com exponential backoff | 5xx da Evolution |
| LLM provider failure | 429 ou 500 do provider | fallback de modelo ou resposta cached | all models failed |
| Loop conversacional | lead stuck > N mensagens mesma intent | surgical reset do lead state | N/A — autonomia local |

---

## 3. AutoRPA — O Paradigma Mais Relevante para Nosso Contexto

> "AutoRPA: Efficient GUI Automation through LLM-Driven Code Synthesis from Interactions" — arXiv:2605.21082v1 (mai/2026)

### O que é
Framework que converte o raciocínio ReAct de um agente LLM em **funções RPA robustas e reutilizáveis** — eliminando a necessidade de invocar LLM em cada iteração de uma tarefa repetitiva.

### Por que importa para o WhatsApp Bot
- O bot Refrimix tem **padrões de falha repetitivos**: Redis cheia, Evolution API timeout, lead em loop.
- Aplicando AutoRPA: o agente LLM observa o padrão 1 vez, o runbook menangkap logic como **função determinística testável**, e nas próximas ocorrências executa sem novo raciocínio LLM — só invoca quando algo sai do expected path.
- Isso é o equivalente a "ensinar o agente a usar o playbook".

### Arquitetura Conceptual (AutoRPA-Inspired para Nossa Stack)

```
[Alert / Incidente detected]
       │
       ▼
[Agent LLM — RACIOCÍNIO PRIMEIRA VEZ]
       │
  1. Observa o comportamento
  2. Consulta o Incident Register
  3. Executa ação canônica
  4. Se SUCESSO → distillation → registra como runbook testável
  5. Se FALHA → escalation → humans notified
       │
 ▼ (se próxima ocorrência do mesmo padrão)
[Runbook determinístico — executa direto, sem LLM]
```

---

## 4. Mapeamento: Onde Estamos vs SOTA

| Componente | Hoje (Refrimix MVP) | SOTA Ideal | Gap |
|-----------|-------------------|------------|-----|
| Incident trigger | healthcheck + manual detection | auto-detect via métricas + SLO | 🔴 Funcionalidade não existe |
| Runbook format | markdown estático em playbook.md | código versionado + testável | 🟡 Razoável — pode evoluir |
| Agente executor | Hermes/CLI com reasoning Socrático | agente autônomo com toolUse | 🟡 Hermes faz parcialmente |
| Escalation | mensagens para o Will | PagerDuty/discord auto-escalation | 🔴 Não existe |
| Auto-remediation | scripts manuais (reset-lead, flush redis) | self-healing loops | 🟡 Scripts existem |
| Distillation | não implementado | próximo passo natural | 🔴 Não existe |

---

## 5. Referências

- arXiv:2605.21082v1 — AutoRPA (mai/2026)
- AWS DevOps Agent — agentic incident response
- devops.com — "Death of the Toil" (AI replacing runbooks)
- digitate.com — AI agent for incident resolution
- tianpan.co/blog — AI-assisted incident response with on-call agent + runbook
- ServiceNow Virtual Agent — ITSM AI integration
