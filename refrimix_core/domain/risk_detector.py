"""risk_detector.py — Pure, deterministic risk classification for HVAC-R attendance."""

from dataclasses import dataclass
from typing import Literal

# ----------------------------------------------------------------------
# Dataclass
# ----------------------------------------------------------------------


@dataclass
class RiskDecision:
    risk_level: Literal["low", "medium", "high"]
    human_handoff: bool
    safety_alert: str | None  # non-None only for high-risk
    trigger_keywords: list[str]  # which keywords fired
    electric_context: bool  # True if message mentions electrical hazard


# ----------------------------------------------------------------------
# Constants — HIGH_RISK_KEYWORDS
# ----------------------------------------------------------------------

_HIGH_RISK_KEYWORD_PATTERNS: list[tuple[str, str]] = [
    # disjuntor
    ("disjuntor", "disjuntor_cai"),  # covers "cai", "caindo", "desarmando", etc.
    ("disjuntor desarmando", "disjuntor_desarmando"),
    # fio
    ("fio esquenta", "fio_esquenta"),
    ("fio aquecimento", "fio_aquecimento"),
    ("fio quente", "fio_quente"),
    # cheiro
    ("cheiro de queimado", "cheiro_queimado"),
    ("cheiro queimado", "cheiro_queimado"),
    ("cheiro de fogo", "cheiro_fogo"),
    # tomada
    ("tomada derretendo", "tomada_derretendo"),
    ("tomada esquentando", "tomada_esquentando"),
    # faísca / fascada
    ("faísca", "faisca"),
    ("fascada", "fascada"),
    # curto circuito
    ("curto circuito", "curto_circuito"),
    ("curto-circuito", "curto_circuito"),
    # derretendo
    ("derretendo", "derretendo"),
    # compressor queimou
    ("compressor queimou", "compressor_queimou"),
    # placa queimou
    ("placa queimou", "placa_queimou"),
]

# Pre-build the keyword set for fast lookup (the trigger phrase itself)
_HIGH_RISK_KEYWORDS: set[str] = {phrase for phrase, _ in _HIGH_RISK_KEYWORD_PATTERNS}

# ----------------------------------------------------------------------
# Constants — Intent sets
# ----------------------------------------------------------------------

HIGH_RISK_INTENTS: set[str] = {
    "disjuntor_cai",
    "cheiro_queimado",
    "curto_circuito",
}

MEDIUM_RISK_INTENTS: set[str] = {
    "barulho",
    "nao_gela",
    "nao_liga",
    "pinga_agua",
}

LOW_RISK_INTENTS: set[str] = {
    "welcome",
    "servicos",
    "higienizacao",
    "cheiro_ruim",
    "orcamento",
}

# ----------------------------------------------------------------------
# Safety alert message (high-risk default)
# ----------------------------------------------------------------------

_SAFETY_ALERT_HIGH: str = "Manter o equipamento desligado até avaliação profissional."


# ----------------------------------------------------------------------
# Electric-context keywords (subset of high-risk that indicate electrical hazard)
# ----------------------------------------------------------------------

_ELECTRIC_CONTEXT_KEYWORDS: set[str] = {
    "disjuntor",
    "fio",
    "tomada",
    "faísca",
    "fascada",
    "curto",
    "placa",
}


# ----------------------------------------------------------------------
# Core detection logic
# ----------------------------------------------------------------------


def _match_high_risk_keywords(message_lower: str) -> list[str]:
    """Return list of matched HIGH_RISK_KEYWORD phrases found in message."""
    matched: list[str] = []
    for phrase in _HIGH_RISK_KEYWORDS:
        if phrase in message_lower:
            matched.append(phrase)
    return matched


def _has_electric_context(message_lower: str) -> bool:
    """Return True if any electric-context keyword is in the message."""
    for kw in _ELECTRIC_CONTEXT_KEYWORDS:
        if kw in message_lower:
            return True
    return False


def detect_risk(
    message: str,
    intent_key: str,
    lead_context: dict,
) -> RiskDecision:
    """
    PURE. Same input → same output.

    message      : raw user message text (will be lowercased for analysis)
    intent_key   : from understand_message (e.g. nao_gela, disjuntor_cai)
    lead_context : {name, phone, collected_fields, ...} (read-only, no side-effects)

    Returns RiskDecision with:
      - risk_level    : "low" | "medium" | "high"
      - human_handoff : True when risk is high
      - safety_alert  : non-None str when risk is high
      - trigger_keywords: list of keyword phrases that fired
      - electric_context: True when message contains electrical-hazard language
    """
    # Normalise
    msg_lower = message.lower()

    # 1. Check explicit high-risk keyword patterns in message
    triggered = _match_high_risk_keywords(msg_lower)
    if triggered:
        return RiskDecision(
            risk_level="high",
            human_handoff=True,
            safety_alert=_SAFETY_ALERT_HIGH,
            trigger_keywords=triggered,
            electric_context=_has_electric_context(msg_lower),
        )

    # 2. Check high-risk intent keys (explicit dangerous intents)
    if intent_key in HIGH_RISK_INTENTS:
        return RiskDecision(
            risk_level="high",
            human_handoff=True,
            safety_alert=_SAFETY_ALERT_HIGH,
            trigger_keywords=[],
            electric_context=_has_electric_context(msg_lower),
        )

    # 3. Medium-risk intents
    if intent_key in MEDIUM_RISK_INTENTS:
        return RiskDecision(
            risk_level="medium",
            human_handoff=False,
            safety_alert=None,
            trigger_keywords=[],
            electric_context=_has_electric_context(msg_lower),
        )

    # 4. Low-risk intents
    # (includes welcome, servicos, higienizacao, cheiro_ruim, orcamento)
    return RiskDecision(
        risk_level="low",
        human_handoff=False,
        safety_alert=None,
        trigger_keywords=[],
        electric_context=_has_electric_context(msg_lower),
    )
