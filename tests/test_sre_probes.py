from __future__ import annotations

from sre.probes import ONE_SECOND_WAV_B64, build_parser, build_webhook_payload, run_evolution_audio


def test_build_webhook_payload_conversation_is_evolution_compatible():
    payload = build_webhook_payload(
        "conversation",
        phone="5513999999999",
        instance="RefrimixLead",
        content="Teste",
        msg_id="fixed-id",
    )

    assert payload["instance"] == "RefrimixLead"
    assert payload["data"]["key"]["remote"] == "5513999999999@s.whatsapp.net"
    assert payload["data"]["key"]["id"] == "fixed-id"
    assert payload["data"]["messageType"] == "conversation"
    assert payload["data"]["message"]["conversation"] == "Teste"


def test_build_webhook_payload_rejects_unknown_type():
    try:
        build_webhook_payload("videoMessage")
    except ValueError as exc:
        assert "nao suportado" in str(exc)
    else:
        raise AssertionError("tipo desconhecido deveria falhar")


def test_evolution_audio_requires_api_key(monkeypatch, capsys):
    monkeypatch.delenv("EVOLUTION_API_KEY", raising=False)
    monkeypatch.delenv("AUTHENTICATION_API_KEY", raising=False)

    args = build_parser().parse_args(["evolution-audio", "--audio-b64", ONE_SECOND_WAV_B64])

    assert run_evolution_audio(args) == 2
    assert "precisa estar configurada" in capsys.readouterr().err
