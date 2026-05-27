"""Testes para conversation_metrics.py."""

import pytest
from datetime import datetime, timezone, timedelta
from refrimix_core.monitoring.conversation_metrics import (
    ConversationMetricsCollector,
    MetricEntry,
)


class TestConversationMetricsCollector:
    """Testes para ConversationMetricsCollector."""

    def test_track_metric_adiciona_entrada(self):
        """track_metric adiciona uma entrada à lista."""
        collector = ConversationMetricsCollector()
        collector.track_metric("conv_001", "sent")
        assert len(collector._metrics) == 1
        entry = collector._metrics[0]
        assert entry.conversation_id == "conv_001"
        assert entry.metric_name == "sent"
        assert entry.value == 1

    def test_track_metric_com_metadata(self):
        """track_metric aceita metadata opcional."""
        collector = ConversationMetricsCollector()
        collector.track_metric("conv_002", "read", metadata={"message_id": "msg_123"})
        entry = collector._metrics[0]
        assert entry.metadata == {"message_id": "msg_123"}

    def test_compute_session_metrics_agrega_corretamente(self):
        """compute_session_metrics soma valores por conversation_id."""
        collector = ConversationMetricsCollector()
        collector.track_metric("conv_001", "sent")
        collector.track_metric("conv_001", "delivered")
        collector.track_metric("conv_001", "delivered")
        collector.track_metric("conv_002", "sent")
        metrics = collector.compute_session_metrics("conv_001")
        assert metrics["sent"] == 1
        assert metrics["delivered"] == 2

    def test_compute_session_metrics_sem_conversa_retorna_vazio(self):
        """compute_session_metrics para conversa inexistente retorna {}."""
        collector = ConversationMetricsCollector()
        metrics = collector.compute_session_metrics("inexistente")
        assert metrics == {}

    def test_get_metrics_summary_agrega_tudo(self):
        """get_metrics_summary agrega todas as conversas."""
        collector = ConversationMetricsCollector()
        collector.track_metric("conv_001", "sent")
        collector.track_metric("conv_001", "read")
        collector.track_metric("conv_002", "sent")
        collector.track_metric("conv_003", "failed")
        summary = collector.get_metrics_summary()
        assert summary["sent"] == 2
        assert summary["read"] == 1
        assert summary["failed"] == 1

    def test_get_metrics_summary_com_time_range_filtra(self):
        """get_metrics_summary com time_range filtra por período."""
        collector = ConversationMetricsCollector()
        agora = datetime.now(timezone.utc)
        # Track before computing so timestamp is within range
        collector.track_metric("conv_001", "sent")
        agora = datetime.now(timezone.utc)
        # Use a generous range that definitely covers the entry we just added
        metrics = collector.get_metrics_summary(time_range=(agora - timedelta(hours=1), agora + timedelta(hours=1)))
        assert "sent" in metrics, f"expected 'sent' in metrics, got {metrics}"

    def test_clear_remove_todas_metricas(self):
        """clear() remove todas as métricas."""
        collector = ConversationMetricsCollector()
        collector.track_metric("conv_001", "sent")
        collector.track_metric("conv_002", "delivered")
        collector.clear()
        assert len(collector._metrics) == 0

    def test_multiple_metrics_same_name_acumula(self):
        """Múltiplas chamadas ao mesmo metric_name acumulam valor."""
        collector = ConversationMetricsCollector()
        collector.track_metric("conv_001", "sent")
        collector.track_metric("conv_001", "sent")
        collector.track_metric("conv_001", "sent", value=2)
        session = collector.compute_session_metrics("conv_001")
        assert session["sent"] == 4