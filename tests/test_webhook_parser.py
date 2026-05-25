from __future__ import annotations

from app.api.webhook import parse_evolution_webhook


def test_parse_conversation_payload_normalizes_phone():
    payload = {
        "instance": "RefrimixLead",
        "data": {
            "key": {
                "remoteJid": "5513999999999:12@s.whatsapp.net",
                "id": "msg-1",
                "fromMe": False,
            },
            "message": {"conversation": "Meu ar não tá gelando"},
            "messageType": "conversation",
        },
    }

    parsed, skipped = parse_evolution_webhook(payload)

    assert skipped is None
    assert parsed is not None
    assert parsed.phone == "5513999999999"
    assert parsed.message == "Meu ar não tá gelando"
    assert parsed.instance == "RefrimixLead"
    assert parsed.msg_id == "msg-1"


def test_parse_evolution_lid_payload_prefers_phone_alt():
    payload = {
        "instance": "RefrimixLead",
        "data": {
            "key": {
                "remoteJid": "47554347716639@lid",
                "remoteJidAlt": "5513996659382@s.whatsapp.net",
                "id": "lid-msg-1",
                "fromMe": False,
            },
            "message": {"conversation": "Oi, quero instalar um split"},
            "messageType": "conversation",
        },
    }

    parsed, skipped = parse_evolution_webhook(payload)

    assert skipped is None
    assert parsed is not None
    assert parsed.phone == "5513996659382"


def test_parse_image_payload_uses_caption_and_media_url():
    payload = {
        "instanceName": "RefrimixLead",
        "data": {
            "key": {"remote": "5513888888888@s.whatsapp.net", "fromMe": False},
            "message": {
                "imageMessage": {
                    "url": "https://example.com/ar.jpg",
                    "caption": "Olha esse vazamento",
                }
            },
        },
    }

    parsed, skipped = parse_evolution_webhook(payload)

    assert skipped is None
    assert parsed is not None
    assert parsed.message_type == "imageMessage"
    assert parsed.message == "Olha esse vazamento"
    assert parsed.media_url == "https://example.com/ar.jpg"


def test_parse_audio_payload_without_caption_uses_placeholder():
    payload = {
        "data": {
            "key": {"remote": "5513777777777@s.whatsapp.net", "fromMe": False},
            "message": {"audioMessage": {"url": "https://example.com/audio.ogg"}},
        },
    }

    parsed, skipped = parse_evolution_webhook(payload)

    assert skipped is None
    assert parsed is not None
    assert parsed.message_type == "audioMessage"
    assert parsed.message == "[áudio]"


def test_parse_group_and_from_me_are_skipped():
    group_payload = {
        "data": {
            "key": {"remote": "120363000000000@g.us", "fromMe": False},
            "message": {"conversation": "teste"},
        },
    }
    own_payload = {
        "data": {
            "key": {"remote": "5513999999999@s.whatsapp.net", "fromMe": True},
            "message": {"conversation": "teste"},
        },
    }

    assert parse_evolution_webhook(group_payload)[1] == "group"
    assert parse_evolution_webhook(own_payload)[1] == "fromMe"


def test_parse_from_me_refrimix_qr_number_is_skipped_even_with_alt():
    payload = {
        "instance": "RefrimixLead",
        "data": {
            "key": {
                "remoteJid": "47554347716639@lid",
                "remoteJidAlt": "5513996659382@s.whatsapp.net",
                "fromMe": True,
                "id": "own-message",
            },
            "message": {"conversation": "Olá"},
            "messageType": "conversation",
        },
        "sender": "5513974139382@s.whatsapp.net",
    }

    parsed, skipped = parse_evolution_webhook(payload)

    assert parsed is None
    assert skipped == "fromMe"


def test_parse_from_me_manager_cron_number_is_skipped_even_with_lid():
    payload = {
        "instance": "RefrimixLead",
        "data": {
            "key": {
                "remoteJid": "5513996659382@s.whatsapp.net",
                "remoteJidAlt": "47554347716639@lid",
                "fromMe": True,
                "id": "manager-cron",
            },
            "message": {"conversation": "Resumo do cron"},
            "messageType": "conversation",
        },
        "sender": "5513974139382@s.whatsapp.net",
    }

    parsed, skipped = parse_evolution_webhook(payload)

    assert parsed is None
    assert skipped == "fromMe"
