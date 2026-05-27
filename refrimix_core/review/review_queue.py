"""ReviewQueue: store in-memory para ReviewItems no modo ASSISTED.

Em produção, isso seria substituido por Postgres com Redis cache.
Por agora: thread-safe in-memory dict com singleton access.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from refrimix_core.review.review_models import ReviewItem, ReviewPriority, ReviewStatus


logger = logging.getLogger(__name__)


class ReviewQueueFilter(str, Enum):
    """Filtros disponíveis para listar review items."""
    ALL = "all"
    PENDING = "pending"
    URGENT = "urgent"
    RISCO_ELETRICO = "risco_eletrico"
    PROJETOS_ALTO_VALOR = "projetos"
    PDF_DOCUMENTOS = "pdf_documentos"
    EDITED = "edited"
    REJECTED = "rejected"
    SENT = "sent"


class ReviewQueue:
    """Store em memória para ReviewItems.

    Singleton thread-safe. Substituir por Postgres em produção.
    """

    def __init__(self) -> None:
        self._items: dict[str, ReviewItem] = {}
        self._lock = threading.RLock()

    # ── Create ──────────────────────────────────────────────────────────────

    def create(self, item: ReviewItem) -> None:
        """Adiciona novo ReviewItem à fila."""
        with self._lock:
            if item.review_id in self._items:
                logger.warning("ReviewItem %s já existe, substituindo", item.review_id)
            self._items[item.review_id] = item
            logger.info(
                "[REVIEW_QUEUE] created review_id=%s intent=%s priority=%s status=%s",
                item.review_id[:8],
                item.intent,
                item.priority.value,
                item.status.value,
            )

    # ── Read ───────────────────────────────────────────────────────────────

    def get(self, review_id: str) -> Optional[ReviewItem]:
        """Retorna ReviewItem por ID ou None."""
        with self._lock:
            return self._items.get(review_id)

    def list_items(
        self,
        filter_mode: ReviewQueueFilter = ReviewQueueFilter.ALL,
        conversation_id: Optional[str] = None,
        phone_hash: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ReviewItem]:
        """Lista ReviewItems com filtros.

        Args:
            filter_mode: filtro por categoria (pending, urgent, etc.)
            conversation_id: filtrar por conversa
            phone_hash: filtrar por lead
            limit: max items (default 50)
            offset: offset para paginação
        """
        with self._lock:
            items = list(self._items.values())

        # Filtro primário
        if filter_mode == ReviewQueueFilter.PENDING:
            items = [i for i in items if i.status == ReviewStatus.PENDING]
        elif filter_mode == ReviewQueueFilter.URGENT:
            items = [i for i in items if i.priority == ReviewPriority.URGENT]
        elif filter_mode == ReviewQueueFilter.RISCO_ELETRICO:
            items = [i for i in items if "risco" in i.intent.lower() or "eletrico" in i.intent.lower()]
        elif filter_mode == ReviewQueueFilter.PROJETOS_ALTO_VALOR:
            high_priority = {ReviewPriority.HIGH, ReviewPriority.URGENT}
            items = [i for i in items if i.priority in high_priority]
        elif filter_mode == ReviewQueueFilter.PDF_DOCUMENTOS:
            from refrimix_core.review.review_models import ProposedChannel
            items = [i for i in items if i.proposed_channel == ProposedChannel.PDF]
        elif filter_mode == ReviewQueueFilter.EDITED:
            items = [i for i in items if i.status == ReviewStatus.EDITED]
        elif filter_mode == ReviewQueueFilter.REJECTED:
            items = [i for i in items if i.status == ReviewStatus.REJECTED]
        elif filter_mode == ReviewQueueFilter.SENT:
            items = [i for i in items if i.status == ReviewStatus.SENT]
        # ALL: sem filtro adicional

        # Filtros secundários
        if conversation_id:
            items = [i for i in items if i.conversation_id == conversation_id]
        if phone_hash:
            items = [i for i in items if i.phone_hash == phone_hash]

        # Ordenar: URGENT primeiro, depois por created_at desc
        priority_order = {ReviewPriority.URGENT: 0, ReviewPriority.HIGH: 1, ReviewPriority.NORMAL: 2, ReviewPriority.LOW: 3}
        items.sort(key=lambda i: (priority_order.get(i.priority, 99), i.created_at), reverse=True)

        # Paginar
        return items[offset:offset + limit]

    def count(self, filter_mode: ReviewQueueFilter = ReviewQueueFilter.ALL) -> int:
        """Conta items no filtro."""
        # Reusa list_items sem paginação
        return len(self.list_items(filter_mode=filter_mode, limit=10000))

    def list_by_conversation(self, conversation_id: str) -> list[ReviewItem]:
        """Lista todos os ReviewItems de uma conversa."""
        with self._lock:
            return [i for i in self._items.values() if i.conversation_id == conversation_id]

    # ── Update ─────────────────────────────────────────────────────────────

    def update(self, review_id: str, updates: dict) -> Optional[ReviewItem]:
        """Atualiza campos de um ReviewItem.

        Args:
            review_id: ID do item
            updates: dict com campos a atualizar. Campos permitidos:
                - status: ReviewStatus
                - approved_response: str
                - edited_by: str
                - edit_reason: str
                - expires_at: datetime

        Returns:
            ReviewItem atualizado ou None se não encontrado.
        """
        with self._lock:
            item = self._items.get(review_id)
            if not item:
                return None

            # Aplicar updates (via dataclass replace)
            new_fields = {**item.__dict__, **updates, "updated_at": datetime.now(timezone.utc)}
            updated = ReviewItem(**new_fields)
            self._items[review_id] = updated

            logger.info(
                "[REVIEW_QUEUE] updated review_id=%s status=%s edited_by=%s",
                review_id[:8],
                updated.status.value,
                updated.edited_by,
            )
            return updated

    def update_status(self, review_id: str, status: ReviewStatus) -> Optional[ReviewItem]:
        """Shortcut para atualizar só o status."""
        return self.update(review_id, {"status": status})

    def mark_sent(self, review_id: str, final_response: str) -> Optional[ReviewItem]:
        """Marca item como SENT com a resposta final enviada."""
        return self.update(review_id, {
            "status": ReviewStatus.SENT,
            "approved_response": final_response,
            "updated_at": datetime.now(timezone.utc),
        })

    def mark_expired(self, review_id: str) -> Optional[ReviewItem]:
        """Marca item como EXPIRED se ainda está PENDING."""
        with self._lock:
            item = self._items.get(review_id)
            if not item:
                return None
            if item.status != ReviewStatus.PENDING:
                return item  # não fazer nada se já foi ação
            return self.update(review_id, {"status": ReviewStatus.EXPIRED})

    # ── Delete ───────────────────────────────────────────────────────────────

    def delete(self, review_id: str) -> bool:
        """Remove ReviewItem da fila."""
        with self._lock:
            if review_id in self._items:
                del self._items[review_id]
                return True
            return False

    def expire_pending(self) -> int:
        """Marca todos os PENDING expirados como EXPIRED.

        Returns:
            Número de itens expirados.
        """
        expired_count = 0
        with self._lock:
            now = datetime.now(timezone.utc)
            for review_id, item in list(self._items.items()):
                if item.status == ReviewStatus.PENDING and item.expires_at:
                    if now > item.expires_at.replace(tzinfo=timezone.utc):
                        self._items[review_id] = ReviewItem(
                            **{**item.__dict__, "status": ReviewStatus.EXPIRED, "updated_at": now}
                        )
                        expired_count += 1
        if expired_count:
            logger.info("[REVIEW_QUEUE] expired %d items", expired_count)
        return expired_count

    # ── Stats ────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        """Retorna estatísticas da fila."""
        with self._lock:
            items = list(self._items.values())
        total = len(items)
        by_status = {s.value: 0 for s in ReviewStatus}
        by_priority = {p.value: 0 for p in ReviewPriority}
        for i in items:
            by_status[i.status.value] = by_status.get(i.status.value, 0) + 1
            by_priority[i.priority.value] = by_priority.get(i.priority.value, 0) + 1
        return {
            "total": total,
            "by_status": by_status,
            "by_priority": by_priority,
            "pending": by_status.get("pending", 0),
            "urgent": by_priority.get("urgent", 0),
        }


# ── Singleton ────────────────────────────────────────────────────────────────

_review_queue_instance: Optional[ReviewQueue] = None
_review_queue_lock = threading.Lock()


def get_review_queue() -> ReviewQueue:
    """Retorna instância singleton da ReviewQueue."""
    global _review_queue_instance
    if _review_queue_instance is None:
        with _review_queue_lock:
            if _review_queue_instance is None:
                _review_queue_instance = ReviewQueue()
    return _review_queue_instance


def reset_review_queue() -> None:
    """Reset para testes — limpa todos os items."""
    global _review_queue_instance
    with _review_queue_lock:
        if _review_queue_instance is not None:
            _review_queue_instance._items.clear()
        _review_queue_instance = None