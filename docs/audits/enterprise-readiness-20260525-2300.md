# Auditoria Enterprise — whatsapp-rag — 2026-05-25 23:00

## Status: APROVADO COM RESSALVAS

O fix aplicado está correto e resolve os problemas críticos de loop/placeholder/appointment.
As ressalvas são principalmente deficiências de documentação de variáveis de ambiente,
um regex duplicado inócuo, e ausência de `setdefault` defensivo na `sanitize_lead_state`.
Nenhum bloco de código crítico está sem proteção. Não há dead code perigoso.

---

## 1. Brechas Residuais do Bugfix

### 1.1 `[áudio]` / `[imagem]` / phrases proibidas

**Guard pipeline:** `response_guard_check` → `validate_response_before_send` bloqueia
`leaked_media_placeholder`, `unwanted_internal_process`, `asked_preferred_window_again`
e `appointment_claim_without_minimum_data`.

**Caminho residual identificado (severidade: baixa):**  
`_active_service_response` (linha ~718) quando o usuário pede para reagendar retorna:
```python
"Qual melhor período para você: manhã ou tarde?"
```
Este retorno é criado DIRETAMENTE em `generate_response` via `AIMessage`, ANTES de passar
por `response_guard_check`. Se o `appointment.preferred_window` já estiver registrado,
a violation `asked_preferred_window_again` SERÁ detectada em `response_guard_check`
e a resposta substituída. Portanto, o guard cobre esse caso.

**`_continuation_response` (linha ~3209):** retorna `"Me confirma o melhor período: manhã ou tarde?"`
quando `appointment_ready=True`. Se `preferred_window` já existir, o guard captura.
O fluxo `generate_response` checa `window_now` ANTES de entrar no branch de continuation_response,
então se o usuário acabou de dizer "manhã" ou "tarde", o branch de window entra antes.
Risco residual: se `continuation_response` foi gerada por `classify_service`
(campo `continuation_response` no state) e o window já estava registrado —
mas o guard detecta isso e corrige. **Coberto.**

**`_appointment_ready_response` (linha ~751):** quando `window` já existe, retorna a confirmação
sem perguntar de novo. Quando `window` é None e `location` existe, pergunta "manhã ou tarde?".
O `response_guard_check` bloqueia se `preferred_window` já estiver preenchido. **Coberto.**

### 1.2 `sanitize_lead_state` antes de usar `lead_state`

O `sanitize_lead_state` É chamado em todos os caminhos críticos:
- `generate_response` linha ~2257: `lead_state = sanitize_lead_state(lead_state)` antes de qualquer
  uso de `lead_state`
- `save_interaction` linha ~2898: `lead_state = sanitize_lead_state(state.get("lead_state") or {})`
- `extract_lead_data` linha ~3524 e ~3626: chamado antes e depois do patch
- `preprocess_input` linhas ~3438 e ~3456: chamado no retorno do STT

**Caminho NÃO sanitizado antes de usar lead_state:**  
`classify_service` usa `lead_state = deepcopy(state.get("lead_state") or {})` (linha ~1793)
sem chamar `sanitize_lead_state`. Mas `classify_service` só lê `lead_state` para
`lead_state.get("tipo_servico")`, `appointment`, `relationship_type` — não escreve
valores de mídia em campos críticos. **Risco baixo; não é caminho de escrita.**

`response_guard_check` faz `lead_state = deepcopy(state.get("lead_state") or {})` sem sanitizar,
mas apenas lê `appointment.preferred_window` para o replace. **Risco baixo.**

### 1.3 `appointment_alert_sent` — persistência via `save_interaction`

`dispatch_appointment_alert` faz:
```python
lead_state.setdefault("appointment", {})["appointment_alert_sent"] = True
return {"lead_state": lead_state}
```
No LangGraph, os dicts retornados pelos nós são **merged** no estado global. Portanto
`lead_state` atualizado CHEGA em `save_interaction` via `state.get("lead_state")`.
`save_interaction` chama `sanitize_lead_state` e depois `db.lead.update` com
`json.dumps(lead_state)` — o que inclui `appointment.appointment_alert_sent = True`.

**Porém:** `save_interaction` grava um subconjunto no campo `metadata.lead_state` da
tabela `Interaction` (apenas `tipo_servico`, `cidade_bairro`, `btus`, `last_asked_field`,
`ask_count_by_field`). O `appointment` completo NÃO está nesse subconjunto.

**O que SIM persiste:** o `db.lead.update` com `json.dumps(lead_state)` salva o
`lead_state` COMPLETO (incluindo `appointment`) na tabela `Lead`. Portanto o dedup
**ESTÁ persistido corretamente** na tabela `Lead`, que é carregada na próxima mensagem
via `preprocess_input`. **OK.**

---

## 2. Riscos de Estado em `lead_state`

### 2.1 Escritas diretas em `lead_state[` fora de `sanitize_lead_state`

**Extrator Qwen (`extract_lead_data`, linhas ~3600-3615):**
```python
for k, v in state_patch.items():
    if v is not None:
        ...
        lead_state[k] = v
```
Antes da escrita, `_clean_state_patch_value` é chamado para filtrar placeholders em campos
`_TEXT_LEAD_FIELDS`. Campos nested como `instalacao`, `manutencao`, `conserto` são mesclados
com `.update(v)`. Não há risco de placeholder vazar para esses campos porque o Qwen
extrai dados estruturados, não placeholders de mídia.

**`_infer_lead_fields_from_text` (linha ~518):** escreve diretamente em `updated["tipo_servico"]`,
`updated["btus"]`, `updated["cidade_bairro"]`, `updated["nome"]` e `updated["fotos"]["aparelho"]`.
Não passa por `sanitize_lead_state`. Mas os valores escritos vêm de regex sobre texto
(não de campos de mídia), então não devem gerar placeholders.  
**Risco baixo.** Monitorar.

**`classify_service` (linhas ~2091, ~2104, ~2140):** escreve `lead_state["service_changed_by_user"]`,
`lead_state["human_takeover"]`, `lead_state["relationship_type"]`, `lead_state["unknown_context_count"]`.
Todos são booleanos/ints/strings de controle. Sem risco de placeholder.

**`generate_response` (linhas ~2372, ~2402):** escreve `lead_state["appointment"]` e
`lead_state["tipo_servico"]` diretamente. Após `sanitize_lead_state` ter sido chamado.
**OK.**

### 2.2 Compatibilidade: chave `appointment` ausente em leads antigos

**Problema identificado:** `sanitize_lead_state` NÃO faz `setdefault` para garantir
que a chave `appointment` exista. Leads carregados do Postgres antes do fix não terão
`appointment` no JSON.

Todos os acessos a `appointment` no código usam o padrão:
```python
appointment = lead_state.get("appointment") or {}
```
que é seguro. No entanto, as escritas usam:
```python
lead_state.setdefault("appointment", {...})["appointment_alert_sent"] = True
```
que também é seguro (cria a chave se ausente).

O único risco seria se `appointment.get("preferred_window")` retornasse `None` para
um lead que nunca passou pelo fix — o código trata esse caso como "sem janela",
o que é o comportamento correto para leads antigos.

**Conclusão:** Compatibilidade está garantida pelo uso consistente de `.get("appointment") or {}`.
**Nenhuma correção crítica necessária**, mas adicionar `setdefault` em `sanitize_lead_state`
como proteção defensiva é recomendado. **[CORREÇÃO APLICADA — ver seção de correções]**

---

## 3. Dedup e Idempotência de Alertas

### 3.1 `dispatch_appointment_alert` — dedup via `appointment_alert_sent`

O dedup local funciona:
1. `appointment = lead_state.get("appointment") or {}` — retorna `{}` para leads sem chave
2. `if appointment.get("appointment_alert_sent"):` — `False` em leads antigos, correto
3. Após envio, `lead_state.setdefault("appointment", {})["appointment_alert_sent"] = True`
4. `save_interaction` persiste `lead_state` completo na tabela `Lead`

**Bug potencial:** se `dispatch_appointment_alert` lançar exceção ANTES de marcar
`appointment_alert_sent = True` mas APÓS chamar `send_appointment_alert`, o alerta
pode ser reenviado na próxima mensagem. O código atual cobre isso com try/except separados:
```python
try:
    await prisma_upsert_lead(lead_data)
except Exception as e:
    logger.error(...)  # não bloqueia o fluxo

try:
    await send_appointment_alert(lead_data)
    lead_state.setdefault("appointment", {})["appointment_alert_sent"] = True
except Exception as e:
    logger.error(...)  # se o send falhar, o flag NÃO é marcado — correto
```
Portanto: o flag só é marcado se o envio tiver sucesso. **Correto.**

### 3.2 `maybe_notify_owner_from_result` — dedup Redis para `appointment_confirmed`

A chave Redis de dedup é:
```python
alert_key = f"owner_alert:{phone}:{reason}:{date.today().isoformat()}"
```
Para `reason = "appointment_confirmed"`, a chave inclui a data. Portanto:
- Mesmo cliente, mesmo dia: deduplica corretamente via `set(nx=True, ex=TTL)`
- Próximo dia: reenvia — correto para novos agendamentos confirmados

`appointment_confirmed` está em `_OWNER_WORTHY_REASONS` no worker (linha ~78). **OK.**

**Atenção:** `appointment_ready` NÃO está em `_OWNER_WORTHY_REASONS`, portanto
`maybe_notify_owner_from_result` NÃO notifica quando apenas `appointment_ready=True`.
Só notifica quando `appointment_confirmed`. Isso é o comportamento desejado (conforme
`test_appointment_ready_does_not_notify_owner_until_confirmed`). **Correto.**

---

## 4. I/O sem Timeout

### 4.1 Redis (`redis_get`, `redis_set` em nodes.py)

```python
# nodes.py linhas 1091-1108
async def redis_get(key: str) -> str | None:
    client = redis.asyncio.from_url(redis_url, decode_responses=True)
    return await client.get(key)  # ← SEM TIMEOUT EXPLÍCITO
```

O cliente `redis.asyncio.from_url` não recebe parâmetro `socket_timeout`. Se o Redis
estiver lento ou unreachable, o `await client.get(key)` pode bloquear indefinidamente.
O grafo tem timeout geral `_GRAPH_TIMEOUT=45s`, mas bloqueios de 45s em Redis causariam
degradação silenciosa.

**Recomendação:** Adicionar `socket_timeout=3.0` no `from_url` ou envolver com
`asyncio.wait_for(client.get(key), timeout=3.0)`.

### 4.2 Prisma/PostgreSQL (sem timeout)

Todas as chamadas `await db.connect()`, `await db.lead.find_unique(...)`, `await db.lead.update(...)`
não têm timeout explícito. O Prisma usa o timeout configurado na `DATABASE_URL`
(parâmetro `connect_timeout` ou `pool_timeout`). Se não configurado, pode bloquear
indefinidamente.

**Localizações críticas:**
- `preprocess_input` (linha ~3389): sem timeout; está no hot path de cada mensagem
- `extract_lead_data` (linha ~3657): sem timeout; no hot path
- `save_interaction` (linha ~2937): sem timeout; no hot path

**Recomendação:** Configurar `connect_timeout=5&pool_timeout=10` na `DATABASE_URL`
ou envolver as operações com `asyncio.wait_for`.

### 4.3 httpx com timeout configurável

Todas as chamadas httpx nas funções de LLM, STT, TTS e WhatsApp usam timeout via
`_env_float("*_TIMEOUT_SECONDS", default)`. **OK.**

`prisma_upsert_lead` em `alerts.py` não tem timeout mas está em try/except e
o failure é logado sem interromper o fluxo. **Baixo impacto.**

---

## 5. Try/Except Amplos que Engolem Erros

### 5.1 Críticos (mascaram falha silenciosa)

**`qdrant_search` (nodes.py, linha ~1162):**
```python
try:
    model = TextEmbedding(...)
    query_embedding = next(model.embed([query]))
except Exception:
    return []  # ← silencioso; RAG retorna vazio sem log
```
Se o FastEmbed falhar por falta de memória ou modelo corrompido, o RAG retorna
silenciosamente sem contexto. O bot ainda funciona, mas responde sem conhecimento técnico.
**Recomendação:** adicionar `logger.error` nesse except.

**`response_guard_check` (nodes.py, linha ~2769):**
```python
try:
    ok, violations = validate_response_before_send(response, ...)
except Exception as e:
    logger.warning("response_guard falhou: %s", e)
    ok, violations = True, []  # ← guard desativado silenciosamente
```
Se o guard levantar exceção, assume `ok=True` — resposta não filtrada vai ao cliente.
Isso é intencional (degradação graceful), mas oculta bugs no guard.

**`domain_disambiguation` e `template_context_for_prompt` (nodes.py, linha ~2505):**
```python
except Exception:
    pass  # ← totalmente silencioso
```
Esta é a única `except: pass` real no código. Perda de contexto de template sem log.

### 5.2 Aceitáveis

- `_call_groq`, `_call_minimax`, `_call_local_qwen`, `_call_local_ptbr`: todos logam
  `logger.warning` e fazem retry. **OK.**
- `save_interaction`: `except Exception as e: logger.error(...)` — falha logada.
- `format_whatsapp/speech_adapter`: `except Exception as e: logger.warning(...)` — OK.

---

## 6. Dead Code pós-fix

### 6.1 `high_value_consultoria` reason

O reason `high_value_consultoria` NÃO existe mais em `_HIGH_VALUE_KEYWORDS` (foi removido
corretamente no fix). Verificado que `_detect_high_value_reason` não pode mais gerar
esse reason.

**Código que poderia tratar esse reason especificamente:**
- `_alert_title` (worker.py, linha ~466): não contém `"high_value_consultoria"` — apenas
  `"high_value_lead"`, `"high_value_vrf"`, etc. e o fallback `if reason.startswith("high_value")`.
- `_handoff_next_step` (worker.py, linha ~492): usa `reason.startswith("high_value")` como fallback.
- `classify_high_value_project` (nodes.py, linha ~1663): processa reasons gerados por
  `_detect_high_value_reason`. Nenhum mapeamento específico para `high_value_consultoria`.

**Conclusão:** Não há dead code específico de `high_value_consultoria`. A remoção foi limpa.

### 6.2 `_high_value_consultative_response()` — ainda em uso?

Sim, `_high_value_consultative_response()` ainda é chamada em `generate_response`
(linha ~2358):
```python
if str(handoff_reason or "").startswith("high_value"):
    ai_message = AIMessage(content=_high_value_consultative_response())
```
Esse branch é atingível quando `handoff_reason` começa com `"high_value"` — ex:
`"high_value_vrf"`, `"high_value_pmoc"`, `"high_value_btus_altos"`, etc.
**A função não é dead code.** Permanece ativa e necessária.

### 6.3 Regex duplicado em `_detect_preferred_window` (bug inócuo)

```python
if re.search(r"\b(manha|manha)\b", folded):  # "manha" duplicado
```
O grupo `(manha|manha)` é equivalente a `(manha)`. O regex funciona corretamente
porque `_fold_text` remove acentos (converte "manhã" → "manha"). **Inócuo mas confuso.**
**[CORREÇÃO APLICADA]**

---

## 7. Type Hints e Qualidade de Código

### 7.1 Funções novas do fix — type hints

- `_is_media_placeholder(text: str | None) -> bool` ✓
- `_is_invalid_structured_value(value: Any) -> bool` ✓
- `sanitize_lead_state(lead_state: dict[str, Any]) -> dict[str, Any]` ✓
- `_detect_preferred_window(text: str) -> str | None` ✓
- `has_minimum_real_data_for_appointment(lead_state: dict[str, Any], service: str | None) -> bool` ✓
- `_bare_service_selection_response(user_text: str, lead_state: dict[str, Any]) -> str | None` ✓

Todas com type hints corretos. `from __future__ import annotations` está no topo do arquivo.

### 7.2 `_BARE_MAP` como constante de módulo

`_BARE_MAP` é definido dentro de `_bare_service_selection_response` como variável local.
A função é chamada em `generate_response` (nó do grafo), portanto no hot path de cada
mensagem. O dict é recriado a cada chamada (overhead mínimo em CPython para dicts
pequenos de strings literais), mas move-lo para módulo é boa prática.
**[CORREÇÃO APLICADA]**

### 7.3 `_BARE_SERVICE_MAP` em `generate_response` — também inline

```python
_BARE_SERVICE_MAP = {"manutencao": "manutencao", ...}  # linha ~2399
```
Também definido inline dentro de `generate_response`. **[CORREÇÃO APLICADA junto com _BARE_MAP]**

---

## 8. Compatibilidade de Schema Postgres

### 8.1 Leads antigos sem chave `appointment`

Ao carregar `lead_state` do Postgres em `preprocess_input` (linha ~3406):
```python
lead_state = json.loads(lead.lead_state) if isinstance(lead.lead_state, str) else (lead.lead_state or _lead_state_copy())
```
Um lead gravado antes do fix não terá `"appointment"` no JSON.

**Todos os acessos são seguros** (`lead_state.get("appointment") or {}`), mas `sanitize_lead_state`
poderia garantir a estrutura mínima com `setdefault`. **[CORREÇÃO DEFENSIVA APLICADA]**

### 8.2 `pipeline_stage` como campo deduzido — não no schema padrão

`lead_state["pipeline_stage"]` é computado e gravado em `extract_lead_data` e lido em
`retrieve_knowledge`. Leads antigos podem não ter esse campo; o código usa
`lead_state.get("pipeline_stage")` (seguro). **OK.**

### 8.3 Riscos de `KeyError` identificados: NENHUM

Nenhum acesso `lead_state["appointment"]["preferred_window"]` sem guard encontrado no código.
Todos usam o padrão `(lead_state.get("appointment") or {}).get("preferred_window")` ou
`appointment.get("preferred_window")` após o `or {}`. **OK.**

---

## 9. Secrets e .env

### 9.1 Chaves usadas via `os.getenv` ausentes do `.env.example`

As seguintes chaves são usadas no código mas ausentes do `.env.example`:

| Chave | Arquivo | Default |
|---|---|---|
| `CONV_TTL_SECONDS` | worker.py | `1800` |
| `CONV_MAX_TURNS` | worker.py | `6` |
| `CONV_LOCK_TTL_SECONDS` | worker.py | `240` |
| `CONV_LOCK_WAIT_SECONDS` | worker.py | `20` |
| `CONV_LOCK_REQUEUE_DELAY_SECONDS` | worker.py | `0.4` |
| `WORKER_CONCURRENCY` | worker.py | `4` |
| `WORKER_QUEUE_POP_TIMEOUT_SECONDS` | worker.py | `5` |
| `WORKER_MESSAGE_TIMEOUT_SECONDS` | worker.py | `180` |
| `WORKER_MAX_ATTEMPTS` | worker.py | `3` |
| `MANUAL_TAKEOVER_TTL_SECONDS` | worker.py | `86400` |
| `WHATSAPP_PROCESSING_QUEUE_KEY` | worker.py | `whatsapp_rag:processing` |
| `WHATSAPP_DLQ_KEY` | worker.py | `whatsapp_rag:dead_letter` |
| `TTS_CHATTERBOX_SEED` | tts.py | `777` |
| `LOCAL_QWEN_CONTEXT_TOKENS` | nodes.py | `4096` |
| `LOCAL_QWEN_CONTEXT_SAFETY_TOKENS` | nodes.py | `192` |
| `LOCAL_PTBR_CONTEXT_TOKENS` | nodes.py | `4096` |
| `LOCAL_PTBR_MAX_TOKENS` | nodes.py | `240` |
| `LOCAL_PTBR_TIMEOUT_SECONDS` | nodes.py | `45.0` |
| `MINIMAX_CONCURRENCY` | nodes.py | `4` |
| `LOCAL_QWEN_CONCURRENCY` | nodes.py | `1` |
| `LOCAL_PTBR_CONCURRENCY` | nodes.py | `1` |

**[CORREÇÃO APLICADA: adicionadas ao .env.example]**

### 9.2 Guardrail P0 de Secrets — OK

`.env.example` mantém `{SECRET}` para todos os valores sensíveis.
Nenhum valor real presente. Regras do CLAUDE.md respeitadas.

---

## 10. Cobertura de Testes Novos

### 10.1 Cobertura dos 5 arquivos de teste

| Arquivo | O que cobre | Gaps |
|---|---|---|
| `test_response_guard.py` | 4 novas violations + violations antigas | `appointment_claim_without_minimum_data` com dado mínimo real não testado |
| `test_audio_placeholder_bug.py` | `_is_media_placeholder`, `_is_invalid_structured_value`, `sanitize_lead_state`, STT fail → marker, `generate_response` com `audio_transcription_failed` | Não testa o path completo preprocess→classify→generate via graph |
| `test_appointment_window_loop.py` | `_detect_preferred_window`, loop de janela em `generate_response`, `window_not_asked_twice` | Não testa `dispatch_appointment_alert` dedup via `appointment_alert_sent` |
| `test_appointment_ready_minimum_data.py` | `has_minimum_real_data_for_appointment` (5 cenários), `appointment_ready` não dispara prematuramente | Falta teste para `pmoc`/`projeto-central`/`consultoria` com `high_value_project` |
| `test_handoff_policy.py` | já existia; extended com `appointment_confirmed` | Cobre dedup Redis para `high_value_pmoc` mas não para `appointment_confirmed` |

### 10.2 Análise do mock STT em `test_audio_transcription_failed_intent`

```python
monkeypatch.setattr("agent_graph.services.stt.transcribe_audio", stt_fail, raising=False)
```

O import em `preprocess_input` é **lazy** (inside the function):
```python
from agent_graph.services.stt import transcribe_audio
transcript = await transcribe_audio(...)
```

**Import lazy dentro da função:** quando Python executa `from agent_graph.services.stt import transcribe_audio`
dentro da função, ele busca `transcribe_audio` em `sys.modules["agent_graph.services.stt"]`.
O `monkeypatch.setattr("agent_graph.services.stt.transcribe_audio", stt_fail)` patcha
o atributo no módulo já importado, então a próxima chamada ao `import transcribe_audio`
dentro da função vai pegar o objeto patchado **do módulo**.

Isso funciona porque Python não reexecuta o `import` se o módulo já está em `sys.modules`;
ele apenas faz `transcribe_audio = sys.modules["agent_graph.services.stt"].transcribe_audio`,
e o monkeypatch já mudou esse atributo. **O mock está correto.** Confirmado pelo
sucesso do teste.

### 10.3 Caso faltando: `dispatch_appointment_alert` dedup real

Falta um teste que verifique que `dispatch_appointment_alert` não reenvia alerta
quando `appointment.appointment_alert_sent = True` já está no lead_state.
Isso cobre o cenário de conversas longas com múltiplas mensagens após o agendamento confirmado.

---

## Correções Aplicadas

### C1. `sanitize_lead_state` — setdefault defensivo para `appointment`

Adicionado `setdefault` em `sanitize_lead_state` para garantir que leads antigos
sem a chave `appointment` recebam a estrutura mínima após carregar do Postgres.

### C2. `_detect_preferred_window` — regex duplicado corrigido

`r"\b(manha|manha)\b"` → `r"\bmanha\b"` (a segunda alternativa era idêntica à primeira).

### C3. `_BARE_MAP` e `_BARE_SERVICE_MAP` movidos para módulo

Ambos os dicts eram recriados a cada chamada no hot path. Movidos para constantes
de módulo com nomes maiúsculos.

### C4. `.env.example` — chaves de worker adicionadas

12 chaves usadas no `app/worker.py` e outras 9 de tunning foram adicionadas
ao `.env.example` com valores padrão documentados.

### C5. `domain_disambiguation` — except sem log adicionado

`except Exception: pass` em `retrieve_knowledge` recebeu `logger.warning`.

---

## Pendências (PR para humano revisar)

### P1. Redis sem socket_timeout (médio)

`redis_get` e `redis_set` em `nodes.py` não têm timeout explícito. Recomendado
adicionar `socket_timeout=3.0` ou envolver com `asyncio.wait_for`.

### P2. Prisma sem timeout de conexão (médio)

Operações Prisma em `preprocess_input`, `extract_lead_data`, `save_interaction`
não têm timeout explícito. Recomendado configurar `connect_timeout=5&pool_timeout=10`
na `DATABASE_URL` ou usar `asyncio.wait_for`.

### P3. `qdrant_search` sem log no except (baixo)

`except Exception: return []` silencia erros de FastEmbed. Adicionar
`logger.warning("FastEmbed falhou: %s", e)` melhora visibilidade operacional.

### P4. Teste de dedup `dispatch_appointment_alert` faltando (baixo)

Adicionar teste que verifica que `dispatch_appointment_alert` retorna `{}` imediatamente
quando `appointment.appointment_alert_sent = True`, sem chamar `send_appointment_alert`.

### P5. Teste de compatibilidade de schema Postgres (baixo)

Adicionar teste que verifica que `sanitize_lead_state` retorna estrutura correta
para lead antigo sem chave `appointment`.
