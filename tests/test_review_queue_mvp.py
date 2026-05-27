"""Tests for refrimix_core/review/review_queue.py"""
from datetime import datetime, timedelta, timezone

import pytest

from refrimix_core.review.review_models import (
    ProposedChannel,
    ReviewItem,
    ReviewPriority,
    ReviewStatus,
)
from refrimix_core.review.review_queue import (
    ReviewQueue,
    ReviewQueueFilter,
    get_review_queue,
    reset_review_queue,
)


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
    expires_hours=24,
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
        expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours),
        updated_at=None,
    )


class TestSingleton:
    def test_get_review_queue_returns_singleton(self):
        q1 = get_review_queue()
        q2 = get_review_queue()
        assert q1 is q2


class TestCreateGet:
    def test_create_and_get(self):
        queue = get_review_queue()
        item = make_item(review_id="test1")
        queue.create(item)
        retrieved = queue.get("test1")
        assert retrieved is not None
        assert retrieved.review_id == "test1"

    def test_get_non_existent(self):
        queue = get_review_queue()
        result = queue.get("nonexistent")
        assert result is None


class TestListItems:
    def test_list_all(self):
        queue = get_review_queue()
        queue.create(make_item("item1"))
        queue.create(make_item("item2"))
        items = queue.list_items(ReviewQueueFilter.ALL)
        assert len(items) == 2

    def test_list_pending(self):
        queue = get_review_queue()
        queue.create(make_item("item1", status=ReviewStatus.PENDING))
        queue.create(make_item("item2", status=ReviewStatus.APPROVED))
        items = queue.list_items(ReviewQueueFilter.PENDING)
        assert len(items) == 1
        assert items[0].review_id == "item1"

    def test_list_urgent(self):
        queue = get_review_queue()
        queue.create(make_item("item1", priority=ReviewPriority.URGENT, intent="risco_eletrico"))
        queue.create(make_item("item2", priority=ReviewPriority.NORMAL))
        items = queue.list_items(ReviewQueueFilter.URGENT)
        assert len(items) == 1

    def test_list_risco_eletrico(self):
        queue = get_review_queue()
        queue.create(make_item("item1", intent="risco_eletrico"))
        queue.create(make_item("item2", intent="welcome"))
        items = queue.list_items(ReviewQueueFilter.RISCO_ELETRICO)
        assert len(items) == 1


class TestCount:
    def test_count_pending(self):
        queue = get_review_queue()
        queue.create(make_item("item1", status=ReviewStatus.PENDING))
        queue.create(make_item("item2", status=ReviewStatus.PENDING))
        queue.create(make_item("item3", status=ReviewStatus.APPROVED))
        count = queue.count(ReviewQueueFilter.PENDING)
        assert count == 2


class TestUpdateStatus:
    def test_update_status(self):
        queue = get_review_queue()
        item = make_item("item1", status=ReviewStatus.PENDING)
        queue.create(item)
        updated = queue.update_status("item1", ReviewStatus.APPROVED)
        assert updated is not None
        assert updated.status == ReviewStatus.APPROVED


class TestMarkSent:
    def test_mark_sent(self):
        queue = get_review_queue()
        item = make_item("item1", status=ReviewStatus.APPROVED)
        queue.create(item)
        updated = queue.mark_sent("item1", "final response")
        assert updated is not None
        assert updated.status == ReviewStatus.SENT
        assert updated.approved_response == "final response"


class TestExpirePending:
    def test_expire_pending(self):
        queue = get_review_queue()
        # Create item that's already expired
        expired_item = ReviewItem(
            review_id="expired1",
            conversation_id="conv_exp",
            lead_id="lead_exp",
            phone_hash="hash_exp",
            intent="welcome",
            risk="low",
            priority=ReviewPriority.LOW,
            user_message="old",
            user_message_preview="old",
            suggested_response="old response",
            proposed_channel=ProposedChannel.TEXT,
            response_modality="text",
            status=ReviewStatus.PENDING,
            created_at=datetime.now(timezone.utc) - timedelta(hours=48),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=24),
            updated_at=None,
        )
        queue.create(expired_item)
        queue.create(make_item("item2"))  # not expired
        count = queue.expire_pending()
        assert count == 1
        expired = queue.get("expired1")
        assert expired.status == ReviewStatus.EXPIRED


class TestStats:
    def test_stats(self):
        queue = get_review_queue()
        queue.create(make_item("item1", status=ReviewStatus.PENDING, priority=ReviewPriority.URGENT))
        queue.create(make_item("item2", status=ReviewStatus.APPROVED))
        stats = queue.stats()
        assert stats["total"] == 2
        assert stats["pending"] == 1
        assert stats["urgent"] == 1