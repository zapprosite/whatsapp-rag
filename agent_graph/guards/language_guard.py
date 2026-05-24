from __future__ import annotations

import unicodedata
import asyncio
from typing import Awaitable, Callable, Final

NON_LATIN_SCRIPTS: Final[set[str]] = {
    "CJK",
    "HIRAGANA",
    "KATAKANA",
    "HANGUL",
    "CYRILLIC",
    "ARABIC",
    "HEBREW",
    "THAI",
    "DEVANAGARI",
    "TAMIL",
    "KANNADA",
    "MALAYALAM",
}


class LanguageViolation(Exception):
    pass


def get_script_usage(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for char in text:
        if char in ("\n", "\r", "\t"):
            continue
        name = unicodedata.name(char, "")
        script = name.split()[0] if name else "UNKNOWN"
        if char == " ":
            script = "SPACE"
        counts[script] = counts.get(script, 0) + 1
    return counts


def has_blocked_script(text: str) -> tuple[bool, list[str]]:
    script_counts = get_script_usage(text)
    blocked = [s for s in NON_LATIN_SCRIPTS if s in script_counts]
    return len(blocked) > 0, blocked


def is_majority_non_latin(text: str, threshold: float = 0.50) -> bool:
    script_counts = get_script_usage(text)
    latin = script_counts.get("LATIN", 0)
    total = sum(script_counts.values())
    if total == 0:
        return False
    return (total - latin) / total > threshold


def sanitize_hard(text: str) -> str:
    """Remove qualquer caractere cujo unicode name nao comeca com LATIN, ASCII ou pontuacao basica."""
    out = []
    for char in text:
        if char in "\n\r\t ":
            out.append(char)
            continue
        # Aceita ASCII imprimivel
        if 0x20 <= ord(char) <= 0x7E:
            out.append(char)
            continue
        # Aceita caracteres cujo nome Unicode comeca com LATIN (acentos pt-BR)
        name = unicodedata.name(char, "")
        if name.startswith("LATIN") or name.startswith("COMBINING"):
            out.append(char)
            continue
        # Aceita pontuacao e simbolos comuns (COPYRIGHT, TRADE MARK, etc.)
        cat = unicodedata.category(char)
        if cat.startswith("P") or cat.startswith("S") or cat.startswith("N"):
            out.append(char)
    return "".join(out).strip()


# Deteccao de idioma: tenta fast-langdetect, cai em langdetect, cai em None
_detect_fn: Callable[[str], str | None] | None = None

try:
    from fast_langdetect import detect as _fast_detect  # type: ignore

    def _detect_fn(text: str) -> str | None:  # type: ignore[misc]
        try:
            result = _fast_detect(text, low_memory=True)
            if isinstance(result, dict):
                return result.get("lang")
            return str(result)
        except Exception:
            return None

except ImportError:
    try:
        from langdetect import detect as _ld_detect, LangDetectException  # type: ignore

        def _detect_fn(text: str) -> str | None:  # type: ignore[misc]
            try:
                return _ld_detect(text)
            except LangDetectException:
                return None

    except ImportError:
        pass


def detect_language(text: str) -> str | None:
    if _detect_fn is None:
        return None
    return _detect_fn(text)


def is_portuguese(text: str) -> bool:
    lang = detect_language(text)
    return lang in ("pt", "pt-br", "pt-BR") if lang else False


class LanguageGuard:
    """
    Guardrail pt-BR para respostas do LLM.

    Repair em cascata:
      1. retry no LLM original com instrucao explicita
      2. repair via Groq Llama (fallback externo)
      3. sanitize_hard (strip de chars nao-latinos)
      4. mensagem de fallback segura
    """

    def __init__(
        self,
        expected_lang: str = "pt-BR",
        majority_threshold: float = 0.50,
        max_retries: int = 2,
    ) -> None:
        self.expected_lang = expected_lang
        self.majority_threshold = majority_threshold
        self.max_retries = max_retries

    def validate(self, text: str) -> tuple[bool, str]:
        if not text or not text.strip():
            return False, "Resposta vazia"

        has_blocked, blocked = has_blocked_script(text)
        if has_blocked:
            return False, f"Scripts bloqueados: {blocked}"

        if is_majority_non_latin(text, self.majority_threshold):
            return False, "Maioria de caracteres nao-latinos"

        # Deteccao de idioma apenas para textos suficientemente longos
        # (langdetect e impreciso em textos < 50 chars)
        if len(text.strip()) >= 50:
            lang = detect_language(text)
            if lang is not None and lang not in ("pt", "pt-br", "pt-BR", "en", "es", "ca"):
                return False, f"Idioma detectado: {lang}"

        return True, "OK"

    async def validate_and_fix(
        self,
        response: str,
        llm_callable: Callable[[str], Awaitable[str]],
        original_prompt: str,
        groq_repair_callable: Callable[[str], Awaitable[str]] | None = None,
    ) -> str:
        is_valid, reason = self.validate(response)
        if is_valid:
            return response

        for attempt in range(1, self.max_retries + 1):
            retry_prompt = (
                f"{original_prompt}\n\n"
                "[CRITICO] Responda APENAS em portugues brasileiro coloquial. "
                "Proibido: caracteres chineses, japoneses, coreanos, arabes, cirilicos. "
                "Escreva como o dono da empresa no WhatsApp, em pt-BR natural."
            )
            try:
                response = await llm_callable(retry_prompt)
            except Exception:
                await asyncio.sleep(min(4.0, 0.5 * (2 ** (attempt - 1))))
                continue
            is_valid, reason = self.validate(response)
            if is_valid:
                return response

        # Repair via Groq como fallback externo
        if groq_repair_callable is not None:
            repair_prompt = (
                "Reescreva o texto abaixo 100% em portugues brasileiro coloquial, "
                "mantendo o sentido, sem nenhum caractere nao-latino:\n\n" + response
            )
            try:
                repaired = await groq_repair_callable(repair_prompt)
                is_valid, _ = self.validate(repaired)
                if is_valid:
                    return repaired
            except Exception:
                pass

        # Sanitize hard
        sanitized = sanitize_hard(response)
        if sanitized and len(sanitized) > 20:
            return sanitized

        return (
            "Ola! Tive um problema tecnico aqui. "
            "Um dos nossos especialistas vai te retornar em breve. "
            "Pode me mandar o endereco e o que precisa?"
        )
