from qdrant.seed_hvac import build_refrimix_documents


def test_refrimix_rag_payloads_have_rich_contract():
    docs = build_refrimix_documents()

    assert docs
    for doc in docs:
        assert doc["doc_id"]
        assert doc["doc_type"]
        assert "service" in doc
        assert doc["segment_market"]
        assert doc["segment_tier"]
        assert doc["intent"]
        assert doc["cta_type"]
        assert doc["goal"]
        assert doc["stage"]
        assert doc["source"]
        assert isinstance(doc["tags"], list)
        assert doc["text"].strip()


def test_qdrant_payload_has_service_segment_goal_stage():
    docs = build_refrimix_documents()
    high_value = next(doc for doc in docs if doc["source"].endswith("commercial_high_end.md"))

    assert high_value["service"] == "geral"
    assert high_value["segment_market"] == "commercial"
    assert high_value["segment_tier"] == "high_value"
    assert high_value["goal"] == "high_value_project"
    assert high_value["stage"] == "qualification"


def test_pricing_policy_is_chunked_by_rule():
    docs = build_refrimix_documents()
    install_price = next(doc for doc in docs if doc["doc_id"] == "pricing_policy:instalacao_split_simples")
    cleaning_price = next(doc for doc in docs if doc["doc_id"] == "pricing_policy:higienizacao_split")

    assert install_price["doc_type"] == "pricing_rule"
    assert install_price["service"] == "instalacao"
    assert install_price["stage"] == "price"
    assert install_price["intent"] == "price_question"
    assert install_price["priority"] >= cleaning_price["priority"]


def test_qualification_questions_are_chunked_by_service_and_segment():
    docs = build_refrimix_documents()
    residential_install = next(
        doc for doc in docs
        if doc["doc_id"] == "qualification:instalacao:residential_common"
    )

    assert residential_install["service"] == "instalacao"
    assert residential_install["segment_market"] == "residential"
    assert residential_install["segment_tier"] == "common"
    assert "cidade_bairro" in residential_install["tags"]
