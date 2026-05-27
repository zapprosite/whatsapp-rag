"""Tests for app/api/review.py — route handlers.

These test the review actions integration. Full API integration tests
(TestClient) require the full FastAPI app context which has complex startup
dependencies. Here we test the action functions and queue integration directly.
"""
from datetime import datetime, timedelta, timezone

import pytest

from refrimix_core.review.review_actions import (
    approve_item,
    edit_item,
    expire_all_pending,
    get_pending_count,
    mark_expired,
    reject_item,
    send_item,
)
from refrimix_core.review.review_models import (
    ProposedChannel,
    ReviewItem,
    ReviewPriority,
    ReviewStatus,
)
from refrimix_core.review.review_queue import get_review_queue, reset_review_queue


@pytest.fixture(autouse=True)
def clean_queue():
    reset_review_queue()
    yield
    reset_review_queue()


def make_item(
    review_id="r1",
    status=ReviewStatus.PENDING,
    priority=ReviewPriority.NORMAL,
    intent="manutencao",
    proposed_channel=ProposedChannel.TEXT,
):
    return ReviewItem(
        review_id=review_id,
        conversation_id=f"conv_{review_id}",
        lead_id=f"lead_{review_id}",
        phone_hash=f"hash_{review_id}",
        intent=intent,
        risk="medium",
        priority=priority,
        user_message="test message",
        user_message_preview="test message",
        suggested_response="suggested response",
        proposed_channel=proposed_channel,
        response_modality="text",
        status=status,
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        updated_at=None,
    )


class TestReviewQueueIntegration:
    """Tests that verify review queue + actions integration."""

    def test_queue_approve_creates_pending_item(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = approve_item("item1")
        assert result.success is True
        assert result.should_send is True
        updated = queue.get("item1")
        assert updated.status == ReviewStatus.APPROVED

    def test_queue_edit_creates_edited_item(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = edit_item("item1", "humans edited response")
        assert result.success is True
        assert result.should_send is True
        updated = queue.get("item1")
        assert updated.status == ReviewStatus.EDITED

    def test_queue_reject_saves_reason(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = reject_item("item1", "cliente resolveu sozinho")
        assert result.success is True
        assert result.should_send is False
        updated = queue.get("item1")
        assert updated.status == ReviewStatus.REJECTED
        assert updated.edit_reason == "cliente resolveu sozinho"

    def test_send_after_edit_flow(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        # Edit first
        edit_result = edit_item("item1", "fixed response")
        assert edit_result.success is True

        # Then send
        send_result = send_item("item1")
        assert send_result.success is True
        updated = queue.get("item1")
        assert updated.status == ReviewStatus.SENT

    def test_send_approved_direct(self):
        queue = get_review_queue()
        item = make_item("item1", status=ReviewStatus.APPROVED)
        queue.create(item)

        result = send_item("item1")
        assert result.success is True

    def test_cannot_send_pending(self):
        queue = get_review_queue()
        item = make_item("item1", status=ReviewStatus.PENDING)
        queue.create(item)

        result = send_item("item1")
        assert result.success is False

    def test_mark_expired_manual(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = mark_expired("item1")
        assert result.success is True
        updated = queue.get("item1")
        assert updated.status == ReviewStatus.EXPIRED

    def test_expire_all_pending(self):
        queue = get_review_queue()
        # Expired item
        expired_item = ReviewItem(
            review_id="expired1",
            conversation_id="conv_e",
            lead_id="lead_e",
            phone_hash="hash_e",
            intent="welcome",
            risk="low",
            priority=ReviewPriority.LOW,
            user_message="old",
            user_message_preview="old",
            suggested_response="old",
            proposed_channel=ProposedChannel.TEXT,
            response_modality="text",
            status=ReviewStatus.PENDING,
            created_at=datetime.now(timezone.utc) - timedelta(hours=48),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=24),
            updated_at=None,
        )
        queue.create(expired_item)
        # Not expired
        queue.create(make_item("item2"))

        count = expire_all_pending()
        assert count == 1

    def test_pending_count(self):
        queue = get_review_queue()
        queue.create(make_item("p1", status=ReviewStatus.PENDING))
        queue.create(make_item("p2", status=ReviewStatus.PENDING))
        queue.create(make_item("a1", status=ReviewStatus.APPROVED))

        count = get_pending_count()
        assert count == 2

    def test_reject_empty_reason_fails(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = reject_item("item1", "")
        assert result.success is False
        assert result.error == "empty_reason"

    def test_edit_empty_response_fails(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = edit_item("item1", "")
        assert result.success is False
        assert result.error == "empty_response"

    def test_approve_nonexistent_fails(self):
        result = approve_item("nonexistent")
        assert result.success is False
        assert result.error == "not_found"

    def test_send_nonexistent_fails(self):
        result = send_item("nonexistent")
        assert result.success is False
        assert result.error == "not_found"