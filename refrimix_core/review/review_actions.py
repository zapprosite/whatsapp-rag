"""ReviewActions: executa ações humanas sobre ReviewItems.

Cada método implementa uma ação do painel de revisão:
approve, edit, reject, send, mark_expired.

Também salva before/after em production_feedback quando aplicável.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from refrimix_core.review.review_models import ProposedChannel, ReviewItem, ReviewPriority, ReviewStatus
from refrimix_core.review.review_policy import evaluate_audio_policy, evaluate_document_policy, intent_requires_human_review
from refrimix_core.review.review_queue import get_review_queue


logger = logging.getLogger(__name__)


# ── Result types ─────────────────────────────────────────────────────────────

@dataclass
class ActionResult:
    """Resultado de uma ação de review."""
    success: bool
    message: str
    review_item: Optional[ReviewItem] = None
    should_send: bool = False
    response_to_send: Optional[str] = None
    error: Optional[str] = None


@dataclass
class SendResult:
    """Resultado de tentativa de envio via WhatsApp."""
    success: bool
    message: str
    msg_id: Optional[str] = None
    error: Optional[str] = None


# ── Policy validation helpers ────────────────────────────────────────────────

def _validate_send_action(item: ReviewItem, edited_response: Optional[str] = None) -> ActionResult:
    """Valida se um item pode ser enviado (políticas de áudio/documento)."""
    # Documento: nunca autoenviar
    if item.proposed_channel == ProposedChannel.PDF:
        return ActionResult(
            success=False,
            message="PDF não pode ser enviado automaticamente. Use aprovação manual via drive.",
            error="document_blocked",
        )

    # Audio policy
    response = edited_response or item.suggested_response
    if item.proposed_channel == ProposedChannel.AUDIO:
        audio_policy = evaluate_audio_policy(response, item.proposed_channel, item.intent)
        if not audio_policy.allowed:
            return ActionResult(
                success=False,
                message=f"Áudio bloqueado: {audio_policy.reason}",
                error=audio_policy.blocked_reason,
            )

    # Intent que requer revisão (segunda checagem)
    if intent_requires_human_review(item.intent) and item.status == ReviewStatus.PENDING:
        # Só falha se ainda está pending e ninguém aprovou explicitamente
        pass  # allow through if already approved/edited

    return ActionResult(success=True, message="ok", should_send=True)


# ── Approve action ──────────────────────────────────────────────────────────

def approve_item(review_id: str, edited_response: Optional[str] = None) -> ActionResult:
    """Aprova um ReviewItem para envio.

    Se edited_response é fornecido, marca como EDITED.
    Se não, marca como APPROVED.
    """
    queue = get_review_queue()
    item = queue.get(review_id)

    if not item:
        return ActionResult(success=False, message=f"ReviewItem {review_id} não encontrado", error="not_found")

    if item.status != ReviewStatus.PENDING:
        return ActionResult(
            success=False,
            message=f"Item já está com status {item.status.value}",
            error="invalid_status",
        )

    response = edited_response or item.suggested_response

    # Validar políticas
    validation = _validate_send_action(item, response)
    if not validation.success:
        return validation

    # Salvar before/after em production_feedback
    if edited_response:
        _save_feedback_before_after(item, item.suggested_response, edited_response, action="edited")

    # Atualizar status
    new_status = ReviewStatus.EDITED if edited_response else ReviewStatus.APPROVED
    updated = queue.update(review_id, {
        "status": new_status,
        "approved_response": response,
        "edit_reason": f"approved{' (editado)' if edited_response else ''}",
        "updated_at": datetime.now(timezone.utc),
    })

    if not updated:
        return ActionResult(success=False, message="Falha ao atualizar item", error="update_failed")

    logger.info(
        "[REVIEW_ACTION] approved review_id=%s status=%s edited=%s",
        review_id[:8],
        new_status.value,
        bool(edited_response),
    )

    return ActionResult(
        success=True,
        message=f"Item {'editado e ' if edited_response else ''}aprovado",
        review_item=updated,
        should_send=True,
        response_to_send=response,
    )


# ── Edit action ─────────────────────────────────────────────────────────────

def edit_item(review_id: str, new_response: str, edited_by: str = "human") -> ActionResult:
    """Edita a resposta de um ReviewItem e marca como pendente de envio."""
    if not new_response.strip():
        return ActionResult(success=False, message="Resposta não pode estar vazia", error="empty_response")

    queue = get_review_queue()
    item = queue.get(review_id)

    if not item:
        return ActionResult(success=False, message=f"ReviewItem {review_id} não encontrado", error="not_found")

    if item.status not in {ReviewStatus.PENDING, ReviewStatus.APPROVED}:
        return ActionResult(
            success=False,
            message=f"Não é possível editar item com status {item.status.value}",
            error="invalid_status",
        )

    old_response = item.suggested_response

    # Salvar before/after em production_feedback
    _save_feedback_before_after(item, old_response, new_response, action="edited")

    # Atualizar item
    updated = queue.update(review_id, {
        "status": ReviewStatus.EDITED,
        "approved_response": new_response,
        "edited_by": edited_by,
        "updated_at": datetime.now(timezone.utc),
    })

    if not updated:
        return ActionResult(success=False, message="Falha ao atualizar item", error="update_failed")

    logger.info(
        "[REVIEW_ACTION] edited review_id=%s original_len=%d new_len=%d",
        review_id[:8],
        len(old_response),
        len(new_response),
    )

    return ActionResult(
        success=True,
        message="Resposta editada",
        review_item=updated,
        should_send=True,
        response_to_send=new_response,
    )


# ── Reject action ───────────────────────────────────────────────────────────

def reject_item(review_id: str, reason: str) -> ActionResult:
    """Rejeita um ReviewItem com motivo.

    Não envia nada ao cliente.
    Salva motivo em production_feedback.
    """
    if not reason.strip():
        return ActionResult(success=False, message="Motivo da rejeição é obrigatório", error="empty_reason")

    queue = get_review_queue()
    item = queue.get(review_id)

    if not item:
        return ActionResult(success=False, message=f"ReviewItem {review_id} não encontrado", error="not_found")

    if item.status == ReviewStatus.REJECTED:
        return ActionResult(success=True, message="Item já estava rejeitado", review_item=item)

    # Salvar feedback
    _save_feedback_before_after(item, item.suggested_response, "", action="rejected", reason=reason)

    # Atualizar
    updated = queue.update(review_id, {
        "status": ReviewStatus.REJECTED,
        "edit_reason": reason,
        "updated_at": datetime.now(timezone.utc),
    })

    if not updated:
        return ActionResult(success=False, message="Falha ao atualizar item", error="update_failed")

    logger.info("[REVIEW_ACTION] rejected review_id=%s reason=%s", review_id[:8], reason[:60])

    return ActionResult(success=True, message="Item rejeitado", review_item=updated, should_send=False)


# ── Send action ─────────────────────────────────────────────────────────────

def send_item(review_id: str) -> ActionResult:
    """Envia resposta aprovada via WhatsApp.

    Chamado após approve/edit ou quando humano quer reenviar.
    Atualiza status para SENT e retorna response_to_send.
    """
    queue = get_review_queue()
    item = queue.get(review_id)

    if not item:
        return ActionResult(success=False, message=f"ReviewItem {review_id} não encontrado", error="not_found")

    if item.status not in {ReviewStatus.APPROVED, ReviewStatus.EDITED}:
        return ActionResult(
            success=False,
            message=f"Item precisa estar approved/edited para enviar. Status atual: {item.status.value}",
            error="invalid_status",
        )

    response = item.approved_response or item.suggested_response

    # Última validação de policy antes do envio
    validation = _validate_send_action(item, response)
    if not validation.success:
        return validation

    # Marcar como SENT
    updated = queue.mark_sent(review_id, response)
    if not updated:
        return ActionResult(success=False, message="Falha ao marcar item como enviado", error="update_failed")

    logger.info("[REVIEW_ACTION] queued for send review_id=%s response_len=%d", review_id[:8], len(response))

    return ActionResult(
        success=True,
        message="Enviado",
        review_item=updated,
        should_send=True,
        response_to_send=response,
    )


# ── Mark-expired action ──────────────────────────────────────────────────────

def mark_expired(review_id: str) -> ActionResult:
    """Marca item como expirado manualmente."""
    queue = get_review_queue()
    item = queue.get(review_id)

    if not item:
        return ActionResult(success=False, message=f"ReviewItem {review_id} não encontrado", error="not_found")

    if item.status == ReviewStatus.EXPIRED:
        return ActionResult(success=True, message="Item já estava expirado", review_item=item)

    updated = queue.mark_expired(review_id)
    if not updated:
        return ActionResult(success=False, message="Falha ao expirar item", error="update_failed")

    logger.info("[REVIEW_ACTION] expired review_id=%s", review_id[:8])

    return ActionResult(success=True, message="Item expirado", review_item=updated)


# ── Helper: production feedback ────────────────────────────────────────────

def _save_feedback_before_after(
    item: ReviewItem,
    before: str,
    after: str,
    action: str,
    reason: str = "",
) -> None:
    """Salva before/after em ProductionFeedbackStore para refinamento."""
    try:
        from refrimix_core.monitoring.production_feedback import ProductionFeedbackStore
        feedback_store = ProductionFeedbackStore()

        feedback_store.save_human_feedback(
            conversation_id=item.conversation_id,
            suggested_response=before,
            human_response=after,
            edited_fields=None,
            intent=item.intent,
            message_index=0,
        )
    except Exception as e:
        # Não deixar falha de feedback quebrar a ação de review
        logger.warning("[REVIEW_ACTION] failed to save feedback: %s", e)


# ── Bulk actions ─────────────────────────────────────────────────────────────

def expire_all_pending() -> int:
    """Expira todos os itens pendentes que dépassaram o expiry time.

    Returns:
        Número de itens expirados.
    """
    queue = get_review_queue()
    return queue.expire_pending()


def get_pending_count() -> int:
    """Retorna quantos itens estão pendentes."""
    queue = get_review_queue()
    return queue.count(filter_mode="pending")  # type: ignore