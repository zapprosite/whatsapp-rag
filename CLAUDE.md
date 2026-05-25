<!-- GENERATED FILE: do not edit manually. Source: .context/docs/*.md. Run ./sync.sh. -->
> Auto-generated from .context/docs | fingerprint: 511e6fd31ed53ec4
## modelos_ptbr_huggingface

---
source: modelos_ptbr_huggingface.md
type: generic
---

# Modelos PT-BR testados no Hugging Face

Objetivo: reduzir português genérico no atendimento da Refrimix sem piorar latência do WhatsApp.

## Resultado prático

- Melhor candidato local encontrado: `mradermacher/AV-BI-Qwen2.5-7B-PT-BR-Instruct-i1-GGUF`, arquivo `AV-BI-Qwen2.5-7B-PT-BR-Instruct.i1-Q4_K_M.gguf`.
- Baixado em `/home/will/llama.cpp/models/AV-BI-Qwen2.5-7B-PT-BR-Instruct.i1-Q4_K_M.gguf`.
- Servidor GPU no PC1 disponível em `http://127.0.0.1:8011/v1`, alias `qwen2.5-7b-pt-br-instruct`.
- Túnel no PC2 disponível em `http://127.0.0.1:8211/v1`.
- Não ativar como polidor em produção por padrão: na RTX 4090 do PC1 ficou muito rápido, mas ainda precisa de contexto comercial forte para não ficar genérico.

## Decisão

- Manter só o 7B PT-BR local como modelo auxiliar.
- Não manter modelos pequenos de português no ambiente.
- LoRA safetensors solto não é o melhor encaixe agora, porque o runtime local usa `llama.cpp`; GGUF mesclado é mais simples e seguro.

## Uso recomendado

- Manter `PTBR_POLISH_ENABLED=0` no atendimento ao vivo.
- Usar o 7B PT-BR em avaliação offline, geração de exemplos e comparação de tom.
- Para melhorar produção, preferir respostas determinísticas para preço e RAG com exemplos locais validados.

---

## playbook_vendas

---
source: playbook_vendas.md
type: generic
---

# Playbook de Vendas — Refrimix Tecnologia

## Contexto de Mercado — Guarujá e Região

O cliente de climatização residencial e comercial no Guarujá e região toma decisão rápida,
pelo celular, no WhatsApp. Se o atendente demorar mais de 30 minutos ou der resposta genérica,
o lead vai pro concorrente. O mercado é dominado por autônomos informais ("Seu João") que
cobram menos mas não têm CREA, não emitem nota, não dão garantia. Esse é o diferencial da
Refrimix: serviço técnico, garantia de 90 dias, emissão de laudo PMOC, profissionalismo real.

## Tabela de Preços — Os Dois Mais Vendidos

### Instalação Split High-Wall
- **R$ 800,00 à vista** (Pix ou dinheiro)
- **R$ 850,00 em 3x sem juros no cartão**
- Inclui: suporte, tubulação (até 3m), dreno, material elétrico básico, mão de obra
- Equipamento fornecido pelo cliente (apenas instalação)
- Acesso difícil (fachada, andaime, distância maior que 3m): orçamento na visita

### Higienização Split High-Wall
- **R$ 200,00 por unidade**
- Inclui: lavagem do evaporador, limpeza dos filtros, verificação geral
- Equipamento permanece no local (não retira)
- Periodicidade recomendada: a cada 6 meses

## Como Qualificar o Lead

### Sinais de Comprador Real (converter rápido, propor agendamento)
- Informa localização (Guarujá, Santos, São Vicente, Praia Grande...)
- Tem urgência: "tá muito quente", "verão chegando", "quebrou ontem"
- Pergunta disponibilidade de agenda ("quando consegue vir?")
- Menciona equipamento específico (marca, BTU, quantidade)
- Aceita agendar visita sem insistir em preço exato antes

### Sinais de Curioso (qualificar mais antes de gastar energia)
- Pede preço sem informar localização
- Compara direto com informal: "aqui tem um que cobra R$400"
- Pergunta sobre 4 serviços diferentes sem foco
- Resposta vaga para "onde fica o equipamento?"
- "Só quero ter uma ideia" sem urgência aparente

### Sequência de Qualificação (na ordem)
1. Identifica o serviço (o que precisa?)
2. Localização (está na área de atendimento?)
3. Equipamento (quantos? marca? BTU? acesso fácil?)
4. Urgência (quando precisa? tem outro orçamento?)
5. Propõe próximo passo (visita técnica gratuita OU fecha direto se for instalação padrão)

## Objeções Comuns e Como Tratar

### "Tá caro"
❌ Não: "é o nosso preço mínimo"
✅ Sim: "Esse valor inclui material, mão de obra e 90 dias de garantia no serviço.
No informal você paga menos, mas qualquer problema você paga de novo. Com a gente,
se der defeito no serviço a gente volta sem cobrar."

### "Fulano cobra R$400 pra instalar"
❌ Não: falar mal do concorrente
✅ Sim: "Deve ser uma instalação mais simples. O nosso preço é com material padrão
técnico, suporte galvanizado e tubulação isolada — que é o que garante que o ar
vai durar. Me passa onde fica que eu vejo se é o mesmo padrão."

### "Me manda o orçamento por escrito"
❌ Não: mandar PDF longo
✅ Sim: "Claro! Instalação padrão high-wall fica R$800 à vista ou R$850 em 3x
sem juros. Equipamento fornecido por você. Se tiver algo fora do padrão (acesso
difícil, distância maior), a gente confirma na visita que é gratuita."

### "Preciso pensar / vou ver com minha esposa"
✅ Sim: "Claro, sem pressão! Só avisa que a agenda tá enchendo rápido pro verão.
Quando decidir me chama que a gente encaixa."

### "Vocês são confiáveis? Nunca ouvi falar"
✅ Sim: "A gente tá há [X] anos no Guarujá e região, com CREA ativo e PMOC certificado.
Se quiser posso te mandar o número do CREA pra verificar. Também emito nota
de serviço pra garantia."

## Tom e Estilo Correto

- WhatsApp real: frases curtas, sem formalidade, sem "prezado", sem "att."
- Usa "a gente" não "nós", "pra" não "para", "tá" não "está"
- NÃO USA bullet points ou listas. Fala como pessoa.
- Uma pergunta por mensagem — não bombardeia
- Propõe ação concreta no final de cada mensagem
- Cria leveza: "pode deixar", "a gente resolve", "sem problema"

## Cenários de Alta Frequência

### Instalação — lead qualificado
Lead: "Quero instalar um ar split na sala. Fica no Guarujá."
Will ideal: "Boa! Instalação padrão high-wall fica R$800 à vista ou R$850 em 3x
sem juros. Qual a BTU e a marca do equipo? Pergunto pra já verificar o acesso
e confirmar o prazo."

### Higienização — lead com dor
Lead: "Meu ar tá com cheiro horrível quando liga."
Will ideal: "Cheiro é sinal de fungo no evaporador — higienização resolve. A gente
faz por R$200 a unidade aqui no Guarujá e região. Onde fica o aparelho e qual a marca?"

### Curioso sobre preço sem contexto
Lead: "Quanto custa pra instalar ar condicionado?"
Will ideal: "Instalação padrão high-wall fica R$800 à vista ou R$850 em 3x
sem juros no cartão. Me passa onde fica e a BTU do equipo que confirmo
se tem algum custo adicional de acesso."

### Manutenção corretiva com urgência
Lead: "Meu ar não tá gelando mais, precisaria ver isso hoje."
Will ideal: "Entendido! Hoje eu não consigo garantir, mas amanhã a gente encaixa.
Visita técnica é gratuita — se resolver na hora a gente já cobra o serviço.
Onde fica e qual a marca do aparelho?"

## Critérios de Qualidade de Resposta (para avaliação automatizada)

Uma boa resposta do Will deve:
1. **Avançar a venda** — não apenas responder, mas mover o lead pro próximo passo
2. **Citar preço quando perguntado** — sem rodeios, sem "depende", sem fugir
3. **Fazer uma pergunta qualificadora** — localização, equipamento ou urgência
4. **Soar humano e local** — linguagem do Guarujá e região, informal, direto
5. **Não repetir o que já foi dito** — cada mensagem acrescenta algo novo
6. **Propor ação concreta** — visita, agendamento, confirmação de dados

---

## project-rules

---
source: CLAUDE.md
type: generic
---

# WhatsApp RAG Lead — Refrimix

## Contexto

Projeto: bot WhatsApp para onboarding e atendimento a leads da Refrimix Tecnologia.
Stack: Evolution API v2.3.7 Docker (8080) + FastAPI + LangGraph (8000) + Qdrant staging (6333) + Redis PC1 (6379).
Seis serviços KB: instalacao, consultoria, manutencao, pmoc, projeto-central, higienizacao.
Coleção Qdrant: `hermes_hvac_rag_service_staging` — 768 dimensões, cosine, 55 pontos.
Redis PC1: 192.168.15.83:6379.
PostgreSQL whatsapp_rag: 192.168.15.83:5432.
Repositório primário: Gitea remoto `origin`.
Espelho público/externo: GitHub remoto `github` (`https://github.com/zapprosite/whatsapp-rag.git`).

## Arquitetura

```
[WhatsApp] → [Evolution API Docker :8080]
                  ↓ webhook POST
            [FastAPI + LangGraph :8000]
              ↓ Redis queue     ↓ worker_loop
         [Redis PC1:6379]   [LangGraph 8 nós]
                                  ↓
                 [Qdrant :6333] + [MiniMax/Groq]
```

## LangGraph — 8 Nós

```
preprocess_input → classify_service → retrieve_knowledge → generate_response
→ language_guard_check → format_whatsapp → decide_response_modality
→ tts_voice_clone | dispatch_appointment_alert → save_interaction
```

## Routing LLM

- `onboarding`, `manutencao`, `instalacao`, `higienizacao` → Groq llama-3.1-8b-instant (~1s)
- `pmoc`, `consultoria`, `projeto-central` → MiniMax M2.7 (~7-15s, raciocínio)
- `classify_service` LLM override → Groq llama-3.3-70b-versatile (~1-2s)

## Regras de Código

1. `from __future__ import annotations` + type hints em todo arquivo Python
2. Nenhum segredo no código — só `os.getenv`
3. Redis usa `redis.asyncio`
4. LangGraph: `messages: Annotated[list[BaseMessage], add_messages]`
5. Não modificar Evolution API docker-compose
6. Histórico de conversa: sliding window 6 turnos, TTL 30min, chave `conv_history:{phone}`
7. Salvar histórico limpo: `messages_with_history + [AIMessage(ai_message)]` — não `messages_out`
8. Voz em produção deve ficar em `TTS_ENGINE=chatterbox` + `TTS_LOCALE=pt-BR` enquanto `.venv/bin/python -m sre.probes tts-audit --require-chatterbox-pt` estiver verde; `OmniVoice` é fallback seguro.
9. Antes de aceitar mudança de voz/PC1/PC2, rode `.venv/bin/python -m sre.probes tts-audit`; para sample local sem WhatsApp real, use `--synthesize`.
10. `5513974139382` é a linha Refrimix/QR lido; `5513996659382` é gerente/crons. Eventos `fromMe=true` desses números devem ser ignorados pelo bot.
11. Copy, PDF, prompts e mensagens de cliente devem seguir `.rules/pt-br.md`: português brasileiro por padrão; inglês só para termos técnicos inevitáveis.

## Documentação e Espelho Git

- `AGENTS.md` é a primeira leitura obrigatória para qualquer agente.
- `CLAUDE.md` é arquivo gerado. A fonte canônica fica em `.context/docs/*.md`.
- Nunca edite `CLAUDE.md` manualmente. Edite `.context/docs/*.md` e rode `./sync.sh`.
- O fluxo correto de publicação é `origin` (Gitea) primeiro e `github` depois.
- Para publicar mudanças: `./sync.sh --message "sync: descreve a mudança"`.
- Para espelhar algo que já está no Gitea: `./sync.sh --mirror-only`.
- O GitHub não é fonte primária; ele é espelho do Gitea.

---

## ptbr_guardrails

---
source: .rules/pt-br.md
type: generic
---

# Guardrails PT-BR

## Regra Principal

Todo atendimento, prompt, documento, PDF, copy e instrução para LLM deve ser produzido em português brasileiro moderno. Inglês só é permitido para nomes técnicos inevitáveis de APIs, bibliotecas, comandos, variáveis, classes, modelos ou protocolos.

## Copy De Cliente

- WhatsApp: natural, curto, com jeito brasileiro de atendimento.
- PDF comercial: português técnico claro, formal o suficiente, sem inglês decorativo.
- Evitar termos como `Breakdown`, `budget`, `labor`, `client-ready`, `Must` e `Required` em qualquer copy final.
- Usar `detalhamento`, `orçamento`, `mão de obra`, `pronto para o cliente final`, `deve` e `obrigatório`.

## Números Fixos

- `5513974139382`: linha Refrimix Tecnologia, QR code lido na Evolution API.
- `5513996659382`: gerente, usado para receber crons e alertas.
- Eventos `fromMe=true` desses números são mensagens enviadas pela operação e devem ser ignorados pelo bot.

## Validação

Antes de finalizar mudança de copy ou documento:

```bash
.venv/bin/python -m pytest
```

---

## refinamento

---
source: GUIDE_REFINAMENTO.md
type: generic
---

# Refinamento — Refrimix WhatsApp RAG

## Os 4 Níveis

```
Nível 1 — Tom e persona     →  WILL_SYSTEM_PROMPT  (agent_graph/nodes/nodes.py)
Nível 2 — Conhecimento RAG  →  chunks no Qdrant    (qdrant/seed_hvac.py)
Nível 3 — Classificação     →  SCORE_MAP           (classify_service em nodes.py)
Nível 4 — Modelo LLM        →  .env MINIMAX_MODEL / GROQ_FALLBACK_MODEL
```

Regra: refine no nível mais baixo que resolve o problema.

## Testar sem WhatsApp

```bash
curl -X POST "http://localhost:8000/test/chat?message=MENSAGEM+AQUI&send=false"
curl -X POST "http://localhost:8000/test/e2e?start=0&limit=35&delay=0"
```

## Git rápido

```bash
# Gera CLAUDE.md, commita, publica no Gitea e espelha no GitHub
./sync.sh --message "refina: mensagem do que mudou"

# Se a mudança já está no Gitea e só falta atualizar o GitHub
./sync.sh --mirror-only
```

Regra de espelho: `origin` é o Gitea primário; `github` é espelho. Nunca trate o GitHub como fonte principal.

## Container

```bash
# Rebuild após mudança em nodes.py
docker compose up -d --build --no-deps fastapi-rag

# Logs ao vivo
docker logs -f whatsapp-rag-fastapi-rag-1 2>&1 | grep -E "INFO|ERROR|WARNING" | grep -v "HTTP Request"
```

## Loop 50x

```bash
python3 refinar.py --loop 50
```

O loop usa `/test/chat?send=false`; ele não envia WhatsApp real. Quando houver mudança aceita no refinamento, use o comando `commit` no `refinar.py` ou deixe o `refinar_llm.py` salvar no final do ciclo. Os dois fluxos chamam `sync.sh`, publicam no Gitea e espelham no GitHub.

## Voz PT-BR

```bash
.venv/bin/python -m sre.probes tts-audit
.venv/bin/python -m sre.probes tts-audit --synthesize
```

Se a voz soar portuguesa ou robótica, verifique primeiro se o Chatterbox está em modo multilíngue e se algum fallback genérico foi reintroduzido. Para produção, mantenha `TTS_ENGINE=chatterbox`, `TTS_LOCALE=pt-BR`, `TTS_CHATTERBOX_LANGUAGE=pt` e `TTS_ALLOW_CHATTERBOX_PTBR=1`. Se o probe Chatterbox falhar, volte temporariamente para `TTS_ENGINE=omnivoice`.

---

## tts_pc1_pc2

---
source: docs/mapa-pc1-pc2-refinamento.md
type: generic
---

# Voz PT-BR / TTS PC1-PC2

## Decisão Operacional

- TTS de produção: `Chatterbox Multilingual` no PC1.
- Locale obrigatório do atendimento: `pt-BR`.
- `OmniVoice` fica como fallback seguro quando Chatterbox falhar.
- `XTTS` foi removido do caminho de produção; não usar como fallback pt-BR.

## Estado PC1 Auditado Em 2026-05-25

- `Chatterbox`: `127.0.0.1:8200`, API ativa como `ChatterboxMultilingualTTS`, com `pt` habilitado.
- `OmniVoice`: `127.0.0.1:8202`, CUDA, 12 vozes em `/srv/data/tts/voices`, fallback.
- Textos de referência: `/srv/data/voice-instance/ref_texts`.
- Backups do ajuste no PC1: `/srv/apps/chatterbox-tts/config.yaml.bak-20260525-060856-pre-multilingual` e `/srv/apps/chatterbox-tts/config.yaml.bak-20260525-060930-selector-repoid`.

## Variáveis Obrigatórias

```env
TTS_ENGINE=chatterbox
TTS_LOCALE=pt-BR
OMNIVOICE_URL=http://127.0.0.1:8202
CHATTERBOX_URL=http://127.0.0.1:8200
TTS_CHATTERBOX_LANGUAGE=pt
TTS_ALLOW_CHATTERBOX_PTBR=1
TTS_MAX_CHARS=420
SSH_HOST_PC1=will-zappro@192.168.15.83
```

## Auditoria SRE

```bash
.venv/bin/python -m sre.probes tts-audit
.venv/bin/python -m sre.probes tts-audit --synthesize
```

Regra: Chatterbox só fica primário enquanto este comando estiver verde:

```bash
.venv/bin/python -m sre.probes tts-audit --require-chatterbox-pt
```

Se falhar, volte para `TTS_ENGINE=omnivoice`.

---
