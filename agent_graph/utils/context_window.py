from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Final

ChatMessage = dict[str, str]

LOCAL_REFRIMIX_SYSTEM_PROMPT: Final[str] = """Você é o Will, proprietário técnico da Refrimix Tecnologia, Guarujá/SP.
Responda sempre em português brasileiro natural de WhatsApp, com educação, segurança técnica e frases curtas.
Não invente preços, prazos, garantias ou procedimentos. Use apenas o contexto Refrimix recebido na mensagem.
Se faltar dado para preço ou diagnóstico, diga que precisa avaliar/calcular e peça uma informação objetiva.
Quando houver problema físico no ar condicionado, peça foto ou vídeo curto se isso ajudar na análise.
Conduza para o próximo passo: endereço, marca/modelo/BTUs, quantidade de aparelhos, visita técnica ou reunião.
Faça no máximo uma pergunta ao final e não repita perguntas já respondidas no histórico."""


@dataclass(frozen=True)
class ContextWindowResult:
    messages: list[ChatMessage]
    original_tokens: int
    trimmed_tokens: int
    dropped_messages: int
    compacted_system_prompt: bool


def estimate_tokens(text: str) -> int:
    """Cheap token estimate suitable for preflight context budgeting."""
    if not text:
        return 0
    # Portuguese WhatsApp text averages near 3-4 chars/token; add word pressure.
    char_estimate = ceil(len(text) / 3.6)
    word_estimate = ceil(len(text.split()) * 1.25)
    return max(1, char_estimate, word_estimate)


def message_tokens(message: ChatMessage) -> int:
    return estimate_tokens(message.get("content", "")) + 6


def count_message_tokens(messages: list[ChatMessage]) -> int:
    return sum(message_tokens(message) for message in messages)


def truncate_text_by_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text

    max_chars = max(80, int(max_tokens * 3.2))
    if len(text) <= max_chars:
        return text

    head_chars = max(40, int(max_chars * 0.42))
    tail_chars = max(40, max_chars - head_chars - 48)
    head = text[:head_chars].rstrip()
    tail = text[-tail_chars:].lstrip()
    return f"{head}\n\n[... contexto truncado por limite do modelo ...]\n\n{tail}"


def _normalize_message(message: ChatMessage) -> ChatMessage:
    role = message.get("role", "user")
    if role not in {"system", "user", "assistant", "tool"}:
        role = "user"
    return {"role": role, "content": str(message.get("content", ""))}


def fit_chat_messages(
    messages: list[ChatMessage],
    *,
    max_context_tokens: int,
    reserved_output_tokens: int,
    safety_margin_tokens: int = 160,
    compact_system_prompt: str = LOCAL_REFRIMIX_SYSTEM_PROMPT,
) -> ContextWindowResult:
    """Apply a sliding window that preserves system policy and the latest user turn."""
    normalized = [_normalize_message(message) for message in messages]
    original_tokens = count_message_tokens(normalized)

    if not normalized:
        return ContextWindowResult([], original_tokens, 0, 0, False)

    budget = max(256, max_context_tokens - reserved_output_tokens - safety_margin_tokens)
    system_message: ChatMessage | None = None
    rest = normalized
    compacted = False

    if normalized[0]["role"] == "system":
        system_message = normalized[0]
        rest = normalized[1:]

        system_budget = max(180, int(budget * 0.30))
        if message_tokens(system_message) > system_budget:
            system_message = {"role": "system", "content": compact_system_prompt}
            compacted = True

        if message_tokens(system_message) > system_budget:
            system_message = {
                "role": "system",
                "content": truncate_text_by_tokens(system_message["content"], system_budget),
            }
            compacted = True

    selected_reversed: list[ChatMessage] = []
    used = message_tokens(system_message) if system_message is not None else 0
    remaining = max(64, budget - used)

    for index, message in enumerate(reversed(rest)):
        tokens = message_tokens(message)
        is_latest = index == 0
        if tokens <= remaining:
            selected_reversed.append(message)
            remaining -= tokens
            continue

        if is_latest:
            content_budget = max(64, remaining - 6)
            selected_reversed.append(
                {"role": message["role"], "content": truncate_text_by_tokens(message["content"], content_budget)}
            )
            remaining = 0
        break

    selected = list(reversed(selected_reversed))
    fitted: list[ChatMessage] = []
    if system_message is not None:
        fitted.append(system_message)
    fitted.extend(selected)

    trimmed_tokens = count_message_tokens(fitted)
    dropped_messages = max(0, len(normalized) - len(fitted))

    return ContextWindowResult(
        messages=fitted,
        original_tokens=original_tokens,
        trimmed_tokens=trimmed_tokens,
        dropped_messages=dropped_messages,
        compacted_system_prompt=compacted,
    )

