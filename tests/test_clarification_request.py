import pytest
from agent_graph.nodes.plan_next_action import plan_next_action
from agent_graph.nodes.compose_response import compose_response
from agent_graph.guards.response_guard import validate_response_before_send

@pytest.mark.anyio
async def test_understand_message_clarification_detection():
    from agent_graph.nodes.understand_message import understand_message
    from langchain_core.messages import HumanMessage
    
    state = {
        "messages": [HumanMessage(content="Não entendi")],
        "lead_state": {"tipo_servico": "instalacao"}
    }
    
    res = await understand_message(state)
    und = res["message_understanding"]
    assert und["asks_clarification"] is True
    assert und["kind"] == "clarification_request"

@pytest.mark.anyio
async def test_plan_next_action_clarification_routing():
    state = {
        "messages": [],
        "latest_user_text": "não entendi nada",
        "message_understanding": {
            "kind": "clarification_request",
            "asks_clarification": True
        },
        "lead_state": {
            "tipo_servico": "instalacao"
        }
    }
    
    res = await plan_next_action(state)
    action = res["next_action"]
    assert action["type"] == "answer_clarification_llm"

@pytest.mark.anyio
async def test_end_to_end_clarification_flow():
    state = {
        "messages": [],
        "message_understanding": {
            "kind": "clarification_request",
            "asks_clarification": True
        },
        "lead_state": {
            "tipo_servico": "instalacao",
            "commercial_decision": {
                "path": "technical_visit_50",
                "visit_price": 50
            }
        },
        "next_action": {
            "type": "explain_last_offer",
            "service": "instalacao"
        }
    }
    
    res_node = await compose_response(state)
    response_text = res_node["messages"][-1].content
    
    assert "Claro." in response_text
    assert "visita técnica de R$50" in response_text
    assert "O técnico avalia no local" in response_text

    ok, violations = validate_response_before_send(response_text, state)
    assert ok, f"Violations detected on clarification response: {violations}"
