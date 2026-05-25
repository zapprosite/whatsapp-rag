from __future__ import annotations

import os
import re
from typing import Any

from agent_graph.services.playbook_loader import get_tts_policy


_DEFAULT_MAX_CHARS = 420
_GREETING_RE = re.compile(r"^(oi|olá|ola|opa|bom dia|boa tarde|boa noite)[,!.\s]*(tudo bem\??)?", re.I)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except (AttributeError, ValueError):
        return default


def _strip_markdown(text: str) -> str:
    clean = re.sub(r"https?://\S+|www\.\S+", "link", text)
    clean = re.sub(r"[*_`#>]+", " ", clean)
    clean = re.sub(r"^\s*[-•]\s+", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^\s*\d+[.)]\s+", "", clean, flags=re.MULTILINE)
    return clean


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    sentences: list[str] = []
    for part in parts:
        part = part.strip(" ;:-")
        if part:
            sentences.append(part)
    return sentences


def _shorten_sentence(sentence: str, max_words: int) -> list[str]:
    words = sentence.split()
    if len(words) <= max_words:
        return [sentence]
    chunks = []
    for start in range(0, len(words), max_words):
        chunk = " ".join(words[start : start + max_words]).strip(" ,;:")
        if chunk:
            chunks.append(chunk + ".")
    return chunks


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    candidate = text[:max_chars].rstrip()
    cut = max(candidate.rfind("."), candidate.rfind("?"), candidate.rfind("!"))
    if cut >= 40:
        return candidate[: cut + 1].strip()
    return candidate.rsplit(" ", 1)[0].rstrip(" ,;:") + "."


def build_tts_text(customer_text: str, lead_mind: dict[str, Any] | None, goal: str | None) -> str:
    """Adapta texto escrito de WhatsApp para fala curta de TTS."""
    policy = get_tts_policy(goal)
    max_chars = min(_env_int("TTS_MAX_CHARS", _DEFAULT_MAX_CHARS), int(policy.get("max_chars") or _DEFAULT_MAX_CHARS))
    sentence_max_words = int(policy.get("sentence_max_words") or 18)

    text = _strip_markdown(customer_text)
    text = text.replace("\n", ". ")
    text = re.sub(r"\s+", " ", text).strip()

    relationship = ((lead_mind or {}).get("lead_profile") or {}).get("relationship_type")
    summary = ((lead_mind or {}).get("tts") or {}).get("speech_summary") or ""
    if relationship and relationship != "new_lead":
        text = _GREETING_RE.sub("", text).strip(" ,.!?")
    elif summary and text.lower().startswith(("oi", "olá", "ola")) and "Continuar" in summary:
        text = _GREETING_RE.sub("", text).strip(" ,.!?")

    sentences: list[str] = []
    for sentence in _split_sentences(text):
        sentences.extend(_shorten_sentence(sentence, sentence_max_words))

    spoken = " ".join(sentences)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    return _truncate(spoken, max_chars)
