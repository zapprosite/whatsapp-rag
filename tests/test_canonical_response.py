"""
Tests for canonical_response module.
Pure pytest — no external services, no network, no database.
"""
from __future__ import annotations

import json
import os

import pytest

# Ensure the module can be imported from the workspace path
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from refrimix_core.domain.canonical_response import (
    ResponseDraft,
    build_response,
    get_intent_block,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_intent_blocks_from_json() -> dict:
    """Load intent blocks directly from JSON for test validation."""
    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "refrimix_core",
        "domain",
        "intent_blocks.json",
    )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _all_nao_pode_dizer(intents_data: dict) -> set[str]:
    """Collect all banned phrases across all intents."""
    phrases: set[str] = set()
    for intent in intents_data.get("intents", []):
        for phrase in intent.get("nao_pode_dizer", []):
            phrases.add(phrase.lower())
    return phrases


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def intents_data():
    return _load_intent_blocks_from_json()


@pytest.fixture
def channel_with_interactive():
    return {"interactive": True, "max_text_length": 4096}


@pytest.fixture
def channel_without_interactive():
    return {"interactive": False, "max_text_length": 4096}


# ---------------------------------------------------------------------------
# 1. test_intent_blocks_json_valid
# ---------------------------------------------------------------------------

def test_intent_blocks_json_valid(intents_data):
    """All 12 intents have required fields."""
    intents = intents_data.get("intents", [])
    assert len(intents) == 12, f"Expected 12 intents, got {len(intents)}"

    required_fields = [
        "intent",
        "label",
        "risk_default",
        "service_type",
        "human_handoff",
        "required_questions",
        "nao_pode_dizer",
        "canonical_response",
        "next_action_hint",
        "interactive_type",
        "interactive_config",
    ]

    expected_intents = {
        "instalacao",
        "higienizacao",
        "nao_gela",
        "pinga_agua",
        "disjuntor_cai",
        "cheiro_ruim",
        "barulho",
        "nao_liga",
        "servicos",
        "orcamento",
        "visita_tecnica",
        "welcome",
    }

    found_intents = {i["intent"] for i in intents}
    assert found_intents == expected_intents, (
        f"Intent mismatch. Expected {expected_intents}, got {found_intents}"
    )

    for intent_obj in intents:
        intent_key = intent_obj.get("intent")
        for field in required_fields:
            assert field in intent_obj, (
                f"Intent '{intent_key}' missing required field: '{field}'"
            )

        # risk_default must be one of the valid values
        risk = intent_obj.get("risk_default")
        assert risk in ("low", "medium", "high"), (
            f"Intent '{intent_key}' has invalid risk: {risk}"
        )

        # human_handoff must be bool
        assert isinstance(intent_obj.get("human_handoff"), bool), (
            f"Intent '{intent_key}' human_handoff must be bool"
        )

        # required_questions max 3
        required = intent_obj.get("required_questions", [])
        assert len(required) <= 3, (
            f"Intent '{intent_key}' has {len(required)} required_questions (max 3)"
        )

        # interactive_type must be null or valid string
        itype = intent_obj.get("interactive_type")
        assert itype is None or itype in ("list", "buttons", "cta"), (
            f"Intent '{intent_key}' has invalid interactive_type: {itype}"
        )

        # If interactive_type is set, interactive_config must also be set
        if itype is not None:
            assert intent_obj.get("interactive_config") is not None, (
                f"Intent '{intent_key}' has interactive_type but no interactive_config"
            )


# ---------------------------------------------------------------------------
# 2. test_build_response_nao_gela
# ---------------------------------------------------------------------------

def test_build_response_nao_gela(channel_with_interactive):
    """Returns canonical text for nao_gela intent."""
    result = build_response(
        intent_key="nao_gela",
        lead_context={"collected_fields": []},
        channel_capabilities=channel_with_interactive,
    )

    assert isinstance(result, ResponseDraft)
    assert result.intent == "nao_gela"
    assert result.risk == "medium"
    assert "não gela" in result.text.lower() or "nao gela" in result.text.lower()
    assert result.human_handoff is False
    assert result.interactive_type is None  # nao_gela has no interactive


# ---------------------------------------------------------------------------
# 3. test_build_response_disjuntor_cai_high_risk
# ---------------------------------------------------------------------------

def test_build_response_disjuntor_cai_high_risk(channel_with_interactive):
    """disjuntor_cai is high risk with human_handoff=True."""
    result = build_response(
        intent_key="disjuntor_cai",
        lead_context={"collected_fields": []},
        channel_capabilities=channel_with_interactive,
    )

    assert result.intent == "disjuntor_cai"
    assert result.risk == "high", f"Expected high risk, got {result.risk}"
    assert result.human_handoff is True, (
        "disjuntor_cai must have human_handoff=True (safety-critical intent)"
    )


# ---------------------------------------------------------------------------
# 4. test_build_response_missing_fields
# ---------------------------------------------------------------------------

def test_build_response_missing_fields(channel_with_interactive):
    """missing_fields computed correctly as required_questions - collected_fields."""
    # instalacao needs: ["Bairro/cidade?", "Aparelho comprado?", "Quantos BTUs?"]
    # If "Bairro/cidade?" is already collected, it should not be in missing_fields
    lead_context = {"collected_fields": ["Bairro/cidade?"]}

    result = build_response(
        intent_key="instalacao",
        lead_context=lead_context,
        channel_capabilities=channel_with_interactive,
    )

    # Should have 2 missing: "Aparelho comprado?" and "Quantos BTUs?"
    assert "Bairro/cidade?" not in result.missing_fields
    assert len(result.missing_fields) == 2


# ---------------------------------------------------------------------------
# 5. test_build_response_fallback_generic
# ---------------------------------------------------------------------------

def test_build_response_fallback_generic(channel_with_interactive):
    """Unknown intent returns generic fallback text."""
    result = build_response(
        intent_key="unknown_intent_xyz",
        lead_context={"collected_fields": []},
        channel_capabilities=channel_with_interactive,
    )

    assert result.text == (
        "Entendi. Me conta mais um pouco o que está acontecendo pra eu te orientar."
    )
    assert result.intent == "unknown_intent_xyz"
    assert result.risk == "medium"


# ---------------------------------------------------------------------------
# 6. test_build_response_welcome_list_interactive
# ---------------------------------------------------------------------------

def test_build_response_welcome_list_interactive(channel_with_interactive):
    """welcome intent uses list interactive when channel supports it."""
    result = build_response(
        intent_key="welcome",
        lead_context={"collected_fields": []},
        channel_capabilities=channel_with_interactive,
    )

    assert result.interactive_type == "list"
    assert result.interactive_config is not None
    assert "sections" in result.interactive_config


# ---------------------------------------------------------------------------
# 7. test_build_response_disjuntor_cai_buttons_handoff
# ---------------------------------------------------------------------------

def test_build_response_disjuntor_cai_buttons_handoff(channel_with_interactive):
    """disjuntor_cai uses buttons and has human_handoff=True."""
    result = build_response(
        intent_key="disjuntor_cai",
        lead_context={"collected_fields": []},
        channel_capabilities=channel_with_interactive,
    )

    assert result.interactive_type == "buttons"
    assert result.human_handoff is True
    assert result.interactive_config is not None
    assert len(result.interactive_config.get("buttons", [])) == 3


# ---------------------------------------------------------------------------
# 8. test_response_text_max_length
# ---------------------------------------------------------------------------

def test_response_text_max_length(intents_data):
    """All canonical_response texts are ≤ 500 characters."""
    for intent_obj in intents_data.get("intents", []):
        text = intent_obj.get("canonical_response", "")
        assert len(text) <= 500, (
            f"Intent '{intent_obj['intent']}' canonical_response has "
            f"{len(text)} chars (max 500): {text[:80]}..."
        )


# ---------------------------------------------------------------------------
# 9. test_no_portuguese_european
# ---------------------------------------------------------------------------

def test_no_portuguese_european(intents_data):
    """Canonical texts do not contain European Portuguese or formal phrases."""
    forbidden = [
        "então",
        "precisa de ajuda?",
        "como posso ajudar?",
        "em que posso ajudar",
        "qualified",
    ]

    for intent_obj in intents_data.get("intents", []):
        text = intent_obj.get("canonical_response", "").lower()
        for phrase in forbidden:
            assert phrase not in text, (
                f"Intent '{intent_obj['intent']}' contains forbidden phrase "
                f"'{phrase}': {text}"
            )


# ---------------------------------------------------------------------------
# 10. test_nao_pode_dizer_not_in_response
# ---------------------------------------------------------------------------

def test_nao_pode_dizer_not_in_response(intents_data):
    """Banned phrases (nao_pode_dizer) never appear in canonical_response."""
    for intent_obj in intents_data.get("intents", []):
        text = intent_obj.get("canonical_response", "").lower()
        for phrase in intent_obj.get("nao_pode_dizer", []):
            assert phrase.lower() not in text, (
                f"Intent '{intent_obj['intent']}' canonical_response contains "
                f"banned phrase '{phrase}': {text}"
            )


# ---------------------------------------------------------------------------
# Extra: get_intent_block
# ---------------------------------------------------------------------------

def test_get_intent_block_found():
    block = get_intent_block("disjuntor_cai")
    assert block is not None
    assert block["intent"] == "disjuntor_cai"
    assert block["risk_default"] == "high"
    assert block["human_handoff"] is True


def test_get_intent_block_not_found():
    block = get_intent_block("inexistente")
    assert block is None


# ---------------------------------------------------------------------------
# Extra: channel without interactive
# ---------------------------------------------------------------------------

def test_no_interactive_when_channel_unsupported(channel_without_interactive):
    """Interactive not used when channel does not support it."""
    result = build_response(
        intent_key="welcome",
        lead_context={"collected_fields": []},
        channel_capabilities=channel_without_interactive,
    )

    # Even though welcome has interactive_type=list, channel doesn't support it
    assert result.interactive_type is None
    assert result.interactive_config is None
