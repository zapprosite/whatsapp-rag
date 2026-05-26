import pytest
from agent_graph.domain.response_catalog import ResponseContext, render_response
from app.mvp_attendance import compose_response_mvp_catalog

def test_mvp_greeting():
    """1. Teste de saudação básica inicial."""
    ctx = ResponseContext()
    res = render_response("welcome_onboarding", ctx)
    assert "Bom dia, tudo joia?" in res
    assert "Como posso te ajudar hoje?" in res

def test_mvp_ask_name():
    """2. Teste de solicitação de nome caso esteja ausente."""
    ctx = ResponseContext(service="instalacao")
    res = render_response("ask_lead_name", ctx)
    assert "Me passa seu nome pra eu deixar o atendimento certinho?" in res

def test_mvp_ask_service():
    """3. Teste de solicitação do tipo de serviço caso esteja ausente."""
    ctx = ResponseContext()
    res = render_response("ask_basic_service", ctx)
    assert "instalação, manutenção, higienização ou conserto?" in res

def test_mvp_fixed_installation():
    """4. Teste do valor fixo de instalação simples (R$850)."""
    ctx = ResponseContext()
    res = render_response("offer_fixed_installation", ctx)
    assert "R$850" in res
    assert "costa/costa" in res
    assert "até 3 metros" in res

def test_mvp_technical_visit():
    """5. Teste da oferta de visita técnica caso falte fotos ou seja manutenção."""
    ctx = ResponseContext(service="manutencao")
    res = render_response("offer_technical_visit", ctx)
    assert "R$50" in res
    assert "Para manutenção, o caminho correto é visita/análise técnica" in res

def test_mvp_fixed_hygienization():
    """6. Teste do valor de higienização padrão (R$200)."""
    ctx = ResponseContext()
    res = render_response("offer_fixed_hygienization", ctx)
    assert "R$200 por aparelho" in res
    assert "Quantos aparelhos são?" in res
