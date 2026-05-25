# Regra Obrigatória: Português Brasileiro

Este repositório atende clientes da Refrimix no WhatsApp e gera documentos comerciais. A copy padrão é sempre português brasileiro moderno, natural e claro.

## O Que É Obrigatório

- Usar português brasileiro em prompts, PDFs, mensagens WhatsApp, documentos, templates, exemplos e instruções para LLM.
- Escrever como atendimento real no Brasil: "a gente", "pra", "tá" podem aparecer em WhatsApp; em PDF comercial use português técnico formal, sem exagero.
- Tratar palavras ambíguas pelo contexto brasileiro de climatização: "ar" geralmente é ar-condicionado, "limpeza" pode ser higienização, "quanto fica" é pedido de preço.
- Converter termos de documento para pt-BR: "detalhamento" em vez de "breakdown", "orçamento" em vez de "budget", "mão de obra" em vez de "labor", "pronto para o cliente final" em vez de "client-ready".
- Manter `5513974139382` como linha Refrimix/QR code e `5513996659382` como gerente/crons; eventos `fromMe=true` desses números não são lead.

## O Que É Permitido Em Inglês

- Nomes técnicos inevitáveis: API, webhook, Docker, Redis, FastAPI, LangGraph, Qdrant, SRE, HVAC-R, endpoint, token, commit, branch.
- Nomes de variáveis, classes, funções, bibliotecas, modelos e rotas quando já fazem parte do contrato técnico.

## Guardrails De Implementação

- Mensagem final ao cliente nunca deve misturar inglês decorativo.
- PDF final não pode conter "Breakdown", "budget", "labor", "client-ready", "Must" ou "Required" como copy.
- Se for necessário usar termo técnico em inglês, explique em português quando houver exposição ao cliente.
- Para áudio, manter `TTS_ENGINE=chatterbox`, `TTS_LOCALE=pt-BR`, `TTS_CHATTERBOX_LANGUAGE=pt` e `TTS_ALLOW_CHATTERBOX_PTBR=1` enquanto o probe estiver verde.
- Antes de finalizar mudança em copy, rode `.venv/bin/python -m pytest`.
