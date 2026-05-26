"""
tests/test_high_value_routing.py
Valida que VRF, VRV, cassete, piso-teto, splitão, multi split, dutos e
aparelhos >18000 BTUs são roteados como project_quote, nunca como instalação simples.
"""
from __future__ import annotations

import asyncio
from copy import deepcopy

import pytest

from agent_graph.domain.commercial_router import decide_commercial_path
from agent_graph.nodes.nodes import _lead_state_copy
from agent_graph.nodes.understand_message import understand_message


def run(coro):
    return asyncio.run(coro)


def _decide(text: str, service: str = "instalacao") -> str:
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = service
    decision = decide_commercial_path(lead_state, text)
    return decision.path


# ---------------------------------------------------------------------------
# Roteamento via texto (palavras-chave)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "preciso de VRF para loja",
    "quero VRV",
    "projeto de dutos",
    "quero cassete",
    "preciso de piso teto",
    "piso-teto para sala",
    "splitão",
    "splitao",
    "multisplit",
    "multi split",
    "projeto para restaurante",
    "alto padrão residencial",
    "alto padrao comercial",
    "ar para galpão",
    "preciso de elétrica",
])
def test_high_value_routes_to_project_quote(text):
    """Palavras-chave de alto valor devem gerar project_quote."""
    path = _decide(text)
    assert path == "project_quote", f"Esperava project_quote para '{text}', obteve '{path}'"


# ---------------------------------------------------------------------------
# BTUs acima de 18000 -> project_quote
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("btus_str", [
    "24000",
    "36000",
    "48000",
    "60000",
])
def test_btus_above_18000_project_quote(btus_str):
    """BTUs acima de 18000 devem gerar project_quote."""
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["btus"] = btus_str
    decision = decide_commercial_path(lead_state, "")
    assert decision.path == "project_quote", (
        f"Esperava project_quote para {btus_str} BTUs, obteve '{decision.path}'"
    )


# ---------------------------------------------------------------------------
# BTUs abaixo de 18000 não devem ir para project_quote apenas por BTU
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("btus_str", [
    "9000",
    "12000",
    "18000",
])
def test_btus_below_18000_not_project(btus_str):
    """BTUs <= 18000 NÃO devem gerar project_quote só por BTU (sem outras pistas)."""
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["btus"] = btus_str
    decision = decide_commercial_path(lead_state, "instalação simples")
    assert decision.path != "project_quote", (
        f"NÃO esperava project_quote para {btus_str} BTUs"
    )


# ---------------------------------------------------------------------------
# Preço correto para cada path
# ---------------------------------------------------------------------------

def test_project_quote_owner_alert():
    """project_quote deve gerar owner_alert=True."""
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    decision = decide_commercial_path(lead_state, "quero VRF para loja")
    assert decision.path == "project_quote"
    assert decision.owner_alert is True
    assert decision.visit_price == 50


def test_fixed_hygienization_price_200():
    """Higienização padrão deve ter fixed_price=200."""
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "higienizacao"
    decision = decide_commercial_path(lead_state, "")
    assert decision.path == "fixed_hygienization"
    assert decision.fixed_price == 200


def test_maintenance_visit_50():
    """Manutenção deve sempre ter visit_price=50."""
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "manutencao"
    decision = decide_commercial_path(lead_state, "meu ar não liga")
    assert decision.path == "technical_visit_50"
    assert decision.visit_price == 50


def test_no_photo_visit_50():
    """Instalação sem foto deve gerar technical_visit_50 com visit_price=50."""
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    decision = decide_commercial_path(lead_state, "não tenho foto")
    assert decision.path == "technical_visit_50"
    assert decision.visit_price == 50
