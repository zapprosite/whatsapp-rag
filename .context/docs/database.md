# Governança de Banco de Dados e lead_state

Este documento descreve a persistência de dados no MVP, detalhando a estrutura das tabelas principais e o esquema interno da coluna JSON de controle de estado.

## 1. Schema Físico (PostgreSQL)

O bot utiliza a tabela `leads` no PostgreSQL para registrar os atendimentos e seu ciclo de vida.

### Tabela `leads`
- `id` (String / UUID): Identificador único do lead.
- `phone` (String, Unique): Número de telefone do cliente no formato internacional (ex: `5513999999999`).
- `name` (String, Nullable): Nome do cliente, extraído deterministicamente.
- `service_type` (String, Nullable): Mapeamento de serviço ativo (`instalacao`, `higienizacao`, `manutencao`, `conserto`).
- `pipeline_stage` (String): Estágio do funil de atendimento (`new`, `awaiting_service`, `awaiting_name`, `pre_agendamento`, `qualified`).
- `city_bairro` (String, Nullable): Município e bairro onde o serviço será executado.
- `lead_state` (JSONB): O estado persistente da conversa, contendo informações comerciais detalhadas.

### Tabela `lead_events`
- Registra cada mensagem enviada (`user` ou `assistant`) associada ao telefone do lead, servindo de base histórica e protegendo a integridade do pipeline conversacional.

---

## 2. Estrutura do `lead_state` (JSON)

A coluna `lead_state` guarda as variáveis que controlam o comportamento do bot em tempo de execução de forma simples e legível:

```json
{
  "nome": "Will",
  "tipo_servico": "instalacao",
  "cidade_bairro": "Guarujá - Centro",
  "btus": "12000 BTUs",
  "fotos": {
    "local_interno": true,
    "local_externo": false
  },
  "instalacao": {
    "ponto_eletrico_exclusivo": true,
    "tubulacao_existente": false,
    "distancia_aproximada": "3m"
  },
  "commercial_decision": {
    "path": "technical_visit_50",
    "visit_price": 50,
    "fixed_price": null,
    "can_schedule_now": true
  },
  "appointment": {
    "preferred_window": "tarde",
    "confirmed_window": false
  },
  "pipeline_stage": "pre_agendamento",
  "last_messages": {
    "user": "quero agendar para tarde",
    "assistant": "Seguimos como visita técnica de R$50..."
  }
}
```

---

## 3. Diretrizes de Schema e Migrations

- **Regra estrita**: Não criar novas tabelas físicas ou colunas sem plano prévio do comitê de infraestrutura.
- A coluna `lead_state` é do tipo `JSONB` especificamente para permitir a expansão de campos virtuais (ex: preferências de data ou detalhes de faturamento) sem a necessidade de rodar migrations de banco de dados (`prisma migrate`), mantendo o banco estável e sem riscos de indisponibilidade.
- Qualquer verificação de schema físico em ambiente local deve usar o validador de ambiente `.venv/bin/python scripts/validate-env.py`.
