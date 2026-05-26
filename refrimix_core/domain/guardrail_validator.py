"""guardrail_validator.py — Pure, deterministic response guardrails for HVAC-R attendance."""

import re
from dataclasses import dataclass

# ----------------------------------------------------------------------
# Dataclass
# ----------------------------------------------------------------------


@dataclass
class ValidationResult:
    is_valid: bool
    violations: list[str]  # empty if is_valid=True
    corrected_text: str | None  # None if is_valid=True


# ----------------------------------------------------------------------
# Violation patterns  (pattern_str, violation_type)
# ----------------------------------------------------------------------

VIOLATION_PATTERNS: list[tuple[str, str]] = [
    # Definitivo diagnóstico (bot não pode diagnosticar com certeza)
    (r"\bfalta de gás com certeza\b", "diagnostico_definitivo"),
    (r"\bo compressor queimou\b", "diagnostico_definitivo"),
    (r"\ba placa queimou\b", "diagnostico_definitivo"),
    (r"\bé vazamento com certeza\b", "diagnostico_definitivo"),
    (r"\bé mofo com certeza\b", "diagnostico_definitivo"),
    # Preço inventado
    (r"r\$\s*\d+\s*(mil|reais|por|kg|unidade)", "preco_inventado"),
    (r"\bvalor fechado\b", "preco_inventado"),
    (r"\bcusta?\s+r\$", "preco_inventado"),
    (r"\bfica\s+r\$", "preco_inventado"),
    # Promessa de disponibilidade (indisponível no momento)
    (r"\btenho disponibilidade\b", "promessa_indisponivel"),
    (r"\btenho\s+vaga\b", "promessa_indisponivel"),
    # Linguagem enganosa / spam
    (r"\bromoÇÃO\b", "linguagem_enganosa"),
    # Português europeu (brasileiro formal esperado)
    (r"^\s*então,?", "portugues_europeu"),
    (r"\bprecisa de ajuda\??", "formalidade_errada"),
    # Espanhol
    (r"\¿", "espanhol"),
]

# Compiled patterns for performance
_COMPILED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.IGNORECASE), v) for p, v in VIOLATION_PATTERNS
]

# ----------------------------------------------------------------------
# Thresholds
# ----------------------------------------------------------------------

MAX_TEXT_LENGTH: int = 500
MAX_QUESTION_MARKS: int = 3

# ----------------------------------------------------------------------
# High-risk safety requirements
# ----------------------------------------------------------------------

_SAFETY_KEYWORDS: list[str] = ["desligad", "avaliação", "profissional"]


# ----------------------------------------------------------------------
# Core validation logic
# ----------------------------------------------------------------------


def _check_pattern_violations(text: str) -> list[str]:
    """Return list of violation types found in text."""
    violations: list[str] = []
    for compiled_re, violation_type in _COMPILED_PATTERNS:
        if compiled_re.search(text):
            violations.append(violation_type)
    return violations


def _check_safety_alert(text_lower: str) -> bool:
    """Return True if text contains at least one safety-alert keyword."""
    for kw in _SAFETY_KEYWORDS:
        if kw in text_lower:
            return True
    return False


def validate_response(
    response_text: str,
    intent_key: str,
    risk_level: str,
    lead_context: dict,
) -> ValidationResult:
    """
    PURE. Same input → same output.

    response_text : the generated bot response string to validate
    intent_key    : intent that triggered this response (for context)
    risk_level    : "low" | "medium" | "high" (from RiskDecision)
    lead_context  : {name, phone, collected_fields, ...} (read-only, no side-effects)

    Returns ValidationResult with:
      - is_valid      : True only when no violations found
      - violations    : [] when valid; list of violation type strings otherwise
      - corrected_text: always None (rejection only, no auto-correct)
    """
    violations: list[str] = []
    text_lower = response_text.lower()

    # 1. Pattern-based violations
    violations.extend(_check_pattern_violations(response_text))

    # 2. Length check
    if len(response_text) > MAX_TEXT_LENGTH:
        violations.append("texto_muito_longo")

    # 3. Question-mark limit
    if response_text.count("?") > MAX_QUESTION_MARKS:
        violations.append("excesso_de_perguntas")

    # 4. High-risk: require safety alert in response text
    if risk_level == "high":
        if not _check_safety_alert(text_lower):
            violations.append("falta_alerta_seguranca")

    # Build result
    if violations:
        return ValidationResult(
            is_valid=False,
            violations=violations,
            corrected_text=None,
        )

    return ValidationResult(
        is_valid=True,
        violations=[],
        corrected_text=None,
    )
