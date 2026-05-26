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


def test_blocks_pushy_sales_pressure():
    ok, violations = validate_response_before_send(
        "Tenho últimas vagas hoje, vamos fechar agora?",
        {"lead_state": {"tipo_servico": "instalacao"}},
    )

    assert ok is False
    assert "pushy_sales_pressure" in violations


def test_blocks_internal_segment_leak():
    ok, violations = validate_response_before_send(
        "Esse é um lead alto valor do segmento commercial_high_value.",
        {"lead_state": {"tipo_servico": "pmoc"}},
    )

    assert ok is False
    assert "internal_segment_leak" in violations


def test_violation_leaked_media_placeholder():
    ok, violations = validate_response_before_send(
        "Agendamento de manutenção em [áudio].",
        {"lead_state": {"tipo_servico": "manutencao"}},
    )
    assert ok is False
    assert "leaked_media_placeholder" in violations


def test_violation_asked_preferred_window_again():
    ok, violations = validate_response_before_send(
        "Me confirma o melhor período: manhã ou tarde?",
        {
            "lead_state": {
                "tipo_servico": "manutencao",
                "appointment": {"preferred_window": "tarde", "confirmed_window": True},
            }
        },
    )
    assert ok is False
    assert "asked_preferred_window_again" in violations


def test_violation_unwanted_internal_manager_phrase():
    ok, violations = validate_response_before_send(
        "Vou sinalizar o gerente agora para confirmar a melhor janela.",
        {"lead_state": {"tipo_servico": "manutencao"}, "handoff_reason": None},
    )
    assert ok is False
    assert "unwanted_internal_process" in violations


def test_violation_appointment_claim_without_minimum_data():
    ok, violations = validate_response_before_send(
        "Perfeito, já tenho dados suficientes para encaminhar o agendamento de manutencao em [áudio].",
        {
            "lead_state": {
                "tipo_servico": "manutencao",
                "cidade_bairro": None,
                "manutencao": {},
                "fotos": {},
                "conserto": {},
                "appointment": {},
            }
        },
    )
    assert ok is False
    assert "appointment_claim_without_minimum_data" in violations or "leaked_media_placeholder" in violations


def test_no_violation_when_window_not_yet_registered():
    ok, violations = validate_response_before_send(
        "Me confirma o melhor período: manhã ou tarde?",
        {
            "lead_state": {
                "tipo_servico": "manutencao",
                "appointment": {"preferred_window": None},
                "appointment_ready": True,
            }
        },
    )
    assert "asked_preferred_window_again" not in violations


def test_no_internal_manager_leak_with_safe_handoff():
    ok, violations = validate_response_before_send(
        "Vou sinalizar o gerente agora, é uma reclamação grave.",
        {
            "lead_state": {"tipo_servico": "manutencao"},
            "handoff_reason": "sensitive_complaint",
        },
    )
    assert "unwanted_internal_process" not in violations
