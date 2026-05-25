from agent_graph.guards.response_guard import validate_response_before_send
from agent_graph.nodes.nodes import infer_asked_field_from_response, should_avoid_reasking


def test_blocks_service_question_when_service_exists():
    ok, violations = validate_response_before_send(
        "Oi, tudo bem? Você precisa de instalação, manutenção ou higienização?",
        {
            "lead_state": {"tipo_servico": "instalacao"},
            "customer_data": {"memory": {"has_persistent_lead": True}},
        },
    )

    assert ok is False
    assert "asked_service_type_again" in violations
    assert "repeated_greeting" in violations


def test_detects_reasked_field_with_ask_count():
    ok, violations = validate_response_before_send(
        "Me confirma a cidade e bairro?",
        {
            "lead_state": {"tipo_servico": "instalacao", "ask_count_by_field": {"cidade_bairro": 2}},
            "do_not_ask": [],
        },
    )

    assert ok is False
    assert "asked_repeated_field:cidade_bairro" in violations


def test_infers_asked_field_from_response():
    field = infer_asked_field_from_response("Qual é a capacidade do aparelho em BTUs?", ["btus"])

    assert field == "btus"
    assert should_avoid_reasking("cidade_bairro", {"ask_count_by_field": {"cidade_bairro": 2}}) is True


def test_detects_possible_truncated_response():
    ok, violations = validate_response_before_send(
        "Entendi. Pode ser placa eletrônica, mas antes preciso",
        {"lead_state": {"tipo_servico": "manutencao"}},
    )

    assert ok is False
    assert "possible_truncated_response" in violations
