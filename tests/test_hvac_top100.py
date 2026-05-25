from qdrant.hvac_top100 import TOP100_FAQ, VALID_SERVICES
from qdrant.seed_hvac import faq_to_text
from refinar import evaluate_ptbr_quality


def test_top100_has_exactly_100_entries():
    assert len(TOP100_FAQ) == 100


def test_top100_entries_have_valid_contract():
    questions = set()
    for item in TOP100_FAQ:
        assert item["question"] not in questions
        questions.add(item["question"])
        assert item["service_name"] in VALID_SERVICES
        assert item["answer"].strip()
        assert "?" in item["answer"], item["question"]
        assert 1 <= item["priority"] <= 100
        assert faq_to_text(item).startswith("Pergunta do lead:")


def test_top100_answers_follow_ptbr_guardrails():
    for item in TOP100_FAQ:
        blockers, _ = evaluate_ptbr_quality(
            item["answer"],
            expected_intent=item["service_name"] or "unknown",
            message=item["question"],
        )
        assert blockers == [], item["question"]
