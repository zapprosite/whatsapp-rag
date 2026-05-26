# Arquitetura de Resiliência e Presença Dinâmica (Evolution API)

Este documento descreve a engenharia de resiliência de requisições HTTP e o controle de mascaramento de latência por meio de sinais de presença inteligentes no bot WhatsApp da Refrimix Tecnologia.

---

## 1. Resiliência de Requisições (Retry & Backoff)

Para proteger a integridade das mensagens e operações contra micro-oscilações de rede, indisponibilidade temporária do container da Evolution API ou limites de taxa (Rate Limits), foi implementado o helper centralizador:

```python
_evolution_request_with_retry(
    method: str,
    url: str,
    headers: dict[str, str],
    json_data: dict[str, Any] | None = None,
    max_retries: int = 3,
)
```

### Mecanismo de Funcionamento
- **Fator de Backoff Exponencial:** A primeira tentativa com falha aguarda `0.5s`, a segunda `1.0s`, a terceira `2.0s` e assim por diante.
- **Tratamento de Erros:**
  - **429 (Too Many Requests):** Intercepta e agenda retentativa após o delay de backoff.
  - **5xx (Server Errors):** Tenta novamente de forma resiliente caso o container da Evolution API esteja reiniciando ou sob estresse.
  - **Connect / Timeout Exceptions:** Captura falhas de rede física e executa o fallback de retentativa.
  - **Outros 4xx:** Retorna imediatamente por se tratar de erros de contrato do lado da aplicação (Bad Request, Unauthorized, etc.).

---

## 2. Indicador de Presença Dinâmico (Typing Indicator)

O bot utiliza o status de digitação para mascarar a latência de processamento da LLM (MiniMax/Qwen) e a síntese de voz (OmniVoice).

### Fluxo de Funcionamento
- **Gerenciador de Contexto Assíncrono:** Utiliza `whatsapp_typing_indicator` em `worker.py` para disparar o sinal imediatamente e mantê-lo ativo a cada `8 segundos` em uma tarefa assíncrona concorrente.
- **Seleção Dinâmica de Modos:**
  - **`recording` (Gravando áudio...):** Ativado quando o cliente envia uma mensagem de áudio e a síntese de voz está habilitada (`TTS_ENABLED=1`), garantindo perfeita imersão e coerência cognitiva.
  - **`composing` (Digitando...):** Ativado em todos os fluxos de texto padrão.
- **Ciclo de Vida Limpo:** Assim que o processamento do grafo termina e a resposta é despachada para o WhatsApp, a tarefa de presença é cancelada de forma determinística, evitando vazamento de tarefas assíncronas.
