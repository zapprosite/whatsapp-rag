"""Testes para SHADOW_MODE: gera resposta mas não envia ao cliente."""
# encoding: utf-8

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def shadow_env():
    """Força BOT_RUNTIME_MODE=shadow para todos os testes."""
    os.environ["BOT_RUNTIME_MODE"] = "shadow"
    os.environ["MINIMAL_MVP_ENABLED"] = "1"
    yield
    # restore
    os.environ.pop("BOT_RUNTIME_MODE", None)
    os.environ.pop("MINIMAL_MVP_ENABLED", None)


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1)
    r.lrem = AsyncMock()
    r.lpush = AsyncMock()
    return r


@pytest.fixture
def mock_metrics():
    collector = MagicMock()
    collector.track_metric = MagicMock()
    return collector


@pytest.fixture
def mock_status_tracker():
    tracker = MagicMock()
    tracker.track_message_status = MagicMock()
    return tracker


@pytest.fixture
def mock_feedback():
    store = MagicMock()
    store.save_human_feedback = MagicMock()
    return store


@pytest.fixture
def mock_outcome():
    tracker = MagicMock()
    tracker.track_outcome = MagicMock()
    return tracker


class TestShadowConfig:
    def test_is_shadow_mode_true(self):
        from app.runtime_config import is_shadow_mode
        assert is_shadow_mode() is True

    def test_is_canary_false(self):
        from app.runtime_config import is_canary_mode
        assert is_canary_mode() is False

    def test_is_assisted_false(self):
        from app.runtime_config import is_assisted_mode
        assert is_assisted_mode() is False

    def test_runtime_mode_is_shadow(self):
        from app.runtime_config import get_runtime_config
        assert get_runtime_config().runtime_mode.value == "shadow"


class TestIntentFilter:
    def test_human_review_required(self):
        from app.runtime_config import IntentFilter
        assert IntentFilter.requires_human_review("risco_eletrico") is True
        assert IntentFilter.requires_human_review("projeto") is True
        assert IntentFilter.requires_human_review("pmoc") is True

    def test_auto_allowed(self):
        from app.runtime_config import IntentFilter
        assert IntentFilter.is_auto_allowed("higienizacao") is True
        assert IntentFilter.is_auto_allowed("visita_tecnica") is True

    def test_risco_not_auto_allowed(self):
        from app.runtime_config import IntentFilter
        assert IntentFilter.is_auto_allowed("risco_eletrico") is False


class TestFromMe:
    def test_from_me_true_returns_none(self):
        from app.api.webhook import parse_evolution_webhook
        body = {
            "event": "messages.upsert",
            "data": {
                "key": {"fromMe": True, "remoteJid": "5511999999999@s.whatsapp.net", "id": "msg_123"},
                "message": {"conversation": "olá"},
            },
        }
        parsed, skipped = parse_evolution_webhook(body)
        assert parsed is None
        assert skipped == "fromMe"


class TestStatusWebhookSkip:
    @pytest.mark.anyio
    async def test_no_message_id_skipped(self, mock_redis):
        from app.api.webhook import receive_status_webhook
        body = {
            "event": "messages.update",
            "data": {"update": {"status": "delivered"}},
        }
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value=body)
        with patch("app.api.webhook.get_redis", AsyncMock(return_value=mock_redis)):
            response = await receive_status_webhook(mock_request)
        assert response.status_code == 200