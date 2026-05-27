"""
test_natural_microcopy.py — Testes para natural_microcopy.
"""
from __future__ import annotations

import pytest

from refrimix_core.domain.natural_microcopy import (
    count_questions,
    is_faq_rigged,
    select_error,
    select_greeting,
    select_transition,
)


class TestSelectGreeting:
    def test_select_greeting_returns_string(self):
        result = select_greeting()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_select_greeting_with_name(self):
        result = select_greeting("Carlos")
        assert isinstance(result, str)
        assert "Carlos" in result or "carlos" in result.lower()

    def test_greeting_not_empty(self):
        for _ in range(10):
            assert select_greeting()


class TestSelectTransition:
    def test_transition_not_empty(self):
        for _ in range(10):
            result = select_transition()
            assert isinstance(result, str)
            assert len(result) > 0

    def test_transition_is_placeholder_free(self):
        result = select_transition()
        assert "[TYPING]" not in result


class TestSelectError:
    def test_error_not_empty(self):
        for _ in range(10):
            result = select_error()
            assert isinstance(result, str)
            assert len(result) > 0


class TestCountQuestions:
    def test_no_questions(self):
        assert count_questions("Olá, tudo bem") == 0

    def test_one_question(self):
        assert count_questions("Qual o preço?") == 1

    def test_two_questions(self):
        assert count_questions("Qual o preço? E o prazo?") == 2

    def test_multiple_questions(self):
        assert count_questions("Qual? Qual? Qual?") == 3


class TestIsFaqRigged:
    def test_normal_text(self):
        assert not is_faq_rigged("Olá, tudo bem?")

    def test_two_questions_ok(self):
        assert not is_faq_rigged("Qual o preço? E o prazo?")

    def test_more_than_two_questions(self):
        text = "Qual? Qual? Qual?"
        assert is_faq_rigged(text)

    def test_faq_keyword(self):
        assert is_faq_rigged("Aqui estão as respostas FAQ sobre instalação.")

    def test_perguntas_frequentes(self):
        assert is_faq_rigged("Perguntas frequentes sobre manutenção:")

    def test_numbered_list(self):
        text = "1. Primeiro item\n2. Segundo item\n3. Terceiro item\n4. Quarto item"
        assert is_faq_rigged(text)

    def test_short_numbered_list_ok(self):
        text = "1. Primeiro\n2. Segundo"
        assert not is_faq_rigged(text)
