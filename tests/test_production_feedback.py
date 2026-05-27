"""Testes para production_feedback.py."""

import pytest
from refrimix_core.monitoring.production_feedback import (
    ProductionFeedbackStore,
    FeedbackEntry,
)


class TestProductionFeedbackStore:
    """Testes para ProductionFeedbackStore."""

    def test_save_human_feedback_salva_entry(self):
        """save_human_feedback adiciona entrada à lista."""
        store = ProductionFeedbackStore()
        store.save_human_feedback("conv_001", "Oi, como posso ajudar?", "Olá, quero saber o preço.")
        assert len(store._entries) == 1
        entry = store._entries[0]
        assert entry.conversation_id == "conv_001"
        assert entry.suggested_response == "Oi, como posso ajudar?"
        assert entry.human_response == "Olá, quero saber o preço."
        assert entry.was_edited is True

    def test_save_human_feedback_sem_edicao(self):
        """save_human_feedback detecta quando não houve edição."""
        store = ProductionFeedbackStore()
        response = "Olá, preciso de ajuda."
        store.save_human_feedback("conv_001", response, response)
        assert store._entries[0].was_edited is False

    def test_save_human_feedback_com_campos_editados(self):
        """save_human_feedback registra campos editados."""
        store = ProductionFeedbackStore()
        store.save_human_feedback(
            "conv_001",
            "Bom dia!",
            "Bom dia, tudo bem?",
            edited_fields=["saudacao"],
            intent="welcome",
        )
        entry = store._entries[0]
        assert "saudacao" in entry.edited_fields
        assert entry.intent == "welcome"

    def test_get_feedback_stats_total_e_taxa(self):
        """get_feedback_stats retorna total e taxa de edição."""
        store = ProductionFeedbackStore()
        store.save_human_feedback("c1", "A", "B", intent="welcome")
        store.save_human_feedback("c2", "A", "A", intent="welcome")
        store.save_human_feedback("c3", "A", "C", intent="higienizacao")
        stats = store.get_feedback_stats()
        assert stats["total"] == 3
        assert stats["edited_rate"] == pytest.approx(2 / 3, rel=0.01)

    def test_get_feedback_stats_common_edits(self):
        """get_feedback_stats lista campos mais editados."""
        store = ProductionFeedbackStore()
        store.save_human_feedback("c1", "A", "B", edited_fields=["tom"], intent="welcome")
        store.save_human_feedback("c2", "A", "B", edited_fields=["tom"], intent="welcome")
        store.save_human_feedback("c3", "A", "B", edited_fields=["comprimento"], intent="welcome")
        stats = store.get_feedback_stats()
        assert stats["common_edits"]["tom"] == 2
        assert stats["common_edits"]["comprimento"] == 1

    def test_get_feedback_stats_vazio(self):
        """get_feedback_stats sem entradas retorna zeros."""
        store = ProductionFeedbackStore()
        stats = store.get_feedback_stats()
        assert stats["total"] == 0
        assert stats["edited_rate"] == 0.0
        assert stats["common_edits"] == {}

    def test_export_feedback_dataset_minimo_nao_atingido(self):
        """export_feedback_dataset retorna lista vazia se mínimo não atingido."""
        store = ProductionFeedbackStore()
        store.save_human_feedback("c1", "A", "B")
        dataset = store.export_feedback_dataset(min_cases=30)
        assert dataset == []

    def test_export_feedback_dataset_anonimiza_conversation_id(self):
        """export_feedback_dataset mascara conversation_id."""
        store = ProductionFeedbackStore()
        for i in range(30):
            store.save_human_feedback(f"conv_{i:03d}", "A", "B", intent="welcome")
        dataset = store.export_feedback_dataset(min_cases=30)
        assert len(dataset) == 30
        for item in dataset:
            assert "MASCARA_" in item["conversation_id"]

    def test_export_feedback_dataset_contem_campos_necessarios(self):
        """export_feedback_dataset inclui campos essenciais."""
        store = ProductionFeedbackStore()
        store.save_human_feedback("conv_001", "Oi", "Olá", edited_fields=["saudacao"], intent="welcome")
        dataset = store.export_feedback_dataset(min_cases=1)
        assert len(dataset) == 1
        item = dataset[0]
        assert "conversation_id" in item
        assert "intent" in item
        assert "suggested_response" in item
        assert "human_response" in item
        assert "was_edited" in item

    def test_clear(self):
        """clear() remove todos os entries."""
        store = ProductionFeedbackStore()
        store.save_human_feedback("c1", "A", "B")
        store.clear()
        assert len(store._entries) == 0