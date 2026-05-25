from qdrant.seed_hvac import build_refrimix_documents


def test_refrimix_rag_payloads_have_rich_contract():
    docs = build_refrimix_documents()

    assert docs
    for doc in docs:
        assert doc["doc_type"]
        assert "service" in doc
        assert doc["segment_market"]
        assert doc["segment_tier"]
        assert doc["goal"]
        assert doc["stage"]
        assert doc["source"]
        assert doc["text"].strip()


def test_qdrant_payload_has_service_segment_goal_stage():
    docs = build_refrimix_documents()
    high_value = next(doc for doc in docs if doc["source"].endswith("commercial_high_end.md"))

    assert high_value["service"] == "geral"
    assert high_value["segment_market"] == "commercial"
    assert high_value["segment_tier"] == "high_value"
    assert high_value["goal"] == "qualify_quote"
    assert high_value["stage"] == "qualification"
