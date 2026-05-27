"""Feedback humano sobre respostas sugeridas pelo bot.

Usado em ASSISTED_MODE para salvar quando o humano edita a resposta
gerada automaticamente, criando dataset para refinamento.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class FeedbackEntry:
    """Entrada de feedback humano."""
    conversation_id: str
    suggested_response: str
    human_response: str
    was_edited: bool
    edited_fields: tuple[str, ...] = field(default_factory=tuple)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    intent: Optional[str] = None
    message_index: int = 0


class ProductionFeedbackStore:
    """Armazenamento de feedback humano (substituir por Postgres em produção)."""

    def __init__(self):
        self._entries: list[FeedbackEntry] = []

    def save_human_feedback(
        self,
        conversation_id: str,
        suggested_response: str,
        human_response: str,
        edited_fields: Optional[list[str]] = None,
        intent: Optional[str] = None,
        message_index: int = 0,
    ) -> None:
        """Salva feedback de edição humana."""
        was_edited = suggested_response != human_response
        edited_fields_tuple = tuple(edited_fields) if edited_fields else tuple()
        entry = FeedbackEntry(
            conversation_id=conversation_id,
            suggested_response=suggested_response,
            human_response=human_response,
            was_edited=was_edited,
            edited_fields=edited_fields_tuple,
            intent=intent,
            message_index=message_index,
        )
        self._entries.append(entry)

    def get_feedback_stats(self) -> dict:
        """Retorna estatísticas de feedback."""
        total = len(self._entries)
        if total == 0:
            return {"total": 0, "edited_rate": 0.0, "common_edits": {}}
        edited = sum(1 for e in self._entries if e.was_edited)
        edit_rate = edited / total if total > 0 else 0.0
        field_counts: dict[str, int] = {}
        for entry in self._entries:
            for field_name in entry.edited_fields:
                field_counts[field_name] = field_counts.get(field_name, 0) + 1
        return {
            "total": total,
            "edited_rate": round(edit_rate, 3),
            "common_edits": dict(sorted(field_counts.items(), key=lambda x: -x[1])[:10]),
        }

    def get_all_entries(self) -> list[FeedbackEntry]:
        """Retorna todas as entradas de feedback."""
        return list(self._entries)

    def export_feedback_dataset(self, min_cases: int = 30) -> list[dict]:
        """Exporta dataset anonimizado para refinamento."""
        if len(self._entries) < min_cases:
            return []
        dataset = []
        for entry in self._entries:
            dataset.append({
                "conversation_id": f"MASCARA_{entry.conversation_id[:8]}",
                "intent": entry.intent or "unknown",
                "suggested_response": entry.suggested_response,
                "human_response": entry.human_response,
                "was_edited": entry.was_edited,
                "edited_fields": list(entry.edited_fields),
                "timestamp": entry.timestamp.isoformat(),
            })
        return dataset

    def clear(self) -> None:
        """Limpa todos os entries (uso em testes)."""
        self._entries.clear()