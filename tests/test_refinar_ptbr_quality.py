from refinar import evaluate_ptbr_quality


def test_ptbr_quality_blocks_european_portuguese_terms():
    blockers, warnings = evaluate_ptbr_quality(
        "Estou a verificar a sua morada e o seu contacto.",
        expected_intent="manutencao",
    )

    assert blockers
    assert any("português europeu" in item for item in blockers)
    assert isinstance(warnings, list)


def test_ptbr_quality_blocks_old_formal_whatsapp_copy():
    blockers, _ = evaluate_ptbr_quality(
        "Prezado cliente, estimado cliente, conforme solicitado, retornaremos cordialmente.",
        expected_intent="instalacao",
    )

    assert any("formalismo" in item or "burocrático" in item for item in blockers)


def test_ptbr_quality_allows_estimated_value_context():
    blockers, warnings = evaluate_ptbr_quality(
        "O valor estimado depende da visita. Me fala a cidade e quantos ambientes são?",
        expected_intent="projeto-central",
    )

    assert blockers == []
    assert warnings == []


def test_ptbr_quality_blocks_free_visit_policy():
    blockers, _ = evaluate_ptbr_quality(
        "Podemos agendar uma visita técnica gratuita para avaliar.",
        expected_intent="manutencao",
    )

    assert any("política comercial" in item for item in blockers)


def test_ptbr_quality_warns_when_whatsapp_response_is_too_long():
    response = "Entendi. " + ("Vou te explicar com calma. " * 40)

    blockers, warnings = evaluate_ptbr_quality(response, expected_intent="consultoria")

    assert blockers == []
    assert any("resposta longa" in item for item in warnings)


def test_ptbr_quality_accepts_modern_sao_paulo_whatsapp_copy():
    blockers, warnings = evaluate_ptbr_quality(
        "Entendi. Pra eu te passar o caminho certo, me manda o bairro e o modelo do ar?",
        expected_intent="manutencao",
    )

    assert blockers == []
    assert warnings == []
