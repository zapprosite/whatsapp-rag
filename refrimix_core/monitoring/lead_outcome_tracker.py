"""Rastreador de desfecho de leads — onde o cliente parou.

OutcomeTypes:
- agendado: cliente agendou serviço
- visitou: cliente teve visita técnica
- orcamento_feito: orçamento simples oferecido
- ignorou: cliente parou de responder
- handoff_humano: transferencia para humano
- bloqueado_guardrail: resposta bloqueada por guardrail
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class OutcomeType(str, Enum):
    """Tipos de desfecho de lead."""
    AGENDADO = "agendado"
    VISITOU = "visitou"
    ORCAMENTO_FEITO = "orcamento_feito"
    IGNOROU = "ignorou"
    HANDOFF_HUMANO = "handoff_humano"
    BLOQUEADO_GUARDRAIL = "bloqueado_guardrail"


@dataclass(frozen=True)
class LeadOutcome:
    """Desfecho de um lead."""
    conversation_id: str
    outcome: OutcomeType
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    turning_point: Optional[str] = None
    messages_until_outcome: int = 0
    intent: Optional[str] = None


class LeadOutcomeTracker:
    """Rastreador de desfechos de leads (substituir por Postgres em produção)."""

    def __init__(self):
        self._outcomes: list[LeadOutcome] = []

    def track_outcome(
        self,
        conversation_id: str,
        outcome: OutcomeType,
        turning_point: Optional[str] = None,
        messages_until_outcome: int = 0,
        intent: Optional[str] = None,
    ) -> None:
        """Registra desfecho de um lead."""
        outcome_entry = LeadOutcome(
            conversation_id=conversation_id,
            outcome=outcome,
            turning_point=turning_point,
            messages_until_outcome=messages_until_outcome,
            intent=intent,
        )
        self._outcomes.append(outcome_entry)

    def get_abandonment_rate(self) -> dict:
        """Calcula taxa de abandono por ponto de abandono."""
        total = len(self._outcomes)
        if total == 0:
            return {"total": 0, "abandonment_rate": 0.0, "by_turning_point": {}}
        ignored = [o for o in self._outcomes if o.outcome == OutcomeType.IGNOROU]
        abandonment_rate = len(ignored) / total if total > 0 else 0.0
        turning_points: dict[str, int] = {}
        for outcome in ignored:
            tp = outcome.turning_point or "unknown"
            turning_points[tp] = turning_points.get(tp, 0) + 1
        return {
            "total": total,
            "abandonment_rate": round(abandonment_rate, 3),
            "abandoned_count": len(ignored),
            "by_turning_point": dict(sorted(turning_points.items(), key=lambda x: -x[1])),
        }

    def get_conversion_by_intent(self) -> dict:
        """Calcula taxa de conversão por intent."""
        intent_stats: dict[str, dict] = {}
        for outcome in self._outcomes:
            intent = outcome.intent or "unknown"
            if intent not in intent_stats:
                intent_stats[intent] = {"total": 0, "converted": 0, "handoff": 0}
            intent_stats[intent]["total"] += 1
            if outcome.outcome in (
                OutcomeType.AGENDADO,
                OutcomeType.VISITOU,
                OutcomeType.ORCAMENTO_FEITO,
            ):
                intent_stats[intent]["converted"] += 1
            if outcome.outcome == OutcomeType.HANDOFF_HUMANO:
                intent_stats[intent]["handoff"] += 1
        result = {}
        for intent, stats in intent_stats.items():
            conversion_rate = stats["converted"] / stats["total"] if stats["total"] > 0 else 0.0
            result[intent] = {
                "total": stats["total"],
                "converted": stats["converted"],
                "handoff": stats["handoff"],
                "conversion_rate": round(conversion_rate, 3),
            }
        return result

    def get_all_outcomes(self) -> list[LeadOutcome]:
        """Retorna todos os desfechos."""
        return list(self._outcomes)

    def clear(self) -> None:
        """Limpa todos os outcomes (uso em testes)."""
        self._outcomes.clear()