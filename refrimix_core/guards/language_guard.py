"""
language_guard — bloqueia CJK, Arabic, Cyrillic, PT-PT e ES em respostas.
"""
from __future__ import annotations

import unicodedata


NON_LATIN_SCRIPTS = frozenset([
    "CJK", "HIRAGANA", "KATAKANA", "HANGUL", "CYRILLIC",
    "ARABIC", "HEBREW", "THAI", "DEVANAGARI",
    "TAMIL", "KANNADA", "MALAYALAM",
])

PT_PT_TERMS = frozenset([
    "telemóvel", "telemovel", "contactar", "morada",
    "marcação", "margacao",
    "encarge", "fazer contacto",
])

ES_TERMS = frozenset([
    "presupuesto", "mantenimiento", "instalación",
    "aire acondicionado",
])


def get_script_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for char in text:
        if char in "\n\r\t ":
            continue
        name = unicodedata.name(char, "")
        script = name.split()[0] if name else "UNKNOWN"
        counts[script] = counts.get(script, 0) + 1
    return counts


def has_blocked_script(text: str) -> tuple[bool, list[str]]:
    counts = get_script_counts(text)
    blocked = [s for s in NON_LATIN_SCRIPTS if s in counts]
    return bool(blocked), blocked


def is_majority_non_latin(text: str, threshold: float = 0.5) -> bool:
    counts = get_script_counts(text)
    latin = counts.get("LATIN", 0)
    total = sum(counts.values())
    if total == 0:
        return False
    return (total - latin) / total > threshold


def has_blocked_terms(text: str) -> tuple[bool, list[str]]:
    """Bloqueia PT-PT e ES terms."""
    t = text.lower()
    found: list[str] = []
    for term in PT_PT_TERMS:
        if term in t:
            found.append(term)
    for term in ES_TERMS:
        if term in t:
            found.append(term)
    return bool(found), found


def sanitize(text: str) -> str:
    """
    Remove qualquer caractere que não seja LATIN, ASCII ou pontuação básica.
    Preserva acentos pt-BR.
    """
    out = []
    for char in text:
        if char in "\n\r\t ":
            out.append(char)
            continue
        # ASCII imprimível
        if 0x20 <= ord(char) <= 0x7E:
            out.append(char)
            continue
        name = unicodedata.name(char, "")
        # LATIN e acentos brasileiros
        if name.startswith("LATIN") or name.startswith("COMBINING"):
            out.append(char)
            continue
        # Pontuação e símbolos
        cat = unicodedata.category(char)
        if cat.startswith(("P", "S", "N")):
            out.append(char)
    return "".join(out).strip()


FALLBACK_RESPONSE = (
    "Ola! Tive um problema tecnico aqui. "
    "Um dos nossos especialistas vai te retornar em breve. "
    "Pode me mandar o endereco e o que precisa?"
)


def validate(text: str) -> tuple[bool, str]:
    """Valida texto. Returns (is_valid, reason)."""
    if not text or not text.strip():
        return False, "Resposta vazia"

    has_blocked, blocked = has_blocked_script(text)
    if has_blocked:
        return False, f"Scripts bloqueados: {blocked}"

    if is_majority_non_latin(text, 0.5):
        return False, "Maioria de caracteres nao-latinos"

    has_terms, found = has_blocked_terms(text)
    if has_terms:
        return False, f"Termos bloqueados: {found}"

    return True, "OK"


def guard(text: str) -> str:
    """
    Se texto é válido → retorna texto.
    Se texto tem problema → tenta sanitize.
    Se sanitize falhar → fallback determinístico.
    """
    is_valid, _ = validate(text)
    if is_valid:
        return text

    # Tenta sanitize
    sanitized = sanitize(text)
    if sanitized and len(sanitized) > 20:
        return sanitized

    return FALLBACK_RESPONSE