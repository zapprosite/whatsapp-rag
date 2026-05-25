# Auditoria: hardening da memória conversacional

Data: 2026-05-25 19:27.

## Estado atual

- O worker carrega `conv_history:{phone}` do Redis em `app/worker.py` e usa esse histórico como fonte principal para decidir `is_first_message`.
- O PostgreSQL já guarda `Lead`, `LeadEvent`, `Interaction` e `CustomerService`.
- `preprocess_input` carrega `Lead` por telefone, inicializa `lead_state`, `already_asked_fields`, `missing_fields`, `do_not_ask` e `conversation_summary`.
- `extract_lead_data` salva a mensagem do cliente em `LeadEvent` e atualiza o `Lead`.
- `save_interaction` salva `Interaction` e cria `LeadEvent` da resposta da IA.

## Pontos de risco

- Redis vazio ou expirado faz `is_first_message=True`, mesmo quando o PostgreSQL tem lead em andamento.
- `classify_service` envia saudações curtas para `onboarding` antes de considerar `lead_state`, podendo repetir pergunta de tipo de serviço.
- O classificador pode deixar palavra solta ou LLM sobrescrever `tipo_servico` salvo, sem correção explícita do cliente.
- Não havia guardrail explícito para pedido de segredo, prompt interno, dados de terceiros ou comando comercial malicioso.
- `save_interaction` buscava a primeira mensagem humana do histórico, não a última mensagem recebida.
- Cache de vendas considerava serviço e texto, mas não estado do lead.

## Plano de mudança

- Criar memória canônica em `agent_graph/services/conversation_memory.py`, usando PostgreSQL como fonte persistente e Redis apenas como cache rápido.
- Alterar o worker para montar histórico canônico e calcular `is_first_message` a partir de metadados persistentes.
- Endurecer `classify_service` com estado primeiro, correção explícita de serviço e resposta de continuidade.
- Criar `security_guard` para recusar pedidos internos/maliciosos sem expor o termo técnico ao cliente.
- Criar `response_guard` para validar resposta final antes do envio.
- Persistir `ask_count_by_field`, `last_asked_field` e `conversation_summary`.
- Ajustar cache de vendas para depender do estado conversacional.
- Adicionar testes cobrindo Redis vazio, recuperação por LeadEvent, prompt injection, anti-repetição, cache e salvamento da última mensagem.

## Riscos

- Prisma pode ter variações de serialização JSON entre ambientes; os helpers tratam `str`, `dict` e `list`.
- Algumas respostas determinísticas podem reduzir variação do LLM em mensagens curtas de continuidade, por escolha deliberada de segurança.
- O validador final pode substituir uma resposta boa por fallback se o LLM insistir em pergunta proibida.

## Rollback

- Reverter a branch `feat/conversation-intelligence-hardening`.
- Se necessário, remover o nó `response_guard_check` do grafo e voltar o worker para `load_history`.
- Não há alteração planejada em `.env`, preços ou TTS.
