"""Políticas de review para o modo ASSISTED.

Define quais intents exigem revisão humana, políticas de áudio/documento,
e regras de expiração.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from refrimix_core.review.review_models import ProposedChannel, ReviewPriority


# ── Configurações via env ─────────────────────────────────────────────────────

_AUDIO_MAX_CHARS = int(os.getenv("REVIEW_AUDIO_MAX_CHARS", "300"))
_AUDIO_MIN_APPROVAL_SCORE = float(os.getenv("REVIEW_AUDIO_MIN_SCORE", "0.7"))
_DOC_BLOCKED_EXTENSIONS = frozenset(
    ext.strip().lower()
    for ext in os.getenv("REVIEW_DOC_BLOCKED_EXTENSIONS", "pdf,doc,docx,xls,xlsx,ppt,pptx").split(",")
    if ext.strip()
)
_EXPIRY_HOURS = int(os.getenv("REVIEW_DEFAULT_EXPIRY_HOURS", "24"))
_EXPIRY_HOURS_URGENT = int(os.getenv("REVIEW_EXPIRY_HOURS_URGENT", "2"))
_EXPIRY_HOURS_HIGH = int(os.getenv("REVIEW_EXPIRY_HOURS_HIGH", "8"))


# ── Intent → Priority (re-exporta lógica do review_models) ───────────────────

from refrimix_core.review.review_models import _classify_priority

# ── Intent filter (mesma lógica do runtime_config) ───────────────────────────

HUMAN_REVIEW_REQUIRED_INTENTS = frozenset(
    s.strip().lower()
    for s in os.getenv(
        "BOT_HUMAN_REVIEW_REQUIRED_INTENTS",
        "risco_eletrico,projeto,pmoc,laudo,contrato,reclamacao"
    ).split(",")
    if s.strip()
)

AUTO_REPLY_ALLOWED_INTENTS = frozenset(
    s.strip().lower()
    for s in os.getenv(
        "BOT_AUTO_REPLY_ALLOWED_INTENTS",
        "welcome,higienizacao,visita_tecnica,servicos,agenda"
    ).split(",")
    if s.strip()
)


def intent_requires_human_review(intent: Optional[str]) -> bool:
    """Verifica se o intent SEMPRE exige revisão humana."""
    if not intent:
        return False
    return intent.lower() in HUMAN_REVIEW_REQUIRED_INTENTS


def intent_is_auto_allowed(intent: Optional[str]) -> bool:
    """Verifica se o intent pode auto-enviar em CANARY (para info)."""
    if not intent:
        return False
    return intent.lower() in AUTO_REPLY_ALLOWED_INTENTS


# ── Expiry hours by priority ─────────────────────────────────────────────────

def get_expiry_hours(priority: ReviewPriority) -> int:
    """Retorna horas até expiração por prioridade."""
    if priority == ReviewPriority.URGENT:
        return _EXPIRY_HOURS_URGENT
    if priority == ReviewPriority.HIGH:
        return _EXPIRY_HOURS_HIGH
    return _EXPIRY_HOURS


# ── Audio policy ──────────────────────────────────────────────────────────────

class AudioPolicyResult:
    """Resultado da avaliação de política de áudio."""

    def __init__(
        self,
        allowed: bool,
        reason: str,
        score: float = 0.0,
        blocked_reason: Optional[str] = None,
    ) -> None:
        self.allowed = allowed
        self.reason = reason
        self.score = score
        self.blocked_reason = blocked_reason

    @classmethod
    def allowed(cls, reason: str, score: float = 1.0) -> "AudioPolicyResult":
        return cls(allowed=True, reason=reason, score=score)

    @classmethod
    def denied(cls, reason: str, score: float = 0.0, blocked_reason: Optional[str] = None) -> "AudioPolicyResult":
        return cls(allowed=False, reason=reason, score=score, blocked_reason=blocked_reason or reason)


def evaluate_audio_policy(
    text_response: str,
    proposed_channel: ProposedChannel,
    intent: str,
) -> AudioPolicyResult:
    """Avalia se um áudio pode ser enviado.

    Regras:
    - Texto > 300 chars: áudio é longa → revisar
    - Texto < 50 chars: áudio curto demais → revisar
    - Intent de risco: SEMPRE revisar
    - ProposedChannel != audio: não aplicar
    """
    # Se não é áudio, não aplicar política
    if proposed_channel != ProposedChannel.AUDIO:
        return AudioPolicyResult.allowed("não é áudio", score=1.0)

    # Intent de risco sempre bloqueia
    if intent_requires_human_review(intent):
        return AudioPolicyResult.denied(
            f"intent '{intent}' requer revisão humana",
            score=0.0,
            blocked_reason="intent_risco",
        )

    text_len = len(text_response)

    # Texto muito longo
    if text_len > _AUDIO_MAX_CHARS:
        return AudioPolicyResult.denied(
            f"texto de {_AUDIO_MAX_CHARS} chars é longo demais para áudio sem revisão",
            score=0.3,
            blocked_reason="texto_longo",
        )

    # Texto muito curto
    if text_len < 50:
        return AudioPolicyResult.denied(
            "texto muito curto para áudio",
            score=0.5,
            blocked_reason="texto_curto",
        )

    # Score baseado no tamanho
    if text_len <= 150:
        score = 1.0
        reason = "texto adequado para áudio"
    elif text_len <= 250:
        score = 0.8
        reason = "texto moderado para áudio"
    else:
        score = 0.6
        reason = "texto longo, verificar manualmente"

    return AudioPolicyResult.allowed(reason, score)


# ── Document policy ───────────────────────────────────────────────────────────

def evaluate_document_policy(proposed_channel: ProposedChannel) -> bool:
    """PDF e documentos NUNCA são autoenviados.

    Sempre retorna False para canais de documento.
    O humano precisa aprovar explicitamente.
    """
    return proposed_channel != ProposedChannel.PDF


# ── Review action validation ─────────────────────────────────────────────────

def can_auto_send_response(
    intent: str,
    priority: ReviewPriority,
    proposed_channel: ProposedChannel,
) -> bool:
    """Determina se uma resposta pode ser enviada automaticamente.

    Em ASSISTED_MODE, isso é chamado para verificar se o item
    pode ser marcado como auto-envio (raro, só casos triviais).
    Na prática, ASSISTED_MODE sempre requer aprovação humana.
    """
    # Documento: nunca autoenviar
    if not evaluate_document_policy(proposed_channel):
        return False

    # Intent que requer revisão: nunca autoenviar
    if intent_requires_human_review(intent):
        return False

    # URGENT: nunca autoenviar
    if priority == ReviewPriority.URGENT:
        return False

    # HIGH: nunca autoenviar
    if priority == ReviewPriority.HIGH:
        return False

    return True


# ── Priority label for display ────────────────────────────────────────────────

def get_priority_label(priority: ReviewPriority) -> str:
    """Label legível para prioridade."""
    return {
        ReviewPriority.URGENT: "🔴 Urgente",
        ReviewPriority.HIGH: "🟠 Alto valor",
        ReviewPriority.NORMAL: "🟡 Normal",
        ReviewPriority.LOW: "🟢 Baixa",
    }.get(priority, str(priority))


def get_status_label(status: "ReviewStatus") -> str:
    """Label legível para status."""
    from refrimix_core.review.review_models import ReviewStatus
    return {
        ReviewStatus.PENDING: "⏳ Pendente",
        ReviewStatus.APPROVED: "✅ Aprovado",
        ReviewStatus.EDITED: "✏️ Editado",
        ReviewStatus.REJECTED: "❌ Rejeitado",
        ReviewStatus.EXPIRED: "⏰ Expirado",
        ReviewStatus.SENT: "📤 Enviado",
    }.get(status, str(status))