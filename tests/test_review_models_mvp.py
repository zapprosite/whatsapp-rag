"""Tests for refrimix_core/review/review_models.py"""
from datetime import datetime, timedelta, timezone

import pytest

from refrimix_core.review.review_models import (
    ProposedChannel,
    ReviewItem,
    ReviewPriority,
    ReviewStatus,
    _classify_priority,
    _mask_phone,
)


class TestEnums:
    def test_review_status_values(self):
        assert ReviewStatus.PENDING.value == "pending"
        assert ReviewStatus.APPROVED.value == "approved"
        assert ReviewStatus.EDITED.value == "edited"
        assert ReviewStatus.REJECTED.value == "rejected"
        assert ReviewStatus.EXPIRED.value == "expired"
        assert ReviewStatus.SENT.value == "sent"

    def test_review_priority_values(self):
        assert ReviewPriority.LOW.value == "low"
        assert ReviewPriority.NORMAL.value == "normal"
        assert ReviewPriority.HIGH.value == "high"
        assert ReviewPriority.URGENT.value == "urgent"

    def test_proposed_channel_values(self):
        assert ProposedChannel.TEXT.value == "text"
        assert ProposedChannel.AUDIO.value == "audio"
        assert ProposedChannel.PDF.value == "pdf"


class TestClassifyPriority:
    def test_risco_eletrico_urgent(self):
        assert _classify_priority("risco_eletrico", "") == ReviewPriority.URGENT
        assert _classify_priority("risco", "") == ReviewPriority.URGENT
        assert _classify_priority("eletrico", "") == ReviewPriority.URGENT
        assert _classify_priority("unknown", "risco de choque") == ReviewPriority.URGENT

    def test_projeto_pmoc_high(self):
        assert _classify_priority("projeto", "") == ReviewPriority.HIGH
        assert _classify_priority("pmoc", "") == ReviewPriority.HIGH
        assert _classify_priority("laudo", "") == ReviewPriority.HIGH
        assert _classify_priority("contrato", "") == ReviewPriority.HIGH
        assert _classify_priority("proposta", "") == ReviewPriority.HIGH

    def test_manutencao_normal(self):
        assert _classify_priority("manutencao", "") == ReviewPriority.NORMAL
        assert _classify_priority("conserto", "") == ReviewPriority.NORMAL
        assert _classify_priority("visita_tecnica", "") == ReviewPriority.NORMAL

    def test_welcome_low(self):
        assert _classify_priority("welcome", "") == ReviewPriority.LOW
        assert _classify_priority("saudacao", "") == ReviewPriority.LOW


class TestMaskPhone:
    def test_masks_phone(self):
        result = _mask_phone("5511987654321")
        assert "..." in result
        assert len(result) <= 12  # 4 + ... + 4

    def test_short_phone(self):
        result = _mask_phone("1234")
        assert result == "<masked>"


class TestReviewItem:
    def test_to_display_dict_no_raw_phone(self):
        item = ReviewItem(
            review_id="abc123",
            conversation_id="conv1",
            lead_id="lead1",
            phone_hash="hash123",
            intent="welcome",
            risk="low",
            priority=ReviewPriority.LOW,
            user_message="oi",
            user_message_preview="oi",
            suggested_response="Olá!",
            proposed_channel=ProposedChannel.TEXT,
            response_modality="text",
            status=ReviewStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            updated_at=None,
        )
        d = item.to_display_dict()
        assert "5511" not in str(d)
        assert "123456" not in str(d)  # no raw digits in any field

    def test_from_worker_response(self):
        item = ReviewItem.from_worker_response(
            phone="5511987654321",
            conversation_id="conv1",
            user_message="Olá, meu ar não gela",
            ai_response="Vou verificar seu equipamento",
            intent="manutencao",
            risk="medium",
            msg_id="msg123",
            response_modality="text",
        )
        assert item.status == ReviewStatus.PENDING
        assert item.intent == "manutencao"
        assert item.priority == ReviewPriority.NORMAL
        assert item.review_id != ""
        assert item.conversation_id == "conv1"

    def test_is_expired_false(self):
        item = ReviewItem(
            review_id="abc",
            conversation_id="c1",
            lead_id="l1",
            phone_hash="h1",
            intent="welcome",
            risk="low",
            priority=ReviewPriority.LOW,
            user_message="oi",
            user_message_preview="oi",
            suggested_response="Oi",
            proposed_channel=ProposedChannel.TEXT,
            response_modality="text",
            status=ReviewStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            updated_at=None,
        )
        assert item.is_expired() is False

    def test_is_expired_true(self):
        item = ReviewItem(
            review_id="abc",
            conversation_id="c1",
            lead_id="l1",
            phone_hash="h1",
            intent="welcome",
            risk="low",
            priority=ReviewPriority.LOW,
            user_message="oi",
            user_message_preview="oi",
            suggested_response="Oi",
            proposed_channel=ProposedChannel.TEXT,
            response_modality="text",
            status=ReviewStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            updated_at=None,
        )
        assert item.is_expired() is True