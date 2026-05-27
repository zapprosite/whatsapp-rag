"""Modelos de review para o modo ASSISTED.

ReviewItem: cada resposta sugerida pelo bot que precisa de aprovação humana.
ReviewStatus: lifecycle do item (pending → approved/edited/rejected/expired/sent).
ReviewPriority: urgência baseada em intent e contexto.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class ReviewStatus(str, Enum):
    """Lifecycle do ReviewItem."""
    PENDING = "pending"       # aguardando revisão humana
    APPROVED = "approved"    # aprovado sem edição
    EDITED = "edited"        # aprovado com edição humana
    REJECTED = "rejected"    # rejeitado com motivo
    EXPIRED = "expired"      # expirou sem ação
    SENT = "sent"            # enviado ao cliente


class ReviewPriority(str, Enum):
    """Prioridade do ReviewItem baseada em risco e tipo de caso."""
    LOW = "low"       # saudação, higienização simples
    NORMAL = "normal" # manutenção, orçamento
    HIGH = "high"     # projeto, PMOC, laudo, contrato, proposta
    URGENT = "urgent" # risco elétrico, reclamação, cheiro queimado


class ProposedChannel(str, Enum):
    """Canal proposto para envio ao cliente."""
    TEXT = "text"
    AUDIO = "audio"
    PDF = "pdf"  # nunca autoenvia


# ── Intent → Priority mapping ────────────────────────────────────────────────

_URGENT_INTENTS = frozenset([
    "risco_eletrico",
    "risco",
    "eletrico",
    "choque",
    "curto",
    "fumaca",
    "cheiro_queimado",
    "desligando",
    "reclamacao",
    "problema",
])

_HIGH_INTENTS = frozenset([
    "projeto",
    "pmoc",
    "laudo",
    "contrato",
    "proposta",
    "sla",
    "proposta_tecnica",
    "orcamento",
])

_NORMAL_INTENTS = frozenset([
    "manutencao",
    "conserto",
    "instalacao",
    "visita_tecnica",
    "servicos",
    "agenda",
    "higienizacao",
    "orcamento",
])

_LOW_INTENTS = frozenset([
    "welcome",
    "saudacao",
    "oi",
    "obrigado",
    "agradecimento",
])


def _classify_priority(intent: str, user_message: str = "") -> ReviewPriority:
    """Classifica prioridade baseando-se em intent e mensagem do usuário."""
    lower_intent = intent.lower()
    lower_msg = user_message.lower()

    # URGENT: qualquer menção de risco elétrico
    if "risco" in lower_intent or "eletrico" in lower_intent:
        return ReviewPriority.URGENT
    if any(kw in lower_msg for kw in ["risco", "eletrico", "choque", "fumaca", "queimado", "curto"]):
        return ReviewPriority.URGENT
    if "reclamacao" in lower_intent or "reclamação" in lower_msg:
        return ReviewPriority.URGENT

    # URGENT: risco no content
    if any(kw in lower_msg for kw in ["socorro", "urgente", "emergencia", "nao funciona", "nao gela"]):
        return ReviewPriority.URGENT

    # HIGH
    if any(kw in lower_intent for kw in _HIGH_INTENTS):
        return ReviewPriority.HIGH

    # NORMAL
    if any(kw in lower_intent for kw in _NORMAL_INTENTS):
        return ReviewPriority.NORMAL

    # LOW
    if any(kw in lower_intent for kw in _LOW_INTENTS):
        return ReviewPriority.LOW

    # Default: NORMAL
    return ReviewPriority.NORMAL


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mask_phone(phone: str) -> str:
    """Máscara parcial de telefone para exibição segura."""
    digits = re.sub(r"\D+", "", phone or "")
    if len(digits) >= 8:
        return f"{digits[:4]}...{digits[-4:]}"
    return "<masked>"


def _generate_review_id() -> str:
    """Gera ID único e não-sequencial para o review."""
    return secrets.token_urlsafe(16)


def _hash_phone_for_review(phone: str) -> str:
    """Hash parcial de telefone para identificar lead sem expor número."""
    return hashlib.sha256(phone.encode()).hexdigest()[:16]


# ── ReviewItem ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReviewItem:
    """Item de revisão humana.

    Criado pelo worker quando o runtime está em modo ASSISTED.
    Contém a resposta sugerida pelo bot e metadados para o humano decidir.
    """

    # Identificação
    review_id: str                    # ID único (token_urlsafe)
    conversation_id: str              # ID da conversa (md5 phone:msg_id)
    lead_id: str                      # Hash SHA256 parcial do telefone
    phone_hash: str                   # Hash parcial do telefone (exibição segura)

    # Conteúdo
    intent: str                       # Intent classificado
    risk: str                         # Classificação de risco
    priority: ReviewPriority           # Prioridade calculada
    user_message: str                 # Mensagem original do cliente
    user_message_preview: str          # Primeros 80 chars da mensagem
    suggested_response: str           # Resposta sugerida pelo bot
    proposed_channel: ProposedChannel # Canal proposto (text/audio/pdf)
    response_modality: str            # "text" | "audio" | "document"

    # State
    status: ReviewStatus
    created_at: datetime
    expires_at: Optional[datetime]    # None = sem expiração
    updated_at: Optional[datetime]    # Última modificação

    # Histórico de edição (só preenchido após ação humana)
    approved_response: Optional[str] = None   # Resposta que foi enviada
    edited_by: Optional[str] = None           # Quem editou (futuro: usuário)
    edit_reason: Optional[str] = None         # Motivo da rejeição/edição

    # Metadata
    phone_number_masked: str = field(default="")  # Telefone mascarado para exibição

    # Audio metadata
    audio_bytes: Optional[bytes] = None          # Bytes do áudio (se modality=audio)
    tts_policy_passed: bool = False             # Passou na policy de áudio?

    def __post_init__(self) -> None:
        """Validações pós-criação e defaults."""
        if not self.phone_number_masked:
            object.__setattr__(self, "phone_number_masked", _mask_phone(self.lead_id))

    def is_expired(self) -> bool:
        """Verifica se o item expirou."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at.replace(tzinfo=timezone.utc)

    def time_pending(self) -> timedelta:
        """Tempo desde a criação até agora (ou até updated_at se finalizado)."""
        end = self.updated_at or datetime.now(timezinfo=timezone.utc)  # type: ignore
        return end - self.created_at

    def to_display_dict(self) -> dict:
        """Versão segura para API — sem dados sensíveis crus."""
        return {
            "review_id": self.review_id,
            "conversation_id": self.conversation_id[:12],
            "phone_masked": self.phone_number_masked,
            "intent": self.intent,
            "risk": self.risk,
            "priority": self.priority.value,
            "user_message_preview": self.user_message_preview,
            "suggested_response_preview": self.suggested_response[:120],
            "proposed_channel": self.proposed_channel.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired(),
            "approved_response_preview": (self.approved_response or "")[:120],
            "edit_reason": self.edit_reason,
        }

    @classmethod
    def from_worker_response(
        cls,
        phone: str,
        conversation_id: str,
        user_message: str,
        ai_response: str,
        intent: str,
        risk: str,
        msg_id: str,
        response_modality: str = "text",
        audio_bytes: Optional[bytes] = None,
    ) -> "ReviewItem":
        """Factory: cria ReviewItem a partir da resposta do worker.

        Chamado pelo worker.py quando is_assisted_mode() == True.
        """
        priority = _classify_priority(intent, user_message)
        phone_hash = _hash_phone_for_review(phone)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=24)  # default 24h

        # Determinar canal proposto
        if response_modality == "audio":
            channel = ProposedChannel.AUDIO
        elif response_modality == "document":
            channel = ProposedChannel.PDF
        else:
            channel = ProposedChannel.TEXT

        return cls(
            review_id=_generate_review_id(),
            conversation_id=conversation_id,
            lead_id=phone_hash,
            phone_hash=phone_hash,
            intent=intent,
            risk=risk,
            priority=priority,
            user_message=user_message,
            user_message_preview=user_message[:80],
            suggested_response=ai_response,
            proposed_channel=channel,
            response_modality=response_modality,
            status=ReviewStatus.PENDING,
            created_at=now,
            expires_at=expires,
            updated_at=None,
            approved_response=None,
            edited_by=None,
            edit_reason=None,
            phone_number_masked=_mask_phone(phone),
            audio_bytes=audio_bytes,
            tts_policy_passed=False,
        )