"""
Tests for autonomous_refiner.evaluator
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from autonomous_refiner.evaluator import (
    ScoreResult, ScoreLevel, JudgeClient, c
)


class TestScoreResult:
    def test_score_level_excellent(self):
        r = ScoreResult(
            score=9.5, level=ScoreLevel.EXCELLENT,
            justification="Perfeito", ideal_response="Oi",
            improvements=[], judge_model="test"
        )
        assert r.passed is True

    def test_score_level_good(self):
        r = ScoreResult(score=7.5, level=ScoreLevel.GOOD,
                         justification="", ideal_response="", improvements=[], judge_model="test")
        assert r.passed is True

    def test_score_level_fair(self):
        r = ScoreResult(score=6.0, level=ScoreLevel.FAIR,
                         justification="", ideal_response="", improvements=[], judge_model="test")
        assert r.passed is False

    def test_score_level_poor(self):
        r = ScoreResult(score=3.0, level=ScoreLevel.POOR,
                         justification="", ideal_response="", improvements=[], judge_model="test")
        assert r.passed is False

    def test_to_dict(self):
        r = ScoreResult(
            score=8.0, level=ScoreLevel.GOOD,
            justification="Boa", ideal_response="Oi",
            improvements=["tom"], judge_model="groq"
        )
        d = r.to_dict()
        assert d["score"] == 8.0
        assert d["level"] == "good"
        assert r.passed is True


class TestJudgeClient:
    def test_detectar_nivel_excellent(self):
        r = ScoreResult(score=10.0, level=ScoreLevel.EXCELLENT,
                         justification="", ideal_response="", improvements=[], judge_model="test")
        assert r.passed is True

    def test_detectar_nivel_poor(self):
        r = ScoreResult(score=2.0, level=ScoreLevel.POOR,
                         justification="", ideal_response="", improvements=[], judge_model="test")
        assert r.passed is False

    @patch("autonomous_refiner.evaluator.OpenAI")
    def test_evaluate_returns_error_on_llm_failure(self, mock_openai):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        judge = JudgeClient(provider="groq")
        result = judge.evaluate("test", "resposta", "intent", "service")

        assert result.score == 0.0
        assert result.level == ScoreLevel.POOR
        assert "API Error" in result.justification

    @patch("autonomous_refiner.evaluator.OpenAI")
    def test_evaluate_parses_valid_json(self, mock_openai):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({
            "score": 8.5,
            "justification": "Boa resposta",
            "ideal_response": "Resposta ideal",
            "improvements": ["tom"]
        })
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        judge = JudgeClient(provider="groq")
        result = judge.evaluate("cenario", "original", "instalacao", "instalacao")

        assert result.score == 8.5
        assert result.level == ScoreLevel.GOOD
        assert result.justification == "Boa resposta"

    @patch("autonomous_refiner.evaluator.OpenAI")
    def test_evaluate_handles_code_block_json(self, mock_openai):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '```json\n{"score": 7.0, "justification": "ok", "ideal_response": "ok", "improvements": []}\n```'
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        judge = JudgeClient(provider="groq")
        result = judge.evaluate("cenario", "original", "intent", "service")
        assert result.score == 7.0

    @patch("autonomous_refiner.evaluator.OpenAI")
    def test_evaluate_handles_invalid_json(self, mock_openai):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json at all"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        judge = JudgeClient(provider="groq")
        result = judge.evaluate("cenario", "original", "intent", "service")

        assert result.score == 5.0
        assert result.level == ScoreLevel.FAIR
        assert ("JSON" in result.justification or "JSON" in result.improvements[0])