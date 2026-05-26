from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph.nodes.nodes as nodes


def run(coro):
    return asyncio.run(coro)


def last_ai(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return str(message.content)
    return ""


def test_only_instalacao_and_higienizacao_have_fixed_price_paths():
    install = nodes._direct_price_response("instalacao", "quanto custa pra instalar?")
    cleaning = nodes._direct_price_response("higienizacao", "quanto custa higienizar?")
    maintenance = nodes._direct_price_response("manutencao", "quanto custa consertar?")

    assert install and "split" in install and "acesso simples" in install
    assert install and "dreno" in install and "quadro de luz" in install
    assert cleaning and "split" in cleaning and "R$200" in cleaning
    assert maintenance and "R$50" in maintenance and "abate" in maintenance
    assert "R$200" not in maintenance


def test_installation_price_does_not_ask_service_again():
    lead_state = {"tipo_servico": "instalacao"}
    response = nodes._direct_price_response(
        "instalacao",
        "quero preço da instalação",
        lead_state,
        ["cidade_bairro", "btus"],
        ["tipo_servico"],
    )

    assert response
    assert "instalação, manutenção ou higienização" not in response.lower()
    assert "qual serviço" not in response.lower()


def test_installation_price_does_not_ask_btu_again():
    lead_state = {"tipo_servico": "instalacao", "btus": "12000"}
    response = nodes._direct_price_response(
        "instalacao",
        "instalação 12000 btus, quanto fica?",
        lead_state,
        ["cidade_bairro", "foto_local_interno"],
        ["tipo_servico", "btus"],
    )

    assert response
    assert "btu" not in response.lower().rstrip("?")


def test_fallback_extractor_reads_common_unitless_btu_for_split():
    lead_state = nodes._infer_lead_fields_from_text({}, "Quanto fica instalar um split 12000 em Santos?")

    assert lead_state["tipo_servico"] == "instalacao"
    assert lead_state["btus"] == "12000"
    assert lead_state["cidade_bairro"] == "santos"


def test_santos_installation_price_uses_850_for_simple_access():
    lead_state = {"tipo_servico": "instalacao", "cidade_bairro": "Santos"}
    response = nodes._direct_price_response(
        "instalacao",
        "em Santos, acesso simples, qual valor?",
        lead_state,
        ["btus"],
        ["tipo_servico", "cidade_bairro"],
    )

    assert response
    assert "R$850" in response
    assert "cidade" not in response.lower().split("?")[-1]


def test_active_customer_service_is_answered_as_followup_not_new_sale():
    state = {
        "messages": [HumanMessage(content="o técnico ainda vem hoje?")],
        "rag_context": [],
        "service": "instalacao",
        "intent": "instalacao",
        "outcome": "analise_tecnica",
        "handoff_mode": "none",
        "handoff_reason": None,
        "customer_data": {
            "phone": "5513999999999",
            "active_service": {
                "service": "instalacao",
                "status": "scheduled",
                "scheduled_window": "terça à tarde",
                "address": "Santos",
            },
        },
    }

    result = run(nodes.generate_response(state))
    response = last_ai(result["messages"])

    assert result["outcome"] == "acompanhamento_servico"
    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"] == "active_service_followup"
    assert "serviço de instalacao" in response
    assert "acompanhamento" in response
    assert "R$800" not in response


def test_completed_customer_service_is_past_customer_post_sale():
    state = {
        "messages": [HumanMessage(content="oi, preciso falar sobre meu ar")],
        "rag_context": [],
        "service": None,
        "intent": "onboarding",
        "outcome": "onboarding",
        "handoff_mode": "none",
        "handoff_reason": None,
        "customer_data": {
            "phone": "5513999999999",
            "last_service": {
                "service": "higienizacao",
                "status": "completed",
                "updated_at": "2026-05-01",
            },
        },
        "lead_state": {"relationship_type": "new_lead"},
    }

    result = run(nodes.generate_response(state))
    response = last_ai(result["messages"])

    assert result["outcome"] == "pos_venda_ou_novo_atendimento"
    assert result["lead_state"]["relationship_type"] == "past_customer"
    assert "atendimento anterior" in response
    assert "novo atendimento" in response
