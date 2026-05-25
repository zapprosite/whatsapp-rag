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
