# Blueprint RAG Consultivo Refrimix

Atualizado em 2026-05-25.

Este blueprint consolida a aula do SRE arquiteto, o estado real do repositório `whatsapp-rag` e a direção técnica para evoluir o atendimento da Refrimix sem transformar o RAG em FAQ engessado.

## Tese

O RAG da Refrimix deve ser uma biblioteca semântica de decisão comercial e técnica. Ele não deve decidir sozinho, nem colar respostas prontas. Ele deve entregar critério, limite, risco e próximo passo para o LLM responder como atendimento técnico consultivo em português brasileiro.

Fórmula operacional:

```text
entendi -> explico -> oriento -> chamo para o próximo passo
```

O objetivo não é vender por pressão. É vender por clareza. Chamamos de `empurro-terapia` qualquer tentativa de forçar fechamento antes de entender contexto, como "últimas vagas", "promoção imperdível", "fechando agora" ou "vamos fechar hoje?".

## Estado Atual Em 2026-05-25

O projeto já tem uma base boa:

- `qdrant/hvac_top100.py`: FAQ Top100 com serviço, outcome, prioridade e tags.
- `knowledge/refrimix/playbooks/*.yaml`: playbooks versionados de atendimento, vendas, objeções, segurança, linguagem e sinais de alto valor.
- `knowledge/refrimix/docs/*.md`: documentos técnicos/comerciais por cenário.
- `knowledge/refrimix/schemas/*.json`: contratos para payload RAG e leitura do lead.
- `agent_graph/services/playbook_loader.py`: loader seguro dos playbooks.
- `agent_graph/services/domain_disambiguation.py`: desambiguação de termos HVAC antes da busca.
- `qdrant/seed_hvac.py`: seed que combina Top100 com knowledge Refrimix.
- `agent_graph/nodes/nodes.py`: classificação, recuperação, prompt principal, CTA e guardrails de resposta.

Isso significa que a próxima etapa não é criar tudo do zero. A próxima etapa é refinar granularidade, payload, filtros, testes e resposta final.

## Princípios De Arquitetura

### 1. Playbook rígido por trás, resposta natural na frente

O playbook precisa ser estruturado o suficiente para o bot decidir:

- serviço provável;
- etapa do atendimento;
- intenção do lead;
- risco técnico/comercial;
- pergunta mínima seguinte;
- CTA permitido;
- limite do que pode ser afirmado.

A resposta para o cliente deve continuar natural, curta e brasileira. Template demais deixa o atendimento com cara de script.

### 2. Qdrant guarda conhecimento reutilizável

O Qdrant deve guardar:

- glossário HVAC Brasil;
- serviços e escopo;
- política de preço;
- perguntas por etapa;
- objeções;
- segurança elétrica;
- sinais de alto valor;
- exemplos bons e ruins;
- templates flexíveis;
- regras de linguagem e TTS.

O Qdrant não deve guardar:

- telefone de lead;
- endereço real;
- agenda do dia;
- histórico individual completo;
- estado vivo da conversa;
- preço negociado individual;
- segredo operacional;
- credencial;
- dado pessoal.

Estado vivo fica em Postgres/Redis. Conhecimento reutilizável fica em `knowledge/refrimix` e Qdrant.

### 3. Payload é parte da inteligência

Todo chunk RAG novo deve ter metadados suficientes para filtro e depuração.

Payload mínimo recomendado:

```json
{
  "doc_id": "pricing_policy:instalacao_split_acesso_simples",
  "doc_type": "pricing_rule",
  "service": "instalacao",
  "stage": "preco",
  "goal": "qualify_quote",
  "segment_market": "residential",
  "segment_tier": "common",
  "intent": "price_question",
  "cta_type": "ask_photos",
  "priority": 90,
  "tags": ["preco", "split", "acesso_simples"],
  "source": "knowledge/refrimix/playbooks/pricing_policy.yaml",
  "text": "..."
}
```

Campos que devem virar filtros/indexes quando a ingestão expandida estiver ativa:

- `doc_type`
- `service`
- `stage`
- `goal`
- `segment_market`
- `segment_tier`
- `intent`
- `cta_type`
- `priority`
- `tags`
- `source`

### 4. Chunk pequeno ganha de YAML inteiro

O seed atual já ingere os playbooks, mas a melhor evolução é quebrar os YAMLs em chunks menores. Em vez de recuperar um playbook inteiro de preço, o RAG deve recuperar a regra certa:

```text
pricing_policy:instalacao_split_acesso_simples
pricing_policy:higienizacao_split_padrao
objection:achei_caro_instalacao
safety:cheiro_queimado
qualification:manutencao_nao_gela
segment:comercial_alto_valor_pmoc
```

Isso aumenta precisão, reduz contexto e evita resposta engessada.

### 5. Busca em camadas

Busca ideal no `retrieve_knowledge`:

```text
1. service + stage + goal + segment_market
2. service + goal
3. service
4. geral
```

Se a coleção tiver pouco retorno, relaxa filtro. Se vier retorno demais ou genérico, prioriza `priority`, `doc_type`, `cta_type` e proximidade semântica.

Hybrid search com dense + sparse é desejável para termos exatos como `PMOC`, `VRF`, `BTU`, `dreno`, `disjuntor`, `splitão`, mas não é a primeira prioridade. Primeiro vem chunk correto e payload filtrável.

## Regra Anti Empurro-Terapia

Empurro-terapia é qualquer resposta que tente pressionar o cliente antes de qualificar:

```text
Fechando hoje eu garanto sua vaga.
Promoção só até agora.
Vamos fechar?
Esse é o melhor preço, posso agendar?
Tenho poucas vagas.
```

Resposta consultiva correta:

```text
Entendi.

Pra não te passar valor errado, preciso confirmar o acesso, a distância entre as unidades e o ponto elétrico.

Me manda uma foto do local interno e uma do local externo?
```

Critério de qualidade:

- confirma o que entendeu;
- educa em uma frase curta;
- não inventa diagnóstico;
- não inventa preço;
- pede só o próximo dado útil;
- termina com CTA leve;
- não revela segmentação interna;
- não usa português europeu;
- não foge do nicho de ar-condicionado.

## Direção De Implementação

### Fase 1: Consolidar documentos RAG em chunks

Criar um builder para transformar `knowledge/refrimix/playbooks/*.yaml`, `knowledge/refrimix/docs/*.md` e exemplos futuros em documentos RAG pequenos.

Saída esperada:

```text
knowledge/refrimix/rag_documents.jsonl
```

Cada linha deve seguir o payload mínimo recomendado e manter `source` apontando para o arquivo original.

### Fase 2: Atualizar seed do Qdrant

Atualizar `qdrant/seed_hvac.py` para:

- manter compatibilidade com `TOP100_FAQ`;
- carregar `knowledge/refrimix/rag_documents.jsonl` quando existir;
- manter fallback para builder direto se o JSONL não existir;
- criar payload indexes para campos filtráveis;
- registrar quantidade por `doc_type`, `service` e `stage`.

### Fase 3: Melhorar recuperação

Ajustar recuperação para buscar primeiro com filtros fortes e relaxar de forma controlada:

```text
service + stage + goal + segment_market
service + goal
service
geral
```

A query reescrita deve continuar transformando frases ambíguas em domínio HVAC:

```text
"meu ar parou"
->
"manutenção ar-condicionado split não liga parou de funcionar diagnóstico técnico foto painel cidade"
```

### Fase 4: Refinador consultivo

Adicionar teste e/ou função de validação para bloquear empurro-terapia e resposta robótica.

O refinador deve avaliar:

- tem pt-BR natural;
- tem no máximo uma pergunta principal;
- usa preço só quando permitido;
- termina com CTA leve;
- não pressiona fechamento;
- não revela segmento interno;
- não pergunta dado já informado;
- não usa termos fora do nicho.

### Fase 5: Testes e probes

Testes mínimos:

- loader carrega playbooks;
- builder gera payload completo;
- seed preserva Top100 e adiciona documentos Refrimix;
- query ambígua é reescrita para HVAC;
- busca relaxa filtros quando necessário;
- resposta consultiva evita empurro-terapia;
- resposta não usa português europeu;
- resposta não revela `segment_market` ou `segment_tier`.

Quando testar atendimento real, usar somente `/test/chat?...&send=false`.

## Critérios De Aceite

Uma etapa estará pronta quando:

- todos os documentos RAG novos tiverem payload rico;
- `TOP100_FAQ` continuar funcionando;
- o seed carregar conhecimento sem segredo;
- Qdrant tiver filtros úteis;
- respostas de preço não inventarem valor;
- manutenção não chutar diagnóstico;
- alto valor alertar internamente sem falar isso ao cliente;
- atendimento terminar com CTA leve;
- testes passarem com `.venv/bin/python -m pytest`;
- fechamento for feito com `./sync.sh --message "tipo: resumo objetivo"`.

## Prompt De Retomada Pós-Reinício

```text
Estamos em /home/will/whatsapp-rag, após reinício do Windows/ambiente.

Leia primeiro:
1. AGENTS.md
2. .rules/secrets-env.md
3. .rules/pt-br.md
4. docs/mapa-pc1-pc2-refinamento.md
5. BLUEPRINT.md

Objetivo:
Executar o blueprint do RAG consultivo da Refrimix sem depender de contexto comprimido.

Contexto:
- O foco é pt-BR brasileiro fluente para HVAC Brasil.
- O bot deve vender como atendimento técnico consultivo, sem empurro-terapia.
- O RAG não deve ser FAQ engessado; deve ser biblioteca semântica de decisão comercial/técnica.
- Estado vivo do lead fica em Postgres/Redis.
- Conhecimento reutilizável fica em knowledge/refrimix e Qdrant.
- Qdrant deve usar payload rico, filtros e, depois, hybrid search quando fizer sentido.
- Resposta ideal: entendi -> explico -> oriento -> chamo para o próximo passo.

Tarefa:
Com base no BLUEPRINT.md, implementar a próxima etapa mais segura e incremental do RAG consultivo:
1. verificar estado atual do repo;
2. propor plano curto se necessário;
3. implementar sem mexer em segredos;
4. validar com .venv/bin/python -m pytest;
5. finalizar com ./sync.sh --message "tipo: resumo objetivo";
6. confirmar git status --short limpo.

Não usar WhatsApp real em testes. Use /test/chat?...&send=false quando precisar testar atendimento.
```
