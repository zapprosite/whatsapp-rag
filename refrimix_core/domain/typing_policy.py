"""
typing_policy.py — Política de quando ativar typing indicator.

Regras:
- Ativar ANTES de slow lane iniciar (< 200ms após decisão)
- Desativar quando resposta chega ou timeout (30s)
- Fast lane: NUNCA ativa typing (resposta instantânea)
- Se slow lane demora mais que 30s, desativa e envia fallback
"""
from __future__ import annotations

from dataclasses import dataclass


# ── Tempos (em segundos) ─────────────────────────────────────────────────────

TYPING_ACTIVATION_DELAY = 0.2   # Ativar até 200ms após decisão slow lane
TYPING_TIMEOUT_SECONDS = 30      # Timeout para slow lane


@dataclass(frozen=True)
class TypingState:
    active: bool
    started_at: float | None  # timestamp ou None
    elapsed: float | None     # segundos desde início


def should_start_typing(
    lane: str,
    message_text: str,
    has_sent_microcopy: bool,
) -> bool:
    """
    Decide se deve ativar typing indicator.

    Args:
        lane: "fast" ou "slow"
        message_text: texto da mensagem original
        has_sent_microcopy: se já enviou microcopy de transição
    """
    # Fast lane: nunca typing — resposta é instantânea
    if lane == "fast":
        return False

    # Se já enviou microcopy, typing já deve estar ativo
    # Não双重激活
    if has_sent_microcopy:
        return False

    return True


def is_typing_timeout(started_at: float, now: float) -> bool:
    """Retorna True se typing indicator está em timeout."""
    return (now - started_at) >= TYPING_TIMEOUT_SECONDS


def typing_duration_text(elapsed: float) -> str:
    """Retorna texto de duração do typing (para logs)."""
    if elapsed < 5:
        return f"{elapsed:.1f}s"
    elif elapsed < 15:
        return f"{elapsed:.0f}s"
    else:
        return f"{elapsed:.0f}s (quase.timeout)"
