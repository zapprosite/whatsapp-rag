<!-- GENERATED FILE: do not edit manually. Source: .context/docs/*.md. Run ./sync.sh. -->
> Auto-generated from .context/docs | fingerprint: 8a5d8830a43754ee
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

## Política Comercial Fixa

Só existem dois serviços com preço fechado por WhatsApp, sem visita:

1. Instalação de split com acesso simples.
2. Higienização de split.

Todo o resto precisa de análise técnica no local ou reunião técnica. A análise custa **R$ 50,00** e esse valor é abatido se o cliente aprovar o orçamento final. Essa taxa filtra curioso, protege agenda e valoriza o diagnóstico técnico.

### Instalação split Com Acesso Simples
- **R$ 800,00 à vista** (Pix ou dinheiro)
- **R$ 850,00 em 3x sem juros no cartão**
- Inclui: instalação padrão split com acesso simples, suporte, tubulação padrão, dreno, material elétrico básico e mão de obra
- Equipamento fornecido pelo cliente (apenas instalação)
- Não vale para telhado, escada alta, fachada, acesso difícil, distância maior, splitão, cassete, VRV/VRF ou dutos
- Para confirmar padrão simples, peça: cidade/bairro, BTU/modelo, foto da unidade interna, foto da unidade externa, foto do quadro de luz/ponto elétrico e destino do dreno

### Higienização split
- **R$ 200,00 por unidade**
- Inclui: lavagem do evaporador, limpeza dos filtros, verificação geral
- Equipamento permanece no local (não retira)
- Periodicidade recomendada: a cada 6 meses
- Cassete, duto, splitão, VRV/VRF ou acesso difícil exigem análise técnica de R$50 abatível

### Serviços Com Análise Técnica de R$50 Abatível

- Manutenção corretiva: não chutar preço sem diagnóstico.
- Carga de gás: primeiro verificar vazamento, tipo de gás e condição do equipamento.
- PMOC, ART, laudo e contrato preventivo.
- VRV/VRF, splitão, rooftop, chiller, dutos, diagramas e projeto central.
- Climatização de galpão, restaurante, hotel, sala de servidor e comércio com vários ambientes.
- Instalação com telhado, fachada, escada alta, acesso difícil, ponto elétrico duvidoso ou dreno sem destino claro.

Resposta padrão: "Esse caso precisa de análise técnica no local. Ela custa R$50 e esse valor abate se você aprovar o orçamento. Me manda cidade, fotos e melhor período pra eu ver agenda?"

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
5. Propõe próximo passo: fecha preço fixo se for split simples, ou agenda análise técnica de R$50 abatível

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
✅ Sim: "Claro! Se for split com acesso simples, fica R$800 no Guarujá ou
R$850 em Santos, São Vicente e Praia Grande. Se tiver acesso difícil, telhado ou
distância maior, fazemos análise técnica de R$50 e abate se aprovar o orçamento."

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
Will ideal: "Boa! Se for split com acesso simples, fica R$800 no Guarujá ou
R$850 em Santos, São Vicente e Praia Grande. Me manda a BTU e fotos de onde vão
ficar a unidade interna, externa, quadro de luz e dreno?"

### Higienização — lead com dor
Lead: "Meu ar tá com cheiro horrível quando liga."
Will ideal: "Cheiro é sinal de sujeira na evaporadora. Higienização de split
split fica R$200 por aparelho. Quantos aparelhos são e em qual cidade fica?"

### Curioso sobre preço sem contexto
Lead: "Quanto custa pra instalar ar condicionado?"
Will ideal: "Se for split com acesso simples, fica R$800 no Guarujá ou
R$850 em Santos, São Vicente e Praia Grande. Me manda cidade, BTU e foto do acesso?"

### Manutenção corretiva com urgência
Lead: "Meu ar não tá gelando mais, precisaria ver isso hoje."
Will ideal: "Entendido. Manutenção precisa de diagnóstico: a análise técnica custa
R$50 e abate se aprovar o orçamento. Onde fica e qual a marca do aparelho?"

### Cliente Com Serviço Em Andamento

Se o número já tiver serviço em `customer_services` com status `scheduled`, `in_progress`,
`awaiting_parts`, `awaiting_customer`, `approved` ou `active`, o bot não deve tratar como lead novo.

Conduta:

- Responder como acompanhamento de serviço.
- Não tentar vender instalação/higienização de novo.
- Confirmar agenda, pendência, endereço ou foto do problema.
- Sinalizar o gerente em paralelo no `OWNER_PHONE`.

Exemplo:

Lead: "o técnico ainda vem hoje?"
Will ideal: "Já identifiquei aqui que você tem um serviço em andamento com a Refrimix. Vou seguir por acompanhamento, sem te passar orçamento novo. Me fala o que você precisa confirmar nesse serviço?"

## Agenda e Google Calendar

O bot pode consultar disponibilidade quando `GOOGLE_CALENDAR_ENABLED=1` e houver credencial configurada. A consulta usa disponibilidade livre/ocupado do Google Calendar e injeta as próximas janelas livres no contexto antes de propor agendamento.

Variáveis:

```env
GOOGLE_CALENDAR_ENABLED=1
GOOGLE_CALENDAR_ID=primary
GOOGLE_SERVICE_ACCOUNT_FILE=/caminho/seguro/service-account.json
GOOGLE_CALENDAR_TIMEZONE=America/Sao_Paulo
```

Sem credencial, o bot não inventa horário. Ele coleta cidade, fotos, dados do serviço e pede melhor período para o gerente confirmar.

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
12. Secrets/env seguem `.rules/secrets-env.md`: `{SECRET}` em `.env.example` é proteção intencional; nenhum agente deve trocar placeholders por valores reais, imprimir segredos ou diagnosticar ambiente mostrando valores.

## Guardrail P0 de Secrets

- `.env.example` deve continuar mascarado com `{SECRET}`.
- Valores reais ficam apenas em `.env`, `.env.local`, vault ou configuração local ignorada pelo Git.
- Diagnóstico de ambiente deve usar `.venv/bin/python scripts/validate-env.py --env-file .env` e listar somente nomes faltantes.
- Se aparecer segredo versionado, trocar por `${VAR}`, documentar em `env.schema.md` e recomendar rotação sem repetir o valor.

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
Nível 2 — Conhecimento RAG  →  top100 FAQ no Qdrant (qdrant/hvac_top100.py + qdrant/seed_hvac.py)
Nível 3 — Classificação     →  SCORE_MAP           (classify_service em nodes.py)
Nível 4 — Modelo LLM        →  .env MINIMAX_MODEL / GROQ_FALLBACK_MODEL
```

Regra: refine no nível mais baixo que resolve o problema.

## Padrão PT-BR/SP de Atendimento

Pesquisa aplicada em 2026-05-25: todo refinamento deve usar português brasileiro moderno, com naturalidade de São Paulo/Baixada Santista e linguagem simples.

Obrigatório no WhatsApp:

- Resposta curta, direta e em voz ativa.
- `você`, `a gente`, `pra` e `tá` são permitidos quando deixam a conversa mais natural.
- Não usar formalismo antigo: `prezado`, `estimado`, `caro cliente`, `atenciosamente`, `cordialmente`, `conforme solicitado`.
- Não usar português europeu: `estou a`, `telemóvel`, `contacto`, `morada`, `avaria`, `autocarro`.
- Não usar inglês em copy de cliente: `breakdown`, `budget`, `labor`, `client-ready`, `required`, `must`.
- Mensagem ambígua vira pergunta curta de desambiguação, sem handoff.
- Reclamação recebe reconhecimento do problema e próximo passo, sem discutir culpa.
- Toda resposta deve ter um próximo passo claro para o lead.

## Política Comercial

Venda consultiva para a Refrimix:

- Só dois preços fechados sem visita: instalação de split com acesso simples e higienização de split.
- Instalação split simples: `R$800` no Guarujá ou `R$850` em Santos, São Vicente e Praia Grande.
- higienização split: `R$200` por aparelho.
- Todo o resto exige análise técnica de `R$50`, abatida se o cliente aprovar o orçamento final.
- Não prometer `visita gratuita`.
- Para instalação, coletar cidade/bairro, BTU/modelo, foto da unidade interna, foto da unidade externa, foto do quadro de luz/ponto elétrico e destino do dreno.
- Cliente com serviço em andamento deve ser tratado como acompanhamento de serviço, não como lead novo; o gerente recebe alerta no `OWNER_PHONE`.

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
python3 refinar.py --loop 50 --strict-ptbr
```

O loop usa `/test/chat?send=false`; ele não envia WhatsApp real. O modo normal bloqueia erro semântico, handoff indevido, português europeu, inglês em copy e formalismo antigo. O modo `--strict-ptbr` também transforma avisos em falha, como resposta longa, perguntas demais ou ausência de próximo passo claro. Quando houver mudança aceita no refinamento, use o comando `commit` no `refinar.py` ou deixe o `refinar_llm.py` salvar no final do ciclo. Os dois fluxos chamam `sync.sh`, publicam no Gitea e espelham no GitHub.

## RAG Top100 e Limpeza

O conhecimento semântico de atendimento e venda fica em `qdrant/hvac_top100.py`, na lista `TOP100_FAQ`, com exatamente 100 perguntas/respostas. Cada resposta precisa estar em pt-BR/SP, ter próximo passo claro e passar nos guardrails do `refinar.py`.

Para recriar a base limpa e remover coleções antigas/sandbox não usadas:

```bash
python qdrant/seed_hvac.py --prune-legacy
```

Coleção de produção: `hermes_hvac_rag_service_staging`.

## Voz PT-BR

```bash
.venv/bin/python -m sre.probes tts-audit
.venv/bin/python -m sre.probes tts-audit --synthesize
```

Se a voz soar portuguesa ou robótica, verifique primeiro se o Chatterbox está em modo multilíngue e se algum fallback genérico foi reintroduzido. Para produção, mantenha `TTS_ENGINE=chatterbox`, `TTS_LOCALE=pt-BR`, `TTS_CHATTERBOX_LANGUAGE=pt` e `TTS_ALLOW_CHATTERBOX_PTBR=1`. Se o probe Chatterbox falhar, volte temporariamente para `TTS_ENGINE=omnivoice`.

Voz única ativa desde 2026-05-25: `willrefrimix-influencer.wav`. Parâmetros tuned para influencer WhatsApp pt-BR:

```env
TTS_CHATTERBOX_CHUNK_SIZE=400
TTS_CHATTERBOX_TEMPERATURE=0.75
TTS_CHATTERBOX_EXAGGERATION=0.5
TTS_CHATTERBOX_CFG_WEIGHT=0.35
TTS_CHATTERBOX_SPEED_FACTOR=1.05
```

`chunk_size=400` elimina pausa de concatenação entre frases (todo o texto ≤420 chars vira 1 chunk). `exaggeration=0.5` dá prosódia natural; abaixar para 0.3 deixa mais neutro/robótico.

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
- `OmniVoice`: `127.0.0.1:8202`, CUDA, fallback.
- Voz única ativa: `willrefrimix-influencer.wav` em `/srv/data/tts/voices` (11 vozes extras removidas em 2026-05-25).
- Textos de referência: `/srv/data/voice-instance/ref_texts/willrefrimix-influencer.txt`.
- Backups do ajuste no PC1: `config.yaml.bak-20260525-060856-pre-multilingual`, `config.yaml.bak-20260525-060930-selector-repoid`, `config.yaml.bak-20260525-094333-pre-singlevoice`.

## Parâmetros de Geração (pt-BR influencer WhatsApp)

| Parâmetro | Valor | Motivo |
|---|---|---|
| `temperature` | 0.75 | prosódia natural sem variação excessiva |
| `exaggeration` | 0.5 | expressividade de influencer, não robótico |
| `cfg_weight` | 0.35 | pacing rápido mantendo aderência à voz |
| `seed` | 0 | variação natural por chamada |
| `speed_factor` | 1.05 | fala levemente mais rápida, estilo WhatsApp |
| `chunk_size` | 400 | 1 chunk único até 420 chars → sem pausa de concatenação |
| `language` | pt | único código aceito pelo multilingual model |

Todos os parâmetros são configuráveis via `.env` sem rebuild de container (ver `.env.example`).

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
TTS_CHATTERBOX_CHUNK_SIZE=400
TTS_CHATTERBOX_TEMPERATURE=0.75
TTS_CHATTERBOX_EXAGGERATION=0.5
TTS_CHATTERBOX_CFG_WEIGHT=0.35
TTS_CHATTERBOX_SPEED_FACTOR=1.05
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
