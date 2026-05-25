import asyncio

from langchain_core.messages import AIMessage

from agent_graph.nodes.nodes import (
    _format_customer_whatsapp_response,
    _shape_whatsapp_response,
    format_whatsapp,
)


def run(coro):
    return asyncio.run(coro)


def test_format_preserves_line_breaks():
    raw = "Perfeito, entendi.\n\nPara acesso simples, fica R$850.\n\nMe manda uma foto do local?"

    formatted = _format_customer_whatsapp_response(raw, "analise_tecnica")

    assert "\n\n" in formatted
    assert "Para acesso simples" in formatted


def test_format_keeps_numbered_list():
    raw = "Me manda:\n1. Foto interna\n2. Foto externa"

    formatted = _format_customer_whatsapp_response(raw, "analise_tecnica")

    assert "1. Foto interna" in formatted
    assert "2. Foto externa" in formatted


def test_format_does_not_join_everything():
    raw = (
        "Perfeito, entendi que é instalação. "
        "Para Santos, instalação de split com acesso simples fica R$850. "
        "Se tiver telhado, altura ou distância grande, precisa avaliar antes. "
        "Me manda uma foto do local interno?"
    )

    formatted = _format_customer_whatsapp_response(raw, "analise_tecnica")

    assert "\n\n" in formatted
    assert max(len(block) for block in formatted.split("\n\n")) < len(formatted)


def test_format_removes_emojis():
    formatted = _format_customer_whatsapp_response("Perfeito ✅ me manda foto 📸", "duvida")

    assert "✅" not in formatted
    assert "📸" not in formatted


def test_format_allows_short_list_when_multiple_fields():
    raw = "Pra eu avaliar certinho, me manda foto interna, foto externa e bairro/cidade."

    formatted = _format_customer_whatsapp_response(raw, "analise_tecnica")

    assert "1. Foto do local interno" in formatted
    assert "2. Foto do local externo" in formatted
    assert "3. Bairro/cidade" in formatted


def test_format_single_question():
    raw = "Qual cidade? Qual BTU? Tem foto? Tem ponto elétrico?"

    formatted = _format_customer_whatsapp_response(raw, "analise_tecnica")

    assert formatted.count("?") <= 2


def test_format_max_chars():
    raw = "Ótima dúvida. " + ("Esse detalhe impacta no consumo e precisa de avaliação. " * 60)

    formatted = _format_customer_whatsapp_response(raw, "consultoria", max_chars=850)

    assert len(formatted) <= 850


def test_format_no_markdown_headers():
    formatted = _format_customer_whatsapp_response("# Orçamento\n\nPara acesso simples, fica R$850.", "duvida")

    assert "#" not in formatted
    assert "Orçamento" in formatted


def test_format_no_robot_phrases():
    formatted = _format_customer_whatsapp_response(
        "Prezado cliente, conforme solicitado, para prosseguirmos, me mande uma foto.",
        "duvida",
    )

    assert "Prezado cliente" not in formatted
    assert "conforme solicitado" not in formatted.lower()
    assert "Para prosseguirmos" not in formatted


def test_price_response_readable():
    raw = (
        "Perfeito, instalação de split 12.000 BTUs em Santos. "
        "Para acesso simples, fica R$850. "
        "Me manda uma foto do local interno e externo?"
    )

    formatted = _shape_whatsapp_response(raw, "analise_tecnica")

    assert "R$850" in formatted
    assert "\n\n" in formatted


def test_installation_data_list_readable():
    raw = "Me manda foto interna, foto externa e bairro/cidade."

    formatted = _format_customer_whatsapp_response(raw, "analise_tecnica")

    assert "1. Foto do local interno" in formatted
    assert "2. Foto do local externo" in formatted
    assert "3. Bairro/cidade" in formatted


def test_no_emoji_customer_final_response():
    result = run(
        format_whatsapp(
            {
                "messages": [AIMessage(content="Perfeito ✅\n\nMe manda foto interna e externa 📸?")],
                "outcome": "analise_tecnica",
            }
        )
    )

    final = result["messages"][-1].content
    assert "✅" not in final
    assert "📸" not in final
