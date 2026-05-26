"""
Pipeline principal do Refrimix Core V2.
Orchestrates: understand_message → reduce_lead_state →
commercial_router → plan_next_action → response_catalog → output.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from refrimix_core.domain.commercial_router import decide_commercial_path
from refrimix_core.domain.response_catalog import get_response
from refrimix_core.domain.text_normalizer import fold
from refrimix_core.nodes.understand_message import understand_message
from refrimix_core.nodes.reduce_lead_state import reduce_lead_state
from refrimix_core.nodes.plan_next_action import plan_next_action
from refrimix_core.guards.language_guard import guard, validate


logger = logging.getLogger(__name__)


def build_lead_state() -> dict:
    """Retorna LeadState vazio com estrutura mínima."""
    return {
        "identity": {"name": None, "phone": None},
        "service": {"type": None, "city_bairro": None},
        "installation": {
            "btus": None,
            "has_photos": {"local_interno": False, "local_externo": False, "aparelho": False},
            "ponto_eletrico_exclusivo": None,
            "distancia_aproximada": None,
            "infra_pronta": None,
        },
        "higienizacao": {"quantidade_aparelhos": None, "aparelho_funcionando": None},
        "maintenance": {"symptom": None, "risk_electric": False},
        "appointment": {"preferred_window": None, "status": None},
        "commercial": {"path": None, "fixed_price": None, "visit_price": None, "owner_alert": False},
        "memory": {
            "last_asked_field": None,
            "last_answered_field": None,
            "do_not_ask": [],
            "last_response_hash": None,
        },
        "fotos": {"local_interno": False, "local_externo": False, "aparelho": False},
    }


def pipeline(
    input_data: dict,
    lead_state: dict,
) -> dict:
    """
    Pipeline principal — determinístico e rastreável.

    Args:
        input_data: PipelineInput (phone, message_id, message_type, text, transcript, ...)
        lead_state: LeadState atual

    Returns:
        PipelineOutput: action, response_text, response_modality, side_effects,
                        lead_state_patch, commercial_decision, debug
    """
    phone = input_data.get("phone", "")
    message_type = input_data.get("message_type", "text")
    text = input_data.get("text", "") or input_data.get("transcript", "") or ""
    last_asked_field = lead_state.get("memory", {}).get("last_asked_field")
    current_service = lead_state.get("service", {}).get("type")

    # ── Step 1: understand_message ──────────────────────────────────────────
    understanding = understand_message(
        text=text,
        message_type=message_type,
        last_asked_field=last_asked_field,
        service_in_state=current_service,
    )
    logger.debug(f"[pipeline] understanding={understanding}")

    # ── Step 2: reduce_lead_state ─────────────────────────────────────────
    updated_state = reduce_lead_state(
        lead_state=lead_state,
        message_understanding=understanding,
        message_type=message_type,
        user_text=text,
    )

    # ── Step 3: commercial_router ─────────────────────────────────────────
    commercial = decide_commercial_path(
        lead_state=updated_state,
        user_text=text,
    )
    logger.debug(f"[pipeline] commercial_path={commercial.get('path')}")

    # ── Step 4: plan_next_action ──────────────────────────────────────────
    next_action = plan_next_action(
        lead_state=updated_state,
        commercial_decision=commercial,
        message_understanding=understanding,
    )
    action_type = next_action.get("type", "fallback_recover_context")
    logger.debug(f"[pipeline] action={action_type}")

    # ── Step 5: response_catalog ───────────────────────────────────────────
    response_kwargs = {}
    if action_type == "offer_hygienization_schedule":
        response_kwargs["quantity"] = next_action.get("quantity", 1)
    if action_type == "save_preferred_window":
        response_kwargs["window"] = next_action.get("window", "manha")

    response_text = get_response(action_type, **response_kwargs)

    # ── Step 6: language_guard ────────────────────────────────────────────
    is_valid, reason = validate(response_text)
    if not is_valid:
        logger.warning(f"[pipeline] language_guard blocked: {reason} — using fallback")
        response_text = guard(response_text)

    # ── Step 7: anti-loop guard (last_response_hash) ──────────────────────
    response_hash = hashlib.sha256(response_text.encode()).hexdigest()[:16]
    last_hash = updated_state.get("memory", {}).get("last_response_hash")
    if response_hash == last_hash and last_hash is not None:
        logger.warning("[pipeline] Anti-loop: identical response detected — fallback")
        response_text = get_response("fallback_recover_context")

    # ── Step 8: update memory ─────────────────────────────────────────────
    updated_state.setdefault("memory", {})
    updated_state["memory"]["last_response_hash"] = response_hash

    # ── Step 9: determine modality ─────────────────────────────────────────
    modality = _determine_modality(input_data, next_action)

    # ── Step 10: build output ─────────────────────────────────────────────
    output = {
        "phone": phone,
        "action": action_type,
        "response_text": response_text,
        "response_modality": modality,
        "side_effects": next_action.get("side_effects", []),
        "lead_state_patch": updated_state,
        "commercial_decision": commercial,
        "debug": {
            "core_version": "v2",
            "message_type": message_type,
            "understanding_kind": understanding.get("kind"),
            "language_guard_passed": is_valid,
        },
    }

    return output


def _determine_modality(input_data: dict, next_action: dict) -> str:
    """
    text input → text
    audioMessage input + TTS → audio (via Chatterbox side effect)
    audioMessage input + no TTS → text
    imageMessage → text
    """
    message_type = input_data.get("message_type", "text")
    if message_type == "text":
        return "text"
    if message_type == "imageMessage":
        return "text"
    if message_type == "audioMessage":
        # TTS é decidido por side_effect, output é sempre text ou audio
        # Chatterbox TTS gera áudio e sendWhatsAppAudio
        return "audio"
    return "text"