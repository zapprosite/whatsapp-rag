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

## 0.1 Pesquisa aplicada em 25/05/2026 — PT-BR/SP

O refinamento do atendimento deve seguir português brasileiro moderno, com recorte operacional para São Paulo/Baixada Santista. A regra prática é: curto, claro, humano e com próximo passo.

Critérios obrigatórios para WhatsApp:

- Começar pelo ponto principal; deixar detalhe técnico só quando ajuda a decisão.
- Usar frase curta, voz ativa e ordem direta.
- Falar com o cliente como atendimento real no Brasil: `você`, `a gente`, `pra`, `tá` podem ser usados quando deixam a conversa natural.
- Evitar formalismo antigo: `prezado`, `estimado`, `caro cliente`, `atenciosamente`, `cordialmente`, `conforme solicitado`.
- Bloquear marcas de português europeu: `estou a`, `telemóvel`, `contacto`, `morada`, `avaria`, `autocarro`.
- Não usar inglês em copy de cliente: `breakdown`, `budget`, `labor`, `client-ready`, `required`, `must`.
- Em mensagem ambígua, perguntar uma coisa por vez. Ex.: "É instalação, manutenção ou limpeza?"
- Em reclamação, reconhecer o problema e dar encaminhamento. Não discutir culpa.
- Toda resposta precisa terminar com próximo passo claro: pedir bairro/modelo/foto, sugerir vistoria, confirmar agenda ou transferir para humano.

O loop `refinar.py --loop 50` agora audita essas regras. O modo estrito transforma avisos de qualidade em falha:

```bash
python3 refinar.py --loop 50 --strict-ptbr
```

Fontes usadas como base: Linguagem Simples do Governo Federal, Programa de Linguagem Simples da Prefeitura de São Paulo, boas práticas do Sebrae para WhatsApp, Decreto SAC/CDC e referência sociolinguística USP sobre uso de `você/cê` em São Paulo.

## 0.2 Política comercial e qualificação

Pesquisa aplicada em 25/05/2026: venda consultiva em serviço técnico deve investigar necessidade real antes de vender; WhatsApp com IA deve responder rápido, qualificar lead, coletar dados, organizar agendamento e transferir só o que precisa de humano.

Regra comercial fixa da Refrimix:

- Só existem dois preços fechados sem visita: instalação de split high-wall com acesso simples e higienização de split high-wall.
- Instalação high-wall simples: `R$800` no Guarujá ou `R$850` em Santos, São Vicente e Praia Grande.
- Higienização de split high-wall: `R$200` por aparelho.
- Todo o resto vira análise técnica de `R$50`, abatida se o cliente aprovar o orçamento final.
- Casos fora do preço fixo: telhado, escada alta, fachada, distância grande, ponto elétrico duvidoso, dreno sem destino, cassete, splitão, VRV/VRF, dutos, galpão, PMOC, manutenção corretiva, carga de gás, projeto e laudo.
- Para instalação, coletar no WhatsApp: cidade/bairro, BTU/modelo, foto da unidade interna, foto da unidade externa, foto do quadro de luz/ponto elétrico e destino do dreno.
- Nunca prometer `visita gratuita`; use `análise técnica de R$50 abatível`.
- Cliente com serviço em andamento não é lead novo. Responder como acompanhamento, não como venda, e sinalizar o gerente em paralelo.

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
Nível 2 — Conhecimento RAG  →  top100 FAQ no Qdrant (hvac_top100.py + seed_hvac.py)
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

**Arquivo:** `qdrant/hvac_top100.py` — lista `TOP100_FAQ`

**Quando usar:** bot dando informação errada, omitindo detalhe importante, sem contexto sobre preços/condições/regiões.

**Estrutura de uma pergunta/resposta:**
```python
faq(
    "Quanto custa para instalar um split?",
    "Instalação padrão no Guarujá fica R$800. Pra Santos, São Vicente e Praia Grande fica R$850 por causa do deslocamento. Qual a cidade e o modelo do aparelho?",
    "instalacao",
    "analise_tecnica",
    5,
    ("preco",),
)
```

**Adicionando ou ajustando FAQ:**
```python
# Abre hvac_top100.py e mantenha TOP100_FAQ com exatamente 100 itens.
faq(
    "Meu ar não está gelando.",
    "Quando não gela, pode ser filtro sujo, gás baixo ou falha em componente. Me fala a marca, o BTU e em qual bairro está?",
    "manutencao",
    "analise_tecnica",
    5,
    ("nao-gela",),
),
```

**Re-seed limpo:**
```bash
source .venv/bin/activate
python qdrant/seed_hvac.py --prune-legacy

# Confirma quantos pontos tem
curl -s http://localhost:6333/collections/hermes_hvac_rag_service_staging | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('Pontos:', d['result']['points_count'])"
```

**Não precisa rebuildar** — o Qdrant é consultado em runtime. O seed recria a coleção alvo com 100 pontos e `--prune-legacy` remove coleções antigas/sandbox que não são usadas pelo runtime.

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
   - Info faltando/errada?   → Nível 2 (Qdrant top100 FAQ)
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
python3 refinar.py --loop 50 --strict-ptbr
```

Esse loop usa `send=false`, então não manda WhatsApp real. O primeiro comando valida intenção, resposta e handoff; o segundo também reprova respostas longas, sem próximo passo claro ou com sinais de PT-PT/formalismo.

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
[ ] `.venv/bin/python -m sre.probes tts-audit` verde
[ ] `Chatterbox Multilingual` primário em pt-BR; `OmniVoice` fallback; `XTTS` fora do caminho de produção
[ ] `.venv/bin/python -m sre.probes tts-audit --synthesize` gera áudio sem enviar WhatsApp real
```
