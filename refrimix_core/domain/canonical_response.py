"""
canonical_response.py — Pure, deterministic response builder for Refrimix WhatsApp bot.

No side effects. No network. No database. Same input → same output.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal

# Path to intent blocks JSON (resolved relative to this file)
_INTENT_BLOCKS_PATH = os.path.join(os.path.dirname(__file__), "intent_blocks.json")

# Singleton cache for intent blocks (pure — same file always yields same data)
_INTENT_BLOCKS_CACHE: dict[str, list[dict]] | None = None


def _load_intent_blocks() -> dict[str, list[dict]]:
    """Load intent blocks from JSON file. Pure — file content is static."""
    global _INTENT_BLOCKS_CACHE
    if _INTENT_BLOCKS_CACHE is None:
        with open(_INTENT_BLOCKS_PATH, encoding="utf-8") as f:
            _INTENT_BLOCKS_CACHE = json.load(f)
    return _INTENT_BLOCKS_CACHE


def get_intent_block(intent_key: str) -> dict | None:
    """
    Load intent block from intent_blocks.json by intent key.

    Returns None if intent not found.
    """
    blocks = _load_intent_blocks()
    for intent_data in blocks.get("intents", []):
        if intent_data.get("intent") == intent_key:
            return intent_data
    return None


@dataclass
class ResponseDraft:
    """Immutable response draft returned by build_response."""

    text: str
    intent: str
    risk: str  # "low" | "medium" | "high"
    human_handoff: bool
    next_action: str
    interactive_type: Literal["list", "buttons", "cta", None]
    interactive_config: dict | None
    missing_fields: list[str]


# Generic fallback when intent is unknown
_GENERIC_FALLBACK_TEXT = (
    "Entendi. Me conta mais um pouco o que está acontecendo pra eu te orientar."
)


def _select_response_text(intent_key: str, lead_context: dict) -> str:
    """
    Select appropriate text: canonical_response from intent block or fallback.

    Pure function — same inputs always return same output.
    """
    block = get_intent_block(intent_key)
    if block is None:
        return _GENERIC_FALLBACK_TEXT
    return block.get("canonical_response", _GENERIC_FALLBACK_TEXT)


def _determine_missing_fields(intent_key: str, lead_context: dict) -> list[str]:
    """
    From intent's required_questions minus already collected fields.

    Pure function.
    """
    block = get_intent_block(intent_key)
    if block is None:
        return []

    required = block.get("required_questions", [])
    collected: list[str] = lead_context.get("collected_fields", [])

    # Normalize: strip punctuation and lowercase for comparison
    def normalize(s: str) -> str:
        return s.strip().rstrip("?").lower()

    collected_normalized = {normalize(c) for c in collected}
    missing = []
    for q in required:
        if normalize(q) not in collected_normalized:
            missing.append(q)
    return missing


def _should_use_interactive(
    intent_key: str,
    lead_context: dict,
    channel_capabilities: dict,
) -> tuple[Literal["list", "buttons", "cta", None], dict | None]:
    """
    Decision: interactive if channel supports and intent has config.

    For intents with empty required_questions (menu flows like welcome/servicos),
    interactive is shown regardless of missing_fields.
    For intents with required_questions, interactive only shown when
    missing_fields exist (still collecting answers).

    Pure function.
    """
    block = get_intent_block(intent_key)
    if block is None:
        return None, None

    # Channel must support interactive
    if not channel_capabilities.get("interactive", False):
        return None, None

    interactive_type = block.get("interactive_type")
    if interactive_type is None:
        return None, None

    interactive_config = block.get("interactive_config")
    if interactive_config is None:
        return None, None

    # If intent has no required_questions (pure menu flow), always show interactive
    required = block.get("required_questions", [])
    if not required:
        return interactive_type, interactive_config

    # Otherwise, only show interactive if still collecting missing fields
    missing = _determine_missing_fields(intent_key, lead_context)
    if not missing:
        return None, None

    return interactive_type, interactive_config


def build_response(
    intent_key: str,
    lead_context: dict,
    channel_capabilities: dict,
) -> ResponseDraft:
    """
    PURE. Same input → same output.

    intent_key: from understand_message (nao_gela, disjuntor_cai, etc)
    lead_context: {collected_fields: [...], name, phone, ...}
    channel_capabilities: {interactive: bool, max_text_length: int}

    Returns ResponseDraft with text, intent, risk, handoff, next_action, interactive, missing_fields.
    """
    block = get_intent_block(intent_key)

    if block is None:
        # Fallback intent
        return ResponseDraft(
            text=_GENERIC_FALLBACK_TEXT,
            intent=intent_key,
            risk="medium",
            human_handoff=False,
            next_action="collect_more_info",
            interactive_type=None,
            interactive_config=None,
            missing_fields=[],
        )

    text = _select_response_text(intent_key, lead_context)
    risk = block.get("risk_default", "medium")
    human_handoff = block.get("human_handoff", False)
    next_action = block.get("next_action_hint", "continue")
    missing_fields = _determine_missing_fields(intent_key, lead_context)
    interactive_type, interactive_config = _should_use_interactive(
        intent_key, lead_context, channel_capabilities
    )

    return ResponseDraft(
        text=text,
        intent=intent_key,
        risk=risk,
        human_handoff=human_handoff,
        next_action=next_action,
        interactive_type=interactive_type,
        interactive_config=interactive_config,
        missing_fields=missing_fields,
    )
