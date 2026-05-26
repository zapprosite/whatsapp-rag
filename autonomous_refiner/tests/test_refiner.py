"""
Tests for autonomous_refiner.refiner
"""
import pytest
import json
import tempfile
from pathlib import Path
from autonomous_refiner.refiner import (
    detectar_nivel, aplicar_refinamento, RefinamentoLog,
    TomRefiner, RagRefiner, ClassificationRefiner, LlmRefiner,
    _REFINERS
)


class TestDetectarNivel:
    def test_tom_keywords_nivel_1(self):
        nivel = detectar_nivel(
            ["tom muito formal", "impessoal"],
            "cenario", "instalacao"
        )
        assert nivel == 1

    def test_info_keywords_nivel_2(self):
        nivel = detectar_nivel(
            ["informação errada", "preço errado"],
            "cenario", "instalacao"
        )
        assert nivel == 2

    def test_classificacao_keywords_nivel_3(self):
        nivel = detectar_nivel(
            ["classificou errado intent"],
            "cenario", "instalacao"
        )
        assert nivel == 3

    def test_profundidade_keywords_nivel_4(self):
        nivel = detectar_nivel(
            ["falta profundidade na análise"],
            "cenario", "instalacao"
        )
        assert nivel == 4

    def test_default_nivel_1(self):
        nivel = detectar_nivel(
            ["algum problema genérico"],
            "cenario", "instalacao"
        )
        assert nivel == 1


class TestRefiners:
    def test_tom_refiner_can_handle(self):
        refiner = TomRefiner()
        assert refiner.can_handle("cenario", ["problema de tom"]) is True

    def test_rag_refiner_can_handle(self):
        refiner = RagRefiner()
        assert refiner.can_handle("cenario", ["informação faltando"]) is True

    def test_classification_refiner_can_handle(self):
        refiner = ClassificationRefiner()
        assert refiner.can_handle("cenario", ["classificação errada"]) is True

    def test_llm_refiner_can_handle(self):
        refiner = LlmRefiner()
        assert refiner.can_handle("cenario", ["falta raciocínio"]) is True


class TestAplicarRefinamento:
    def test_returns_log_entry(self, tmp_path):
        import autonomous_refiner.refiner as r
        original_log = r.LOG_FILE
        r.LOG_FILE = tmp_path / "refinamento_test.jsonl"

        try:
            log = aplicar_refinamento(
                scenario="Quero instalar split em Santos",
                ideal_response="R$850, me passa o modelo?",
                problems=["tom formal demais"],
                intent="instalacao",
                service="instalacao",
                original_score=5.5,
                judge_model="groq-test",
            )
            assert isinstance(log, RefinamentoLog)
            assert log.nivel == 1
            assert log.original_score == 5.5
            assert log.scenario == "Quero instalar split em Santos"
        finally:
            r.LOG_FILE = original_log


class TestRefinamentoLog:
    def test_to_dict(self):
        log = RefinamentoLog(
            timestamp="2026-05-26T10:00:00",
            scenario="Teste",
            intent="instalacao",
            service="instalacao",
            original_score=5.5,
            final_score=8.0,
            nivel=1,
            arquivo_alvo="nodes.py",
            acao="diff",
            diff_preview="preview",
            judge_model="groq",
        )
        d = log.to_dict()
        assert d["nivel"] == 1
        assert d["original_score"] == 5.5
        assert d["final_score"] == 8.0


class TestRefinersApply:
    def test_tom_refiner_apply(self):
        refiner = TomRefiner()
        diff = refiner.apply(
            scenario="Quero instalar split",
            ideal_response="Instalação R$850, me passa o modelo?",
            problems=["formal demais"],
            intent="instalacao",
            service="instalacao",
        )
        assert "Nível 1" in diff or "TOM" in diff
        assert len(diff) > 20

    def test_rag_refiner_apply(self):
        refiner = RagRefiner()
        diff = refiner.apply(
            scenario="Quero instalar split",
            ideal_response="R$850, me passa o modelo?",
            problems=["faltando informação"],
            intent="instalacao",
            service="instalacao",
        )
        assert "Nível 2" in diff or "RAG" in diff

    def test_classification_refiner_apply(self):
        refiner = ClassificationRefiner()
        diff = refiner.apply(
            scenario="Preciso de laudo PMOC",
            ideal_response="PMOC fica R$X",
            problems=["classificação errada"],
            intent="pmoc",
            service="pmoc",
        )
        assert "Nível 3" in diff or "CLASSIFICAÇÃO" in diff or "pmoc" in diff.lower()

    def test_llm_refiner_apply(self):
        refiner = LlmRefiner()
        diff = refiner.apply(
            scenario="Análise técnica complexa",
            ideal_response="Análise detalhada",
            problems=["raciocínio insuficiente"],
            intent="consultoria",
            service="consultoria",
        )
        assert "Nível 4" in diff or "LLM" in diff