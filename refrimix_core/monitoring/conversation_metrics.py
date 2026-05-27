"""Coleta e agregação de métricas de conversa em produção.

Métricas monitoradas:
- sent, delivered, read, failed
- user_replied
- appointment_offered, appointment_scheduled
- human_handoff, guardrail_blocked
- audio_sent, audio_failed, text_fallback_sent
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class MetricEntry:
    """Entrada individual de métrica."""
    conversation_id: str
    metric_name: str
    value: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[dict] = None


class ConversationMetricsCollector:
    """Coletor de métricas em memória (substituir por Postgres em produção)."""

    def __init__(self):
        self._metrics: list[MetricEntry] = []

    def track_metric(
        self,
        conversation_id: str,
        metric_name: str,
        value: int = 1,
        metadata: Optional[dict] = None,
    ) -> None:
        """Registra uma métrica para uma conversa."""
        entry = MetricEntry(
            conversation_id=conversation_id,
            metric_name=metric_name,
            value=value,
            metadata=metadata,
        )
        self._metrics.append(entry)

    def compute_session_metrics(self, conversation_id: str) -> dict:
        """Agrega métricas de uma conversa específica."""
        entries = [e for e in self._metrics if e.conversation_id == conversation_id]
        result: dict[str, int] = {}
        for entry in entries:
            if entry.metric_name not in result:
                result[entry.metric_name] = 0
            result[entry.metric_name] += entry.value
        return result

    def get_metrics_summary(
        self,
        time_range: Optional[tuple[datetime, datetime]] = None,
    ) -> dict:
        """Retorna métricas agregadas por todas as conversas no período."""
        if time_range:
            start, end = time_range
            entries = [e for e in self._metrics if start <= e.timestamp <= end]
        else:
            entries = self._metrics

        summary: dict[str, int] = {}
        for entry in entries:
            if entry.metric_name not in summary:
                summary[entry.metric_name] = 0
            summary[entry.metric_name] += entry.value
        return summary

    def clear(self) -> None:
        """Limpa todas as métricas (uso em testes)."""
        self._metrics.clear()