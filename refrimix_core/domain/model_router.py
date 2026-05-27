"""
model_router.py — Decide entre fast lane (Qwen 3B) e slow lane (MiniMax M2.7).

Fast lane: saudação, "sim"/"não", "vc funciona?"
Slow lane: tudo que precisa de interpretação, preço, agenda, Drive, Calendar
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from refrimix_core.domain.natural_microcopy import FAST_LANE_INTENTS


class Lane(Enum):
    FAST = "fast"       # Qwen2.5 3B — microcopy rápida
    SLOW = "slow"       # MiniMax M2.7 — interpretação completa


@dataclass(frozen=True)
class RoutingDecision:
    lane: Lane
    intent: str
    reason: str
    should_send_microcopy: bool


# ── Padrões que FORÇAM slow lane ─────────────────────────────────────────────

SLOW_LANE_PATTERNS = (
    # Serviços e preços
    "quanto custa",
    "quanto fica",
    "preço",
    "valor",
    "orçamento",
    "orcamento",
    "cotação",
    "quanto tempo",
    # Dados técnicos
    "BTU",
    "btu",
    "capacidade",
    "potent",
    "litros",
    "metro",
    "平米",
    # Agendamento
    "agendar",
    "horário",
    "horario",
    "visita técnica",
    "visita",
    # Interesse comercial
    "tenho interesse",
    "tenho pressa",
    "quero contratar",
    "pode vim",
    "pode vir",
    "quando podem",
    "quando poderia",
    "quando seria",
    # Problemas específicos
    "não gela",
    "nao gela",
    "não esfria",
    "nao esfria",
    "vazando",
    "gotejando",
    "ruído",
    "barulho",
    "elétrico",
    "fio",
    "tomada",
    "disjuntor",
    # RAG / contexto
    "vocês",
    "a refrimix",
    "empresa",
    "histórico",
    # Instagram / redes
    "instagram",
    "instragram",
    # Nomes de modelos específicos
    "springer",
    "carrier",
    "lg",
    "samsung",
    "gree",
    "midea",
    "komeco",
    # Envio de mídia
    "enviar foto",
    "manda foto",
    "enviei",
    "enviar imagem",
)

# ── Padrões que FORÇAM fast lane (ignoram slow patterns) ─────────────────────

FAST_LANE_PATTERNS = (
    # Apenas saudação ou resposta curta
    r"^oi\s*$",
    r"^olá\s*$",
    r"^ola\s*$",
    r"^bom\s*d(ia|a)\s*$",
    r"^boa\s*tarde\s*$",
    r"^boa\s*noite\s*$",
    r"^td\s*(bém|bm|b| bem)?\s*$",
    r"^tbm\s*$",
    r"^tudo\s*bem?\s*$",
    r"^tudo\s*$",
    r"^como\s*vc\s*(ta|tá|t)\s*$",
    r"^e\s*ai\s*$",
    r"^iai\s*$",
    r"^blz\s*$",
    r"^beleza\s*$",
    r"^opa\s*$",
    # Afirmar/negativa sozinha
    r"^sim\s*$",
    r"^s\b",
    r"^não\s*$",
    r"^nao\s*$",
    r"^tenho\s*$",
    r"^tenho\s+sim\s*$",
    r"^pode\s*ser\s*$",
    r"^ok\s*$",
    r"^blz\s*$",
    # Auto-introdução
    "vc funciona?",
    "vc atende?",
    "vc é um bot?",
    "vc e um robô?",
)


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def is_fast_lane_only(text: str) -> bool:
    """Retorna True se mensagem é puramente saudação/resposta curta."""
    folded = _fold(text)
    for pattern in FAST_LANE_PATTERNS:
        if re.match(pattern, folded):
            return True
    return False


def should_use_slow_lane(text: str) -> bool:
    """Retorna True se mensagem requer processamento slow lane."""
    folded = _fold(text)
    # Padrão rápido override
    if is_fast_lane_only(folded):
        return False
    # Qualquer menção de slow lane = slow
    return any(p in folded for p in SLOW_LANE_PATTERNS)


def route(text: str, intent_hint: str | None = None) -> RoutingDecision:
    """
    Decide qual lane usar para uma mensagem.

    Args:
        text: mensagem do cliente
        intent_hint: intent já classificada (opcional)
    """
    folded = _fold(text)

    # Se intent é conhecida e é fast lane pura
    if intent_hint in FAST_LANE_INTENTS and is_fast_lane_only(folded):
        return RoutingDecision(
            lane=Lane.FAST,
            intent=intent_hint,
            reason="greeting/affirmative pattern",
            should_send_microcopy=True,
        )

    # Slow lane patterns
    if should_use_slow_lane(folded):
        return RoutingDecision(
            lane=Lane.SLOW,
            intent=intent_hint or "unknown",
            reason="technical/commercial/scheduling content",
            should_send_microcopy=True,  # Envia microcopy de transição
        )

    # Padrão fast lane
    if is_fast_lane_only(folded):
        return RoutingDecision(
            lane=Lane.FAST,
            intent=intent_hint or "greeting_short",
            reason="pure fast lane pattern",
            should_send_microcopy=True,
        )

    # Default: slow lane (mais seguro)
    return RoutingDecision(
        lane=Lane.SLOW,
        intent=intent_hint or "unknown",
        reason="default to slow for safety",
        should_send_microcopy=True,
    )
