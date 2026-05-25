from langchain_core.messages import AIMessage, HumanMessage

from agent_graph.nodes.nodes import _looks_like_incomplete_customer_response, _shape_whatsapp_response, format_whatsapp


def test_whatsapp_formatter_repairs_punctuation_spacing():
    formatted = _shape_whatsapp_response(
        "Entendi,split que não liga precisa avaliar.Para eu te orientar,me manda foto?",
        "analise_tecnica",
    )

    assert "Entendi, split" in formatted
    assert "avaliar. Para" in formatted
    assert "orientar, me" in formatted


def test_whatsapp_formatter_does_not_cut_mid_sentence_when_truncating():
    text = "Primeira frase ok. " + ("explicação longa " * 80)

    formatted = _shape_whatsapp_response(text, "duvida", max_chars=120)

    assert formatted.endswith((".", "?"))
    assert not formatted.endswith("long")
    assert len(formatted) <= 121


def test_incomplete_detector_allows_numbered_list_tail():
    assert _looks_like_incomplete_customer_response("Me manda:\n\n1. Foto\n2. Bairro/cidade") is False
    assert _looks_like_incomplete_customer_response("Me manda, po") is True


def test_format_whatsapp_repairs_incomplete_maintenance_response():
    state = {
        "messages": [
            HumanMessage(content="Meu ar tá com problema na placa"),
            AIMessage(content="Entendi. Placa eletrônica precisa testar. Me manda, po"),
        ],
        "lead_state": {"tipo_servico": "manutencao"},
        "service": "manutencao",
        "outcome": "analise_tecnica",
    }

    result = __import__("asyncio").run(format_whatsapp(state))
    response = result["messages"][-1].content

    assert response.endswith("?")
    assert "Me manda uma foto" in response
