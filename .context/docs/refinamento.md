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

- Só dois preços fechados sem visita: instalação de split high-wall com acesso simples e higienização de split high-wall.
- Instalação high-wall simples: `R$800` no Guarujá ou `R$850` em Santos, São Vicente e Praia Grande.
- Higienização high-wall: `R$200` por aparelho.
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
