import pytest
import os
import json
from langchain_core.messages import HumanMessage
from agent_graph.nodes.understand_message import understand_message
from agent_graph.nodes.plan_next_action import plan_next_action
from agent_graph.nodes.compose_response import compose_response
from agent_graph.guards.response_guard import validate_response_before_send

@pytest.mark.anyio
async def test_user_greeting_with_legacy_service_routes_to_welcome():
    # Cenário 1: Cliente manda "bom dia" com lead_state antigo contendo tipo_servico="instalacao"
    # Deve responder welcome_onboarding, não offer_technical_visit.
    
    state = {
        "messages": [HumanMessage(content="bom dia")],
        "lead_state": {
            "tipo_servico": "instalacao",
            "commercial_decision": {
                "path": "technical_visit_50",
                "visit_price": 50
            }
        }
    }
    
    und_res = await understand_message(state)
    state["message_understanding"] = und_res["message_understanding"]
    
    plan_res = await plan_next_action(state)
    action = plan_res["next_action"]
    
    assert action["type"] == "welcome_onboarding"
    assert action.get("service") is None

    # Composição do response final
    state["next_action"] = action
    comp_res = await compose_response(state)
    response_text = comp_res["messages"][-1].content
    
    assert "joia" in response_text
    assert "Como posso te ajudar hoje?" in response_text
    # Garante que não ofertou visita de R$50 indevidamente
    assert "R$50" not in response_text


@pytest.mark.anyio
async def test_user_greeting_with_legacy_commercial_decision():
    # Cenário 2: Cliente manda "oi" com commercial_decision antigo technical_visit_50
    # Não pode responder R$50 de imediato.
    
    state = {
        "messages": [HumanMessage(content="oi")],
        "lead_state": {
            "tipo_servico": "instalacao",
            "commercial_decision": {
                "path": "technical_visit_50",
                "visit_price": 50
            }
        }
    }
    
    und_res = await understand_message(state)
    state["message_understanding"] = und_res["message_understanding"]
    
    plan_res = await plan_next_action(state)
    action = plan_res["next_action"]
    
    assert action["type"] == "welcome_onboarding"
    
    state["next_action"] = action
    comp_res = await compose_response(state)
    response_text = comp_res["messages"][-1].content
    
    assert "R$50" not in response_text
    assert "Como posso te ajudar hoje?" in response_text


@pytest.mark.anyio
async def test_user_greeting_with_explicit_service_does_not_trigger_generic_welcome():
    # Cenário 3: Cliente manda "bom dia quero instalação"
    # Pode responder com a oferta de instalação ou pedir nome (fluxo normal), não welcome genérico puro.
    
    state = {
        "messages": [HumanMessage(content="bom dia quero instalação")],
        "lead_state": {}
    }
    
    und_res = await understand_message(state)
    state["message_understanding"] = und_res["message_understanding"]
    
    assert state["message_understanding"]["is_greeting"] is True
    assert state["message_understanding"]["service_mentioned"] == "instalacao"
    
    plan_res = await plan_next_action(state)
    action = plan_res["next_action"]
    
    # Não pode ser welcome_onboarding genérico puro!
    assert action["type"] != "welcome_onboarding"
    # Deve ir para ask_lead_name com nota "include_greeting" ou direto para a oferta
    assert action["type"] in ("ask_lead_name", "offer_fixed_installation", "ask_basic_service")


@pytest.mark.anyio
async def test_reset_lead_clears_state_but_keeps_phone():
    # Cenário 4: Reset-lead limpa o banco/Redis sem apagar o fone
    
    from scripts.reset_lead import reset_lead
    from prisma import Prisma
    
    db = Prisma()
    await db.connect()
    try:
        phone_test = "5513996659389"
        
        # Cria ou atualiza o lead no postgres para teste de reset
        lead = await db.lead.upsert(
            where={"phone": phone_test},
            data={
                "create": {
                    "phone": phone_test,
                    "service_type": "instalacao",
                    "pipeline_stage": "ongoing",
                    "lead_state": json.dumps({"test_key": "test_val"}),
                    "conversation_summary": "Histórico ativo fictício",
                },
                "update": {
                    "service_type": "instalacao",
                    "pipeline_stage": "ongoing",
                    "lead_state": json.dumps({"test_key": "test_val"}),
                    "conversation_summary": "Histórico ativo fictício",
                }
            }
        )
        
        # Executa o reset_lead
        await reset_lead(phone=phone_test, keep_phone=True)
        
        # Recarrega o lead para validação
        cleared_lead = await db.lead.find_unique(where={"phone": phone_test})
        
        assert cleared_lead is not None
        assert cleared_lead.phone == phone_test  # Telefone deve continuar intacto
        
        # Estados devem estar limpos
        assert cleared_lead.service_type is None
        assert cleared_lead.pipeline_stage == "new"
        
        lead_state_dict = json.loads(cleared_lead.lead_state) if cleared_lead.lead_state else {}
        assert len(lead_state_dict) == 0
        assert cleared_lead.conversation_summary is None
        
    finally:
        await db.disconnect()
