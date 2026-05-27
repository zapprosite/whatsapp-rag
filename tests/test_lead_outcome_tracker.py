"""Testes para lead_outcome_tracker.py."""

import pytest
from refrimix_core.monitoring.lead_outcome_tracker import (
    LeadOutcomeTracker,
    OutcomeType,
    LeadOutcome,
)


class TestLeadOutcomeTracker:
    """Testes para LeadOutcomeTracker."""

    def test_track_outcome_adiciona_entry(self):
        """track_outcome adiciona entrada à lista."""
        tracker = LeadOutcomeTracker()
        tracker.track_outcome("conv_001", OutcomeType.AGENDADO, turning_point="ofereceu_agenda")
        assert len(tracker._outcomes) == 1
        outcome = tracker._outcomes[0]
        assert outcome.conversation_id == "conv_001"
        assert outcome.outcome == OutcomeType.AGENDADO
        assert outcome.turning_point == "ofereceu_agenda"

    def test_track_outcome_com_intent(self):
        """track_outcome registra intent quando fornecido."""
        tracker = LeadOutcomeTracker()
        tracker.track_outcome("conv_001", OutcomeType.IGNOROU, intent="higienizacao")
        assert tracker._outcomes[0].intent == "higienizacao"

    def test_track_outcome_messages_until_outcome(self):
        """track_outcome registra quantas mensagens até o desfecho."""
        tracker = LeadOutcomeTracker()
        tracker.track_outcome("conv_001", OutcomeType.AGENDADO, messages_until_outcome=5)
        assert tracker._outcomes[0].messages_until_outcome == 5

    def test_get_abandonment_rate_vazio(self):
        """get_abandonment_rate sem dados retorna zeros."""
        tracker = LeadOutcomeTracker()
        result = tracker.get_abandonment_rate()
        assert result["total"] == 0
        assert result["abandonment_rate"] == 0.0

    def test_get_abandonment_rate_com_ignora(self):
        """get_abandonment_rate calcula corretamente."""
        tracker = LeadOutcomeTracker()
        tracker.track_outcome("c1", OutcomeType.IGNOROU, turning_point="pediu_bairro")
        tracker.track_outcome("c2", OutcomeType.IGNOROU, turning_point="pediu_bairro")
        tracker.track_outcome("c3", OutcomeType.AGENDADO)
        result = tracker.get_abandonment_rate()
        assert result["total"] == 3
        assert result["abandoned_count"] == 2
        assert result["abandonment_rate"] == pytest.approx(2 / 3, rel=0.01)
        assert result["by_turning_point"]["pediu_bairro"] == 2

    def test_get_abandonment_rate_por_turning_point(self):
        """get_abandonment_rate ordena por frequência."""
        tracker = LeadOutcomeTracker()
        tracker.track_outcome("c1", OutcomeType.IGNOROU, turning_point="perguntou_preco")
        tracker.track_outcome("c2", OutcomeType.IGNOROU, turning_point="perguntou_preco")
        tracker.track_outcome("c3", OutcomeType.IGNOROU, turning_point="pediu_foto")
        tracker.track_outcome("c4", OutcomeType.AGENDADO)
        result = tracker.get_abandonment_rate()
        top = list(result["by_turning_point"].keys())
        assert top[0] == "perguntou_preco"

    def test_get_conversion_by_intent_vazio(self):
        """get_conversion_by_intent sem dados retorna vazio."""
        tracker = LeadOutcomeTracker()
        result = tracker.get_conversion_by_intent()
        assert result == {}

    def test_get_conversion_by_intent_calcula_taxa(self):
        """get_conversion_by_intent calcula conversão por intent."""
        tracker = LeadOutcomeTracker()
        tracker.track_outcome("c1", OutcomeType.AGENDADO, intent="higienizacao")
        tracker.track_outcome("c2", OutcomeType.IGNOROU, intent="higienizacao")
        tracker.track_outcome("c3", OutcomeType.HANDOFF_HUMANO, intent="risco_eletrico")
        result = tracker.get_conversion_by_intent()
        assert result["higienizacao"]["total"] == 2
        assert result["higienizacao"]["converted"] == 1
        assert result["higienizacao"]["conversion_rate"] == 0.5

    def test_get_conversion_by_intent_handoff_conta_separado(self):
        """get_conversion_by_intent conta handoffs separadamente."""
        tracker = LeadOutcomeTracker()
        tracker.track_outcome("c1", OutcomeType.HANDOFF_HUMANO, intent="risco_eletrico")
        tracker.track_outcome("c2", OutcomeType.HANDOFF_HUMANO, intent="risco_eletrico")
        result = tracker.get_conversion_by_intent()
        assert result["risco_eletrico"]["handoff"] == 2
        assert result["risco_eletrico"]["converted"] == 0

    def test_get_all_outcomes_retorna_lista(self):
        """get_all_outcomes retorna cópia da lista."""
        tracker = LeadOutcomeTracker()
        tracker.track_outcome("c1", OutcomeType.AGENDADO)
        outcomes = tracker.get_all_outcomes()
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], LeadOutcome)

    def test_clear(self):
        """clear() remove todos os outcomes."""
        tracker = LeadOutcomeTracker()
        tracker.track_outcome("c1", OutcomeType.AGENDADO)
        tracker.clear()
        assert len(tracker._outcomes) == 0