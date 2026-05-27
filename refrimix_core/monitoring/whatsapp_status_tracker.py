"""Rastreador de status de mensagens WhatsApp.

StatusTypes:
- pending: mensagem pendente
- sent: enviada ao WhatsApp
- delivered: entregue ao cliente
- read: lida pelo cliente
- failed: falha no envio
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class StatusType(str, Enum):
    """Status possíveis de mensagem WhatsApp."""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


@dataclass(frozen=True)
class MessageStatusEntry:
    """Status de uma mensagem específica."""
    message_id: str
    conversation_id: str
    status: StatusType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None


class WhatsAppStatusTracker:
    """Rastreador de status de mensagens (substituir por Postgres em produção)."""

    def __init__(self):
        self._statuses: list[MessageStatusEntry] = []

    def track_message_status(
        self,
        message_id: str,
        conversation_id: str,
        status: StatusType,
        error_message: Optional[str] = None,
    ) -> None:
        """Registra status de uma mensagem."""
        entry = MessageStatusEntry(
            message_id=message_id,
            conversation_id=conversation_id,
            status=status,
            error_message=error_message,
        )
        self._statuses.append(entry)

    def get_delivery_stats(self, conversation_id: str) -> dict:
        """Retorna estatísticas de entrega para uma conversa."""
        entries = [e for e in self._statuses if e.conversation_id == conversation_id]
        counts = {s.value: 0 for s in StatusType}
        for entry in entries:
            counts[entry.status.value] += 1
        return {
            "conversation_id": conversation_id,
            "pending": counts[StatusType.PENDING.value],
            "sent": counts[StatusType.SENT.value],
            "delivered": counts[StatusType.DELIVERED.value],
            "read": counts[StatusType.READ.value],
            "failed": counts[StatusType.FAILED.value],
            "total_messages": len(entries),
        }

    def detect_stale_conversation(
        self,
        conversation_id: str,
        threshold_minutes: int = 30,
    ) -> bool:
        """Detecta se conversa está estagnada (sem resposta do cliente)."""
        entries = [e for e in self._statuses if e.conversation_id == conversation_id]
        if not entries:
            return False
        last_entry = max(entries, key=lambda e: e.timestamp)
        now = datetime.now(timezone.utc)
        diff = (now - last_entry.timestamp).total_seconds() / 60
        return diff > threshold_minutes

    def get_all_statuses(self) -> list[MessageStatusEntry]:
        """Retorna todos os status."""
        return list(self._statuses)

    def clear(self) -> None:
        """Limpa todos os statuses (uso em testes)."""
        self._statuses.clear()