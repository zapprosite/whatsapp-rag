"""Tests for refrimix_core/review/review_policy.py"""

import pytest

from refrimix_core.review.review_models import ProposedChannel, ReviewPriority, ReviewStatus
from refrimix_core.review.review_policy import (
    evaluate_audio_policy,
    evaluate_document_policy,
    get_priority_label,
    get_status_label,
    intent_is_auto_allowed,
    intent_requires_human_review,
)


class TestIntentRequiresHumanReview:
    def test_risco_eletrico_true(self):
        assert intent_requires_human_review("risco_eletrico") is True

    def test_risco_alone_not_in_human_review_set(self):
        # "risco" alone is not in the set, only full intent names like "risco_eletrico"
        assert intent_requires_human_review("risco") is False

    def test_projeto_true(self):
        assert intent_requires_human_review("projeto") is True
        assert intent_requires_human_review("pmoc") is True

    def test_welcome_false(self):
        assert intent_requires_human_review("welcome") is False
        assert intent_requires_human_review("higienizacao") is False

    def test_none_intent(self):
        assert intent_requires_human_review(None) is False


class TestIntentIsAutoAllowed:
    def test_welcome_true(self):
        assert intent_is_auto_allowed("welcome") is True
        assert intent_is_auto_allowed("higienizacao") is True

    def test_risco_eletrico_false(self):
        assert intent_is_auto_allowed("risco_eletrico") is False


class TestEvaluateAudioPolicy:
    def test_non_audio_allowed(self):
        result = evaluate_audio_policy("short text", ProposedChannel.TEXT, "welcome")
        assert result.allowed is True

    def test_text_too_long_blocks(self):
        long_text = "a" * 350
        result = evaluate_audio_policy(long_text, ProposedChannel.AUDIO, "welcome")
        assert result.allowed is False
        assert result.blocked_reason == "texto_longo"

    def test_text_too_short_blocks(self):
        result = evaluate_audio_policy("oi", ProposedChannel.AUDIO, "welcome")
        assert result.allowed is False
        assert result.blocked_reason == "texto_curto"

    def test_risco_intent_blocks_audio(self):
        result = evaluate_audio_policy("medium text here", ProposedChannel.AUDIO, "risco_eletrico")
        assert result.allowed is False
        assert result.blocked_reason == "intent_risco"

    def test_adequate_audio_allowed(self):
        # Text between 50-150 chars is adequate for audio
        medium_text = "Olá, tudo bem com seu equipamento? Preciso agendar uma visita técnica para manutenção do ar condicionado."
        result = evaluate_audio_policy(medium_text, ProposedChannel.AUDIO, "manutencao")
        assert result.allowed is True


class TestEvaluateDocumentPolicy:
    def test_pdf_blocked(self):
        result = evaluate_document_policy(ProposedChannel.PDF)
        assert result is False

    def test_text_allowed(self):
        result = evaluate_document_policy(ProposedChannel.TEXT)
        assert result is True

    def test_audio_allowed(self):
        result = evaluate_document_policy(ProposedChannel.AUDIO)
        assert result is True


class TestGetPriorityLabel:
    def test_urgent_label(self):
        label = get_priority_label(ReviewPriority.URGENT)
        assert "Urgente" in label

    def test_high_label(self):
        label = get_priority_label(ReviewPriority.HIGH)
        assert "Alto" in label

    def test_normal_label(self):
        label = get_priority_label(ReviewPriority.NORMAL)
        assert "Normal" in label

    def test_low_label(self):
        label = get_priority_label(ReviewPriority.LOW)
        assert "Baixa" in label


class TestGetStatusLabel:
    def test_pending_label(self):
        label = get_status_label(ReviewStatus.PENDING)
        assert "Pendente" in label

    def test_approved_label(self):
        label = get_status_label(ReviewStatus.APPROVED)
        assert "Aprovado" in label

    def test_rejected_label(self):
        label = get_status_label(ReviewStatus.REJECTED)
        assert "Rejeitado" in label

    def test_sent_label(self):
        label = get_status_label(ReviewStatus.SENT)
        assert "Enviado" in label