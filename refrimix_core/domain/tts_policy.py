"""TTS Policy — when to generate audio vs send text.

Defines what content is allowed to become synthesized speech,
what document types are always blocked, and what action types
are permitted to use audio.

This is NOT a synthesis engine — it only decides *whether* to request TTS.
"""

from dataclasses import dataclass
from enum import Enum


class TTSDecisionReason(str, Enum):
    ALLOWED_SHORT_CONFIRMATION = "allowed_short_confirmation"
    BLOCKED_TOO_LONG = "blocked_too_long"
    BLOCKED_DOCUMENT_TYPE = "blocked_document_type"
    BLOCKED_SENSITIVE = "blocked_sensitive"
    BLOCKED_USER_PREFERS_TEXT = "blocked_user_prefers_text"


@dataclass(frozen=True)
class TTSDecision:
    should_speak: bool
    reason: TTSDecisionReason
    text_fallback: bool = False


# Document types that must NEVER be sent as audio
BLOCKED_DOC_TYPES = {
    "quote_pdf",
    "budget_pdf",
    "technical_report_pdf",
    "pmoc_pdf",
    "contract_pdf",
    "sla_pdf",
    "technical_proposal_pdf",
    "proposal_pdf",
    "invoice_pdf",
    "receipt_pdf",
}

# Action types permitted to use audio
ALLOWED_ACTIONS = {
    "welcome_onboarding",
    "microcopy",
    "schedule_confirmation",
    "schedule_reminder",
    "visit_orientation",
    "short_followup",
    "callback_reminder",
    "simple_ack",
}


def should_generate_tts(
    text: str,
    action_type: str,
    document_type: str | None = None,
    user_prefers_text: bool = False,
    max_chars: int = 420,
) -> TTSDecision:
    """Decide whether to generate TTS audio or fall back to text.

    Args:
        text: raw message text
        action_type: business action from conversation router
        document_type: optional PDF/doc type tag
        user_prefers_text: explicit user preference
        max_chars: character limit for audio (default 420)

    Returns:
        TTSDecision with should_speak, reason, and text_fallback flag
    """
    if user_prefers_text:
        return TTSDecision(
            False,
            TTSDecisionReason.BLOCKED_USER_PREFERS_TEXT,
            text_fallback=True,
        )

    stripped = text.strip()
    if not stripped:
        return TTSDecision(
            False,
            TTSDecisionReason.BLOCKED_TOO_LONG,
            text_fallback=True,
        )

    if document_type in BLOCKED_DOC_TYPES:
        return TTSDecision(
            False,
            TTSDecisionReason.BLOCKED_DOCUMENT_TYPE,
            text_fallback=True,
        )

    if len(stripped) > max_chars:
        return TTSDecision(
            False,
            TTSDecisionReason.BLOCKED_TOO_LONG,
            text_fallback=True,
        )

    if action_type not in ALLOWED_ACTIONS:
        return TTSDecision(
            False,
            TTSDecisionReason.BLOCKED_SENSITIVE,
            text_fallback=True,
        )

    return TTSDecision(True, TTSDecisionReason.ALLOWED_SHORT_CONFIRMATION)


# Good audio phrases — natural, short, human
GOOD_AUDIO_PHRASES = [
    "bom dia, tudo joia?",
    "me conta: é instalação, manutenção, higienização ou conserto?",
    "certo, entendi. vou verificar o melhor caminho pra você.",
    "perfeito. vou ver os horários disponíveis por aqui.",
    "nesse caso, mantém o equipamento desligado até avaliação, por segurança.",
    "fechado. a visita técnica fica cinquenta reais e esse valor é abatido se fechar o serviço.",
    "收到. entendi perfeitamente.",
    "blz. já anoto aqui.",
    "de boa. te passo o horário assim que confirmar.",
]

# Phrases to AVOID in audio (too formal, robotic, salesy)
FORBIDDEN_AUDIO_PHRASES = [
    "segue abaixo a relação completa",
    "conforme informado anteriormente",
    "prezado cliente",
    "a refrimax tecnologia agradece",
    "como assistente virtual",
    "atenciosamente",
    "sendo assim, passamos ao",
    "no tocante ao",
    "outrossim",
]
