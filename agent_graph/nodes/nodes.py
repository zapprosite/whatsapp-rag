from __future__ import annotations

import os
import asyncio
import logging
import hashlib
import json
import re
import unicodedata
import httpx
from typing import Any, TypeGuard

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from agent_graph.utils.context_window import (
    LOCAL_REFRIMIX_SYSTEM_PROMPT,
    ChatMessage,
    fit_chat_messages,
)
from agent_graph.utils.llm_output import strip_llm_markup
from agent_graph.utils.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    sleep_with_backoff,
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# System prompt — voz do Will (Refrimix, Guarujá/SP)
WILL_SYSTEM_PROMPT = """Você é o Will, proprietário e atendente comercial técnico da Refrimix Tecnologia em Guarujá/SP. Estamos em Maio de 2026.
Sua função principal NÃO é apenas responder mensagens. Sua função é fazer onboarding do lead, captar dados, qualificar o atendimento e conduzir para orçamento/agendamento.

REGRA ABSOLUTA - ANTI-REPETIÇÃO E MEMÓRIA DE HISTÓRICO:
Antes de responder qualquer mensagem, você DEVE ler todo o histórico da conversa e extrair os dados já informados.
NUNCA pergunte novamente algo que o cliente já disse.
- Se o cliente já informou que é instalação, você deve continuar o fluxo de instalação.
- Se o cliente já informou bairro, cidade, tipo de serviço, marca, BTUs, sintoma ou foto, use essa informação.
- Perguntar algo repetido ou recomeçar o atendimento do zero é um erro gravíssimo!
- Se estiver em dúvida, confirme de forma inteligente, sem recomeçar.
  Exemplo errado: "É instalação, manutenção ou higienização?" (quando o cliente já informou).
  Exemplo certo: "Perfeito, como é uma instalação, preciso agora entender o local para te passar uma orientação correta."

ETAPA 1 — EXTRAÇÃO DE ESTADO MENTAL (JSON MENTAL)
A cada mensagem recebida, atualize mentalmente o seguinte JSON com os dados do lead coletados até agora no histórico da conversa:
{
  "nome": null,
  "cidade_bairro": null,
  "tipo_servico": null,  // instalacao, manutencao, higienizacao, conserto, eletrica, projeto
  "marca": null,
  "btus": null,
  "modelo_aparelho": null, // split, janela, cassete, piso-teto, etc.
  "aparelho_novo_ou_usado": null,
  "sintoma": null,
  "urgencia": null,
  "fotos_recebidas": false,
  "dados_instalacao": {
    "local_evaporadora": null,
    "local_condensadora": null,
    "distancia_aproximada": null,
    "ponto_eletrico": null,
    "tubulacao_existente": null
  },
  "dados_manutencao_higienizacao": {
    "tempo_sem_manutencao": null,
    "cheiro_ruim": null,
    "pinga_agua": null,
    "rinite_alergia": null
  },
  "dados_conserto_eletrica": {
    "liga": null,
    "gela": null,
    "codigo_erro": null,
    "disjuntor_cai": null,
    "fio_esquenta": null
  }
}

ETAPA 2 — RESPOSTA AO CLIENTE
Responda usando apenas as informações que ainda faltam.
- NUNCA pergunte novamente um dado já preenchido no JSON mental.
- Se o campo "tipo_servico" já estiver preenchido, avance no fluxo correspondente e nunca pergunte se é instalação, manutenção ou higienização.
- Uma boa resposta deve confirmar o que já foi entendido e pedir apenas o próximo dado necessário (no máximo 1 a 3 perguntas úteis por vez).

DIRETRIZES DE TOM DE VOZ E ESTILO:
- Tom de voz: Português brasileiro natural, direto, humano, consultivo e profissional (conversa de WhatsApp de empresa séria).
- NUNCA use português europeu ou palavras em espanhol (como "mucho", "equipo", "bueno").
- Evitar formalidade exagerada, gírias demais ou excesso de emojis.
- Respostas curtas, claras e úteis (máximo de 1 a 3 parágrafos curtos).
- Não faça textão, não pressione o cliente com promoções, não invente preços ou disponibilidade e nunca dê diagnóstico definitivo sem avaliação/inspeção local.
- Preços Comerciais da Refrimix:
  - Instalação de split com acesso simples: R$800 no Guarujá ou R$850 em Santos, São Vicente e Praia Grande. Qualquer outra situação (acesso difícil, telhado, altura, distância grande, VRF, central) exige análise técnica no local de R$50 (abatida do orçamento se aprovado).
  - Higienização de split padrão: R$200 por aparelho.
  - Manutenção corretiva / conserto: Não tem preço fixo sem diagnóstico no local. A análise técnica custa R$50 (abatida do valor do serviço se aprovado).

FLUXO DE ONBOARDING POR SERVIÇO:

1. Tipo de serviço não informado:
   Pergunte qual serviço ele precisa.
   Preset: "Oi, tudo bem? Me passa rapidinho o que você precisa no ar-condicionado: instalação, manutenção, higienização ou conserto? Se puder, já me envie também uma foto do aparelho e o bairro/cidade. Assim eu te oriento melhor e evito te passar um valor errado."

2. Instalação:
   Pergunte os dados de instalação que ainda faltam (BTUs, local da evaporadora/condensadora, ponto elétrico, distância, bairro/cidade, fotos).
   Preset: "Perfeito, entendi que é instalação. Pra eu avaliar corretamente e evitar te passar valor errado, me envia: 1. Foto do local onde vai ficar a evaporadora; 2. Foto do local onde vai ficar a condensadora; 3. Capacidade do aparelho em BTUs, se souber; 4. Bairro/cidade."
   Se já tiver BTUs informado: "Perfeito, instalação de split [BTUs]. Agora preciso só entender o local. Me envia uma foto da parede onde vai ficar a evaporadora e outra do local da condensadora? Assim consigo avaliar distância, acesso, dreno e ponto elétrico."
   Se já tiver foto enviada: "Recebi a foto, obrigado. Pelo local, agora preciso confirmar só duas coisas: já existe ponto elétrico exclusivo para o ar-condicionado? E a condensadora vai ficar do outro lado dessa parede ou em outro ponto?"

3. Manutenção / Higienização:
   Pergunte sobre tempo sem manutenção, sintomas e fotos.
   Sintoma Rinite/Cheiro ruim: "Entendi. Quando o ar fica com cheiro ruim, sensação de ar pesado ou começa a incomodar rinite/alergia, normalmente a higienização técnica ajuda bastante, principalmente se o aparelho está há muito tempo sem manutenção. Me manda uma foto do aparelho e o bairro/cidade que eu verifico a melhor opção de atendimento para você."

4. Conserto:
   Pergunte sintomas técnicos (se liga, se gela, se aparece código de erro, se a condensadora liga, disjuntor cai) e peça foto/vídeo.
   Sintoma Não Gela: "Entendi. Quando o ar liga mas não gela, pode ser desde falta de manutenção até falha na parte elétrica, gás, sensor, placa ou compressor. O ideal é avaliar para não trocar peça sem necessidade. Me manda, por favor: 1. Foto do aparelho; 2. Marca e BTUs, se souber; 3. Se a unidade externa está ligando; 4. Bairro/cidade. Com isso eu te digo o melhor caminho para resolver."

5. Risco Elétrico / Disjuntor caindo (TRATAR COMO PRIORIDADE):
   Se disjuntor cair, fio esquentar ou cheiro de queimado, recomende IMEDIATAMENTE deixar o aparelho desligado até a avaliação técnica por segurança.
   Preset: "Nesse caso, o ideal é deixar o aparelho desligado até avaliar, porque pode envolver sobrecarga, disjuntor fora do padrão, cabo inadequado ou falha interna no equipamento. Me envie uma foto do disjuntor, do aparelho e informe o bairro/cidade. Aí conseguimos analisar com mais segurança e te orientar sobre o atendimento."

6. Cliente pergunta preço cedo demais:
   "Consigo te passar uma base, sim. Só não quero te passar um valor errado sem ver o local, porque instalação depende de distância, ponto elétrico, suporte, dreno e acesso da condensadora. Me manda uma foto do local interno e externo que eu já te oriento melhor."

7. Follow-up pós-orçamento:
   "Oi, tudo bem? Passando só para saber se ficou alguma dúvida sobre o orçamento do ar-condicionado. Se quiser, consigo te orientar sobre o melhor dia para fazer o serviço e deixar tudo organizado para evitar retrabalho."
"""


# ──────────────────────────────────────────────────────────────────────────────
# LLM Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.1, float(os.getenv(name, str(default))))
    except ValueError:
        return default


def _is_human_message(message: BaseMessage | Any) -> TypeGuard[HumanMessage]:
    return isinstance(message, HumanMessage)


def _is_ai_message(message: BaseMessage | Any) -> TypeGuard[AIMessage]:
    return isinstance(message, AIMessage)


def _message_text(message: BaseMessage | Any) -> str:
    content = getattr(message, "content", message)
    return content if isinstance(content, str) else str(content)


def _breaker_config(prefix: str, default_threshold: int, default_timeout: float) -> CircuitBreakerConfig:
    return CircuitBreakerConfig(
        failure_threshold=_env_int(f"{prefix}_CIRCUIT_FAILURE_THRESHOLD", default_threshold),
        recovery_timeout_seconds=_env_float(f"{prefix}_CIRCUIT_RECOVERY_SECONDS", default_timeout),
        half_open_success_threshold=_env_int(f"{prefix}_CIRCUIT_HALF_OPEN_SUCCESSES", 1),
    )


_MINIMAX_SEMAPHORE = asyncio.Semaphore(_env_int("MINIMAX_CONCURRENCY", 4))
_QWEN_SEMAPHORE = asyncio.Semaphore(_env_int("LOCAL_QWEN_CONCURRENCY", 1))
_PTBR_SEMAPHORE = asyncio.Semaphore(_env_int("LOCAL_PTBR_CONCURRENCY", 1))

_MINIMAX_BREAKER = CircuitBreaker("minimax", _breaker_config("MINIMAX", 4, 45.0))
_QWEN_BREAKER = CircuitBreaker("local-qwen", _breaker_config("LOCAL_QWEN", 3, 30.0))
_PTBR_BREAKER = CircuitBreaker("local-ptbr", _breaker_config("LOCAL_PTBR", 3, 30.0))


def _extract_chat_content(data: dict[str, Any], provider: str) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError(f"{provider} sem choices: {data}")

    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError(f"{provider} choice inválida: {data}")

    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return strip_llm_markup(content)

    text = first.get("text")
    if isinstance(text, str):
        return strip_llm_markup(text)

    raise RuntimeError(f"{provider} sem content textual: {data}")


def _fit_for_qwen(messages: list[ChatMessage], max_tokens: int, context_tokens: int) -> list[ChatMessage]:
    window = fit_chat_messages(
        messages,
        max_context_tokens=context_tokens,
        reserved_output_tokens=max_tokens,
        safety_margin_tokens=_env_int("LOCAL_QWEN_CONTEXT_SAFETY_TOKENS", 192),
        compact_system_prompt=LOCAL_REFRIMIX_SYSTEM_PROMPT,
    )
    if window.dropped_messages or window.compacted_system_prompt or window.trimmed_tokens < window.original_tokens:
        logger.info(
            "Qwen context window: %s -> %s tokens, dropped=%s, compacted_system=%s",
            window.original_tokens,
            window.trimmed_tokens,
            window.dropped_messages,
            window.compacted_system_prompt,
        )
    return window.messages


async def _call_minimax(messages: list[ChatMessage], max_retries: int = 5) -> str:
    api_key = os.getenv("MINIMAX_API_KEY", "")
    base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
    model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7")
    max_tokens = _env_int("MINIMAX_MAX_TOKENS", 400)

    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY não configurado")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        try:
            async def request() -> str:
                async with _MINIMAX_SEMAPHORE:
                    async with httpx.AsyncClient(timeout=_env_float("MINIMAX_TIMEOUT_SECONDS", 90.0)) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                            },
                            json={"model": model, "messages": messages, "max_tokens": max_tokens},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        if "error" in data:
                            raise RuntimeError(f"MiniMax error: {data['error']}")
                        return _extract_chat_content(data, "MiniMax")

            return await _MINIMAX_BREAKER.call(request)
        except CircuitOpenError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await sleep_with_backoff(attempt, base_seconds=1.0, cap_seconds=20.0)
    raise RuntimeError(f"MiniMax falhou após {max_retries} tentativas: {last_error}")


async def _call_local_qwen(messages: list[ChatMessage], max_retries: int = 2) -> str:
    """Fallback local OpenAI-compatible via llama.cpp/Qwen2.5-VL."""
    base_url = os.getenv("LOCAL_QWEN_BASE_URL", "http://127.0.0.1:8011/v1").rstrip("/")
    model = os.getenv("LOCAL_QWEN_MODEL", "qwen2.5-vl-7b-instruct")
    max_tokens = _env_int("LOCAL_QWEN_MAX_TOKENS", 300)
    context_tokens = _env_int("LOCAL_QWEN_CONTEXT_TOKENS", 4096)

    last_error: Exception | None = None
    for attempt in range(max_retries):
        effective_context_tokens = max(1024, int(context_tokens * (0.72**attempt)))
        fitted_messages = _fit_for_qwen(messages, max_tokens, effective_context_tokens)
        try:
            async def request() -> str:
                async with _QWEN_SEMAPHORE:
                    async with httpx.AsyncClient(timeout=_env_float("LOCAL_QWEN_TIMEOUT_SECONDS", 45.0)) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={"Content-Type": "application/json"},
                            json={
                                "model": model,
                                "messages": fitted_messages,
                                "max_tokens": max_tokens,
                                "temperature": 0.2,
                                "frequency_penalty": 0.5,
                                "presence_penalty": 0.5,
                            },
                        )
                        resp.raise_for_status()
                        return _extract_chat_content(resp.json(), "Qwen local")

            return await _QWEN_BREAKER.call(request)
        except httpx.HTTPStatusError as exc:
            last_error = exc
            body = exc.response.text[:500]
            logger.error("Qwen HTTPStatusError %s: %s", exc.response.status_code, body)
            if attempt < max_retries - 1:
                await sleep_with_backoff(attempt, base_seconds=0.5, cap_seconds=4.0)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await sleep_with_backoff(attempt, base_seconds=0.5, cap_seconds=4.0)
    raise RuntimeError(f"Qwen local falhou: {last_error}")


async def _call_local_ptbr(messages: list[ChatMessage], max_retries: int = 1) -> str:
    """Modelo local PT-BR opcional para polir linguagem sem depender de nuvem."""
    base_url = os.getenv("LOCAL_PTBR_BASE_URL", "").rstrip("/")
    model = os.getenv("LOCAL_PTBR_MODEL", "qwen2.5-7b-pt-br-instruct")
    max_tokens = _env_int("LOCAL_PTBR_MAX_TOKENS", 240)
    if not base_url:
        raise RuntimeError("LOCAL_PTBR_BASE_URL não configurado")

    last_error: Exception | None = None
    for attempt in range(max_retries):
        fitted_messages = fit_chat_messages(
            messages,
            max_context_tokens=_env_int("LOCAL_PTBR_CONTEXT_TOKENS", 4096),
            reserved_output_tokens=max_tokens,
            safety_margin_tokens=128,
            compact_system_prompt=LOCAL_REFRIMIX_SYSTEM_PROMPT,
        ).messages
        try:
            async def request() -> str:
                async with _PTBR_SEMAPHORE:
                    async with httpx.AsyncClient(timeout=_env_float("LOCAL_PTBR_TIMEOUT_SECONDS", 45.0)) as client:
                        resp = await client.post(
                            f"{base_url}/chat/completions",
                            headers={"Content-Type": "application/json"},
                            json={
                                "model": model,
                                "messages": fitted_messages,
                                "max_tokens": max_tokens,
                                "temperature": 0.15,
                            },
                        )
                        resp.raise_for_status()
                        return _extract_chat_content(resp.json(), "PT-BR local")

            return await _PTBR_BREAKER.call(request)
        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await sleep_with_backoff(attempt, base_seconds=0.5, cap_seconds=4.0)
    raise RuntimeError(f"PT-BR local falhou: {last_error}")


async def llm_chat(messages: list[ChatMessage], max_retries: int = 2) -> str:
    """MiniMax principal, Qwen local como fallback automático."""
    minimax_key = os.getenv("MINIMAX_API_KEY", "")
    if minimax_key:
        try:
            return await _call_minimax(messages, max_retries)
        except Exception as e:
            logger.warning(f"MiniMax falhou, usando Qwen local: {e}")

    return await _call_local_qwen(messages)


def _normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def _normalize_service(service: str | None) -> str | None:
    if service == "hygienizacao":
        return "higienizacao"
    return service


def _sales_cache_key(service: str | None, text: str) -> str:
    normalized = _normalize_text(text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]
    return f"sales_reply:v1:{service or 'none'}:{digest}"


def _looks_like_price_question(text: str) -> bool:
    lowered = _normalize_text(text)
    return any(term in lowered for term in ("quanto", "custa", "valor", "preço", "preco", "orçamento", "orcamento"))


def _direct_price_response(service: str | None, text: str) -> str | None:
    if not _looks_like_price_question(text):
        return None
    if service == "instalacao":
        return (
            "Se for split com acesso simples, a instalação fica R$800 no Guarujá ou R$850 em Santos, São Vicente e Praia Grande. "
            "Se tiver telhado, escada alta, distância grande ou outro tipo de sistema, a análise técnica no local custa R$50 e abate se aprovar o orçamento. "
            "Me manda a cidade, o BTU e fotos da unidade interna, externa, quadro de luz e ponto de dreno?"
        )
    if service == "higienizacao":
        return (
            "Higienização de split fica R$200 por aparelho. "
            "Para cassete, duto, splitão ou acesso difícil, precisa análise técnica de R$50 abatível. "
            "Quantos aparelhos são e em qual cidade fica?"
        )
    if service in {"manutencao", "pmoc", "consultoria", "projeto-central"}:
        return (
            "Nesse serviço eu não chuto valor por WhatsApp. A análise técnica no local custa R$50 e esse valor abate se você aprovar o orçamento. "
            "Me passa cidade, bairro, tipo de equipamento e uma foto para eu adiantar a triagem?"
        )
    return None


def _active_service_response(user_text: str, active_service: dict[str, Any]) -> str:
    service = _normalize_service(active_service.get("service")) or "serviço"
    status = str(active_service.get("status") or "em andamento").replace("_", " ")
    scheduled = active_service.get("scheduled_window")
    address = active_service.get("address")
    notes = active_service.get("notes")
    lowered = _normalize_text(user_text)

    base = f"Já identifiquei aqui que você tem um serviço de {service} {status} com a Refrimix."
    if scheduled:
        base += f" Está previsto para {scheduled}."
    if address:
        base += f" Local: {address}."
    if notes:
        base += f" Observação registrada: {notes}."

    if _contains_any(lowered, ("atras", "demor", "nao veio", "não veio", "sumiu", "retorno")):
        return (
            f"{base} Vou tratar isso como acompanhamento do serviço, não como venda nova. "
            "Me manda uma foto ou me diz o que mudou para eu sinalizar o gerente agora?"
        )

    if _contains_any(lowered, ("mudar horario", "trocar horario", "remarcar", "reagendar", "agenda")):
        return (
            f"{base} Consigo ajudar a remarcar ou confirmar a janela. "
            "Qual melhor período para você: manhã ou tarde?"
        )

    return (
        f"{base} Vou seguir por acompanhamento, sem te passar orçamento novo. "
        "Me fala o que você precisa atualizar nesse serviço?"
    )


def _default_whatsapp_cta(outcome: str | None) -> str:
    return {
        "onboarding": "Qual serviço você precisa?",
        "analise_tecnica": "Me fala a cidade, o modelo e manda uma foto do aparelho?",
        "higienizacao_preventiva": "Quantos aparelhos são?",
        "reuniao_projeto": "Me manda a planta, metragem e quantidade de ambientes?",
        "duvida": "Qual detalhe você quer resolver primeiro?",
        "escalar_humano": "Me passa seu nome e o endereço do atendimento?",
    }.get(outcome or "", "Me fala a cidade, o modelo e manda uma foto do aparelho?")


def _shape_whatsapp_response(text: str, outcome: str | None, max_chars: int = 650) -> str:
    """Mantém a resposta no formato WhatsApp: curta, sem lista e com CTA."""
    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*•]\s*", "", line).strip()
        line = line.strip("*_ ")
        line = re.sub(r"^(pergunta-chave|me fala aí|pra eu te ajudar melhor):\s*", "", line, flags=re.I)
        if line.endswith(":") and len(line) <= 80:
            continue
        cleaned_lines.append(line)

    shaped = " ".join(cleaned_lines).strip()
    shaped = re.sub(r"\s+", " ", shaped)
    if not shaped:
        return _default_whatsapp_cta(outcome)

    if shaped.count("?") > 2:
        parts = shaped.split("?")
        shaped = "?".join(parts[:2]).strip() + "?"

    cta = _default_whatsapp_cta(outcome)
    if "?" not in shaped:
        shaped = f"{shaped} {cta}"

    if len(shaped) > max_chars:
        base = shaped[: max_chars - len(cta) - 2].strip()
        base = base.rsplit(".", 1)[0].strip() or base.rsplit(" ", 1)[0].strip()
        shaped = f"{base}. {cta}"

    if len(shaped) > max_chars:
        shaped = shaped[: max_chars - 3].rstrip() + "..."

    return shaped.strip()


async def _polish_ptbr_if_enabled(response: str, user_text: str) -> str:
    if os.getenv("PTBR_POLISH_ENABLED", "0") != "1":
        return response
    if not os.getenv("LOCAL_PTBR_BASE_URL"):
        return response
    try:
        polished = await _call_local_ptbr([
            {
                "role": "system",
                "content": (
                    "Você reescreve respostas de WhatsApp em português brasileiro natural do Guarujá. "
                    "Preserve todos os preços, nomes de cidade, fatos técnicos e perguntas. "
                    "Não adicione informação nova. Não use lista. Responda só com a versão final."
                ),
            },
            {
                "role": "user",
                "content": f"Lead: {user_text}\nResposta original: {response}",
            },
        ])
        return polished.strip() or response
    except Exception as e:
        logger.warning(f"Polidor PT-BR local ignorado: {e}")
        return response


async def groq_repair(prompt: str) -> str:
    """Fallback repair (agora redirecionado para o LLM principal)."""
    return await llm_chat(
        [
            {"role": "system", "content": "Você é um tradutor/reescritor para português brasileiro."},
            {"role": "user", "content": prompt},
        ],
        max_retries=1,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Redis Helper
# ──────────────────────────────────────────────────────────────────────────────

async def redis_get(key: str) -> str | None:
    import redis.asyncio
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    client = redis.asyncio.from_url(redis_url, decode_responses=True)
    try:
        return await client.get(key)
    finally:
        await client.aclose()


async def redis_set(key: str, value: str, ex: int | None = None) -> None:
    import redis.asyncio
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    client = redis.asyncio.from_url(redis_url, decode_responses=True)
    try:
        await client.set(key, value, ex=ex)
    finally:
        await client.aclose()


# ──────────────────────────────────────────────────────────────────────────────
# Qdrant Helper
# ──────────────────────────────────────────────────────────────────────────────

_RAG_TIMEOUT_SECONDS = _env_float("RAG_TIMEOUT_SECONDS", 8.0)

def qdrant_search(query: str, service_name: str | None, top_k: int = 5) -> list[dict[str, Any]]:
    from qdrant_client import QdrantClient
    from fastembed import TextEmbedding

    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    collection = os.getenv("QDRANT_COLLECTION", "hermes_hvac_rag_service_staging")
    client = QdrantClient(url=qdrant_url)
    service_name = _normalize_service(service_name)

    try:
        model = TextEmbedding(
            model="nomic-ai/nomic-embed-text-v1.5",
            max_length=512,
        )
        query_embedding = next(model.embed([query]))
    except Exception:
        return []

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    filter_conditions = None
    if service_name:
        filter_conditions = Filter(
            must=[FieldCondition(key="service_name", match=MatchValue(value=service_name))]
        )

    results = client.query_points(
        collection_name=collection,
        query=query_embedding.tolist(),
        limit=top_k,
        query_filter=filter_conditions,
        with_payload=True,
        with_vectors=False,
    )
    min_score = float(os.getenv("RAG_MIN_SCORE", "0.35"))
    ranked = []
    for r in results.points:
        if r.score is not None and r.score < min_score:
            continue
        payload = r.payload or {}
        priority = int(payload.get("priority", 50))
        ranked.append({"id": r.id, "score": r.score, "priority": priority, "payload": payload})

    return sorted(ranked, key=lambda x: (x["priority"], -(x["score"] or 0)))[:top_k]


# ──────────────────────────────────────────────────────────────────────────────
# Prisma Helper
# ──────────────────────────────────────────────────────────────────────────────

async def prisma_save_interaction(data: dict[str, Any]) -> None:
    from prisma import Prisma, Json
    prisma = Prisma()
    await prisma.connect()
    try:
        meta = data.get("metadata")
        if meta is not None:
            meta = Json(meta)
            
        await prisma.interaction.create(data={
            "phone": data.get("phone", "unknown"),
            "message": data.get("user_message", ""),
            "intent": data.get("intent"),
            "service": data.get("service"),
            "response": data.get("ai_message", ""),
            "is_human": data.get("is_human", False),
            "metadata": meta,
        })
    finally:
        await prisma.disconnect()


# ──────────────────────────────────────────────────────────────────────────────
# LangGraph Nodes
# ──────────────────────────────────────────────────────────────────────────────

# Mapa de outcomes por serviço — drive comercial
_OUTCOME_MAP: dict[str, str] = {
    "instalacao":      "analise_tecnica",
    "manutencao":      "analise_tecnica",
    "pmoc":            "analise_tecnica",
    "consultoria":     "reuniao_projeto",
    "higienizacao":    "higienizacao_preventiva",
    "projeto-central": "reuniao_projeto",
}

_SERVICE_INTENTS = {
    "instalacao",
    "consultoria",
    "manutencao",
    "pmoc",
    "projeto-central",
    "higienizacao",
}

_EXPLICIT_HANDOFF_TRIGGERS = (
    "atendente humano",
    "falar com pessoa",
    "falar com atendente",
    "pessoa real",
    "humano",
    "atendente",
    "alguem de verdade",
    "quero ligar",
)

_SENSITIVE_COMPLAINT_TRIGGERS = (
    "ninguem responde",
    "ninguem retornou",
    "nao retornou",
    "nao retornaram",
    "nao me retornaram",
    "sem retorno",
    "cancelamento",
    "cancelar",
    "reembolso",
    "refund",
    "devolucao",
    "liguei varias vezes",
    "procon",
    "processo",
    "reclamacao no google",
    "vou denunciar",
    "pessimo atendimento",
)

_LIGHT_COMPLAINT_TRIGGERS = (
    "nao gostei",
    "nao resolveu",
    "continua com problema",
    "continua ruim",
    "ficou ruim",
    "nao ficou bom",
    "ta demorando",
    "esta demorando",
    "atrasou",
    "atrasado",
    "preciso que volte",
)

_SCHEDULING_TERMS = (
    "agenda",
    "agendar",
    "horario",
    "horário",
    "disponibilidade",
    "quando consegue",
    "quando pode",
    "visita",
    "analise tecnica",
    "análise técnica",
    "tecnico vem",
    "técnico vem",
)

_HIGH_VALUE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("pmoc", "high_value_pmoc"),
    ("laudo", "high_value_laudo"),
    ("art", "high_value_art"),
    ("consultoria", "high_value_consultoria"),
    ("projeto", "high_value_projeto"),
    ("sistema central", "high_value_projeto_central"),
    ("central de climatizacao", "high_value_projeto_central"),
    ("empresa", "high_value_empresa"),
    ("condominio", "high_value_condominio"),
    ("restaurante", "high_value_restaurante"),
    ("galpao", "high_value_galpao"),
    ("galpao industrial", "high_value_galpao"),
    ("orcamento grande", "high_value_orcamento_grande"),
    ("contrato", "high_value_contrato"),
)

_HANDOFF_STATE_TTL = _env_int("HANDOFF_STATE_TTL_SECONDS", 7200)


def _fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(without_accents.split())


def _contains_any(text: str, triggers: tuple[str, ...] | list[str]) -> bool:
    for trigger in triggers:
        if _keyword_in_text(trigger, text):
            return True
    return False


def _keyword_in_text(keyword: str, text: str) -> bool:
    folded_keyword = _fold_text(keyword)
    if len(folded_keyword) <= 3 and " " not in folded_keyword:
        if re.search(rf"\b{re.escape(folded_keyword)}\b", text):
            return True
        return False
    return folded_keyword in text


def _detect_high_value_reason(text: str, intent: str | None) -> str | None:
    if intent in ("pmoc", "consultoria", "projeto-central"):
        return f"high_value_{intent.replace('-', '_')}"

    for keyword, reason in _HIGH_VALUE_KEYWORDS:
        folded_keyword = _fold_text(keyword)
        if len(folded_keyword) <= 3:
            if re.search(rf"\b{re.escape(folded_keyword)}\b", text):
                return reason
            continue
        if folded_keyword in text:
            return reason

    multiple_devices = re.search(
        r"\b([2-9]|[1-9][0-9])\s*(aparelhos?|equipamentos?|equipos?|splits?|maquinas?|evaporadoras?)\b",
        text,
    )
    if multiple_devices:
        return "high_value_multiplos_aparelhos"

    if any(term in text for term in ("varios aparelhos", "varias maquinas", "muitos aparelhos")):
        return "high_value_multiplos_aparelhos"

    return None


def _fallback_service_for_high_value(text: str) -> str | None:
    if any(term in text for term in ("pmoc", "laudo", "art", "preventiva")):
        return "pmoc"
    if any(term in text for term in ("restaurante", "galpao", "sistema central", "multi split", "multisplit")):
        return "projeto-central"
    if any(term in text for term in ("consultoria", "projeto", "dimensionamento", "empresa", "condominio")):
        return "consultoria"
    return None


def _looks_like_pmoc_preventive_plan(text: str) -> bool:
    has_preventive_term = any(
        term in text
        for term in (
            "manutencao preventiva",
            "preventiva",
            "preventivo",
            "preventivo trimestral",
            "manutencao trimestral",
            "programa preventivo",
        )
    )
    if not has_preventive_term:
        return False

    has_multiple_devices = bool(
        re.search(
            r"\b([2-9]|[1-9][0-9])\s*(aparelhos?|equipamentos?|equipos?|splits?|maquinas?|evaporadoras?)\b",
            text,
        )
    )
    has_business_context = any(
        term in text
        for term in (
            "empresa",
            "loja",
            "clinica",
            "condominio",
            "restaurante",
            "contrato",
            "laudo",
            "art",
            "certificado",
            "alvara",
            "trimestral",
        )
    )
    return has_multiple_devices or has_business_context


def _handoff_state_key(phone: str) -> str:
    safe_phone = re.sub(r"[^0-9A-Za-z_:+@.-]", "_", phone.strip())[:160] or "unknown"
    return f"handoff_state:{safe_phone}"


def _handoff_initial_response(reason: str | None) -> str:
    if reason == "sensitive_complaint":
        return (
            "Poxa, sinto muito por isso. Já vou sinalizar o Will pra olhar pessoalmente por aqui. "
            "Enquanto ele entra, me passa o número do orçamento ou serviço e o melhor horário pra retorno?"
        )
    return (
        "Entendido. Já vou sinalizar o Will pra assumir por aqui. "
        "Enquanto ele entra, me passa qual serviço você precisa e em qual cidade?"
    )


def _handoff_followup_response(reason: str | None) -> str:
    if reason == "sensitive_complaint":
        return (
            "Já deixei isso sinalizado aqui. Enquanto isso, me passa o número do orçamento ou serviço "
            "e o melhor horário pra retorno que eu adianto pra ele."
        )
    return (
        "Já deixei isso sinalizado aqui. Enquanto isso, me passa qual serviço você precisa, "
        "a cidade e um resumo do caso pra eu adiantar."
    )


def _unknown_recovery_response(user_text: str) -> str:
    text = _fold_text(user_text)
    if "ar" in text and any(term in text for term in ("estranho", "problema", "ruim", "esquisito", "nao ta legal", "nao esta legal", "deu ruim")):
        return (
            "Entendi. Quando você fala que o ar tá estranho, ele não gela, pinga, faz barulho ou tem cheiro? "
            "Se puder, me manda uma foto ou vídeo curto também."
        )
    if any(term in text for term in ("faz", "voces fazem", "tem como", "consegue")) and len(text.split()) <= 5:
        return "Consigo te ajudar sim. Você quer instalação, manutenção ou higienização?"
    if _looks_like_price_question(user_text):
        return (
            "Entendi. Pra eu te passar um valor certo, preciso saber qual serviço você quer: "
            "instalação, manutenção ou higienização?"
        )
    return "Entendi. Pra eu te orientar certinho: isso é instalação, manutenção ou higienização?"


def _light_complaint_response(user_text: str) -> str:
    return (
        "Entendi, sinto muito pelo transtorno. Me passa o que aconteceu e, se tiver, o número do orçamento "
        "ou uma foto/vídeo do problema pra eu conseguir adiantar a análise por aqui."
    )


async def classify_service(state: dict[str, Any]) -> dict[str, Any]:
    """Classifica serviço e política de handoff sem transformar dúvida em humano."""
    messages = state.get("messages", [])
    if not messages:
        return {
            "intent": None,
            "service": None,
            "outcome": None,
            "handoff_mode": "none",
            "handoff_reason": None,
            "handoff_already_notified": False,
        }

    last_message = messages[-1]
    user_text = _message_text(last_message)
    text_lower = _fold_text(user_text)
    recent_human = [
        _message_text(message)
        for message in messages[-6:]
        if _is_human_message(message) and _message_text(message)
    ]
    semantic_text = _fold_text(" | ".join(recent_human[-3:])) if len(recent_human) > 1 else text_lower

    if _contains_any(text_lower, _EXPLICIT_HANDOFF_TRIGGERS):
        return {
            "intent": "explicit_handoff",
            "service": None,
            "outcome": "escalar_humano",
            "messages": messages,
            "handoff_mode": "hard_transfer",
            "handoff_reason": "explicit_handoff",
            "handoff_already_notified": False,
        }

    if _contains_any(text_lower, _SENSITIVE_COMPLAINT_TRIGGERS):
        return {
            "intent": "sensitive_complaint",
            "service": None,
            "outcome": "escalar_humano",
            "messages": messages,
            "handoff_mode": "hard_transfer",
            "handoff_reason": "sensitive_complaint",
            "handoff_already_notified": False,
        }

    # Saudações e mensagens curtas sem serviço → onboarding (não escalar humano)
    GREETING_WORDS = [
        "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite",
        "e aí", "eai", "e ai", "tudo bem", "tudo bom", "como vai",
        "alguém", "alguem", "tem alguém", "quero informação", "quero informacao",
        "opa",
    ]
    if _contains_any(text_lower, GREETING_WORDS) and len(text_lower.split()) <= 8:
        return {
            "intent": "onboarding",
            "service": None,
            "outcome": "onboarding",
            "messages": messages,
            "handoff_mode": "none",
            "handoff_reason": None,
            "handoff_already_notified": False,
        }

    # Scoring por keywords
    SCORE_MAP: dict[tuple[str, int], str] = {
        ("quanto custa instalar", 8): "instalacao",
        ("quanto fica pra instalar", 8): "instalacao",
        ("quanto sai instalar", 8): "instalacao",
        ("custa instalar", 7): "instalacao",
        ("preço pra instalar", 7): "instalacao",
        ("preço de instalação", 7): "instalacao",
        ("vocês instalam", 6): "instalacao",
        ("colocar ar", 5): "instalacao",
        ("por ar", 5): "instalacao",
        ("splits novos", 5): "instalacao",
        ("split novo", 5): "instalacao",
        ("pra por", 4): "instalacao",
        ("instalação de", 3): "instalacao",
        ("instalar", 1): "instalacao",
        ("instalação", 1): "instalacao",
        ("split", 2): "instalacao",
        ("equipamento que eu já comprei", 5): "instalacao",
        ("não esquenta", 5): "manutencao",
        ("não aquece", 5): "manutencao",
        ("não gela", 6): "manutencao",
        ("nao gela", 6): "manutencao",
        ("não está gelando", 6): "manutencao",
        ("não tá gelando", 6): "manutencao",
        ("nao ta gelando", 6): "manutencao",
        ("parou de gelar", 6): "manutencao",
        ("barulho de vibração", 5): "manutencao",
        ("barulho", 3): "manutencao",
        ("vazamento", 4): "manutencao",
        ("pingando", 5): "manutencao",
        ("pingar", 5): "manutencao",
        ("pingou", 5): "manutencao",
        ("comecou a pingar", 6): "manutencao",
        ("pinga agua", 5): "manutencao",
        ("vazando agua", 5): "manutencao",
        ("não liga", 4): "manutencao",
        ("queimou", 3): "manutencao",
        ("deu ruim no ar", 3): "manutencao",
        ("corretiva", 3): "manutencao",
        ("gela demais", 3): "manutencao",
        ("manutenção", 1): "manutencao",
        ("consertar", 1): "manutencao",
        ("defeito", 1): "manutencao",
        ("pmoc", 5): "pmoc",
        ("laudo pmoc", 5): "pmoc",
        ("art", 5): "pmoc",
        ("certificado dos aparelhos", 5): "pmoc",
        ("certificado", 3): "pmoc",
        ("contrato de manutencao", 4): "pmoc",
        ("programa preventivo", 5): "pmoc",
        ("preventivo trimestral", 5): "pmoc",
        ("manutencao trimestral", 4): "pmoc",
        ("manutenção preventiva", 2): "pmoc",
        ("alvará do bombeiros", 4): "pmoc",
        ("higienização", 5): "higienizacao",
        ("higienizacao", 5): "higienizacao",
        ("ozônio", 4): "higienizacao",
        ("ácaros", 4): "higienizacao",
        ("fungos", 3): "higienizacao",
        ("sanitização", 3): "higienizacao",
        ("faz limpeza", 6): "higienizacao",
        ("limpeza de split", 6): "higienizacao",
        ("limpeza do ar", 4): "higienizacao",
        ("limpeza", 4): "higienizacao",
        ("limpar", 2): "higienizacao",
        ("mofo", 3): "higienizacao",
        ("cheiro", 1): "higienizacao",
        ("projeto de climatização", 4): "consultoria",
        ("projeto de ar", 4): "consultoria",
        ("split ou cassete", 6): "consultoria",
        ("ajuda pra escolher", 5): "consultoria",
        ("escolher o equipamento", 5): "consultoria",
        ("dimensionar ar", 5): "consultoria",
        ("dimensionar", 4): "consultoria",
        ("consultoria", 3): "consultoria",
        ("assessoria", 3): "consultoria",
        ("btu", 3): "consultoria",
        ("dimensionamento", 3): "consultoria",
        ("obra nova", 4): "consultoria",
        ("eficiência energética", 4): "consultoria",
        ("eficiencia energetica", 4): "consultoria",
        ("o que é melhor", 3): "consultoria",
        ("qual capacidade", 3): "consultoria",
        ("melhor para", 2): "consultoria",
        ("projeto central", 5): "projeto-central",
        ("central de climatização", 6): "projeto-central",
        ("multi split", 4): "projeto-central",
        ("multisplit", 4): "projeto-central",
        ("cassete", 2): "projeto-central",
        ("galpão", 3): "projeto-central",
        ("restaurante", 3): "projeto-central",
        ("para climatização", 2): "projeto-central",
        ("sistema central", 5): "projeto-central",
        ("controle individual", 4): "projeto-central",
        ("carga térmica", 4): "projeto-central",
        ("carga termica", 4): "projeto-central",
        ("6 ambientes", 4): "projeto-central",
        ("vários ambientes", 4): "projeto-central",
    }

    scores: dict[str, int] = {}
    for (keyword, weight), svc in SCORE_MAP.items():
        if _keyword_in_text(keyword, semantic_text):
            scores[svc] = scores.get(svc, 0) + weight

    intent = max(scores, key=lambda k: scores[k]) if scores else None
    sorted_scores = sorted(scores.values(), reverse=True) if scores else []
    top_score = sorted_scores[0] if sorted_scores else 0
    runner_up = sorted_scores[1] if len(sorted_scores) > 1 else 0

    # LLM override: consulta o classificador local para zero-score ou ambiguidade.
    try:
        prompt = (
            f"Classifique a mensagem do cliente entre: "
            f"instalacao, consultoria, manutencao, pmoc, projeto-central, higienizacao, unknown, explicit_handoff, sensitive_complaint\n"
            f"'instalacao' = instalar aparelho novo\n"
            f"'manutencao' = consertar/reparar aparelho existente\n"
            f"'pmoc' = plano preventivo obrigatório/laudo técnico\n"
            f"'consultoria' = dúvida técnica, assessoria, qual equipamento escolher, projeto de obra\n"
            f"'projeto-central' = sistema central, multisplit, vários ambientes, carga térmica\n"
            f"'higienizacao' = limpeza, higienização, cheiro, ácaros\n"
            f"'explicit_handoff' = cliente pede claramente humano/atendente/pessoa real\n"
            f"'sensitive_complaint' = cancelamento, reembolso, ameaça pública/legal ou reclamação forte de falta de retorno\n"
            f"'unknown' = mensagem vaga, gíria, áudio ruim, fora de domínio ou intenção incerta. Nunca use handoff para dúvida incerta.\n"
            f"Use português brasileiro real: considere histórico, elipse e contexto. Em HVAC, 'ar' geralmente significa ar-condicionado.\n"
            f"Histórico recente do lead: \"{' | '.join(recent_human[-3:])}\"\n"
            f"Mensagem: \"{user_text}\"\n"
            f"Responda apenas o nome da categoria, sem explicação."
        )
        resp = await _call_local_qwen([{"role": "user", "content": prompt}])
        intent_llm = resp.strip().lower().replace(" ", "-")
        if intent_llm == "hygienizacao":
            intent_llm = "higienizacao"
        if intent_llm in ("human", "handoff"):
            intent_llm = "explicit_handoff"
        if intent_llm in ("duvida", "dúvida", "fora-de-dominio", "fora-do-dominio"):
            intent_llm = "unknown"
        VALID = _SERVICE_INTENTS | {"unknown", "explicit_handoff", "sensitive_complaint"}
        if intent_llm in VALID:
            if not scores:
                # Sem keyword match — confia no LLM
                intent = intent_llm
            else:
                strong_keyword = top_score >= 3 and (runner_up == 0 or top_score > runner_up * 2)
                if not strong_keyword:
                    intent = intent_llm
    except Exception as e:
        logger.warning(f"LLM classify falhou, mantendo keyword: {e}")

    if _looks_like_pmoc_preventive_plan(semantic_text):
        intent = "pmoc"

    # Se intent ainda None (sem keywords e LLM falhou) → recuperação conversacional, não handoff.
    if intent is None:
        intent = _fallback_service_for_high_value(semantic_text) or "unknown"

    intent = _normalize_service(intent)
    if intent in ("explicit_handoff", "sensitive_complaint"):
        return {
            "intent": intent,
            "service": None,
            "outcome": "escalar_humano",
            "messages": messages,
            "handoff_mode": "hard_transfer",
            "handoff_reason": intent,
            "handoff_already_notified": False,
        }

    service = intent if intent in _SERVICE_INTENTS else None
    outcome = _OUTCOME_MAP.get(intent, "duvida")
    handoff_mode = "none"
    handoff_reason = None

    high_value_reason = _detect_high_value_reason(semantic_text, intent)
    if high_value_reason:
        handoff_mode = "soft_alert"
        handoff_reason = high_value_reason
    elif _contains_any(text_lower, _LIGHT_COMPLAINT_TRIGGERS):
        handoff_mode = "soft_alert"
        handoff_reason = "light_complaint"
        if intent == "unknown":
            outcome = "duvida"

    return {
        "intent": intent,
        "service": service,
        "outcome": outcome,
        "messages": messages,
        "handoff_mode": handoff_mode,
        "handoff_reason": handoff_reason,
        "handoff_already_notified": False,
    }


async def retrieve_knowledge(state: dict[str, Any]) -> dict[str, Any]:
    """Busca contexto técnico e comercial no Qdrant com FastEmbed."""
    messages = state.get("messages", [])
    service = _normalize_service(state.get("service"))

    if not messages:
        return {"rag_context": [], "messages": messages}

    last_message = messages[-1]
    user_text = _message_text(last_message)
    recent_human = [
        _message_text(m) for m in messages[-6:]
        if _is_human_message(m) and _message_text(m)
    ]
    query = f"servico={service or 'geral'} lead={' | '.join(recent_human[-3:])}"

    try:
        rag_context = await asyncio.wait_for(
            asyncio.to_thread(qdrant_search, query, service, 5),
            timeout=_RAG_TIMEOUT_SECONDS,
        )
        if len(rag_context) < 3:
            # Complementa com conhecimento geral de vendas, preço e políticas.
            seen = {ctx["id"] for ctx in rag_context}
            general_context = await asyncio.wait_for(
                asyncio.to_thread(qdrant_search, user_text, None, 5),
                timeout=_RAG_TIMEOUT_SECONDS,
            )
            for ctx in general_context:
                if ctx["id"] not in seen:
                    rag_context.append(ctx)
                    seen.add(ctx["id"])
                if len(rag_context) >= 5:
                    break
    except asyncio.TimeoutError:
        logger.warning("Qdrant search excedeu timeout de %.1fs", _RAG_TIMEOUT_SECONDS)
        rag_context = []
    except Exception as e:
        logger.warning(f"Qdrant search falhou: {e}")
        rag_context = []

    return {"rag_context": rag_context, "service": service, "messages": messages}


async def generate_response(state: dict[str, Any]) -> dict[str, Any]:
    """Gera resposta na voz do Will usando RAG + MiniMax (Groq fallback)."""
    messages = state.get("messages", [])
    rag_context = state.get("rag_context", [])
    service = _normalize_service(state.get("service"))
    intent = _normalize_service(state.get("intent"))
    outcome = state.get("outcome", "duvida")
    handoff_mode = state.get("handoff_mode", "none")
    handoff_reason = state.get("handoff_reason")

    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    user_text = _message_text(last_message)
    active_service = (state.get("customer_data") or {}).get("active_service")
    if isinstance(active_service, dict) and active_service.get("status"):
        ai_message = AIMessage(content=_active_service_response(user_text, active_service))
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service or _normalize_service(active_service.get("service")),
            "outcome": "acompanhamento_servico",
            "handoff_mode": "soft_alert",
            "handoff_reason": "active_service_followup",
        }

    if handoff_reason == "light_complaint":
        ai_message = AIMessage(content=_light_complaint_response(user_text))
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service,
            "outcome": outcome,
        }

    if intent == "unknown":
        ai_message = AIMessage(content=_unknown_recovery_response(user_text))
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service,
            "outcome": outcome,
        }

    human_count = sum(1 for m in messages if _is_human_message(m))
    cache_key = _sales_cache_key(service, user_text)
    if human_count <= 2:
        try:
            cached = await redis_get(cache_key)
            if cached:
                logger.info(f"Resposta validada via Redis cache: {cache_key}")
                ai_message = AIMessage(content=cached)
                return {
                    "messages": messages + [ai_message],
                    "rag_context": rag_context,
                    "service": service,
                    "outcome": outcome,
                }
        except Exception as e:
            logger.warning(f"Redis sales cache falhou: {e}")

    direct_response = _direct_price_response(service, user_text)
    if direct_response:
        direct_response = await _polish_ptbr_if_enabled(direct_response, user_text)
        ai_message = AIMessage(content=direct_response)
        return {
            "messages": messages + [ai_message],
            "rag_context": rag_context,
            "service": service,
            "outcome": outcome,
        }

    context_parts = []
    for ctx in rag_context:
        payload = ctx.get("payload", {})
        text = payload.get("text")
        if not text:
            continue
        doc_type = payload.get("doc_type", "technical")
        title = payload.get("title", "contexto")
        context_parts.append(f"[{doc_type} | {title}]\n{text}")
    context_str = "\n---\n".join(context_parts) or ""
    if _contains_any(_normalize_text(user_text), _SCHEDULING_TERMS):
        try:
            from agent_graph.services.calendar import get_availability_summary

            availability = await get_availability_summary()
        except Exception:
            availability = ""
        if availability:
            context_str = "\n---\n".join(
                part for part in (context_str, f"[agenda | disponibilidade]\n{availability}") if part
            )

    # CTA por outcome — guia o Will a conduzir o lead pro próximo passo certo
    outcome_cta = {
        "onboarding":              "Se o cliente ainda não disse o que deseja, cumprimente-o educadamente e pergunte qual serviço precisa. Se ele já disse, NUNCA pergunte 'como posso ajudar' ou 'qual serviço precisa'; continue o fluxo específico daquele serviço.",
        "analise_tecnica":         "Finalize oferecendo análise técnica no local por R$50, abatida se aprovar o orçamento, e peça cidade/bairro, modelo e foto do equipamento.",
        "higienizacao_preventiva": "Se for split, cite R$200 por aparelho e peça quantidade/cidade. Se não for split, conduza para análise técnica de R$50 abatível.",
        "reuniao_projeto":         "Finalize pedindo planta, metragem e quantidade de ambientes, e proponha análise/reunião técnica de R$50 abatível quando houver visita ao local.",
        "duvida":                  "Responda a dúvida tecnicamente, mas de forma simples, e pergunte se precisa de mais alguma ajuda.",
        "escalar_humano":          "Informe com empatia que um especialista da equipe (ou você mesmo em breve) vai assumir o atendimento.",
    }.get(outcome, "Avance a conversa fazendo uma pergunta técnica simples para qualificar o problema do cliente.")

    if handoff_mode == "soft_alert":
        outcome_cta = (
            "Caso de alto valor ou risco comercial: responda normalmente, sem dizer que vai passar para humano. "
            "Peça dados de qualificação como cidade/bairro, quantidade de aparelhos, tipo de estabelecimento e urgência."
        )

    # ── Monta multi-turn com histórico de conversa ────────────────────────────
    # system + histórico alternado (user/assistant) + última mensagem com contexto RAG
    llm_messages: list[ChatMessage] = [
        {"role": "system", "content": WILL_SYSTEM_PROMPT},
    ]

    # Adiciona histórico (todas as mensagens exceto a última — que vira user_prompt abaixo)
    for msg in messages[:-1]:
        if _is_human_message(msg):
            llm_messages.append({"role": "user", "content": _message_text(msg)})
        elif _is_ai_message(msg):
            llm_messages.append({"role": "assistant", "content": _message_text(msg)})

    lead_state = state.get("lead_state") or {}
    do_not_ask = state.get("do_not_ask") or []
    missing_fields = state.get("missing_fields") or []
    already_asked_fields = state.get("already_asked_fields") or []

    # Última mensagem do lead enriquecida com contexto RAG e CTA
    user_prompt = (
        f"==========================================================\n"
        f"[INÍCIO DO CONTEXTO RECUPERADO DA REFRIMIX - USE APENAS ISSO COMO BASE TÉCNICA E COMERCIAL]\n"
        f"{context_str or 'Nenhum contexto recuperado. Você NÃO DEVE inventar preços ou informações técnicas. Peça mais detalhes ao cliente.'}\n"
        f"[FIM DO CONTEXTO RECUPERADO]\n"
        f"==========================================================\n\n"
        f"ESTADO DO ONBOARDING DO LEAD:\n"
        f"- Estado estruturado atual: {json.dumps(lead_state, ensure_ascii=False)}\n"
        f"- Informações já fornecidas (PROIBIDO PERGUNTAR): {do_not_ask}\n"
        f"- Próximas informações em falta que você deve obter: {missing_fields}\n\n"
        f"Objetivo do Atendimento: Resolver a dúvida e avançar na qualificação do lead.\n"
        f"Serviço identificado: {service or 'não classificado'}\n"
        f"Modo de handoff: {handoff_mode}; motivo: {handoff_reason or 'nenhum'}.\n"
        f"Meta para esta mensagem específica: {outcome_cta}\n\n"
        f"MENSAGEM ATUAL DO CLIENTE:\n"
        f"\"{user_text}\"\n\n"
        f"CONTRATO DE GERAÇÃO DA RESPOSTA (OBRIGATÓRIO):\n"
        f"1. Responda de forma profissional e direta, em no máximo 4 frases.\n"
        f"2. ATENÇÃO MÁXIMA: Se o cliente perguntar preço/prazo/detalhe que NÃO está explícito no bloco de contexto acima, VOCÊ NÃO PODE INVENTAR. Responda elegantemente que precisa calcular ou avaliar os detalhes.\n"
        f"3. Faça no máximo UMA pergunta ao final para obter o PRÓXIMO campo da lista de informações em falta ({missing_fields}).\n"
        f"4. NUNCA faça perguntas ou peça dados sobre informações que já foram fornecidas ({do_not_ask}).\n"
        f"5. Não ofereça handoff humano, especialista ou atendimento manual quando o modo de handoff for 'none' ou 'soft_alert'.\n"
        f"6. Nunca diga visita gratuita. Fora os dois preços fixos, conduza para análise técnica de R$50 abatível no orçamento aprovado."
    )
    llm_messages.append({"role": "user", "content": user_prompt})

    try:
        response = await llm_chat(llm_messages, max_retries=2)
    except Exception as e:
        logger.warning(f"LLM falhou em generate_response: {e}")
        response = {
            "analise_tecnica": (
                "Pode deixar que a gente resolve! "
                "A análise técnica no local custa R$50 e abate se você aprovar o orçamento. Me manda a cidade e o modelo do aparelho?"
            ),
            "higienizacao_preventiva": (
                "Ótimo! A higienização é fundamental pra qualidade do ar. "
                "Me fala quantos aparelhos são e o endereço que eu já calculo o orçamento."
            ),
            "reuniao_projeto": (
                "Pra esse tipo de projeto, melhor a gente sentar e conversar com a planta em mãos. "
                "Me manda planta, metragem e quantidade de ambientes para eu ver agenda e adiantar a análise?"
            ),
        }.get(outcome or "", "Me manda mais detalhes que eu te ajudo!")

    # ── Guardrail Conversacional Anti-Burrice (Anti-Repetição) ───────────────
    forbidden_mapping = {
        "tipo_servico": ["instala", "higieni", "manuten", "consert", "limp", "eletri"],
        "cidade_bairro": ["cidade", "bairro", "onde você", "seu endereço", "onde fica"],
        "btus": ["btu", "potencia", "capacidade"],
        "marca": ["marca", "fabricante"],
        "modelo_aparelho": ["modelo", "aparelho", "equipamento"],
        "aparelho_ja_comprado": ["já comprou", "já tem o ar", "adquiriu"],
        "foto_aparelho": ["foto do aparelho", "foto da evaporadora", "imagem do ar"],
        "foto_local_interno": ["foto de dentro", "foto do local interno", "imagem interna"],
        "foto_local_externo": ["foto de fora", "foto do local externo", "imagem externa"],
        "foto_disjuntor": ["foto do disjuntor", "foto do quadro"],
        "ponto_eletrico_exclusivo": ["ponto elétrico", "ponto de energia", "220v"],
        "distancia_aproximada": ["distancia", "metros", "tubulação"],
        "tubulacao_existente": ["infraestrutura", "tubulação pronta", "infra pronta"],
        "tempo_sem_manutencao": ["tempo sem", "última manutenção", "quanto tempo"],
        "cheiro_ruim": ["cheiro", "odor"],
        "pinga_agua": ["pingando", "vazando água", "pinga"],
        "rinite_alergia": ["rinite", "alergia"],
    }

    detected_violations = []
    response_lower = response.lower()
    for field in do_not_ask:
        keywords = forbidden_mapping.get(field, [])
        if "?" in response_lower:
            for kw in keywords:
                if kw in response_lower:
                    detected_violations.append(field)
                    break
                    
    if detected_violations:
        logger.warning(
            "Guardrail conversacional detectou perguntas repetitivas proibidas: %s. Resposta original: %r",
            detected_violations,
            response
        )
        correct_prompt = (
            "Você é o Will da Refrimix. Corrija a resposta abaixo removendo qualquer pergunta ou pedido "
            "sobre informações que o cliente já nos forneceu e que estão marcadas como proibidas.\n\n"
            f"Campos já fornecidos e PROIBIDOS de perguntar: {', '.join(detected_violations)}\n\n"
            f"Resposta original: \"{response}\"\n\n"
            "Escreva a nova versão da resposta de forma natural, educada e direta, sem fazer nenhuma pergunta sobre os campos proibidos. Retorne APENAS o texto da nova resposta:"
        )
        try:
            corrected = await llm_chat([
                {"role": "system", "content": WILL_SYSTEM_PROMPT},
                {"role": "user", "content": correct_prompt}
            ])
            corrected = corrected.strip()
            if corrected:
                logger.info("Resposta corrigida pelo Guardrail: %r", corrected)
                response = corrected
        except Exception as e:
            logger.warning("Falha ao rodar LLM corretivo no Guardrail: %s", e)

    response = await _polish_ptbr_if_enabled(response, user_text)
    ai_message = AIMessage(content=response)
    return {
        "messages": messages + [ai_message],
        "rag_context": rag_context,
        "service": service,
        "outcome": outcome,
        "lead_state": lead_state,
        "already_asked_fields": already_asked_fields,
        "missing_fields": missing_fields,
        "do_not_ask": do_not_ask,
    }


async def language_guard_check(state: dict[str, Any]) -> dict[str, Any]:
    """Valida e corrige resposta do LLM — garante pt-BR sem drift CJK/árabe."""
    messages = state.get("messages", [])
    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    ai_response = _message_text(last_message)
    rag_context = state.get("rag_context", [])
    service = state.get("service", "não classificado")
    outcome = state.get("outcome", "duvida")

    context_str = "\n".join(
        ctx["payload"].get("text", "")
        for ctx in rag_context
        if ctx.get("payload", {}).get("text")
    ) or "Sem contexto."

    user_text = next(
        (_message_text(m) for m in messages if _is_human_message(m)),
        "",
    )

    original_prompt = (
        f"Serviço: {service}\n"
        f"Contexto: {context_str}\n"
        f"Mensagem do lead: {user_text}\n"
        f"Responda em português brasileiro coloquial como o Will da Refrimix."
    )

    from agent_graph.guards.language_guard import LanguageGuard

    guard = LanguageGuard(expected_lang="pt-BR", majority_threshold=0.50, max_retries=2)

    async def retry_llm(prompt: str) -> str:
        return await llm_chat([
            {"role": "system", "content": WILL_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])

    try:
        fixed_response = await guard.validate_and_fix(
            ai_response,
            retry_llm,
            original_prompt,
            groq_repair_callable=groq_repair,
        )
    except Exception as e:
        logger.warning("LanguageGuard repair falhou; usando resposta original sanitizada: %s", e)
        from agent_graph.guards.language_guard import sanitize_hard

        fixed_response = sanitize_hard(ai_response) or (
            "Tive uma instabilidade técnica aqui. Me manda o endereço e os detalhes do aparelho "
            "que eu já te ajudo pelo WhatsApp."
        )

    return {"messages": messages[:-1] + [AIMessage(content=fixed_response)]}


async def format_whatsapp(state: dict[str, Any]) -> dict[str, Any]:
    """
    Formata resposta para WhatsApp: remove markdown pesado, quebra textos longos,
    e retorna o AIMessage atualizado nos messages.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"messages": messages}

    last_message = messages[-1]
    raw = _message_text(last_message)

    # Remove markdown que não renderiza bem no WhatsApp
    formatted = raw
    formatted = formatted.replace("**", "*")   # bold MD → WhatsApp bold
    formatted = formatted.replace("__", "_")    # italic
    if len(formatted) >= 2 and formatted[0] == formatted[-1] and formatted[0] in ("'", '"'):
        formatted = formatted[1:-1].strip()
    # Remove headers markdown
    import re
    formatted = re.sub(r"^#{1,6}\s+", "", formatted, flags=re.MULTILINE)
    # Normaliza múltiplas linhas em branco
    formatted = re.sub(r"\n{3,}", "\n\n", formatted)
    formatted = formatted.strip()
    formatted = _shape_whatsapp_response(formatted, state.get("outcome"))

    # Se muito longo (>1500 chars), trunca com gancho
    if len(formatted) > 1500:
        formatted = formatted[:1450].rsplit("\n", 1)[0] + (
            "\n\nPosso te passar mais detalhes. Qual a sua dúvida principal?"
        )

    return {"messages": messages[:-1] + [AIMessage(content=formatted)]}


async def save_interaction(state: dict[str, Any]) -> dict[str, Any]:
    """Persiste interação no PostgreSQL via Prisma."""
    messages = state.get("messages", [])
    intent = state.get("intent")
    service = state.get("service")
    outcome = state.get("outcome")
    customer_data = state.get("customer_data", {})
    phone = customer_data.get("phone", "unknown")

    user_message = next((_message_text(m) for m in messages if _is_human_message(m)), None)
    ai_message = next((_message_text(m) for m in reversed(messages) if _is_ai_message(m)), None)

    try:
        await prisma_save_interaction({
            "phone": phone,
            "user_message": user_message or "",
            "intent": intent,
            "service": service,
            "ai_message": ai_message or "",
            "is_human": state.get("is_human", False),
            "metadata": {
                "outcome": outcome,
                "handoff_mode": state.get("handoff_mode"),
                "handoff_reason": state.get("handoff_reason"),
                "active_service": customer_data.get("active_service"),
            },
        })
    except Exception as e:
        logger.error(f"Falha ao salvar interação: {e}")

    # ── Cria LeadEvent transacional para resposta da IA (Assistant) ───────────
    if phone and phone != "unknown" and ai_message:
        from prisma import Prisma
        db = Prisma()
        await db.connect()
        try:
            lead = await db.lead.find_unique(where={"phone": phone})
            if lead:
                await db.leadevent.create(
                    data={
                        "lead_id": lead.id,
                        "role": "assistant",
                        "message": ai_message,
                        "extracted_data": json.dumps({}),
                    }
                )
        except Exception as e:
            logger.warning("Falha ao salvar LeadEvent para assistant: %s", e)
        finally:
            await db.disconnect()

    return {"messages": messages}


async def route_human(state: dict[str, Any]) -> dict[str, Any]:
    """Hard handoff: responde uma vez e evita loop de passagem humana."""
    messages = state.get("messages", [])
    customer_data = state.get("customer_data", {})
    phone = customer_data.get("phone", "")
    reason = state.get("handoff_reason") or state.get("intent") or "explicit_handoff"
    already_notified = False

    if phone:
        key = _handoff_state_key(phone)
        try:
            existing = await redis_get(key)
            already_notified = bool(existing)
            if not already_notified:
                value = json.dumps({"reason": reason}, ensure_ascii=False)
                await redis_set(key, value, ex=_HANDOFF_STATE_TTL)
        except Exception as e:
            logger.warning("Redis handoff_state falhou para %s: %s", phone, e)

    content = _handoff_followup_response(reason) if already_notified else _handoff_initial_response(reason)
    handoff = AIMessage(content=content)
    return {
        "messages": messages + [handoff],
        "is_human": True,
        "handoff_mode": "hard_transfer",
        "handoff_reason": reason,
        "handoff_already_notified": already_notified,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa 3 — preprocess_input (STT + Vision)
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_LEAD_STATE = {
  "tipo_servico": None,
  "nome": None,
  "cidade_bairro": None,
  "tipo_imovel": None,
  "marca": None,
  "btus": None,
  "modelo_aparelho": None,
  "aparelho_ja_comprado": None,
  "fotos": {
    "aparelho": False,
    "local_interno": False,
    "local_externo": False,
    "disjuntor": False,
    "erro_display": False
  },
  "instalacao": {
    "local_evaporadora": None,
    "local_condensadora": None,
    "distancia_aproximada": None,
    "ponto_eletrico_exclusivo": None,
    "tubulacao_existente": None,
    "precisa_suporte": None,
    "precisa_dreno": None
  },
  "manutencao": {
    "tempo_sem_manutencao": None,
    "cheiro_ruim": None,
    "pinga_agua": None,
    "rinite_alergia": None
  },
  "conserto": {
    "liga": None,
    "gela": None,
    "codigo_erro": None,
    "condensadora_liga": None,
    "disjuntor_cai": None
  },
  "eletrica": {
    "disjuntor_cai": None,
    "fio_esquenta": None,
    "cheiro_queimado": None,
    "circuito_individual": None
  }
}

def compute_fields_status(lead_state: dict) -> tuple[list[str], list[str], list[str]]:
    """
    Computa do_not_ask, already_asked_fields e missing_fields com base no lead_state.
    Retorna (do_not_ask, already_asked_fields, missing_fields).
    """
    tipo_servico = lead_state.get("tipo_servico")
    
    # 1. Determina quais campos já foram preenchidos (flat list)
    filled_fields = []
    
    # Campos gerais
    for field in ["tipo_servico", "nome", "cidade_bairro", "tipo_imovel", "marca", "btus", "modelo_aparelho", "aparelho_ja_comprado"]:
        if lead_state.get(field) is not None:
            filled_fields.append(field)
            
    # Fotos
    fotos = lead_state.get("fotos", {})
    for f in ["aparelho", "local_interno", "local_externo", "disjuntor", "erro_display"]:
        if fotos.get(f):
            filled_fields.append(f"foto_{f}")
            
    # Instalação
    inst = lead_state.get("instalacao", {})
    for field in ["local_evaporadora", "local_condensadora", "distancia_aproximada", "ponto_eletrico_exclusivo", "tubulacao_existente", "precisa_suporte", "precisa_dreno"]:
        if inst.get(field) is not None:
            filled_fields.append(field)
            
    # Manutenção/Higienização
    manut = lead_state.get("manutencao", {})
    for field in ["tempo_sem_manutencao", "cheiro_ruim", "pinga_agua", "rinite_alergia"]:
        if field in manut and manut[field] is not None:
            filled_fields.append(field)
            
    # Conserto
    cons = lead_state.get("conserto", {})
    for field in ["liga", "gela", "codigo_erro", "condensadora_liga", "disjuntor_cai"]:
        if field in cons and cons[field] is not None:
            filled_fields.append(field)
            
    # Elétrica
    elet = lead_state.get("eletrica", {})
    for field in ["disjuntor_cai", "fio_esquenta", "cheiro_queimado", "circuito_individual"]:
        if field in elet and elet[field] is not None:
            filled_fields.append(field)
            
    # do_not_ask e already_asked_fields são basicamente os campos preenchidos
    do_not_ask = list(set(filled_fields))
    already_asked_fields = list(set(filled_fields))
    
    # 2. Computa missing_fields de acordo com o tipo_servico
    missing_fields = []
    
    if not tipo_servico:
        # Se não tem tipo_servico, os campos básicos em falta são tipo_servico e cidade_bairro
        if "tipo_servico" not in do_not_ask:
            missing_fields.append("tipo_servico")
        if "cidade_bairro" not in do_not_ask:
            missing_fields.append("cidade_bairro")
    elif tipo_servico == "instalacao":
        reqs = ["cidade_bairro", "btus", "foto_local_interno", "foto_local_externo", "ponto_eletrico_exclusivo", "distancia_aproximada", "tubulacao_existente"]
        for r in reqs:
            if r not in do_not_ask:
                missing_fields.append(r)
    elif tipo_servico in ["manutencao", "higienizacao"]:
        reqs = ["cidade_bairro", "tempo_sem_manutencao", "cheiro_ruim", "pinga_agua", "rinite_alergia", "foto_aparelho"]
        for r in reqs:
            if r not in do_not_ask:
                missing_fields.append(r)
    elif tipo_servico == "conserto":
        reqs = ["cidade_bairro", "liga", "gela", "codigo_erro", "foto_aparelho"]
        for r in reqs:
            if r not in do_not_ask:
                missing_fields.append(r)
    elif tipo_servico == "eletrica":
        reqs = ["cidade_bairro", "disjuntor_cai", "fio_esquenta", "cheiro_queimado", "foto_disjuntor"]
        for r in reqs:
            if r not in do_not_ask:
                missing_fields.append(r)
                
    return do_not_ask, already_asked_fields, missing_fields

async def preprocess_input(state: dict[str, Any]) -> dict[str, Any]:
    """
    Pré-processa input multimodal antes de classify_service:
    - audioMessage → transcreve com Groq Whisper → substitui texto
    - imageMessage → analisa com Vision LLM → prepend descrição ao texto
    - conversation → passa direto
    - Inicializa/carrega o lead_state estruturado e campos associados a partir do Postgres 17.
    """
    message_type = state.get("message_type", "conversation")
    media_url = state.get("media_url", "")
    media_base64 = state.get("media_base64", "")
    msg_id = state.get("msg_id", "")
    instance = state.get("instance", "")
    messages = state.get("messages", [])

    # ── 1. Inicializa o estado com os dados do banco ────────────────────────
    customer_data = state.get("customer_data", {})
    phone = customer_data.get("phone", "unknown")
    
    lead_state = None
    already_asked_fields = []
    missing_fields = []
    do_not_ask = []
    conversation_summary = ""
    
    if phone and phone != "unknown":
        from prisma import Prisma
        import json
        db = Prisma()
        await db.connect()
        try:
            lead = await db.lead.find_unique(where={"phone": phone})
            if not lead:
                # Cria novo lead no Postgres com estado inicial padrão
                lead = await db.lead.create(
                    data={
                        "phone": phone,
                        "name": customer_data.get("name"),
                        "lead_state": json.dumps(DEFAULT_LEAD_STATE),
                        "already_asked_fields": json.dumps([]),
                        "missing_fields": json.dumps(["tipo_servico", "cidade_bairro"]),
                        "do_not_ask": json.dumps([]),
                    }
                )
            
            # Carrega campos do Postgres 17
            lead_state = json.loads(lead.lead_state) if isinstance(lead.lead_state, str) else (lead.lead_state or DEFAULT_LEAD_STATE)
            if not lead_state:
                lead_state = DEFAULT_LEAD_STATE
                
            already_asked_fields = json.loads(lead.already_asked_fields) if isinstance(lead.already_asked_fields, str) else (lead.already_asked_fields or [])
            missing_fields = json.loads(lead.missing_fields) if isinstance(lead.missing_fields, str) else (lead.missing_fields or ["tipo_servico", "cidade_bairro"])
            do_not_ask = json.loads(lead.do_not_ask) if isinstance(lead.do_not_ask, str) else (lead.do_not_ask or [])
            conversation_summary = lead.conversation_summary or ""
        except Exception as e:
            logger.warning("Falha ao carregar Lead do Postgres em preprocess_input: %s", e)
            lead_state = DEFAULT_LEAD_STATE
            missing_fields = ["tipo_servico", "cidade_bairro"]
        finally:
            await db.disconnect()
    else:
        lead_state = DEFAULT_LEAD_STATE
        missing_fields = ["tipo_servico", "cidade_bairro"]

    # ── 2. Processa mídia multimodal ────────────────────────────────────────
    if message_type == "audioMessage" and (media_url or media_base64 or msg_id):
        try:
            from agent_graph.services.stt import transcribe_audio
            transcript = await transcribe_audio(media_url, instance or None, msg_id, media_base64)
            logger.info(f"STT transcript: {transcript[:80]!r}")
            # Substitui última HumanMessage pelo texto transcrito
            new_messages = list(messages)
            if new_messages and _is_human_message(new_messages[-1]):
                new_messages[-1] = HumanMessage(content=transcript)
            else:
                new_messages.append(HumanMessage(content=transcript))
            return {
                "messages": new_messages,
                "message_type": message_type,
                "lead_state": lead_state,
                "already_asked_fields": already_asked_fields,
                "missing_fields": missing_fields,
                "do_not_ask": do_not_ask,
                "conversation_summary": conversation_summary,
            }
        except Exception as e:
            logger.error(f"STT falhou: {e}")

    elif message_type == "imageMessage" and (media_url or media_base64 or msg_id):
        try:
            from agent_graph.services.vision import analyze_image
            caption = ""
            if messages and _is_human_message(messages[-1]):
                caption = _message_text(messages[-1]) or ""
            description = await analyze_image(media_url, caption, instance or None, msg_id, media_base64)
            logger.info(f"Vision description: {description[:80]!r}")
            combined = f"[Imagem: {description}]"
            if caption:
                combined = f"[Imagem: {description}]\n{caption}"
            new_messages = list(messages)
            if new_messages and _is_human_message(new_messages[-1]):
                new_messages[-1] = HumanMessage(content=combined)
            else:
                new_messages.append(HumanMessage(content=combined))
            return {
                "messages": new_messages,
                "message_type": message_type,
                "lead_state": lead_state,
                "already_asked_fields": already_asked_fields,
                "missing_fields": missing_fields,
                "do_not_ask": do_not_ask,
                "conversation_summary": conversation_summary,
            }
        except Exception as e:
            logger.error(f"Vision falhou: {e}")

    return {
        "messages": messages,
        "message_type": message_type,
        "lead_state": lead_state,
        "already_asked_fields": already_asked_fields,
        "missing_fields": missing_fields,
        "do_not_ask": do_not_ask,
        "conversation_summary": conversation_summary,
    }

async def extract_lead_data(state: dict[str, Any]) -> dict[str, Any]:
    """
    Nó Extrator (Extractor LLM):
    - Lê a última mensagem do cliente e o histórico.
    - Chama o LLM (Qwen local) para extrair novos dados estruturados e obter um patch JSON.
    - Mescla o patch ao lead_state no Postgres.
    - Registra a mensagem do usuário como LeadEvent.
    """
    from datetime import datetime
    
    messages = state.get("messages", [])
    if not messages:
        return {}

    customer_data = state.get("customer_data", {})
    phone = customer_data.get("phone", "unknown")
    
    lead_state = state.get("lead_state") or dict(DEFAULT_LEAD_STATE)
    last_message = messages[-1]
    user_text = _message_text(last_message)
    
    prompt = (
        "Você é um extrator de dados para atendimento comercial de ar-condicionado no Brasil.\n\n"
        "Leia o histórico da conversa e a nova mensagem do cliente abaixo.\n"
        "Atualize APENAS os dados que o cliente informou claramente na última mensagem ou no histórico recente.\n"
        "Não invente nenhuma informação. Não tente adivinhar. Não apague dados existentes. Nunca marque um campo como null/None se ele já estava preenchido.\n\n"
        f"ESTADO ATUAL DO LEAD (JSON):\n{json.dumps(lead_state, ensure_ascii=False, indent=2)}\n\n"
        f"NOVA MENSAGEM DO CLIENTE:\n\"{user_text}\"\n\n"
        "Retorne APENAS um JSON válido no seguinte formato exato, sem explicações:\n"
        "{\n"
        "  \"state_patch\": {\n"
        "     // altere apenas os campos que o cliente informou claramente na nova mensagem ou no histórico\n"
        "     // Exemplos de campos válidos no primeiro nível:\n"
        "     // \"tipo_servico\" (valores: \"instalacao\", \"manutencao\", \"higienizacao\", \"conserto\", \"eletrica\", \"projeto\"), \"nome\", \"cidade_bairro\", \"marca\", \"btus\"\n"
        "  },\n"
        "  \"detected_service_type\": null // string com o tipo de serviço detectado ou null\n"
        "}"
    )
    
    state_patch = {}
    detected_service_type = None
    
    try:
        resp = await _call_local_qwen([{"role": "user", "content": prompt}])
        clean_resp = resp.strip()
        if "```json" in clean_resp:
            clean_resp = clean_resp.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_resp:
            clean_resp = clean_resp.split("```")[1].strip()
            
        data = json.loads(clean_resp)
        state_patch = data.get("state_patch") or {}
        detected_service_type = data.get("detected_service_type")
    except Exception as e:
        logger.warning("Falha ao rodar LLM Extractor em extract_lead_data: %s", e)
        
    if state_patch:
        for k, v in state_patch.items():
            if v is not None:
                if k in lead_state and isinstance(lead_state[k], dict) and isinstance(v, dict):
                    lead_state[k].update(v)
                else:
                    lead_state[k] = v
                    
    if detected_service_type and not lead_state.get("tipo_servico"):
        lead_state["tipo_servico"] = detected_service_type
        
    do_not_ask, already_asked_fields, missing_fields = compute_fields_status(lead_state)
    
    if phone and phone != "unknown":
        from prisma import Prisma
        db = Prisma()
        await db.connect()
        try:
            lead = await db.lead.find_unique(where={"phone": phone})
            if lead:
                await db.lead.update(
                    where={"phone": phone},
                    data={
                        "lead_state": json.dumps(lead_state),
                        "already_asked_fields": json.dumps(already_asked_fields),
                        "missing_fields": json.dumps(missing_fields),
                        "do_not_ask": json.dumps(do_not_ask),
                        "service_type": lead_state.get("tipo_servico"),
                        "city_bairro": lead_state.get("cidade_bairro"),
                        "last_user_message_at": datetime.now(),
                    }
                )
                
                await db.leadevent.create(
                    data={
                        "lead_id": lead.id,
                        "role": "user",
                        "message": user_text,
                        "extracted_data": json.dumps(state_patch),
                    }
                )
        except Exception as e:
            logger.warning("Falha ao salvar dados de extração no Postgres: %s", e)
        finally:
            await db.disconnect()
            
    return {
        "lead_state": lead_state,
        "already_asked_fields": already_asked_fields,
        "missing_fields": missing_fields,
        "do_not_ask": do_not_ask,
        "service": lead_state.get("tipo_servico") or state.get("service"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa 5 — decide_response_modality + tts_voice_clone
# ──────────────────────────────────────────────────────────────────────────────

async def decide_response_modality(state: dict[str, Any]) -> dict[str, Any]:
    """
    Decide se a resposta vai em áudio ou texto, com base em:
    - Tipo da mensagem inbound (espelha áudio)
    - Intent (pmoc/consultoria → sempre texto)
    - Conteúdo (saudações → áudio)
    """
    from agent_graph.services.tts import should_respond_with_audio

    message_type = state.get("message_type", "conversation")
    intent = state.get("intent")
    outcome = state.get("outcome")
    messages = state.get("messages", [])

    user_text = next(
        (_message_text(m) for m in messages if _is_human_message(m)),
        "",
    )

    use_audio = should_respond_with_audio(message_type, intent, outcome, user_text)
    modality = "audio" if use_audio else "text"
    logger.info(f"Response modality: {modality} (message_type={message_type}, intent={intent})")

    return {"response_modality": modality}


async def tts_voice_clone(state: dict[str, Any]) -> dict[str, Any]:
    """
    Se modality == 'audio', sintetiza resposta com Coqui XTTS (voz do Will).
    Armazena audio_bytes no state para o worker enviar via Evolution API.
    """
    if state.get("response_modality") != "audio":
        return {}

    from agent_graph.services.tts import synthesize, choose_voice_style

    messages = state.get("messages", [])
    intent = state.get("intent")
    outcome = state.get("outcome")

    ai_text = next(
        (_message_text(m) for m in reversed(messages) if _is_ai_message(m)),
        "",
    )

    if not ai_text:
        return {"response_modality": "text"}

    voice_style = choose_voice_style(intent, outcome)
    try:
        audio_bytes = await synthesize(ai_text, voice_style)
        if audio_bytes:
            logger.info(f"TTS OK: {len(audio_bytes)} bytes (style={voice_style})")
            return {"audio_bytes": audio_bytes}
        # XTTS indisponível — degrada para texto silenciosamente
        logger.warning("XTTS indisponível, degradando para texto")
        return {"response_modality": "text"}
    except Exception as e:
        logger.error(f"TTS falhou: {e}")
        return {"response_modality": "text"}


# ──────────────────────────────────────────────────────────────────────────────
# Tarefa 6 — dispatch_appointment_alert
# ──────────────────────────────────────────────────────────────────────────────

# Keywords que indicam intenção de agendar (extraídos da fala do lead)
_ADDRESS_PATTERNS: tuple[str, ...] = (
    "rua ", "av ", "avenida ", "bairro ", "cep ", "praia grande",
    "santos", "são vicente", "guarujá", "cubatão", "mongaguá",
    "itanhaém", "peruíbe",
)

_WINDOW_PATTERNS: tuple[str, ...] = (
    "manhã", "tarde", "noite", "segunda", "terça", "quarta",
    "quinta", "sexta", "sábado", "domingo", "amanhã", "hoje",
    "próxima semana", "semana que vem",
)


def _extract_appointment_data(messages: list, customer_data: dict, service: str | None) -> dict | None:
    """
    Extrai dados de agendamento das mensagens do lead.
    Retorna dict com {address, window} se detectar, ou None.
    """
    full_text = " ".join(
        _message_text(m).lower() for m in messages if _is_human_message(m) and _message_text(m)
    )

    address = next((p for p in _ADDRESS_PATTERNS if p in full_text), None)
    window = next((p for p in _WINDOW_PATTERNS if p in full_text), None)

    # Só dispara alerta se tiver pelo menos endereço OU janela
    if not address and not window:
        return None

    return {
        "phone": customer_data.get("phone", ""),
        "name": customer_data.get("name"),
        "service": service,
        "address": address,
        "window": window,
    }


async def dispatch_appointment_alert(state: dict[str, Any]) -> dict[str, Any]:
    """
    Detecta intenção de agendamento nas mensagens e, se encontrar
    endereço ou janela de horário, envia alerta WhatsApp para o dono.
    """
    outcome = state.get("outcome", "")
    service = state.get("service")
    messages = state.get("messages", [])
    customer_data = state.get("customer_data", {})

    # Só verifica outcomes que levam a visita/reunião
    if outcome not in ("analise_tecnica", "higienizacao_preventiva", "reuniao_projeto"):
        return {}

    lead_data = _extract_appointment_data(messages, customer_data, service)
    if not lead_data:
        return {}

    from agent_graph.services.alerts import send_appointment_alert, prisma_upsert_lead

    try:
        await prisma_upsert_lead(lead_data)
    except Exception as e:
        logger.error(f"Lead upsert falhou: {e}")

    try:
        await send_appointment_alert(lead_data)
    except Exception as e:
        logger.error(f"Alert dispatch falhou: {e}")

    return {}
