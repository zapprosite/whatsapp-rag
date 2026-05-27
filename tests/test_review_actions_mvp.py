"""Tests for refrimix_core/review/review_actions.py"""
from datetime import datetime, timedelta, timezone

import pytest

from refrimix_core.review.review_models import (
    ProposedChannel,
    ReviewItem,
    ReviewPriority,
    ReviewStatus,
)
from refrimix_core.review.review_actions import (
    approve_item,
    edit_item,
    expire_all_pending,
    get_pending_count,
    mark_expired,
    reject_item,
    send_item,
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


class TestApproveItem:
    def test_approve_pending_item(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = approve_item("item1")
        assert result.success is True
        assert result.should_send is True
        assert result.review_item is not None
        assert result.review_item.status == ReviewStatus.APPROVED

    def test_approve_with_edit(self):
        queue = get_review_queue()
        item = make_item("item2")
        queue.create(item)

        result = approve_item("item2", edited_response="edited text")
        assert result.success is True
        assert result.review_item.status == ReviewStatus.EDITED

    def test_approve_nonexistent(self):
        result = approve_item("nonexistent")
        assert result.success is False
        assert result.error == "not_found"


class TestEditItem:
    def test_edit_item(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = edit_item("item1", "new response text")
        assert result.success is True
        assert result.should_send is True
        assert result.review_item.status == ReviewStatus.EDITED

    def test_edit_empty_response_fails(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = edit_item("item1", "")
        assert result.success is False
        assert result.error == "empty_response"

    def test_edit_nonexistent(self):
        result = edit_item("nonexistent", "new response")
        assert result.success is False


class TestRejectItem:
    def test_reject_item_with_reason(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = reject_item("item1", "Cliente resolveu sozinho")
        assert result.success is True
        assert result.should_send is False
        assert result.review_item.status == ReviewStatus.REJECTED

    def test_reject_empty_reason_fails(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = reject_item("item1", "")
        assert result.success is False
        assert result.error == "empty_reason"


class TestSendItem:
    def test_send_approved_item(self):
        queue = get_review_queue()
        item = make_item("item1", status=ReviewStatus.APPROVED)
        queue.create(item)

        result = send_item("item1")
        assert result.success is True

    def test_send_pending_item_fails(self):
        queue = get_review_queue()
        item = make_item("item1", status=ReviewStatus.PENDING)
        queue.create(item)

        result = send_item("item1")
        assert result.success is False
        assert result.error == "invalid_status"

    def test_send_nonexistent(self):
        result = send_item("nonexistent")
        assert result.success is False


class TestMarkExpired:
    def test_mark_expired(self):
        queue = get_review_queue()
        item = make_item("item1")
        queue.create(item)

        result = mark_expired("item1")
        assert result.success is True
        assert result.review_item.status == ReviewStatus.EXPIRED


class TestExpireAllPending:
    def test_expire_all_pending(self):
        queue = get_review_queue()
        # Create expired item
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
        queue.create(make_item("item2"))  # not expired

        count = expire_all_pending()
        assert count == 1


class TestGetPendingCount:
    def test_get_pending_count(self):
        queue = get_review_queue()
        queue.create(make_item("item1", status=ReviewStatus.PENDING))
        queue.create(make_item("item2", status=ReviewStatus.PENDING))
        queue.create(make_item("item3", status=ReviewStatus.APPROVED))

        count = get_pending_count()
        assert count == 2