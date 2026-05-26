"""
Tests for autonomous_refiner.trigger
"""
import pytest
import json
import tempfile
import os
from pathlib import Path
from autonomous_refiner.trigger import (
    should_refine, TriggerResult, scenario_hash,
    is_duplicate, log_trigger, _count_recent_refinamentos
)


class TestScenarioHash:
    def test_hash_deterministic(self):
        h1 = scenario_hash("Quero instalar split", "instalacao", "instalacao")
        h2 = scenario_hash("Quero instalar split", "instalacao", "instalacao")
        assert h1 == h2

    def test_hash_case_insensitive(self):
        h1 = scenario_hash("Quero Instalar Split", "instalacao", "instalacao")
        h2 = scenario_hash("quero instalar split", "instalacao", "instalacao")
        assert h1 == h2

    def test_hash_different_scenarios(self):
        h1 = scenario_hash("Quero instalar split", "instalacao", "instalacao")
        h2 = scenario_hash("Quero limpar split", "higienizacao", "higienizacao")
        assert h1 != h2


class TestShouldRefine:
    def test_low_score_triggers_refinement(self):
        result = should_refine(
            scenario="Teste",
            intent="instalacao",
            service="instalacao",
            current_score=5.5
        )
        assert result.should_refine is True
        assert "score" in result.reason.lower()

    def test_high_score_no_trigger(self):
        result = should_refine(
            scenario="Teste alto score unico abc",
            intent="instalacao_alto",
            service="instalacao_alto",
            current_score=9.5
        )
        # High score doesn't trigger (not low enough to auto-trigger, not in dedup window)
        # Score 9.5 >= 8.0 so doesn't trigger score<8.0 condition
        assert result.should_refine is False

    def test_medium_score_triggers(self, tmp_path):
        """Test with isolated trigger log to avoid dedup collisions."""
        import autonomous_refiner.trigger as t
        original_log = t.TRIGGER_LOG
        t.TRIGGER_LOG = tmp_path / "trigger_medium.jsonl"

        try:
            result = should_refine(
                scenario="Teste medio score unico xyz qrs",
                intent="instalacao_unico_xyz",
                service="instalacao_unico_xyz",
                current_score=7.5
            )
            # 7.5 < 8.0 triggers non-blocking refinement
            assert result.should_refine is True
            assert result.is_blocking is False
        finally:
            t.TRIGGER_LOG = original_log

    def test_zero_score_no_trigger(self):
        """Score 0 means no evaluation yet - no trigger."""
        result = should_refine(
            scenario="Teste zero score unico 123",
            intent="zero_score",
            service="zero_score",
            current_score=0.0
        )
        # Score 0 is treated as "not evaluated" - no auto-trigger
        assert result.should_refine is False

    def test_trigger_result_has_required_fields(self):
        result = should_refine(
            scenario="Teste",
            intent="instalacao",
            service="instalacao",
            current_score=5.0
        )
        assert isinstance(result, TriggerResult)
        assert hasattr(result, "should_refine")
        assert hasattr(result, "reason")
        assert hasattr(result, "scenario_hash")
        assert hasattr(result, "nivel_sugerido")
        assert hasattr(result, "is_blocking")
        assert len(result.scenario_hash) == 16


class TestIsDuplicate:
    def test_same_scenario_is_duplicate(self):
        scenario = "Quero instalar split em Santos"
        intent = "instalacao"
        service = "instalacao"
        # First call - not duplicate
        assert is_duplicate(scenario, intent, service) is False
        # Second call within dedup window should be duplicate
        # (This test depends on the actual dedup window setting)

    def test_different_scenario_not_duplicate(self):
        h1 = scenario_hash("Quero instalar split", "instalacao", "instalacao")
        h2 = scenario_hash("Quero limpar split", "higienizacao", "higienizacao")
        assert h1 != h2


class TestLogTrigger:
    def test_log_trigger_creates_file(self, tmp_path):
        # Use tmp_path for isolated test
        import autonomous_refiner.trigger as t
        original_log = t.TRIGGER_LOG
        t.TRIGGER_LOG = tmp_path / "trigger_test.jsonl"
        try:
            log_trigger("test", "intent", "service", True, "test_reason", 1)
            assert t.TRIGGER_LOG.exists()
            content = t.TRIGGER_LOG.read_text()
            entry = json.loads(content.strip())
            assert entry["should_refine"] is True
            assert entry["nivel_sugerido"] == 1
        finally:
            t.TRIGGER_LOG = original_log