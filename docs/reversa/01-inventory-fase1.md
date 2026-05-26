# FASE 1 — Reversa Inventory: WhatsApp-RAG
**Data:** 2026-05-26
**Projeto:** Refrimix WhatsApp RAG — Reconstrução Reversa

---

## R1: Regra Comercial — Instalação Simples R$850

**Origem:** `agent_graph/nodes/nodes.py` — WILL_SYSTEM_PROMPT + `_direct_price_response` + `compose_response.py`
**Confiança:** HIGH
**Arquivo(s):** `agent_graph/domain/commercial_router.py`, `agent_graph/nodes/compose_response.py`
**Função:** `decide_commercial_path()` → `fixed_installation_simple`

**Regra extraída:**
- Instalação simples costa/costa, até 3 metros, acesso fácil, ponto elétrico individual
- Valor: R$850 com material e mão de obra
- Condição: fotos do local interno + externo, BTUs ≤ 18000, ponto elétrico exclusivo, tubulação existente, distância ≤ 3m
- Se faltar foto/informação/validação: visita técnica R$50, abatível se aprovar orçamento final

**Teste de paridade:**
```
input: "bom dia"
input: "preciso instalar um split 12000"
input: "tenho foto do local" (com imagens)
expected path: fixed_installation_simple
expected price: 850
```

---

## R2: Regra Comercial — Higienização R$200/aparelho

**Origem:** `agent_graph/domain/commercial_router.py` → `fixed_hygienization`
**Confiança:** HIGH
**Arquivo(s):** `agent_graph/domain/commercial_router.py`, `agent_graph/nodes/compose_response.py`

**Regra extraída:**
- Higienização split padrão funcionando: R$200 por aparelho
- Equipamento deve estar funcionando e instalado dentro do padrão
- Se não climatiza, não liga, tem erro, pinga muito: análise/manutenção R$50

**Fluxo de quantidade:**
1. `offer_fixed_hygienization` pergunta: "Quantos aparelhos são?"
2. Cliente responde: "1", "um", "uma", "só um"
3. `understand_message._short_answer_kind()` reconhece como `short_answer = yes` + `slot_choice = 1`
4. `reduce_lead_state._apply_short_answer()` salva `quantidade_aparelhos = 1`
5. Próximo action: `offer_hygienization_schedule` com total

**Teste de paridade:**
```
input: "preciso fazer higienização"
expected action: offer_fixed_hygienization
input: "1"
expected: quantidade_aparelhos=1, action=offer_hygienization_schedule, total=R$200
input: "3"
expected: quantidade_aparelhos=3, action=offer_hygienization_schedule, total=R$600
```

---

## R3: Regra Comercial — Visita/Análise Técnica R$50

**Origem:** `agent_graph/domain/commercial_router.py` → `technical_visit_50`
**Confiança:** HIGH
**Arquivo(s):** `agent_graph/domain/commercial_router.py`

**Regra extraída:**
- Manutenção/conserto: sempre análise técnica R$50
- R$50 pode ser abatido se aprovar orçamento final
- Coletar sintoma ajuda, mas não bloqueia visita
- Instalação sem foto/validação completa: visita técnica R$50

---

## R4: Regra Comercial — Alto Valor / Project Quote

**Origem:** `agent_graph/domain/commercial_router.py` → `_is_project_scope()`
**Confiança:** HIGH
**Arquivo(s):** `agent_graph/domain/commercial_router.py`

**Regra extraída:**
- VRF, VRV, dutos, splitão, cassete, piso-teto, multi split, acima de 18.000 BTUs
- Alto padrão residencial, alto padrão comercial, infraestrutura, elétrica, PMOC, ART, laudo
- Loja, restaurante, hotel, clínica, mercado, galpão
- Ação: visita técnica/projeto a partir de R$50
- Alerta para humano/admin quando OWNER_PHONE configurado (`owner_alert=True`)

**Keywords detectadas:**
```
multi, multisplit, cassete, piso teto, piso-teto, vrf, vrv,
splitao, splitão, duto, dutado, alto padrão, alto padrao,
comercial, galpao, galpão, eletrica, elétrica
```

---

## R5: Action Catalog — Respostas Determinísticas

**Origem:** `agent_graph/nodes/compose_response.py` (264 linhas)
**Confiança:** HIGH
**Arquivo(s):** `agent_graph/nodes/compose_response.py`, `agent_graph/domain/actions.py`

**Actions definidas (20 tipos):**

| Action | Gatilho | Resposta |
|---|---|---|
| `welcome_onboarding` | saudação, "bom dia" | "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?" |
| `ask_lead_name` | serviço identificado, sem nome | "Me passa seu nome pra eu deixar o atendimento certinho?" |
| `ask_basic_service` | tipo_servico null | "Isso é instalação, manutenção, higienização ou conserto?" |
| `offer_fixed_installation` | installation_simple validado | "Instalação simples costa/costa...R$850...Qual período: manhã ou tarde?" |
| `offer_fixed_hygienization` | hygienization validado | "Higienização de split padrão fica R$200 por aparelho...Quantos aparelhos são?" |
| `offer_technical_visit` | installation sem foto / manutenção | "Sem problema...visita técnica de R$50...Qual período: manhã ou tarde?" |
| `offer_project_visit` | project_quote path | "Esse caso sai do escopo de serviço fixo...a partir de R$50...Me passa cidade/bairro?" |
| `save_preferred_window` | resposta de janela (manhã/tarde) | "Perfeito, deixei a preferência pela {window} anotada." |
| `fallback_recover_context` | unknown / unclear | "Desculpa, deixa eu organizar por aqui.\n\nVocê quer seguir com instalação, manutenção, higienização ou visita técnica?" |
| `answer_services_list` | pergunta sobre serviços | lista de 4 serviços |
| `answer_clarification` | "não entendi" / ambiguidade | explicação simples dos preços |
| `offer_hygienization_schedule` | quantidade recebida | "Perfeito, {N} aparelho(s). R${total}. Qual período: manhã ou tarde?" |
| `answer_capability_question` | "vocês trabalham com X" | resposta sobre capacidade |
| `explain_process` | "como funciona" | explicação do processo |

---

## R6: Language Guard — Bloqueio de Scripts Não Latinos

**Origem:** `agent_graph/guards/language_guard.py`
**Confiança:** HIGH
**Arquivo(s):** `agent_graph/guards/language_guard.py`

**Regras extraídas:**
- Scripts bloqueados: CJK, HIRAGANA, KATAKANA, HANGUL, CYRILLIC, ARABIC, HEBREW, THAI, DEVANAGARI, TAMIL, KANNADA, MALAYALAM
- Termos bloqueados em resposta: telemóvel, contactar, morada, marcação (PT-PT)
- Termos bloqueados: presupuesto, mantenimiento, instalación, aire acondicionado (ES)
- Repair cascade: LLM retry → Groq repair → sanitize_hard → fallback determinístico

**Fallback determinístico:**
```
"Ola! Tive um problema tecnico aqui. Um dos nossos especialistas vai te retornar em breve."
```

---

## R7: Modality Policy — Áudio, TTS e Vision

**Origem:** `app/worker.py`, `agent_graph/services/stt.py`, `agent_graph/services/tts.py`, `agent_graph/services/vision.py`
**Confiança:** HIGH
**Arquivo(s):** `app/worker.py`, `agent_graph/services/stt.py`, `agent_graph/services/tts.py`, `agent_graph/services/vision.py`

**Regras extraídas:**
- Áudio → Groq/Grok STT → transcript → mesmo pipeline de texto
- Se STT falhar: "Não consegui entender o áudio com segurança. Pode me mandar em texto?"
- Áudio input + TTS_ENABLED=1 → áudio output via Chatterbox (PC1)
- Áudio input + TTS_ENABLED=0 → texto output
- Imagem input + VISION_ENABLED=1 → Vision (Qwen2.5 7B VL no PC2)
- Imagem input + VISION_ENABLED=0 → ignora imagem, processa caption se houver
- Nunca usar Vision para mensagem de texto
- Nunca usar TTS para resposta de texto
- Typing presence antes de texto
- "Gravando áudio" somente se realmente for enviar áudio

---

## R8: Pipeline LangGraph — 15 Nós Atuais

**Origem:** `agent_graph/graph/graph.py`
**Confiança:** HIGH

**Nós atuais:**
```
preprocess_input
extract_lead_data
understand_message
reduce_lead_state
classify_service
plan_next_action
  ├─ needs_rag → retrieve_knowledge → compose_response
  └─ else → compose_response
compose_response
language_guard_check
response_guard_check
format_whatsapp
decide_response_modality
  ├─ audio → tts_voice_clone → dispatch_side_effects
  └─ text → dispatch_side_effects
dispatch_side_effects
save_interaction
```

**Fluxo novo exigido:**
```
Evolution webhook
→ Redis queue
→ worker
→ load/create lead
→ understand_message
→ reduce_lead_state
→ commercial_router
→ plan_next_action
→ response_catalog
→ sendText
→ save LeadEvent
```

**Diferença:** o pipeline atual faz classify_service antes do reduce_lead_state, e o novo coloca commercial_router antes de plan_next_action.

---

## R9: LeadState Schema — Estado Disperso

**Origem:** múltiplos arquivos — `reduce_lead_state.py`, `nodes.py`, `compose_response.py`
**Confiança:** MEDIUM (schema não está explícito)

**Campos existentes:**
```python
{
  "nome": None,
  "cidade_bairro": None,
  "tipo_servico": None,        # instalacao, manutencao, higienizacao
  "marca": None,
  "btus": None,
  "modelo_aparelho": None,
  "aparelho_novo_ou_usado": None,
  "sintoma": None,
  "urgencia": None,
  "fotos": {"local_interno": bool, "local_externo": bool, "aparelho": bool},
  "instalacao": {
    "ponto_eletrico_exclusivo": bool,
    "tubulacao_existente": bool,
    "distancia_aproximada": None
  },
  "manutencao": {"tempo_sem_manutencao": None, "cheiro_ruim": None, "pinga_agua": None},
  "conserto": {"liga": None, "gela": None, "codigo_erro": None, "disjuntor_cai": None},
  "last_asked_field": None,
  "lead_identity": {...},
  "appointment": {"preferred_window": None, "confirmed_window": bool},
  "pipeline_stage": "new",
  "relationship_type": None,
}
```

**Schema novo exigido (LeadState mínimo):**
```python
{
  "identity": {"name": None, "phone": None},
  "service": {"type": None, "city_bairro": None},
  "installation": {
    "btus": None,
    "has_photos": False,
    "ponto_eletrico_exclusivo": None,
    "distancia_aproximada": None,
    "infra_pronta": None
  },
  "higienizacao": {
    "quantidade_aparelhos": None,
    "aparelho_funcionando": None
  },
  "maintenance": {
    "symptom": None,
    "risk_electric": False
  },
  "appointment": {
    "preferred_window": None,
    "status": None
  },
  "commercial": {
    "path": None,
    "fixed_price": None,
    "visit_price": None,
    "owner_alert": False
  },
  "memory": {
    "last_asked_field": None,
    "last_answered_field": None,
    "do_not_ask": [],
    "last_response_hash": None
  }
}
```

---

## R10: Evolution Webhook — Parser e Contrato

**Origem:** `app/api/webhook.py`
**Confiança:** HIGH
**Arquivo(s):** `app/api/webhook.py`

**Payload de entrada (Evolution API):**
```python
{
  "event": "messages.upsert",
  "instanceName": "...",
  "data": {
    "key": {"remoteJid", "remoteJidAlt", "participantAlt", "fromMe", "id"},
    "message": {"conversation": "...", "imageMessage": {...}, "audioMessage": {...}},
    "messageType": "conversation|audioMessage|imageMessage"
  }
}
```

**Normalização:**
- Ignorar: fromMe=True, groups, broadcast, stickerMessage, videoMessage, documentMessage
- Preferir: `remoteJidAlt`/`participantAlt` quando apontarem para `@s.whatsapp.net`
- `phone` = normalize_whatsapp_number(phone_raw)
- Deduplicação por `msg_id` em Redis por 60 segundos

**Teste de paridade:**
- fromMe=true event → ignorar (não vira lead)
- @lid JID → procurar JID telefônico, não usar como phone
- duplicado → ignorar

---

## R11: Commercial Router — 5 Paths

**Origem:** `agent_graph/domain/commercial_router.py`
**Confiança:** HIGH

```
ask_basic_service        → missing_service, tipo_servico=null
fixed_installation_simple → R$850, all fields validated
fixed_hygienization      → R$200/aparelho, cooling confirmed
technical_visit_50       → R$50, default for missing info
project_quote            → R$50 + owner_alert, VRF/cassete/acima 18k BTUs
```

**Decisões sempre via commercial_router — LLM nunca sobrescreve.**

---

## R12: Response Guard — Anti-Loop

**Origem:** `agent_graph/guards/response_guard.py`
**Confiança:** MEDIUM

**Regra:** duas mensagens diferentes não recebem resposta idêntica consecutiva, salvo cliente repetindo mesma mensagem.

**Implementação:** `last_response_hash` no LeadState.memory, hash da resposta comparada no response_guard.

---

## Gaps Identificados

| ID | Descrição | Impacto | Prioridade |
|---|---|---|---|
| G1 | `response_catalog.py` não existe — respostas definidas em `compose_response.py` e `nodes.py` | Dificulta manutenção, não há fallback isolado | ALTA |
| G2 | `lead_state.py` não existe — schema disperso | Impossível saber exatamente o estado do lead | ALTA |
| G3 | `text_normalizer.py` não existe — normalização ("1"→quantidade, "um"→1) em `reduce_lead_state.py` | Mistura redução com normalização | MÉDIA |
| G4 | `nodes.py` com 4380 linhas — viola separação de concerns | Manutenção difícil, impossível testar isolado | ALTA |
| G5 | WILL_SYSTEM_PROMPT dentro de `nodes.py` — 4000 chars | Deve ser isolado em arquivo próprio | MÉDIA |
| G6 | RAG como dependência do pipeline — não deve ser | RAG é辅助, não core | MÉDIA |
| G7 | 15 nós LangGraph vs. 10 nós do novo pipeline | Nódes extras que não pertencem ao fluxo principal | MÉDIA |

---

## Risk Map

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Core novo quebra atendimento em produção | MÉDIA | CRÍTICO | Manter legacy funcional, flag REFRIMIX_CORE_VERSION |
| Secrets vazados durante rebuild | BAIXA | CRÍTICO | Nunca tocar .env real, usar .env.example |
| Evolution API quebrada por mudança de versão | BAIXA | CRÍTICO | Não trocar tag sem estudar releases, usar evolution-safe-up.sh |
| LLM decide preço final (viola commercial_router) | MÉDIA | ALTO | Tests de paridade, nunca usar 3B para decisão comercial |
| Language contamination (CJK/ES/PT-PT) | MÉDIA | ALTO | language_guard com tests, fallback determinístico |
| Loop de resposta (duas msgs = mesma resposta) | MÉDIA | ALTO | response_guard com last_response_hash |
| Redis queue quebrada | BAIXA | CRÍTICO | Health honesto, não dependedência só de Redis para estado |
| Banco Prisma quebrado por migration | BAIXA | CRÍTICO | Não criar migration sem necessidade |