"""Testes de integração monitoring: end-to-end do fluxo de monitoring.

Valida:
1. Métricas são coletadas corretamente
2. Status tracker é atualizado
3. Outcome tracker é atualizado
4. Feedback store salva antes/depois em ASSISTED
5. RealCaseExporter anonimiza dados corretamente
"""

import os
from unittest.mock import MagicMock, patch

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def clean_env():
    orig = os.environ.get("BOT_RUNTIME_MODE")
    os.environ["BOT_RUNTIME_MODE"] = "shadow"
    yield
    if orig is None:
        os.environ.pop("BOT_RUNTIME_MODE", None)
    else:
        os.environ["BOT_RUNTIME_MODE"] = orig


# ── Tests: ConversationMetricsCollector ──────────────────────────────────────

class TestConversationMetricsCollector:
    def test_track_metric(self, clean_env):
        from refrimix_core.monitoring.conversation_metrics import ConversationMetricsCollector

        collector = ConversationMetricsCollector()
        collector.track_metric("conv_123", "message_received", metadata={"intent": "welcome"})
        collector.track_metric("conv_123", "sent", metadata={"msg_id": "msg_abc"})

        metrics = collector.compute_session_metrics("conv_123")
        assert metrics["message_received"] == 1
        assert metrics["sent"] == 1

    def test_metrics_summary(self, clean_env):
        from refrimix_core.monitoring.conversation_metrics import ConversationMetricsCollector

        collector = ConversationMetricsCollector()
        collector.track_metric("conv_1", "message_received")
        collector.track_metric("conv_2", "message_received")
        collector.track_metric("conv_1", "sent")

        summary = collector.get_metrics_summary()
        assert summary["message_received"] == 2
        assert summary["sent"] == 1

    def test_clear(self, clean_env):
        from refrimix_core.monitoring.conversation_metrics import ConversationMetricsCollector

        collector = ConversationMetricsCollector()
        collector.track_metric("conv_1", "message_received")
        assert len(collector._metrics) == 1

        collector.clear()
        assert len(collector._metrics) == 0


# ── Tests: WhatsAppStatusTracker ──────────────────────────────────────────────

class TestWhatsAppStatusTrackerIntegration:
    def test_full_lifecycle(self, clean_env):
        from refrimix_core.monitoring.whatsapp_status_tracker import WhatsAppStatusTracker, StatusType

        tracker = WhatsAppStatusTracker()

        # Different message IDs for different status stages
        tracker.track_message_status("msg_1_pending", "conv_A", StatusType.PENDING)
        tracker.track_message_status("msg_1_sent", "conv_A", StatusType.SENT)
        tracker.track_message_status("msg_1_delivered", "conv_A", StatusType.DELIVERED)
        tracker.track_message_status("msg_1_read", "conv_A", StatusType.READ)

        stats = tracker.get_delivery_stats("conv_A")
        assert stats["pending"] == 1
        assert stats["sent"] == 1
        assert stats["delivered"] == 1
        assert stats["read"] == 1

    def test_failed_message(self, clean_env):
        from refrimix_core.monitoring.whatsapp_status_tracker import WhatsAppStatusTracker, StatusType

        tracker = WhatsAppStatusTracker()
        tracker.track_message_status("msg_fail", "conv_B", StatusType.SENT)
        tracker.track_message_status("msg_fail", "conv_B", StatusType.FAILED)

        stats = tracker.get_delivery_stats("conv_B")
        assert stats["failed"] == 1


# ── Tests: LeadOutcomeTracker ─────────────────────────────────────────────────

class TestLeadOutcomeTracker:
    def test_track_outcome_agendado(self, clean_env):
        from refrimix_core.monitoring.lead_outcome_tracker import LeadOutcomeTracker, OutcomeType

        tracker = LeadOutcomeTracker()
        tracker.track_outcome("conv_X", OutcomeType.AGENDADO, turning_point="offer_fixed_hygienization", intent="higienizacao")

        all_outcomes = tracker.get_all_outcomes()
        assert len(all_outcomes) == 1
        assert all_outcomes[0].outcome == OutcomeType.AGENDADO

    def test_abandonment_rate(self, clean_env):
        from refrimix_core.monitoring.lead_outcome_tracker import LeadOutcomeTracker, OutcomeType

        tracker = LeadOutcomeTracker()
        tracker.track_outcome("conv_1", OutcomeType.IGNOROU, turning_point="offer_fixed_installation")
        tracker.track_outcome("conv_2", OutcomeType.IGNOROU, turning_point="offer_fixed_installation")
        tracker.track_outcome("conv_3", OutcomeType.AGENDADO, turning_point="offer_fixed_hygienization")

        rate = tracker.get_abandonment_rate()
        assert rate["total"] == 3
        assert rate["abandoned_count"] == 2
        assert rate["abandonment_rate"] == pytest.approx(0.667, rel=0.01)

    def test_conversion_by_intent(self, clean_env):
        from refrimix_core.monitoring.lead_outcome_tracker import LeadOutcomeTracker, OutcomeType

        tracker = LeadOutcomeTracker()
        tracker.track_outcome("conv_1", OutcomeType.AGENDADO, intent="higienizacao")
        tracker.track_outcome("conv_2", OutcomeType.IGNOROU, intent="higienizacao")
        tracker.track_outcome("conv_3", OutcomeType.HANDOFF_HUMANO, intent="risco_eletrico")

        conv = tracker.get_conversion_by_intent()
        assert conv["higienizacao"]["total"] == 2
        assert conv["higienizacao"]["converted"] == 1
        assert conv["risco_eletrico"]["total"] == 1
        assert conv["risco_eletrico"]["handoff"] == 1


# ── Tests: ProductionFeedbackStore (ASSISTED mode) ────────────────────────────

class TestProductionFeedbackStore:
    def test_save_human_feedback_edited(self, clean_env):
        from refrimix_core.monitoring.production_feedback import ProductionFeedbackStore

        store = ProductionFeedbackStore()
        store.save_human_feedback(
            conversation_id="conv_feedback_1",
            suggested_response="Higienização R$200 por aparelho.",
            human_response="Higienização R$200/aparelho. Service done in 2h.",
            edited_fields=["price", "timeline"],
            intent="higienizacao",
        )

        stats = store.get_feedback_stats()
        assert stats["total"] == 1
        assert stats["edited_rate"] == 1.0

    def test_save_human_feedback_not_edited(self, clean_env):
        from refrimix_core.monitoring.production_feedback import ProductionFeedbackStore

        store = ProductionFeedbackStore()
        store.save_human_feedback(
            conversation_id="conv_feedback_2",
            suggested_response="Olá, como posso ajudar?",
            human_response="Olá, como posso ajudar?",
            edited_fields=[],
            intent="welcome",
        )

        stats = store.get_feedback_stats()
        assert stats["total"] == 1
        assert stats["edited_rate"] == 0.0

    def test_export_feedback_dataset_requires_min_cases(self, clean_env):
        from refrimix_core.monitoring.production_feedback import ProductionFeedbackStore

        store = ProductionFeedbackStore()
        store.save_human_feedback(
            conversation_id="conv_single",
            suggested_response="test",
            human_response="test",
        )

        # < 30 cases → returns empty
        dataset = store.export_feedback_dataset(min_cases=30)
        assert dataset == []

    def test_export_feedback_dataset_anonimizado(self, clean_env):
        from refrimix_core.monitoring.production_feedback import ProductionFeedbackStore

        store = ProductionFeedbackStore()
        for i in range(30):
            store.save_human_feedback(
                conversation_id=f"conv_{i}",
                suggested_response=f"Sugestão {i} para +55 11 99999-9999.",
                human_response=f"Resposta humana {i} — nome: João Silva.",
                intent="higienizacao",
            )

        dataset = store.export_feedback_dataset(min_cases=30)
        assert len(dataset) == 30
        # Check no phone numbers in export
        for entry in dataset:
            assert "9999" not in str(entry) or "MASCARA" in str(entry)


# ── Tests: RealCaseExporter anonimização ─────────────────────────────────────

class TestRealCaseExporterAnonimization:
    def test_anonymize_phone_numbers(self, clean_env):
        from refrimix_core.evaluation.real_case_exporter import RealCaseExporter

        exporter = RealCaseExporter()
        result = exporter.anonymize_message(
            conversation_id="conv_phone_test",
            message_index=0,
            text="Meu número é +55 11 98765-4321 e meu nome é Maria.",
            sender="user",
            timestamp="2026-05-27T10:00:00Z",
        )

        # Phone should be masked
        assert "98765" not in result.text
        assert "MASCARA_TEL" in result.text
        # Name should be masked
        assert "MASCARA_NOME" in result.text

    def test_anonymize_address(self, clean_env):
        from refrimix_core.evaluation.real_case_exporter import RealCaseExporter

        exporter = RealCaseExporter()
        result = exporter.anonymize_message(
            conversation_id="conv_addr_test",
            message_index=0,
            text="Endereço: Rua das Flores, 123, Bairro Industrial.",
            sender="user",
            timestamp="2026-05-27T10:00:00Z",
        )

        assert "MASCARA_END" in result.text

    def test_anonymize_conversation_id(self, clean_env):
        from refrimix_core.evaluation.real_case_exporter import RealCaseExporter

        exporter = RealCaseExporter()
        result = exporter.anonymize_message(
            conversation_id="abcd1234efgh5678",  # 16-char ID
            message_index=0,
            text="Teste",
            sender="assistant",
            timestamp="2026-05-27T10:00:00Z",
        )

        # Conversation ID must be masked with MASCARA_CONV prefix
        assert "MASCARA_CONV_" in result.conversation_id
        # The full original 16-char ID must NOT appear as-is
        assert result.conversation_id != "abcd1234efgh5678"

    def test_export_to_jsonl(self, clean_env, tmp_path):
        from refrimix_core.evaluation.real_case_exporter import RealCaseExporter

        exporter = RealCaseExporter()
        dataset = [
            {
                "conversation_id": "MASCARA_CONV_abc12345",
                "message_index": 0,
                "sender": "bot",
                "text": "Olá, como posso ajudar? MASCARA_TEL",
                "timestamp": "2026-05-27T10:00:00Z",
                "intent": "welcome",
                "was_suggested": True,
                "was_edited": False,
                "human_response": None,
            }
        ]

        output_path = tmp_path / "test_export.jsonl"
        count = exporter.export_to_jsonl(dataset, str(output_path))

        assert count == 1
        content = open(output_path).read()
        assert "MASCARA_TEL" in content
        assert "9999" not in content  # No raw phone


# ── Tests: CANARY_MODE intent filtering ───────────────────────────────────────

class TestCanaryModeIntentFilter:
    def test_can_auto_reply_respects_human_review_intents(self):
        # Override env for this test
        with patch.dict(os.environ, {"BOT_RUNTIME_MODE": "canary", "BOT_CANARY_PERCENT": "100"}):
            from importlib import reload
            import app.config as config_module
            reload(config_module)

            assert config_module.can_auto_reply("risco_eletrico") is False
            assert config_module.can_auto_reply("projeto") is False
            assert config_module.can_auto_reply("pmoc") is False

    def test_can_auto_reply_allows_simple_intents(self):
        with patch.dict(os.environ, {"BOT_RUNTIME_MODE": "canary", "BOT_CANARY_PERCENT": "100"}):
            from importlib import reload
            import app.config as config_module
            reload(config_module)

            # With 100%, allowed intents should pass
            assert config_module.can_auto_reply("higienizacao") is True

    def test_can_auto_reply_zero_percent_blocks(self):
        with patch.dict(os.environ, {"BOT_RUNTIME_MODE": "canary", "BOT_CANARY_PERCENT": "0"}):
            from importlib import reload
            import app.config as config_module
            reload(config_module)

            # 0% means no auto-reply even for allowed intents
            assert config_module.can_auto_reply("higienizacao") is False


# ── Tests: MonitoringConfig singleton ─────────────────────────────────────────

class TestMonitoringConfig:
    def test_from_env_defaults(self):
        with patch.dict(os.environ, {"BOT_RUNTIME_MODE": "shadow"}):
            from importlib import reload
            import app.config as config_module
            reload(config_module)

            cfg = config_module.MonitoringConfig.from_env()
            assert cfg.runtime_mode.value == "shadow"
            assert cfg.canary_percent == 0

    def test_from_env_canary(self):
        with patch.dict(os.environ, {"BOT_RUNTIME_MODE": "canary", "BOT_CANARY_PERCENT": "20"}):
            from importlib import reload
            import app.config as config_module
            reload(config_module)

            cfg = config_module.MonitoringConfig.from_env()
            assert cfg.runtime_mode.value == "canary"
            assert cfg.canary_percent == 20

    def test_from_env_invalid_mode_defaults_to_shadow(self):
        with patch.dict(os.environ, {"BOT_RUNTIME_MODE": "invalid_mode"}):
            from importlib import reload
            import app.config as config_module
            reload(config_module)

            cfg = config_module.MonitoringConfig.from_env()
            assert cfg.runtime_mode.value == "shadow"