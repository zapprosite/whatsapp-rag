from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo


_SAO_PAULO = ZoneInfo("America/Sao_Paulo")
_GENERIC_GREETING_TERMS = (
    "oi",
    "ola",
    "olá",
    "opa",
    "bom dia",
    "boa tarde",
    "boa noite",
    "td bem",
    "tudo bem",
)
_GENERIC_INTENT_TERMS = (
    "preciso de ajuda",
    "quero saber",
    "como funciona",
    "quanto fica",
    "valor",
)


def _fold(text: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text.strip().lower())


def greeting_by_time(now: datetime | None = None) -> str:
    current = now.astimezone(_SAO_PAULO) if now else datetime.now(_SAO_PAULO)
    hour = current.hour
    if 5 <= hour <= 11:
        return "Bom dia"
    if 12 <= hour <= 17:
        return "Boa tarde"
    return "Boa noite"


def is_generic_greeting_or_message(text: str | None) -> bool:
    folded = _fold(text)
    if not folded:
        return True
    if folded in _GENERIC_GREETING_TERMS:
        return True
    if any(term == folded for term in _GENERIC_INTENT_TERMS):
        return True
    return len(folded.split()) <= 3 and any(term in folded for term in _GENERIC_GREETING_TERMS)


def has_objective_request(text: str | None) -> bool:
    folded = _fold(text)
    if not folded:
        return False
    service_terms = (
        "instalar",
        "instalacao",
        "instalação",
        "manutencao",
        "manutenção",
        "conserto",
        "higienizacao",
        "higienização",
        "limpeza",
        "agendar",
        "visita",
        "orçamento",
        "orcamento",
    )
    return any(term in folded for term in service_terms)


def should_send_welcome(
    *,
    is_first_message: bool,
    has_persistent_history: bool,
    lead_state: dict | None,
    user_text: str | None,
) -> bool:
    state = lead_state or {}
    if not is_first_message or has_persistent_history:
        return False
    if state.get("tipo_servico"):
        return False
    return is_generic_greeting_or_message(user_text) or has_objective_request(user_text)
