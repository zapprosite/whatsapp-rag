from agent_graph.services.domain_disambiguation import (
    build_rag_query,
    disambiguate_user_text,
    find_forbidden_context_drift,
    select_response_template,
)


def test_disambiguates_placa_as_hvac_electronic_board():
    result = disambiguate_user_text("Meu ar tá com problema na placa", {"tipo_servico": "manutencao"})

    assert "placa" in result.matched_terms
    assert "placa eletronica" in result.rewritten_query.lower()
    assert "ar-condicionado" in result.rewritten_query.lower()
    assert "placa do veículo" not in result.rewritten_query


def test_disambiguates_carga_by_context_as_thermal_load():
    result = disambiguate_user_text("Preciso calcular carga para projeto por BTUs e metragem", {})

    assert result.variant == "carga_termica"
    assert result.service_hint == "consultoria"
    assert "carga termica" in result.rewritten_query.lower()


def test_build_rag_query_adds_recent_history_and_hvac_context():
    query, meta = build_rag_query(
        "Preciso de retorno, o problema voltou",
        {"relationship_type": "active_customer"},
        ["O ar não gela", "Fiz serviço com vocês"],
    )

    assert "pos-venda" in query.lower()
    assert "historico_recente=" in query
    assert meta["matched_terms"] == ["retorno"]


def test_selects_residential_price_template():
    state = {
        "service": "instalacao",
        "conversation_objective": "qualify_quote",
        "lead_state": {
            "cidade_bairro": "Santos",
            "lead_mind": {
                "segment": {"id": "residential_common"},
                "intent": {"last_user_intent": "price_question"},
            },
        },
    }

    template = select_response_template(state, "Quanto fica?")

    assert template is not None
    assert template["id"] == "instalacao_preco_simples"


def test_forbidden_context_drift_detects_wrong_domain_words():
    hits = find_forbidden_context_drift("Isso parece placa do veículo e split financeiro.")

    assert "wrong_domain_words:placa do veículo" in hits
    assert "wrong_domain_words:split financeiro" in hits
