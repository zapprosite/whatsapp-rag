# Mapa PC1/PC2 e Refinamento do Atendimento

Atualizado em 2026-05-25.

Este documento mapeia o que o projeto `whatsapp-rag` usa em cada máquina, onde ficam as falas prontas e como refinar o atendimento sem quebrar o fluxo LangGraph/RAG.

## Visão Rápida

```
WhatsApp
  -> Evolution API :8080
  -> FastAPI :8000 /webhook/evolution
  -> Redis queue
  -> worker_loop
  -> LangGraph
     -> preprocess_input
     -> classify_service
     -> retrieve_knowledge
     -> generate_response
     -> language_guard_check
     -> format_whatsapp
     -> decide_response_modality
     -> tts_voice_clone ou dispatch_appointment_alert
     -> save_interaction
  -> Evolution API sendText/sendAudio
```

O repositório roda o chatbot e orquestra o atendimento. A infraestrutura fica dividida entre PC2, onde este projeto é operado, e PC1, que fornece serviços persistentes ou pesados.

## PC2

PC2 é o ambiente operacional deste repositório.

No PC2 ficam:

- Código do projeto: `/home/will/whatsapp-rag`.
- FastAPI/LangGraph: porta `8000`.
- Rotas HTTP:
  - `/webhook/evolution`: entrada da Evolution API.
  - `/health`: checagem de Redis, Qdrant e runtime.
  - `/bot`: painel liga/desliga do bot.
  - `/test/*`: diagnósticos sem WhatsApp real.
- Worker: `app/worker.py`, que consome Redis e executa o grafo.
- Scripts de refinamento:
  - `refinar.py`
  - `refinar_llm.py`
- Espelho Git:
  - Gitea primário: remoto `origin`.
  - GitHub espelho: remoto `github`.
  - Publicação correta: `./sync.sh --message "..."`.
  - Espelho sem commit local: `./sync.sh --mirror-only`.
- Probes SRE:
  - `python -m sre.probes webhook-smoke`
  - `python -m sre.probes webhook-stress`
  - `python -m sre.probes evolution-audio`
- Vault local do projeto:
  - `.env`: valores reais, não versionar.
  - `.env.example`: contrato mascarado.
  - `scripts/env-vault.sh sync`: gera `.env.example` a partir do `.env`.

Serviços acessados como localhost no PC2:

- `http://localhost:8000`: FastAPI do bot.
- `http://localhost:8080`: Evolution API, quando exposta localmente.
- `http://localhost:6333`: Qdrant, quando está local ou tunelado.
- `http://127.0.0.1:8011/v1`: Qwen local/GPU, conforme túnel/configuração.
- `http://127.0.0.1:8211/v1`: modelo PT-BR auxiliar, conforme túnel/configuração.

Observação: `127.0.0.1` sempre significa "a máquina/container onde o processo está rodando". Como o container usa `network_mode: host`, os endereços localhost dependem dos túneis e serviços ativos no host.

## PC1

PC1 é a máquina de serviços persistentes e/ou pesados.

O projeto referencia PC1 como:

- Redis: `192.168.15.83:6379`.
- PostgreSQL: `192.168.15.83:5432`.
- Host SSH padrão para TTS/OmniVoice: `will-zappro@192.168.15.83`.
- Chave SSH usada no container: `pc1_zappro_ed25519`.
- Vozes TTS: `/srv/data/tts/voices`.
- Serviços locais de IA/voz, quando expostos por túnel:
  - Qwen local OpenAI-compatible.
  - Modelo auxiliar PT-BR.
  - OmniVoice/XTTS.

O que normalmente depende do PC1:

- Histórico de conversa no Redis.
- Fila `whatsapp_rag:queue`.
- Locks de conversa para evitar resposta concorrente.
- Deduplicação de mensagem.
- Dados PostgreSQL/Prisma.
- Voz do Will quando a resposta é áudio.
- Alguns modelos locais usados como fallback/classificador/polidor.

## O Que Este Repositório Usa de Cada Lado

| Recurso | Onde roda | Como o repo usa | Configuração |
|---|---|---|---|
| FastAPI | PC2 | Recebe webhook, health, testes e painel bot | `app/main.py`, `app/api/*` |
| LangGraph | PC2 | Fluxo de atendimento e decisão | `agent_graph/graph/graph.py` |
| Worker | PC2 | Consome Redis e responde WhatsApp | `app/worker.py` |
| Evolution API | PC2/local | Entrada e saída WhatsApp | `EVOLUTION_API_URL`, `EVOLUTION_INSTANCE` |
| Redis | PC1 ou local/túnel | Queue, histórico, locks, bot on/off | `REDIS_URL`, `WHATSAPP_QUEUE_KEY` |
| PostgreSQL | PC1 | Prisma, interações, leads | `DATABASE_URL` |
| Qdrant | PC1/PC2/túnel | RAG semântico dos serviços | `QDRANT_URL`, `QDRANT_COLLECTION` |
| MiniMax | externo | Resposta principal quando configurado | `MINIMAX_*` |
| Groq | externo | STT, Vision e fallback | `GROQ_*` |
| Qwen local | PC1/túnel | Classificação/fallback local | `LOCAL_QWEN_*` |
| PT-BR local | PC1/túnel | Polimento opcional offline/experimental | `LOCAL_PTBR_*`, `PTBR_POLISH_ENABLED` |
| OmniVoice/XTTS | PC1 | TTS/voz do Will | `TTS_*`, `OMNIVOICE_URL`, `XTTS_URL`, `SSH_HOST_PC1` |

## Fluxo do Webhook

1. Evolution envia payload para `/webhook/evolution`.
2. `app/api/webhook.py` normaliza:
   - telefone,
   - tipo de mensagem,
   - texto/caption,
   - áudio/imagem,
   - `msg_id`,
   - instância.
3. Webhook deduplica por `processed_msg:{msg_id}` no Redis.
4. Webhook empilha payload em `WHATSAPP_QUEUE_KEY`.
5. `worker_loop` consome a fila.
6. Worker carrega histórico da conversa no Redis.
7. LangGraph classifica, busca RAG, gera resposta e salva interação.
8. Worker envia texto/áudio pela Evolution API.

Se o webhook responde `{"status":"ok"}` mas o cliente não recebe resposta, verificar:

```bash
curl -s http://localhost:8000/health
./bot.sh status
docker logs -f whatsapp-rag-fastapi-rag-1 2>&1 | grep -E "ERROR|WARNING|Enfileirado|processando|sendText"
```

## Onde Ficam as Falas Prontas

Não existe um único arquivo de "falas". O atendimento é composto por camadas.

### 1. Persona, tom e exemplos

Arquivo:

```text
agent_graph/nodes/nodes.py
```

Bloco:

```python
WILL_SYSTEM_PROMPT = """..."""
```

Use para mudar:

- jeito de falar do Will;
- regras de tom;
- frases proibidas;
- exemplos bons de resposta;
- conduta geral de atendimento.

Marcadores importantes:

```text
# EXEMPLOS_VALIDADOS_START
# EXEMPLOS_VALIDADOS_END
```

Adicione exemplos nesse formato:

```text
Lead: "Meu ar não tá gelando"
Will: "Entendi. Quando o ar não gela, pode ser filtro sujo, gás baixo ou falha no equipamento. Qual a marca e em qual bairro ele está?"
```

### 2. Respostas determinísticas de preço

Arquivo:

```text
agent_graph/nodes/nodes.py
```

Função:

```python
_direct_price_response(service, text)
```

Use quando uma resposta deve ser exata e não depender do LLM, por exemplo:

- instalação padrão;
- higienização por aparelho;
- regras comerciais simples.

### 3. Recuperação de mensagem ambígua

Arquivo:

```text
agent_graph/nodes/nodes.py
```

Função:

```python
_unknown_recovery_response(user_text)
```

Use para mudar falas como:

- "quanto fica?"
- "faz?"
- "não sei explicar"
- "o ar tá estranho"

Regra: mensagem ambígua não deve virar handoff. Ela deve virar pergunta curta de desambiguação.

### 4. Reclamação leve e handoff

Arquivo:

```text
agent_graph/nodes/nodes.py
```

Funções:

```python
_light_complaint_response(user_text)
_handoff_initial_response(reason)
_handoff_followup_response(reason)
```

Use para mudar:

- resposta quando cliente reclama mas ainda dá para conduzir;
- resposta quando cliente pede humano;
- resposta quando há reclamação sensível.

### 5. Semântico/classificação de intenção

Arquivo:

```text
agent_graph/nodes/nodes.py
```

Função:

```python
classify_service(state)
```

Mapa principal:

```python
SCORE_MAP: dict[tuple[str, int], str]
```

Serviços válidos:

- `instalacao`
- `manutencao`
- `higienizacao`
- `pmoc`
- `consultoria`
- `projeto-central`
- `unknown`
- `explicit_handoff`
- `sensitive_complaint`

Exemplo de ajuste:

```python
("não tá gelando", 6): "manutencao",
("faz limpeza", 6): "higienizacao",
("programa preventivo", 5): "pmoc",
```

Peso recomendado:

- `1-2`: termo fraco/genérico.
- `3-4`: termo médio.
- `5-8`: termo forte, quase determinístico.

### 6. Conhecimento RAG

Arquivo:

```text
qdrant/seed_hvac.py
```

Use quando a resposta precisa de conhecimento técnico/comercial:

- preços e condições;
- política de garantia;
- o que inclui no serviço;
- regiões atendidas;
- argumentos de venda;
- detalhes de PMOC, ART, laudo, contrato.

Depois de editar:

```bash
source .venv/bin/activate
python qdrant/seed_hvac.py
```

RAG é runtime: normalmente não precisa rebuildar container, só reindexar o Qdrant.

## Como Refinar Atendimento

Use sempre o nível mais baixo que resolve o problema.

| Problema visto | Onde mexer | Precisa rebuild? |
|---|---|---|
| Tom formal/robótico | `WILL_SYSTEM_PROMPT` | Sim |
| Fala pronta de ambiguidade ruim | `_unknown_recovery_response` | Sim |
| Handoff/reclamação ruim | `_handoff_*` ou `_light_complaint_response` | Sim |
| Preço fixo errado | `_direct_price_response` ou RAG | Sim se código; não se RAG |
| Serviço classificado errado | `SCORE_MAP` | Sim |
| Informação técnica/comercial faltando | `qdrant/seed_hvac.py` | Não, só re-seed |
| Variação inconsistente do LLM | exemplo validado no prompt ou resposta determinística | Sim |

### Fluxo Manual Seguro

1. Teste sem mandar WhatsApp real:

```bash
curl -X POST "http://localhost:8000/test/chat?message=O+ar+nao+ta+gelando&send=false"
```

2. Rode variações:

```bash
curl -X POST "http://localhost:8000/test/refine?message=Quero+instalar+split"
```

3. Use o refinador:

```bash
python3 refinar.py
```

4. Escolha o tipo de correção:

- `1`: tom/persona, adiciona exemplo no prompt.
- `2`: regra absoluta nova.
- `3`: intent errado, adiciona keyword no `SCORE_MAP`.
- `4`: informação faltando, adiciona chunk no Qdrant.
- `5`: ver 3 variações.

5. Rode bateria semântica:

```bash
python3 refinar.py --loop 50
```

6. Rode testes:

```bash
.venv/bin/python -m pytest
```

7. Se mexeu em código ou prompt:

```bash
docker compose build fastapi-rag
docker rm -f whatsapp-rag-fastapi-rag-1
docker run -d --name whatsapp-rag-fastapi-rag-1 --network host --restart unless-stopped \
  --env-file .env \
  -e QDRANT_URL=http://127.0.0.1:6333 \
  -e QDRANT_COLLECTION=hermes_hvac_rag_service_staging \
  whatsapp-rag-fastapi-rag:latest
```

8. Confirme saúde:

```bash
curl -s http://localhost:8000/health
```

## Exemplos de Decisão

### Caso 1: "quanto fica?"

Se não há histórico, deve continuar `unknown` e perguntar qual serviço.

Se o histórico anterior era instalação, deve resolver como `instalacao`.

Onde mexer se falhar:

- `semantic_text` em `classify_service`;
- `SCORE_MAP`;
- teste em `tests/test_handoff_policy.py`.

### Caso 2: "faz limpeza?"

Deve cair em `higienizacao`, não em instalação.

Onde mexer:

```python
("faz limpeza", 6): "higienizacao"
```

### Caso 3: "programa preventivo trimestral"

Deve cair em `pmoc`.

Onde mexer:

```python
("programa preventivo", 5): "pmoc"
("preventivo trimestral", 5): "pmoc"
```

### Caso 4: "quero falar com humano"

Deve cair em `explicit_handoff` e `hard_transfer`.

Onde mexer:

```python
_EXPLICIT_HANDOFF_TRIGGERS
_handoff_initial_response
_handoff_followup_response
```

## Checklist de Mudança

Antes de considerar concluído:

```bash
.venv/bin/python -m pytest
python3 refinar.py --loop 50
curl -s http://localhost:8000/health
```

Se o atendimento real estiver ativo:

```bash
./bot.sh status
docker logs -f whatsapp-rag-fastapi-rag-1 2>&1 | grep -E "INFO|ERROR|WARNING" | grep -v "HTTP Request"
```

## Arquivos Principais

| Arquivo | Função |
|---|---|
| `app/main.py` | Composition root do FastAPI |
| `app/api/webhook.py` | Webhook Evolution API |
| `app/worker.py` | Consumo da fila e envio WhatsApp |
| `agent_graph/graph/graph.py` | StateGraph e roteamento |
| `agent_graph/nodes/nodes.py` | Nós do grafo, prompt, semântico, RAG e respostas |
| `qdrant/seed_hvac.py` | Base de conhecimento RAG |
| `refinar.py` | Refinamento manual e loop semântico |
| `refinar_llm.py` | Refinamento automático com juiz LLM |
| `sre/probes.py` | Smoke/stress operacional |
| `scripts/env-vault.sh` | Sync `.env` -> `.env.example` mascarado |

## Regras de Segurança

- Nunca versionar `.env`.
- Nunca colocar token, senha, telefone completo sensível ou chave API em docs.
- `.env.example` deve conter somente `{SECRET}` para valores reais.
- Use `scripts/env-vault.sh sync` depois de alterar `.env`.
- Testes e `/test/chat` devem usar `send=false` para não mandar WhatsApp real.
- `CLAUDE.md` é gerado; altere `.context/docs/*.md` e rode `./sync.sh`.
- GitHub é espelho do Gitea. O fluxo correto é `origin` -> `github`.
