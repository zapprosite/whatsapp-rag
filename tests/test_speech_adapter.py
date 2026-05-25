from agent_graph.services.speech_adapter import build_tts_text


def test_tts_text_removes_lists_and_markdown():
    text = "Perfeito.\n\n1. Foto interna\n2. Foto externa\n**Me manda quando puder?**"

    spoken = build_tts_text(text, None, "qualify_quote")

    assert "1." not in spoken
    assert "**" not in spoken
    assert "\n" not in spoken


def test_tts_does_not_repeat_greeting_mid_conversation():
    mind = {
        "lead_profile": {"relationship_type": "qualifying_lead"},
        "tts": {"speech_summary": "Continuar instalação sem repetir serviço."},
    }

    spoken = build_tts_text("Oi, tudo bem? Me manda a foto do local interno?", mind, "qualify_quote")

    assert not spoken.lower().startswith("oi")
    assert "foto do local interno" in spoken
