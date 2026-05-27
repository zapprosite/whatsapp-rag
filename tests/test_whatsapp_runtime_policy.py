"""
test_whatsapp_runtime_policy.py — Testes para whatsapp_runtime_policy.
"""
from __future__ import annotations

import pytest

from refrimix_core.domain.whatsapp_runtime_policy import (
    BLOCK_PRICE_KEYWORDS,
    MAX_QUESTIONS_PER_TURN,
    ElectricalRisk,
    can_show_instagram,
    check_electrical_risk,
    client_already_explained_problem,
    count_questions,
    enforce_question_limit,
    get_electrical_directive,
    should_block_price,
    validate_response,
)


class TestElectricalRisk:
    def test_no_risk(self):
        assert check_electrical_risk("oi") == ElectricalRisk.NONE
        assert check_electrical_risk("quanto custa") == ElectricalRisk.NONE

    def test_suspected_risk(self):
        assert check_electrical_risk("o disjuntor desarmou") == ElectricalRisk.SUSPECTED
        assert check_electrical_risk("fio soltando") == ElectricalRisk.SUSPECTED
        assert check_electrical_risk("tomada esquentando") == ElectricalRisk.SUSPECTED

    def test_confirmed_risk(self):
        assert check_electrical_risk("faísca na tomada") == ElectricalRisk.CONFIRMED
        assert check_electrical_risk("cheiro de queimado") == ElectricalRisk.CONFIRMED
        assert check_electrical_risk("curto circuito") == ElectricalRisk.CONFIRMED

    def test_directive_for_confirmed(self):
        result = get_electrical_directive(ElectricalRisk.CONFIRMED)
        assert result is not None
        assert "Desligue" in result

    def test_directive_for_suspected(self):
        result = get_electrical_directive(ElectricalRisk.SUSPECTED)
        assert result is not None

    def test_directive_for_none(self):
        assert get_electrical_directive(ElectricalRisk.NONE) is None


class TestBlockPrice:
    def test_price_mention_blocks_without_data(self):
        blocked, reason = should_block_price("quanto custa", lead_state={})
        assert blocked is True

    def test_price_mention_blocks_without_city(self):
        blocked, reason = should_block_price("qual o valor", lead_state={"tipo_servico": "instalacao"})
        assert blocked is True

    def test_price_mention_allows_with_minimal_data(self):
        blocked, reason = should_block_price(
            "qual o preço",
            lead_state={"tipo_servico": "instalacao", "cidade_bairro": "São Paulo"},
        )
        assert blocked is False


class TestCanShowInstagram:
    def test_empty_history(self):
        assert can_show_instagram([]) is False

    def test_confirmation_moment(self):
        assert can_show_instagram(["perfeito", "combinado então"]) is True

    def test_asking_schedule(self):
        assert can_show_instagram(["quando", "funciona"]) is True

    def test_no_instagram_on_first_contact(self):
        assert can_show_instagram(["oi", "tudo bem"]) is False


class TestCountQuestions:
    def test_no_questions(self):
        assert count_questions("Olá") == 0

    def test_one_question(self):
        assert count_questions("Qual o preço?") == 1

    def test_multiple_questions(self):
        assert count_questions("Qual? E o que?") == 2

    def test_text_with_no_question_marks(self):
        assert count_questions("olá tudo bem") == 0


class TestEnforceQuestionLimit:
    def test_under_limit(self):
        text = "Qual o preço?"
        assert enforce_question_limit(text) == text

    def test_at_limit(self):
        text = "Qual o preço? E o prazo?"
        assert enforce_question_limit(text) == text

    def test_over_limit(self):
        text = "Qual? E? O quê?"
        result = enforce_question_limit(text)
        assert count_questions(result) <= MAX_QUESTIONS_PER_TURN


class TestClientAlreadyExplainedProblem:
    def test_greeting_alone(self):
        assert client_already_explained_problem("Oi") is False
        assert client_already_explained_problem("Bom dia") is False
        assert client_already_explained_problem("Olá") is False

    def test_problem_stated(self):
        assert client_already_explained_problem("Quero instalar um ar") is True
        assert client_already_explained_problem("O ar não gela") is True


class TestValidateResponse:
    def test_valid_response(self):
        ok, err = validate_response("Bom dia! Quanto custa?")
        assert ok is True
        assert err == ""

    def test_empty_response(self):
        ok, err = validate_response("")
        assert ok is False

    def test_too_many_questions(self):
        text = "Qual? E? O quê?"
        ok, err = validate_response(text)
        assert ok is False
        assert "perguntas" in err

    def test_whitespace_only(self):
        ok, err = validate_response("   ")
        assert ok is False
