from agent_graph.domain.lead_mind import compact_lead_mind_if_needed, default_lead_mind


def test_lead_mind_compaction_preserves_do_not_ask():
    mind = default_lead_mind()
    mind["memory"]["conversation_summary"] = "Lead quer instalação de split 12.000 BTUs em Santos."
    mind["memory"]["facts"] = [f"fato={idx}" for idx in range(200)]
    mind["memory"]["do_not_ask"] = ["tipo_servico", "cidade_bairro", "btus"]
    mind["memory"]["missing_fields"] = ["foto_local_interno"]

    compacted = compact_lead_mind_if_needed(mind, max_chars=500)

    assert compacted["memory"]["do_not_ask"] == ["tipo_servico", "cidade_bairro", "btus"]
    assert compacted["memory"]["missing_fields"] == ["foto_local_interno"]
    assert compacted["compaction"]["last_compacted_at"]
