# FASE 2 — Especificação Operacional: Refrimix Core V2
**Data:** 2026-05-26
**Projeto:** Refrimix WhatsApp RAG — Reconstrução Reversa
**Versão:** 1.0.0

---

## 1. Visão Geral

Este documento define a arquitetura operacional do novo core da Refrimix para atendimento WhatsApp HVAC-R Brasil.

O core novo é:
- **Determinístico:** respostas de catálogo fixas, comercial_router como autoridade final
- **Rastreável:** cada ação tem arquivo, função e teste associado
- **Operável:** health honesto, rollback por flag, Evolution preservado
- **Separado:** core novo em diretório próprio, nunca mixado com legado no mesmo commit

---

## 2. Pipeline Oficial

```
EVOLUTION_WEBHOOK (POST /webhook/evolution)
  ↓
redis_queue (WHATSAPP_QUEUE_KEY)
  ↓
worker_loop (app/worker.py)
  ↓
load/create_lead (lead_repository.py)
  ↓
understand_message (nodes/understand_message.py)
  ↓
reduce_lead_state (nodes/reduce_lead_state.py)
  ↓
commercial_router (domain/commercial_router.py) ← AUTORIDADE FINAL
  ↓
plan_next_action (nodes/plan_next_action.py)
  ↓
response_catalog (domain/response_catalog.py) ← RESPOSTAS DETERMINÍSTICAS
  ↓
sendText (Evolution API sendWhatsAppText)
  ↓
save LeadEvent (postgres/prisma)
```

**O que NÃO pertence ao pipeline principal:**
- RAG (Qdrant) —辅助, ativado por flag, não bloqueia
- Google Calendar — opcional, ativado por flag
- Google Sheets — opcional, ativado por flag
- Vision — só quando `message_type == imageMessage` E `VISION_ENABLED=1`
- TTS — só quando `input modality == audio` E `TTS_ENABLED=1`

---

## 3. Contratos de Input/Output

### 3.1 Input Normalizado para Pipeline

```python
{
  "phone": "5513988887777",
  "message_id": "AB123CD456",
  "message_type": "text|audioMessage|imageMessage",
  "text": "bom dia",
  "transcript": None,           # só quando audio
  "media_url": "",
  "instance": "Refrimix",
  "timestamp": "2026-05-26T10:00:00Z",
  "raw": {...}                  # payload original do webhook
}
```

### 3.2 Output do Pipeline

```python
{
  "phone": "5513988887777",
  "action": "welcome_onboarding",
  "response_text": "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?",
  "response_modality": "text|audio",
  "side_effects": [
    {"type": "send_owner_alert", "payload": {...}}
  ],
  "lead_state_patch": {
    "memory.last_asked_field": "window",
    "appointment.preferred_window": "manha"
  },
  "commercial_decision": {
    "path": "ask_basic_service",
    "fixed_price": None,
    "visit_price": None,
    "owner_alert": False
  },
  "debug": {
    "core_version": "v2",
    "message_type": "text"
  }
}
```

---

## 4. Schema LeadState (Minimal)

```python
class LeadState(TypedDict, total=False):
    identity: dict[str, Any]  # name, phone
    service: dict[str, Any]    # type, city_bairro
    installation: dict[str, Any]   # btus, has_photos, ponto_eletrico_exclusivo,
                                   # distancia_aproximada, infra_pronta
    higienizacao: dict[str, Any]   # quantidade_aparelhos, aparelho_funcionando
    maintenance: dict[str, Any]   # symptom, risk_electric
    appointment: dict[str, Any]   # preferred_window, status
    commercial: dict[str, Any]     # path, fixed_price, visit_price, owner_alert
    memory: dict[str, Any]        # last_asked_field, last_answered_field,
                                   # do_not_ask, last_response_hash
```

---

## 5. Catálogo de Actions

### A1: welcome_onboarding
**Texto:**
```
Bom dia, tudo joia?

Como posso te ajudar hoje?
```
**Gatilho:** saudação ("bom dia", "oi", "ola", "opa", "e aí")
**Gatilho:** primeira mensagem sem contexto
**Não pergunta:** nada além do problema do lead

### A2: answer_services_list
**Texto:**
```
Trabalhamos com instalação, manutenção, higienização e visita técnica para ar-condicionado.

Também atendemos casos maiores, como infraestrutura, cassete, piso-teto, splitão, VRF/VRV, dutos e projetos comerciais ou residenciais de alto padrão.

Os serviços mais comuns são:

1. Instalação simples
2. Higienização
3. Manutenção ou conserto
4. Visita técnica de análise

Me fala qual desses você precisa hoje?
```
**Gatilho:** "quais serviços", "o que vocês fazem", "o que atendem"

### A3: answer_clarification
**Texto:**
```
Claro, vou explicar de forma simples.

Se for instalação simples, o valor base é R$850.

Se faltar alguma informação, foto ou precisar avaliar o local, seguimos como visita técnica de R$50. Esse valor pode ser abatido se o orçamento final for aprovado.

Para higienização, split padrão funcionando fica R$200 por aparelho.

Qual serviço você quer ver primeiro?
```
**Gatilho:** "não entendi", "não ficou claro", "me explica"

### A4: ask_lead_name
**Texto:**
```
Perfeito.

Me passa seu nome pra eu deixar o atendimento certinho?
```
**Gatilho:** tipo_servico identificado + nome não coletado

### A5: ask_basic_service
**Texto:**
```
Entendi.

Isso é instalação, manutenção, higienização ou conserto?
```
**Gatilho:** tipo_servico null E mensagem ambígua

### A6: offer_fixed_installation
**Texto:**
```
Perfeito.

Instalação simples costa/costa, até 3 metros e com acesso fácil, fica R$850 com material e mão de obra.

Esse valor considera ponto elétrico individual e cenário dentro do padrão. Se no local tiver algo fora disso, o técnico explica antes e o valor pode ajustar.

Qual período fica melhor: manhã ou tarde?
```
**Gatilho:** commercial_path == "fixed_installation_simple"

### A7: offer_technical_visit_installation
**Texto:**
```
Sem problema.

A foto ajuda a adiantar, mas não trava o atendimento.

Como ainda falta confirmar o local completo, seguimos como visita técnica de R$50. Se o orçamento final for aprovado, esse valor pode ser abatido.

Qual período fica melhor: manhã ou tarde?
```
**Gatilho:** commercial_path == "technical_visit_50" E service == "instalacao"

### A8: offer_technical_visit_maintenance
**Texto:**
```
Para manutenção, o caminho correto é visita/análise técnica.

A visita fica R$50 e pode ser abatida se o orçamento final for aprovado.

No local o técnico verifica o sintoma. Se der para resolver ali, passa o valor para aprovação. Se precisar retirar ou testar em laboratório, os valores são passados separados.

Qual período fica melhor para a visita?
```
**Gatilho:** commercial_path == "technical_visit_50" E service == "manutencao"

### A9: offer_fixed_hygienization
**Texto:**
```
Higienização de split padrão fica R$200 por aparelho, desde que o equipamento esteja funcionando e instalado dentro do padrão.

Se o aparelho não estiver climatizando, o atendimento pode virar análise de manutenção por R$50.

Quantos aparelhos são?
```
**Gatilho:** commercial_path == "fixed_hygienization"

### A10: offer_hygienization_schedule
**Lógica:**
- quantidade == 1: "Perfeito, 1 aparelho. A higienização fica R$200. Qual período fica melhor: manhã ou tarde?"
- quantidade > 1: "Perfeito, {N} aparelhos. A higienização fica R${total}. Qual período fica melhor: manhã ou tarde?"
**Gatilho:** quantidade_aparelhos recebida após offer_fixed_hygienization

### A11: offer_project_visit
**Texto:**
```
Esse caso sai do escopo de serviço fixo.

Para esse tipo de atendimento, fazemos visita técnica ou projeto a partir de R$50 nas proximidades, podendo ajustar conforme distância e complexidade.

Me passa cidade/bairro e tipo de ambiente para direcionar certo?
```
**Gatilho:** commercial_path == "project_quote"

### A12: save_preferred_window
**Texto:**
```
Perfeito, deixei a preferência pela {window} anotada.

Vou deixar isso separado para o atendimento.
```
**Gatilho:**lead responde "manhã" ou "tarde" (via understand_message.window_detection)

### A13: fallback_recover_context
**Texto:**
```
Desculpa, deixa eu organizar por aqui.

Você quer seguir com instalação, manutenção, higienização ou visita técnica?
```
**Gatilho:** ação unknown / unrecognized

---

## 6. Política Comercial

### Preços Fixos
- Instalação simples (validada): **R$850**
- Higienização (por aparelho, equipamento funcionando): **R$200**

### Preço Variável
- Visita/análise técnica: **R$50** (abatível se aprovar orçamento)
- Project quote: **R$50** + alerta owner + cidade/bairro para avaliar distância

### Condições de Instalação Simples
Todas devem ser verdadeiras:
- BTUs ≤ 18000
- has_photos.local_interno == True
- has_photos.local_externo == True
- ponto_eletrico_exclusivo == True
- infra_pronta == True
- distancia_aproximada ≤ 3 metros

Se qualquer uma faltar → `technical_visit_50`

### Condições de Higienização
- Equipamento deve estar funcionando
- Se não climatiza, não liga, tem erro, pinga muito → `technical_visit_50`

### Project Quote (alto valor)
Keywords que disparam project_quote:
- multi, multisplit, cassete, piso-teto, piso teto, vrf, vrv
- splitao, splitão, duto, dutado
- alto padrão, alto padrao, comercial
- galpão, galpao, elétrica, elétrica
- btus > 18000
- PMOC, ART, laudo, loja, restaurante, hotel, clínica, mercado

owner_alert=True quando detectar.

---

## 7. Política de Modalidade

| Input | TTS_ENABLED | Output |
|---|---|---|
| text | qualquer | text |
| audioMessage | 0 | text (STT transcript) |
| audioMessage | 1 | audio (Chatterbox) |
| imageMessage | qualquer | text (Vision ou caption) |

**Typing indicator:** antes de toda resposta text
**Gravando indicador:** só antes de áudio real

---

## 8. Política de Linguagem

**Output deve ser:** PT-BR puro

**Bloquear:**
- CJK, HIRAGANA, KATAKANA, HANGUL, CYRILLIC, ARABIC, HEBREW, THAI, DEVANAGARI, TAMIL, KANNADA, MALAYALAM
- Termos PT-PT: telemóvel, contactar, morada, marcação
- Termos ES: presupuesto, mantenimiento, instalación, aire acondicionado

**Repair cascade:**
1. LLM retry com instrução explícita
2. Groq repair
3. sanitize_hard (strip chars não-latinos)
4. Fallback: "Ola! Tive um problema tecnico aqui. Um dos nossos especialistas vai te retornar em breve."

---

## 9. Side Effects

| Side Effect | Quando | Destino |
|---|---|---|
| send_owner_alert | owner_alert=True (project_quote) | OWNER_PHONE via Evolution sendText |
| send_agenda_group_alert | appointment_confirmed | AGENDA_GROUP_JID via Evolution |
| tts_synthesize | response_modality=audio | Chatterbox PC1 → OGG → Evolution sendAudio |
| sync_lead_sheet | lead event completo | Google Sheets (se configurado) |

---

## 10. Eventos Persistidos

```python
LeadEvent {
  id: str (uuid)
  lead_id: str (fk)
  event_type: str  # message_in, message_out, state_change, commercial_decision
  action: str       # welcome_onboarding, offer_fixed_installation, etc.
  text: str        # response_text
  modality: str     # text|audio
  lead_state_snapshot: dict  # JSON do lead_state após este turno
  created_at: datetime
}
```

---

## 11. Health Honesto

```
/health retorna:
{
  "status": "up|degraded|down",
  "core_version": "v2|legacy",
  "redis": "connected|disconnected",
  "postgres": "connected|disconnected",
  "evolution_api": "connected|disconnected",
  "worker_heartbeat": "alive|dead|unknown",
  "models": {
    "minimax": "enabled|disabled|degraded",
    "local_qwen": "enabled|disabled|degraded",
    "chatterbox_tts": "enabled|disabled|degraded"
  }
}
```

**Regras:**
- Se Redis down → status=down (não pode processar mensagens)
- Se Postgres down → status=degraded (pode responder, não pode salvar LeadEvent)
- Se Evolution API down → status=degraded (mensagens ficam na fila)
- Se todos modelos down → status=degraded (fallback determinístico disponível)

---

## 12. Flags e Rollback

| Flag | Valores | Comportamento |
|---|---|---|
| REFRIMIX_CORE_VERSION | legacy/v2 | Qual pipeline usar |
| RAG_ENABLED | 0/1 | Ativa/desativa RAG |
| VISION_ENABLED | 0/1 | Ativa/desativa Vision |
| TTS_ENABLED | 0/1 | Ativa/desativa TTS |
| GOOGLE_CALENDAR_ENABLED | 0/1 | Ativa/desativa Calendar |
| OWNER_ALERTS_ENABLED | 0/1 | Ativa/desativa alertas owner |

**Rollback:** trocar `REFRIMIX_CORE_VERSION=legacy` + rebuild container

---

## 13. Testes de Paridade (obrigatórios antes de merge)

```
pytest tests/ -v

Smoke curl:
curl -s http://localhost:8000/health
curl -X POST "http://localhost:8000/test/chat?message=Bom+dia&send=false"
curl -X POST "http://localhost:8000/test/chat?message=Quais+serviços+oferecem%3F&send=false"
curl -X POST "http://localhost:8000/test/chat?message=Não+entendi&send=false"
curl -X POST "http://localhost:8000/test/chat?message=Preciso+fazer+uma+higienização&send=false"
curl -X POST "http://localhost:8000/test/chat?message=1&send=false"
curl -X POST "http://localhost:8000/test/chat?message=Meu+ar+não+gela&send=false"
curl -X POST "http://localhost:8000/test/chat?message=Preciso+de+VRF+para+restaurante&send=false"
```

**Critérios:**
- "bom dia" → welcome_onboarding
- "quais serviços" → answer_services_list
- "não entendi" → answer_clarification
- "higienização" → offer_fixed_hygienization
- "1" após pergunta de quantidade → quantidade_aparelhos=1, offer_hygienization_schedule
- "ar não gela" → technical_visit_50 + offer_technical_visit_maintenance
- "VRF para restaurante" → project_quote + owner_alert
- texto → no TTS, no Vision
- áudio → STT transcript no pipeline
- idioma final → PT-BR (CJK/ES/PT-PT bloqueados)