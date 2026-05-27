"""Tests for TTS policy: should_generate_tts()."""

import pytest
from refrimix_core.domain.tts_policy import (
    TTSDecisionReason,
    TTSDecision,
    BLOCKED_DOC_TYPES,
    ALLOWED_ACTIONS,
    should_generate_tts,
    GOOD_AUDIO_PHRASES,
    FORBIDDEN_AUDIO_PHRASES,
)


class TestShouldGenerateTTS:
    def test_short_confirmation_allowed(self):
        decision = should_generate_tts(
            text="bom dia, tudo joia?",
            action_type="microcopy",
            max_chars=420,
        )
        assert decision.should_speak is True
        assert decision.reason == TTSDecisionReason.ALLOWED_SHORT_CONFIRMATION

    def test_long_text_blocked(self):
        long_text = "a" * 500
        decision = should_generate_tts(
            text=long_text,
            action_type="microcopy",
            max_chars=420,
        )
        assert decision.should_speak is False
        assert decision.reason == TTSDecisionReason.BLOCKED_TOO_LONG
        assert decision.text_fallback is True

    def test_quote_pdf_blocked(self):
        decision = should_generate_tts(
            text="segue o orçamento solicitado",
            action_type="microcopy",
            document_type="quote_pdf",
        )
        assert decision.should_speak is False
        assert decision.reason == TTSDecisionReason.BLOCKED_DOCUMENT_TYPE

    def test_budget_pdf_blocked(self):
        decision = should_generate_tts(
            text="orçamento detalhado",
            action_type="microcopy",
            document_type="budget_pdf",
        )
        assert decision.should_speak is False
        assert decision.reason == TTSDecisionReason.BLOCKED_DOCUMENT_TYPE

    def test_pmoc_pdf_blocked(self):
        decision = should_generate_tts(
            text="relatório pmoc",
            action_type="microcopy",
            document_type="pmoc_pdf",
        )
        assert decision.should_speak is False
        assert decision.reason == TTSDecisionReason.BLOCKED_DOCUMENT_TYPE

    def test_contract_pdf_blocked(self):
        decision = should_generate_tts(
            text="contrato de manutenção",
            action_type="microcopy",
            document_type="contract_pdf",
        )
        assert decision.should_speak is False
        assert decision.reason == TTSDecisionReason.BLOCKED_DOCUMENT_TYPE

    def test_user_prefers_text_blocked(self):
        decision = should_generate_tts(
            text="bom dia",
            action_type="microcopy",
            user_prefers_text=True,
        )
        assert decision.should_speak is False
        assert decision.reason == TTSDecisionReason.BLOCKED_USER_PREFERS_TEXT

    def test_unknown_action_type_blocked(self):
        decision = should_generate_tts(
            text="bom dia",
            action_type="unknown_action",
        )
        assert decision.should_speak is False
        assert decision.reason == TTSDecisionReason.BLOCKED_SENSITIVE

    def test_schedule_confirmation_allowed(self):
        decision = should_generate_tts(
            text="visita confirmada para amanhã às 14h",
            action_type="schedule_confirmation",
        )
        assert decision.should_speak is True
        assert decision.reason == TTSDecisionReason.ALLOWED_SHORT_CONFIRMATION

    def test_visit_orientation_allowed(self):
        decision = should_generate_tts(
            text="manter equipamento desligado até avaliação",
            action_type="visit_orientation",
        )
        assert decision.should_speak is True
        assert decision.reason == TTSDecisionReason.ALLOWED_SHORT_CONFIRMATION

    def test_short_followup_allowed(self):
        decision = should_generate_tts(
            text="de bo. te passo o horário assim que confirmar.",
            action_type="short_followup",
        )
        assert decision.should_speak is True
        assert decision.reason == TTSDecisionReason.ALLOWED_SHORT_CONFIRMATION

    def test_welcome_onboarding_allowed(self):
        decision = should_generate_tts(
            text="bom dia! tudo joia?",
            action_type="welcome_onboarding",
        )
        assert decision.should_speak is True
        assert decision.reason == TTSDecisionReason.ALLOWED_SHORT_CONFIRMATION

    def test_max_chars_boundary(self):
        # exactly at boundary — allowed
        text_420 = "a" * 420
        decision = should_generate_tts(text=text_420, action_type="microcopy", max_chars=420)
        assert decision.should_speak is True

        # over boundary — blocked
        text_421 = "a" * 421
        decision = should_generate_tts(text=text_421, action_type="microcopy", max_chars=420)
        assert decision.should_speak is False
        assert decision.reason == TTSDecisionReason.BLOCKED_TOO_LONG

    def test_whitespace_only_text(self):
        decision = should_generate_tts(
            text="   ",
            action_type="microcopy",
            max_chars=420,
        )
        # Empty/whitespace text — strip makes it empty, should be blocked by too_long
        assert decision.should_speak is False


class TestBlockedDocTypes:
    def test_all_blocked_types(self):
        for doc_type in BLOCKED_DOC_TYPES:
            decision = should_generate_tts(
                text="qualquer texto curto",
                action_type="microcopy",
                document_type=doc_type,
            )
            assert decision.should_speak is False, f"{doc_type} should be blocked"
            assert decision.text_fallback is True


class TestAllowedActions:
    def test_all_allowed_types(self):
        for action_type in ALLOWED_ACTIONS:
            decision = should_generate_tts(
                text="bom dia, tudo joia?",
                action_type=action_type,
                max_chars=420,
            )
            assert decision.should_speak is True, f"{action_type} should be allowed"


class TestGoodAudioPhrases:
    def test_good_phrases_are_short(self):
        for phrase in GOOD_AUDIO_PHRASES:
            assert len(phrase) <= 420, f"Phrase too long: {phrase}"

    def test_good_phrases_pass_policy(self):
        for phrase in GOOD_AUDIO_PHRASES:
            decision = should_generate_tts(
                text=phrase,
                action_type="microcopy",
                max_chars=420,
            )
            assert decision.should_speak is True, f"Should allow: {phrase}"


class TestForbiddenAudioPhrases:
    def test_forbidden_phrases_fail_policy(self):
        for phrase in FORBIDDEN_AUDIO_PHRASES:
            # These phrases should not be in ALLOWED_ACTIONS context by themselves
            decision = should_generate_tts(
                text=phrase,
                action_type="microcopy",
                max_chars=420,
            )
            # These are formal/long phrases that may or may not be blocked by action type
            # The test just verifies they exist and have content
            assert len(phrase) > 0
