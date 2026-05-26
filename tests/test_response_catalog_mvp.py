import pytest
from agent_graph.domain.response_catalog import ResponseContext, render_response
from agent_graph.guards.response_guard import validate_response_before_send
from agent_graph.nodes.compose_response import compose_response

def test_welcome_onboarding():
    ctx = ResponseContext(greeting="Bom dia")
    res = render_response("welcome_onboarding", ctx)
    assert "Bom dia, tudo joia?" in res
    assert "Como posso te ajudar hoje?" in res

    ctx_default = ResponseContext()
    res_default = render_response("welcome_onboarding", ctx_default)
    assert "Olá, tudo joia?" in res_default

def test_ask_lead_name():
    ctx_greeting = ResponseContext(greeting="Boa tarde")
    res_g = render_response("ask_lead_name", ctx_greeting)
    assert "Boa tarde, tudo joia?" in res_g
    assert "Me passa seu nome" in res_g

    ctx_service = ResponseContext(service="instalacao")
    res_s = render_response("ask_lead_name", ctx_service)
    assert "Consigo te ajudar com instalação sim." in res_s
    assert "Me passa seu nome" in res_s

    ctx_default = ResponseContext()
    res_d = render_response("ask_lead_name", ctx_default)
    assert "Perfeito." in res_d
    assert "Me passa seu nome" in res_d

def test_ask_basic_service():
    ctx = ResponseContext()
    res = render_response("ask_basic_service", ctx)
    assert "instalação, manutenção, higienização ou conserto" in res

def test_offer_fixed_installation():
    ctx = ResponseContext()
    res = render_response("offer_fixed_installation", ctx)
    assert "R$850" in res
    assert "até 3 metros" in res
    assert "acesso fácil" in res
    assert "Qual período fica melhor" in res

def test_offer_technical_visit():
    ctx_inst = ResponseContext(service="instalacao")
    res_inst = render_response("offer_technical_visit", ctx_inst)
    assert "R$50" in res_inst
    assert "Como ainda falta confirmar" in res_inst

    ctx_maint = ResponseContext(service="manutencao")
    res_maint = render_response("offer_technical_visit", ctx_maint)
    assert "Para manutenção, o caminho correto é visita/análise técnica" in res_maint
    assert "R$50" in res_maint

    ctx_gen = ResponseContext()
    res_gen = render_response("offer_technical_visit", ctx_gen)
    assert "Seguimos como visita técnica de R$50." in res_gen

def test_offer_fixed_hygienization():
    ctx = ResponseContext()
    res = render_response("offer_fixed_hygienization", ctx)
    assert "R$200 por aparelho" in res
    assert "Quantos aparelhos são" in res

def test_explain_last_offer():
    ctx_visit = ResponseContext(commercial_path="technical_visit_50")
    res_visit = render_response("explain_last_offer", ctx_visit)
    assert "Claro." in res_visit
    assert "visita técnica de R$50" in res_visit

    ctx_inst = ResponseContext(commercial_path="fixed_installation_simple")
    res_inst = render_response("explain_last_offer", ctx_inst)
    assert "Costa/costa" in res_inst or "costa/costa" in res_inst
    assert "R$850" in res_inst

    ctx_hyg = ResponseContext(commercial_path="fixed_hygienization")
    res_hyg = render_response("explain_last_offer", ctx_hyg)
    assert "R$200 por aparelho" in res_hyg
    assert "limpeza mais completa" in res_hyg

    ctx_fallback = ResponseContext()
    res_fallback = render_response("explain_last_offer", ctx_fallback)
    assert "Funciona assim" in res_fallback
    assert "R$850" in res_fallback
    assert "R$50" in res_fallback

@pytest.mark.anyio
async def test_compose_response_integration():
    state = {
        "messages": [],
        "lead_state": {
            "tipo_servico": "instalacao",
            "cidade_bairro": "Guarujá",
            "btus": "9000 BTUs",
            "aparelho_ja_comprado": True,
            "fotos": {
                "local_interno": "http://example.com/interno.jpg",
                "local_externo": "http://example.com/externo.jpg"
            },
            "commercial_decision": {
                "path": "fixed_installation_simple",
                "fixed_price": 850
            }
        },
        "next_action": {
            "type": "offer_fixed_installation"
        }
    }
    res_node = await compose_response(state)
    response_text = res_node["messages"][-1].content
    assert "R$850" in response_text
    
    # Validação com o response guard
    ok, violations = validate_response_before_send(response_text, state)
    assert ok, f"Guardrail violations: {violations}"
