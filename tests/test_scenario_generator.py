"""
Tests for scenario_generator.py
"""
import pytest
from refrimix_core.evaluation.scenario_generator import (
    generate_scenarios,
    LeadScenario,
    CATEGORY_DISTRIBUTION,
    scenarios_to_jsonl,
    load_scenarios_from_jsonl,
)
import json
import os
import tempfile


class TestGenerateScenarios:
    def test_generates_exact_count(self):
        scenarios = generate_scenarios(100, seed=42)
        assert len(scenarios) == 100

    def test_scenario_has_required_fields(self):
        scenarios = generate_scenarios(10, seed=42)
        for s in scenarios:
            assert s.id is not None
            assert s.category is not None
            assert s.message is not None
            assert s.message_type in ("text", "audio_transcribed")

    def test_scenario_distribution(self):
        """Testa que a distribuição por categoria respeita os limites."""
        scenarios = generate_scenarios(100, seed=42)
        category_counts = {}
        for s in scenarios:
            category_counts[s.category] = category_counts.get(s.category, 0) + 1

        # Verifica que nenhuma categoria excede o limite
        for cat, quota in CATEGORY_DISTRIBUTION.items():
            count = category_counts.get(cat, 0)
            assert count <= quota, f"{cat} tem {count} mas limite é {quota}"

    def test_deterministic_with_seed(self):
        """Mesma seed gera mesmos cenários."""
        a = generate_scenarios(20, seed=99)
        b = generate_scenarios(20, seed=99)
        assert len(a) == len(b)
        for s1, s2 in zip(a, b):
            assert s1.message == s2.message
            assert s1.category == s2.category

    def test_different_seed_different_scenarios(self):
        """Seed diferente gera cenários diferentes."""
        a = generate_scenarios(20, seed=1)
        b = generate_scenarios(20, seed=2)
        # Not all should be equal (probabilistic)
        messages_a = [s.message for s in a]
        messages_b = [s.message for s in b]
        # At least some should differ
        assert messages_a != messages_b

    def test_has_photo_default_true(self):
        scenarios = generate_scenarios(50, seed=42)
        photo_scenarios = [s for s in scenarios if not s.has_photo]
        # Only 5% should not have photo (sem_foto category)
        assert len(photo_scenarios) <= 10

    def test_audio_transcribed_percentage(self):
        scenarios = generate_scenarios(100, seed=42)
        audio_count = sum(1 for s in scenarios if s.message_type == "audio_transcribed")
        # ~8% should be audio
        assert audio_count <= 15, f"Audio count {audio_count} too high"

    def test_cidades_brasileiras(self):
        scenarios = generate_scenarios(30, seed=42)
        cidades = set(s.cidade for s in scenarios)
        assert len(cidades) > 5  # Should have variety

    def test_scenario_to_dict(self):
        s = LeadScenario(
            id=1,
            category="instalacao",
            message="quero instalar um ar",
            cidade="Santos",
            bairro="Gonzaga",
        )
        d = s.to_dict()
        assert d["id"] == 1
        assert d["category"] == "instalacao"
        assert d["message"] == "quero instalar um ar"
        assert d["cidade"] == "Santos"

    def test_risco_eletrico_flag(self):
        scenarios = generate_scenarios(50, seed=42)
        risco = [s for s in scenarios if s.category == "risco_eletrico"]
        for s in risco:
            assert s.is_urgent


class TestScenariosJsonl:
    def test_scenarios_to_jsonl_and_load(self):
        scenarios = generate_scenarios(10, seed=42)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            path = f.name

        try:
            scenarios_to_jsonl(scenarios, path)
            assert os.path.exists(path)

            loaded = load_scenarios_from_jsonl(path)
            assert len(loaded) == 10

            for orig, loaded_s in zip(scenarios, loaded):
                assert orig.id == loaded_s.id
                assert orig.category == loaded_s.category
                assert orig.message == loaded_s.message
        finally:
            os.unlink(path)


class TestCategoryDistribution:
    def test_total_categories_sums_to_100(self):
        total = sum(CATEGORY_DISTRIBUTION.values())
        assert total == 100, f"Distribution sums to {total}, not 100"

    def test_all_categories_present(self):
        expected = {
            "saudacao_triagem", "instalacao", "higienizacao",
            "manutencao_conserto", "nao_gela", "pingando_agua",
            "risco_eletrico", "orcamento_preco", "agendamento",
            "sem_foto", "cliente_apressado", "cliente_confuso",
            "cliente_irritado", "alto_valor_projeto",
        }
        assert set(CATEGORY_DISTRIBUTION.keys()) == expected

    def test_instalacao_has_12(self):
        assert CATEGORY_DISTRIBUTION["instalacao"] == 12

    def test_risco_eletrico_has_8(self):
        assert CATEGORY_DISTRIBUTION["risco_eletrico"] == 8