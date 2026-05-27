"""
understand_message — extrai intenção e classificação da mensagem.
"""
from __future__ import annotations

from typing import Any

from refrimix_core.domain.text_normalizer import (
    fold, detect_service_mentioned, detect_window,
    detect_quantity, short_answer_kind, is_greeting,
)


_MAINTENANCE_SIGNALS = (
    # Não gela / não funciona (todas as variações)
    "nao gela", "não gela",
    "nao liga", "não liga",
    "nao funciona", "não funciona",
    "nao esfria", "não esfria",
    "nao resfria", "não resfria",
    "nao ta gelando", "não ta gelando", "não tá gelando",
    "nao ta resfriar", "não ta resfriar",
    # Parou
    "parou de gelar", "parou de funcionar", "parou de resfriar",
    "parou de ligar", "não liga mais",
    # Ventilação sem frio
    "so ventila", "só ventila", "ventila mas não gela", "ventila mas não resfria",
    "só vento", "vento quente",
    # Água / vazamento
    "pinga", "pingando", "gotejando", "vazando",
    # Cheiro
    "cheiro ruim", "cheiro mal",
    # Ruído
    "barulho", "barulhento", "vibrando", "roncando",
    # Elétrica (com e sem typo)
    "disjuntor cai", "disjuntor caindo", "disjuntor desarmando",
    "dijuntor cai", "dijuntor caindo",  # typo comum: disjuntor → dijuntor
    # Erro no visor
    "codigo erro", "codigo de erro", "erro no visor", "erro e1", "erro e2", "codigo e1", "codigo e2",
)


def _detect_maintenance_signal(text: str) -> str | None:
    """Detecta sinais de manutenção no texto."""
    t = fold(text)
    for signal in _MAINTENANCE_SIGNALS:
        if signal in t:
            return signal
    return None


def understand_message(
    text: str,
    message_type: str,
    last_asked_field: str | None,
    service_in_state: str | None,
) -> dict[str, Any]:
    """
    Analisa a mensagem e retorna estrutura de entendimento.
    """
    t = fold(text)
    service_mentioned = detect_service_mentioned(text)

    # Detectar tipo de mensagem
    kind = _classify_kind(t, message_type, last_asked_field, service_in_state, service_mentioned)

    # Slot choice (número simples 1-3)
    import re as _re
    slot_choice = int(t) if _re.fullmatch(r"[123]", t) else None

    # Short answer
    short_answer = short_answer_kind(text)

    # Window
    window = detect_window(text)

    # Quantity (só quando último campo era quantidade_aparelhos)
    quantity = None
    if last_asked_field == "quantidade_aparelhos":
        quantity = detect_quantity(text)

    # Greeting
    greeting = is_greeting(text)

    # Maintenance signal
    maintenance_signal = _detect_maintenance_signal(text)

    return {
        "kind": kind,
        "service_mentioned": service_mentioned,
        "slot_choice": slot_choice,
        "short_answer": short_answer,
        "window": window,
        "quantity": quantity,
        "is_greeting": greeting,
        "is_image": message_type == "imageMessage",
        "is_audio": message_type == "audioMessage",
        "maintenance_signal": maintenance_signal,
    }


def _classify_kind(
    text: str,
    message_type: str,
    last_asked_field: str | None,
    service_in_state: str | None,
    service_mentioned: str | None,
) -> str:
    # Audio transcription failure
    if message_type == "audioMessage" and not text.strip():
        return "audio_transcription_failed"

    # Image
    if message_type == "imageMessage":
        return "image_upload"

    # Maintenance signal → manutenção
    if _detect_maintenance_signal(text):
        return "maintenance_signal"

    # Services question ("quais serviços", "o que vocês fazem", etc.)
    if _is_services_question(text):
        return "services_question"

    # Clarification request ("não entendi", "me explica", "não ficou claro")
    if _is_clarification_request(text):
        return "clarification_request"

    # Window preference
    window = detect_window(text)
    if window and last_asked_field == "preferred_window":
        return "window_preference"

    # Quantity response (after "Quantos aparelhos são?")
    if last_asked_field == "quantidade_aparelhos":
        if detect_quantity(text):
            return "quantity_response"

    # Short answer (yes/no for point_eletrico, etc.)
    if short_answer_kind(text):
        return "short_answer"

    # Greeting only
    if is_greeting(text) and len(text.split()) <= 5 and not service_in_state:
        return "greeting"

    # Service mentioned in text
    if service_mentioned and not service_in_state:
        return "service_new"

    # Already in service flow
    if service_in_state or service_mentioned:
        return "in_service_flow"

    # Ambiguous / unclear
    if len(text.split()) <= 3:
        return "short_unclear"

    return "unknown"


def _is_services_question(text: str) -> bool:
    t = fold(text)
    q_terms = (
        "quais servicos", "quais serviços",
        "o que voces fazem", "o que vocês fazem",
        "o que voces atendem", "o que vocês atendem",
        "quais servicios", "que servico", "que serviço",
        "quais atividades", "o que oferecem",
        "quais servicos", "servicos de",
    )
    return any(term in t for term in q_terms)


def _is_clarification_request(text: str) -> bool:
    t = fold(text)
    c_terms = (
        "nao entendi", "não entendi", "não intendi",
        "não ficou claro", "não ficou bem", "não tá claro",
        "me explica", "explica ai", "explica isso",
        "não sei", "não sei como", "não tenho certeza",
        "poderia explicar", "pode explicar",
    )
    return any(term in t for term in c_terms)