from __future__ import annotations

import asyncio
import importlib

from langchain_core.messages import HumanMessage

from agent_graph.domain.commercial_router import decide_commercial_path
from agent_graph.nodes.compose_response import compose_response
from agent_graph.nodes.nodes import _direct_price_response, _lead_state_copy
from agent_graph.nodes.plan_next_action import plan_next_action
from agent_graph.nodes.reduce_lead_state import reduce_lead_state

planner_module = importlib.import_module("agent_graph.nodes.plan_next_action")


def run(coro):
    return asyncio.run(coro)


def _last_ai_text(result: dict) -> str:
    messages = result.get("messages") or []
    return str(messages[-1].content) if messages else ""


def test_installation_without_external_photo_offers_technical_visit_50():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["cidade_bairro"] = "Santos"
    lead_state["btus"] = "12000"
    lead_state["fotos"]["local_interno"] = True
    lead_state["instalacao"]["ponto_eletrico_exclusivo"] = True

    decision = decide_commercial_path(lead_state, "não tenho foto do lado de fora")

    assert decision.path == "technical_visit_50"
    assert decision.visit_price == 50
    assert decision.can_schedule_now is True


def test_maintenance_offers_technical_visit_50():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "manutencao"

    decision = decide_commercial_path(lead_state, "quero manutenção")

    assert decision.path == "technical_visit_50"
    assert decision.visit_price == 50
    assert decision.can_schedule_now is True


def test_hygienization_explains_200_and_working_condition():
    response = _direct_price_response("higienizacao", "quanto fica higienização?", {"tipo_servico": "higienizacao"})

    assert response
    assert "R$200" in response
    assert "funcionando" in response


def test_no_cooling_hygienization_becomes_maintenance_analysis():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "higienizacao"

    decision = decide_commercial_path(lead_state, "quero higienização mas ele não climatiza")

    assert decision.path == "technical_visit_50"
    assert decision.reason == "no_cooling"


def test_above_18000_btus_becomes_project_quote():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["btus"] = "24000"

    decision = decide_commercial_path(lead_state, "quero instalar um split 24000")

    assert decision.path == "project_quote"
    assert decision.can_schedule_now is True


def test_cassete_piso_teto_vrf_and_duto_become_project_quote():
    for text in ("cassete", "piso-teto", "vrf", "duto"):
        lead_state = _lead_state_copy()
        lead_state["tipo_servico"] = "instalacao"
        lead_state["modelo_aparelho"] = text
        decision = decide_commercial_path(lead_state, f"quero {text}")
        assert decision.path == "project_quote"


def test_nao_tenho_foto_does_not_block_service():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    result = run(
        compose_response(
            {
                "messages": [HumanMessage(content="Não tenho foto")],
                "lead_state": lead_state,
                "message_understanding": {"unavailable_photo": True},
                "next_action": {"type": "answer_question", "service": "instalacao", "answer_kind": "commercial"},
            }
        )
    )

    response = _last_ai_text(result)
    assert "visita técnica de R$50" in response


def test_nao_tenho_infra_does_not_block_service():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    result = run(
        compose_response(
            {
                "messages": [HumanMessage(content="Não tenho infra")],
                "lead_state": lead_state,
                "message_understanding": {"unavailable_infra": True},
                "next_action": {"type": "answer_question", "service": "instalacao", "answer_kind": "commercial"},
            }
        )
    )

    response = _last_ai_text(result)
    assert "infra" in response.lower()
    assert "visita técnica de R$50" in response


def test_sim_after_electrical_point_saves_true():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["last_asked_field"] = "ponto_eletrico_exclusivo"

    result = run(
        reduce_lead_state(
            {
                "lead_state": lead_state,
                "message_understanding": {"short_answer": "yes"},
                "customer_data": {},
            }
        )
    )

    assert result["lead_state"]["instalacao"]["ponto_eletrico_exclusivo"] is True


def test_nao_consegue_horario_calls_calendar_when_schedule_allowed(monkeypatch):
    async def fake_slots(period, lead_state, days=7, max_slots=3):
        del period, lead_state, days, max_slots
        return [{"label": "Amanhã 14:00"}, {"label": "Amanhã 16:00"}]

    monkeypatch.setattr(planner_module, "suggest_slots", fake_slots)

    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "manutencao"
    lead_state["cidade_bairro"] = "Santos"
    state = {
        "messages": [HumanMessage(content="Não consegue me dizer um horário?")],
        "lead_state": lead_state,
        "customer_data": {},
        "missing_fields": [],
        "do_not_ask": ["tipo_servico", "cidade_bairro"],
        "message_understanding": {"asks_time_specific": True, "kind": "calendar_request", "asks_calendar": True},
    }

    result = run(plan_next_action(state))

    assert result["next_action"]["type"] == "offer_calendar_slots"
    assert len(result["calendar_slots"]) == 2


def test_event_is_only_created_after_slot_choice(monkeypatch):
    async def fake_slots(period, lead_state, days=7, max_slots=3):
        del period, lead_state, days, max_slots
        return [{"label": "Amanhã 14:00"}, {"label": "Amanhã 16:00"}]

    monkeypatch.setattr(planner_module, "suggest_slots", fake_slots)

    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "manutencao"
    lead_state["cidade_bairro"] = "Santos"

    initial = run(
        plan_next_action(
            {
                "messages": [HumanMessage(content="Consegue me dizer um horário?")],
                "lead_state": lead_state,
                "customer_data": {},
                "missing_fields": [],
                "do_not_ask": ["tipo_servico", "cidade_bairro"],
                "message_understanding": {"asks_time_specific": True, "kind": "calendar_request", "asks_calendar": True},
            }
        )
    )
    assert all(effect["type"] != "google_calendar_insert" for effect in initial["next_action"]["side_effects"])

    chosen_state = initial["lead_state"]
    chosen_state["appointment"]["offered_slots"] = [{"label": "Amanhã 14:00"}, {"label": "Amanhã 16:00"}]
    confirmed = run(
        plan_next_action(
            {
                "messages": [HumanMessage(content="2")],
                "lead_state": chosen_state,
                "customer_data": {},
                "missing_fields": [],
                "do_not_ask": ["tipo_servico", "cidade_bairro"],
                "message_understanding": {"kind": "slot_choice", "slot_choice": 2},
            }
        )
    )

    assert confirmed["next_action"]["type"] == "confirm_calendar_slot"
    assert any(effect["type"] == "google_calendar_insert" for effect in confirmed["next_action"]["side_effects"])
