from agent_graph.domain.lead_mind import default_lead_mind, update_from_lead_state


def test_lead_mind_updates_from_structured_state():
    lead_state = {
        "tipo_servico": "instalacao",
        "cidade_bairro": "Santos",
        "btus": "12000",
        "relationship_type": "qualifying_lead",
    }

    mind = update_from_lead_state(
        default_lead_mind("lead-test"),
        lead_state,
        "Quanto fica instalar split 12000 no quarto em Santos?",
        phone="lead-test",
        conversation_goal="qualify_quote",
        do_not_ask=["tipo_servico", "cidade_bairro", "btus"],
        missing_fields=["foto_local_interno"],
    )

    assert mind["intent"]["primary_service"] == "instalacao"
    assert mind["segment"]["id"] == "residential_common"
    assert mind["segment"]["do_not_say_to_customer"] is True
    assert "btus=12000" in mind["memory"]["facts"]
    assert mind["commercial_context"]["next_best_action"] == "ask_foto_local_interno"
