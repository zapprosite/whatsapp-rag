from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage

from agent_graph.domain.commercial_router import decide_commercial_path
from agent_graph.nodes.compose_response import compose_response
from agent_graph.nodes.nodes import _lead_state_copy


def run(coro):
    return asyncio.run(coro)


def _last_ai_text(result: dict) -> str:
    return str(result["messages"][-1].content)


def test_nao_tenho_foto_offers_technical_visit():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    decision = decide_commercial_path(lead_state, "Não tenho foto")
    assert decision.path == "technical_visit_50"


def test_instalacao_validada_returns_850():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["btus"] = "12000"
    lead_state["fotos"]["local_interno"] = True
    lead_state["fotos"]["local_externo"] = True
    lead_state["instalacao"]["ponto_eletrico_exclusivo"] = True
    lead_state["instalacao"]["tubulacao_existente"] = True
    lead_state["instalacao"]["distancia_aproximada"] = "3"

    decision = decide_commercial_path(lead_state, "quero instalar")
    assert decision.path == "fixed_installation_simple"
    assert decision.fixed_price == 850


def test_manutencao_returns_50():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "manutencao"
    decision = decide_commercial_path(lead_state, "meu ar não gela")
    assert decision.path == "technical_visit_50"


def test_higienizacao_returns_200():
    result = run(
        compose_response(
            {
                "messages": [HumanMessage(content="quanto fica higienização?")],
                "lead_state": {"tipo_servico": "higienizacao", "lead_identity": {}, "appointment": {}},
                "next_action": {"type": "offer_fixed_hygienization", "service": "higienizacao"},
            }
        )
    )
    assert "R$200" in _last_ai_text(result)


def test_higienizacao_sem_climatizar_vira_50():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "higienizacao"
    decision = decide_commercial_path(lead_state, "quero higienização mas não climatiza")
    assert decision.path == "technical_visit_50"


def test_vrf_duto_splitao_cassete_viram_project_visit():
    for text in ("vrf", "duto", "splitão", "cassete"):
        lead_state = _lead_state_copy()
        lead_state["tipo_servico"] = "instalacao"
        decision = decide_commercial_path(lead_state, text)
        assert decision.path == "project_quote"
