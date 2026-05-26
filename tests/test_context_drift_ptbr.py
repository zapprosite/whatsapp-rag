from agent_graph.guards.response_guard import validate_response_before_send


def test_response_guard_blocks_wrong_hvac_context_drift():
    ok, violations = validate_response_before_send(
        "A placa do veículo pode estar com problema.",
        {"lead_state": {"tipo_servico": "manutencao"}},
    )

    assert ok is False
    assert "context_drift:wrong_domain_words:placa do veículo" in violations


def test_response_guard_blocks_generic_ai_phrase():
    ok, violations = validate_response_before_send(
        "Como modelo de linguagem, não posso navegar na internet.",
        {"lead_state": {"tipo_servico": "instalacao"}},
    )

    assert ok is False
    assert any(v.startswith("context_drift:generic_ai_phrases") for v in violations)
