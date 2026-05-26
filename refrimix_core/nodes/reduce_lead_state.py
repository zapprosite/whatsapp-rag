"""
reduce_lead_state — reduz mensagem para estado do lead.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from refrimix_core.domain.text_normalizer import (
    fold, normalize_service, detect_window, detect_quantity,
)


def reduce_lead_state(
    lead_state: dict,
    message_understanding: dict,
    message_type: str,
    user_text: str,
) -> dict:
    """
    Atualiza o LeadState a partir da mensagem recebida.
    Retorna dicionário de mudanças (patch) para aplicar.
    """
    state = deepcopy(lead_state)
    understanding = message_understanding

    # ── Service ────────────────────────────────────────────────────────────
    service_mentioned = understanding.get("service_mentioned")
    current_service = state.get("service", {}).get("type")

    if service_mentioned and not current_service:
        if "service" not in state:
            state["service"] = {}
        state["service"]["type"] = service_mentioned

    # ── Identity ───────────────────────────────────────────────────────────
    name = _extract_name(user_text)
    if name:
        if "identity" not in state:
            state["identity"] = {}
        state["identity"]["name"] = name

    # ── Appointment: preferred window ─────────────────────────────────────
    window = understanding.get("window")
    if window:
        if "appointment" not in state:
            state["appointment"] = {}
        state["appointment"]["preferred_window"] = window

    # ── Higienização: quantidade ───────────────────────────────────────────
    quantity = understanding.get("quantity")
    if quantity is not None and current_service == "higienizacao":
        if "higienizacao" not in state:
            state["higienizacao"] = {}
        state["higienizacao"]["quantidade_aparelhos"] = quantity

    # ── Short answer (yes/no for boolean fields) ──────────────────────────
    short_answer = understanding.get("short_answer")
    last_asked = understanding.get("last_asked_field")
    if short_answer and last_asked:
        _apply_short_answer(state, last_asked, short_answer)

    # ── Image: marca has_photos ───────────────────────────────────────────
    if message_type == "imageMessage":
        if "fotos" not in state:
            state["fotos"] = {}
        # Basic: assume que imagem é do local (mais tarde vision refine)
        state["fotos"]["has_image"] = True

    # ── Memory ────────────────────────────────────────────────────────────
    if "memory" not in state:
        state["memory"] = {}
    state["memory"]["last_answered_field"] = last_asked

    return state


def _apply_short_answer(state: dict, last_asked: str, short_answer: str) -> None:
    """Aplica resposta yes/no a campos booleanos do lead_state."""
    mapping = {
        "ponto_eletrico_exclusivo": ("installation", "ponto_eletrico_exclusivo"),
        "tubulacao_existente": ("installation", "tubulacao_existente"),
        "aparelho_funcionando": ("higienizacao", "aparelho_funcionando"),
        "infra_pronta": ("installation", "infra_pronta"),
    }
    target = mapping.get(last_asked)
    if not target:
        return
    bucket, field = target
    if bucket not in state:
        state[bucket] = {}
    state[bucket][field] = (short_answer == "yes")


def _extract_name(text: str) -> str | None:
    """Extrai nome do texto."""
    import re
    cleaned = text.strip()
    if not cleaned or "@" in cleaned or any(c.isdigit() for c in cleaned):
        return None
    patterns = [
        r"^meu nome é (.+)",
        r"^sou (.+)",
        r"^chamo(?:s)? (.+)",
    ]
    for pat in patterns:
        m = re.search(pat, cleaned, re.I)
        if m:
            name = m.group(1).strip()
            parts = name.split()
            if 1 <= len(parts) <= 3:
                return " ".join(p.capitalize() for p in parts[:3])
    return None