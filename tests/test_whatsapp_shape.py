from agent_graph.nodes.nodes import _shape_whatsapp_response


def test_shape_whatsapp_response_removes_lists_and_limits_questions():
    raw = """Oi! Me fala aí:

- Quantos metros tem?
- Quais cômodos precisam?
- Tem sol da tarde?
- Qual cidade?
"""

    shaped = _shape_whatsapp_response(raw, "reuniao_projeto")

    assert "- " not in shaped
    assert shaped.count("?") <= 2
    assert len(shaped) <= 650


def test_shape_whatsapp_response_trims_long_answer_and_keeps_cta():
    raw = "Ótima dúvida. " + ("Esse detalhe impacta no consumo. " * 40)

    shaped = _shape_whatsapp_response(raw, "consultoria")

    assert len(shaped) <= 650
    assert shaped.endswith("?")
