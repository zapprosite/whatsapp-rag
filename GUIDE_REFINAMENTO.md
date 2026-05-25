# Guia de Refinamento Infinito — Refrimix WhatsApp RAG

## 0. Fonte Canônica e Espelho Git

`CLAUDE.md` é gerado. Não edite esse arquivo na mão.

Fonte canônica:

```text
.context/docs/*.md
```

Fluxo correto de publicação:

```text
Gitea origin/main -> GitHub github/main
```

Use:

```bash
# Gera CLAUDE.md, commita, publica no Gitea e espelha no GitHub
./sync.sh --message "refina: descreve o que mudou"

# Se a mudança já está no Gitea, só atualiza o espelho GitHub
./sync.sh --mirror-only

# Só regenera CLAUDE.md localmente, sem commit/push
./sync.sh --no-git
```

O GitHub é espelho. A fonte primária é o Gitea (`origin`).

## 1. Testando como lead

A instância `RefrimixLead` está conectada (`state: open`).  
Manda mensagem direto para o número WhatsApp vinculado à instância e o bot responde.

**Bypass rápido (sem WhatsApp):**
```bash
# Testa uma mensagem específica direto pelo graph
curl -X POST "http://localhost:8000/test/chat?message=MENSAGEM+AQUI&send=false"

# Ou via httpie / browser:
# http://localhost:8000/docs  → POST /test/chat
```

**E2E batch (35 cenários pré-definidos):**
```bash
# Roda os primeiros 10 cenários e mede acurácia
curl -X POST "http://localhost:8000/test/e2e?start=0&limit=10&delay=1"

# Roda tudo
curl -X POST "http://localhost:8000/test/e2e?start=0&limit=35&delay=2"
```

**Vê a resposta bruta do LLM (sem WhatsApp):**
```bash
curl -X POST "http://localhost:8000/test/refine?message=O+ar+ta+com+barulho"
# Roda 3x a mesma mensagem para observar variação
```

---

## 2. Os 4 níveis de refinamento

```
Nível 1 — Tom e persona     →  WILL_SYSTEM_PROMPT  (nodes.py)
Nível 2 — Conhecimento RAG  →  chunks no Qdrant    (seed_hvac.py)
Nível 3 — Classificação     →  keyword scoring     (classify_service)
Nível 4 — Modelo LLM        →  .env MINIMAX_MODEL
```

Regra: **sempre refine no nível mais baixo que resolve o problema.**  
Um tom errado → nível 1. Informação errada → nível 2. Intent errado → nível 3.

---

## 3. Nível 1 — Refinando tom e persona

**Arquivo:** `agent_graph/nodes/nodes.py` — constante `WILL_SYSTEM_PROMPT`

**Quando usar:** bot falando formal demais, usando palavras erradas, esquecendo serviços, saindo do personagem.

**Como editar:**
```python
# Abre o arquivo e encontra WILL_SYSTEM_PROMPT
# Adiciona/remove regras, exemplos de tom, regiões de atendimento

# Exemplo: adicionar nova regra
WILL_SYSTEM_PROMPT = """
...
- NUNCA diga "prezado" ou "estimado"
- Diga "pode deixar" em vez de "pode ficar tranquilo"  # ← adicionar
...
"""
```

**Aplica em produção:**
```bash
# Rebuild/restart correto do serviço FastAPI sem recriar Evolution
docker compose up -d --build --no-deps fastapi-rag

# Confirma health
curl -s http://localhost:8000/health
```

**Testa imediatamente:**
```bash
curl -X POST "http://localhost:8000/test/chat?message=Quero+instalar+ar+split&send=false"
```

---

## 4. Nível 2 — Refinando o conhecimento RAG

**Arquivo:** `qdrant/seed_hvac.py` — lista `CHUNKS`

**Quando usar:** bot dando informação errada, omitindo detalhe importante, sem contexto sobre preços/condições/regiões.

**Estrutura de um chunk:**
```python
{
    "service_name": "instalacao",   # filtra por serviço no Qdrant
    "text": "A gente instala split...",  # o que o LLM vai ler como contexto
    "outcome": "analise_tecnica",   # guia o CTA da resposta
    "source": "manual_will_2026",
}
```

**Adicionando um chunk:**
```python
# Abre seed_hvac.py e adiciona na lista CHUNKS
{
    "service_name": "manutencao",
    "text": "Cobro R$150 a visita técnica diagnóstica. Se fechar o serviço na hora, desconto na visita.",
    "outcome": "analise_tecnica",
    "source": "tabela_precos_2026",
},
```

**Re-seed (não apaga, faz upsert):**
```bash
source .venv/bin/activate
python qdrant/seed_hvac.py

# Confirma quantos pontos tem
curl -s http://localhost:6333/collections/whatsapp_rag | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('Pontos:', d['result']['points_count'])"
```

**Não precisa rebuildar** — o Qdrant é consultado em runtime.

---

## 5. Nível 3 — Refinando classificação de intent

**Arquivo:** `agent_graph/nodes/nodes.py` — `SCORE_MAP` dentro de `classify_service`

**Quando usar:** bot classificando "PMOC" como manutenção, ou "higienização" como instalação.

**Como funciona o scoring:**
```python
# Cada entrada: (keyword, peso) → serviço
("pmoc", 5): "pmoc",           # peso alto = match forte
("preventiva", 2): "pmoc",     # peso baixo = hint
("manutenção", 1): "manutencao",  # genérico, peso baixo
```

**Quando o LLM override acontece:**  
Se `top_score < 4` ou há empate, o LLM decide a classe final.  
Se `top_score >= 4` e 2x maior que o 2º lugar → keyword ganha (mais rápido, sem LLM extra).

**Adicionando keyword:**
```python
# Exemplo: "Preciso de laudo" → pmoc
("laudo", 4): "pmoc",
("certificado pmoc", 6): "pmoc",
("rito de passagem", 3): "pmoc",  # gíria regional
```

**Testa com E2E batch:**
```bash
curl -X POST "http://localhost:8000/test/e2e?start=0&limit=35&delay=0" | \
  python3 -c "
import sys,json; d=json.load(sys.stdin)
print(f'Acerto: {d[\"correct\"]}/{len(d[\"results\"])}')
[print(f'✗ {r[\"service_tag\"]} → {r[\"intent\"]}') for r in d['results'] if not r['correct']]
"
```

---

## 6. Nível 4 — Trocando o modelo LLM

**Política de routing atual** (`nodes.py` → `generate_response`):
```
onboarding, manutencao, instalacao, higienizacao → Groq llama-3.1-8b-instant (~1s)
pmoc, consultoria, projeto-central               → MiniMax-M2.7 (~5-15s, raciocínio)
classify_service (LLM override)                  → Groq llama-3.1-8b-instant (~1s)
```
Regra: MiniMax só entra quando o lead precisa de análise técnica profunda (PMOC, projetos).

**Arquivo:** `.env`

**Modelos disponíveis na conta MiniMax:**
```
MiniMax-M2.7           ← atual (raciocínio, mais lento, mais preciso)
MiniMax-M2.7-highspeed ← rápido (pode ter rate limit no free tier)
MiniMax-M2.5           ← equilibrado
MiniMax-M2.5-highspeed ← mais rápido
MiniMax-M2.1
```

**Para mover um intent de Groq → MiniMax** (`nodes.py`, `generate_response`):
```python
# Adiciona o intent ao set MINIMAX_INTENTS
MINIMAX_INTENTS = {"pmoc", "consultoria", "projeto-central", "higienizacao"}  # ← exemplo
```

**Para usar Groq em tudo** (mais rápido, menos custo):
```bash
# Zera a chave MiniMax no .env
MINIMAX_API_KEY=
# llm_chat() automaticamente cai para Groq
```

**Troca do modelo Groq** (`.env`):
```bash
GROQ_FALLBACK_MODEL=llama-3.3-70b-versatile  # mais inteligente, ainda rápido
```

---

## 7. Loop de refinamento — fluxo recomendado

```
1. Manda mensagem como lead (WhatsApp ou /test/chat)
        ↓
2. Vê a resposta — algo errado?
        ↓
3. Identifica o nível:
   - Tom/persona errado?     → Nível 1 (WILL_SYSTEM_PROMPT)
   - Info faltando/errada?   → Nível 2 (Qdrant chunk)
   - Intent classificado mal? → Nível 3 (SCORE_MAP)
   - Resposta lenta/cara?    → Nível 4 (modelo)
        ↓
4. Faz a mudança mínima necessária
        ↓
5. Aplica (rebuild ou re-seed)
        ↓
6. Roda /test/e2e para garantir que não quebrou outros cenários
        ↓
7. Roda ./sync.sh --message "refina: ..." para publicar Gitea -> GitHub
        ↓
8. Volta ao passo 1
```

Loop semântico obrigatório quando pedir "50 vezes":

```bash
python3 refinar.py --loop 50
```

Esse loop usa `send=false`, então não manda WhatsApp real.

---

## 8. Monitorando em tempo real

```bash
# Logs do container (filtra só respostas e erros)
docker logs -f whatsapp-rag-fastapi-rag-1 2>&1 | grep -E "INFO|ERROR|WARNING" | grep -v "HTTP Request"

# Vê as últimas interações salvas no PostgreSQL
ssh will-zappro@192.168.15.83 \
  "sudo -u postgres psql -d whatsapp_rag -c \
  'SELECT phone, intent, service, LEFT(response,80) FROM interactions ORDER BY created_at DESC LIMIT 5;'"

# Vê leads que pediram agendamento
ssh will-zappro@192.168.15.83 \
  "sudo -u postgres psql -d whatsapp_rag -c \
  'SELECT phone, service, address, window FROM leads ORDER BY created_at DESC LIMIT 10;'"
```

---

## 9. Adicionando cenários E2E novos

**Arquivo:** `app/api/test_routes.py` — lista `E2E_SCENARIOS`

```python
E2E_SCENARIOS = [
    ...
    # Adiciona seu cenário real
    ("manutencao", "O split fica desligando sozinho depois de 10 minutos"),
    ("pmoc", "Preciso do PMOC pra renovar o alvará da minha clínica"),
]
```

Cada linha que você adiciona vira um teste permanente. Nunca remove — o objetivo é só aumentar a cobertura.

---

## 10. Checklist antes de considerar refinamento completo

```
[ ] /test/e2e com todos os 35 cenários → 100% acerto
[ ] Manda 5 mensagens reais como lead e aprova as respostas
[ ] Nenhum WARNING de drift CJK/árabe nos logs
[ ] save_interaction gravando no PostgreSQL (vê via psql)
[ ] Alertas chegando no WhatsApp do dono quando lead manda endereço
[ ] XTTS funcionando (quando PC1 montar /srv/data/tts/voices)
```
