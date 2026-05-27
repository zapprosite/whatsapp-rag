"""Review API: FastAPI routes para a inbox de aprovação humana.

GET  /review/inbox          — lista items com filtros
GET  /review/items/{id}     — detalhes de um item
POST /review/items/{id}/approve   — aprova sem editar
POST /review/items/{id}/edit      — edita e marca pending
POST /review/items/{id}/reject    — rejeita com motivo
POST /review/items/{id}/send      — envia resposta aprovada
POST /review/items/{id}/mark-expired — marca como expirado
GET  /review/stats          — estatísticas da fila
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from refrimix_core.review.review_actions import (
    ActionResult,
    approve_item,
    edit_item,
    expire_all_pending,
    get_pending_count,
    mark_expired,
    reject_item,
    send_item,
)
from refrimix_core.review.review_models import ReviewItem, ReviewStatus
from refrimix_core.review.review_queue import ReviewQueueFilter
from refrimix_core.review.review_policy import get_priority_label, get_status_label


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["review"])

# Auth: simples token via env (futuro: OAuth/user auth)
_REVIEW_API_TOKEN = os.getenv("REVIEW_API_TOKEN", "")


def _check_auth(request: Request) -> None:
    """Valida token de autenticação."""
    if not _REVIEW_API_TOKEN:
        return  # Sem token configurado = sem auth
    auth_header = request.headers.get("authorization", "")
    if auth_header != f"Bearer {_REVIEW_API_TOKEN}":
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _mask_id(review_id: str) -> str:
    """Máscara para logging."""
    return review_id[:8]


# ── Routes ──────────────────────────────────────────────────────────────────

@router.get("/inbox")
async def list_inbox(
    filter_mode: str = "all",
    conversation_id: Optional[str] = None,
    phone_hash: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    """Lista ReviewItems com filtros.

    Filtros disponíveis: all, pending, urgent, risco_eletrico, projetos,
        pdf_documentos, edited, rejected, sent
    """
    from refrimix_core.review.review_queue import get_review_queue

    try:
        filter_enum = ReviewQueueFilter(filter_mode.lower())
    except ValueError:
        filter_enum = ReviewQueueFilter.ALL

    queue = get_review_queue()
    items = queue.list_items(
        filter_mode=filter_enum,
        conversation_id=conversation_id,
        phone_hash=phone_hash,
        limit=limit,
        offset=offset,
    )

    return JSONResponse({
        "items": [item.to_display_dict() for item in items],
        "count": len(items),
        "filter": filter_mode,
        "pending_total": get_pending_count(),
    })


@router.get("/stats")
async def get_stats() -> JSONResponse:
    """Retorna estatísticas da fila de review."""
    from refrimix_core.review.review_queue import get_review_queue

    queue = get_review_queue()
    stats = queue.stats()

    # Adicionar labels
    stats["pending_label"] = "⏳ Pendente"
    stats["urgent_items"] = queue.count(ReviewQueueFilter.URGENT)
    stats["risco_eletrico_items"] = queue.count(ReviewQueueFilter.RISCO_ELETRICO)

    return JSONResponse(stats)


@router.get("/items/{review_id}")
async def get_item(review_id: str) -> JSONResponse:
    """Retorna detalhes de um ReviewItem."""
    from refrimix_core.review.review_queue import get_review_queue

    queue = get_review_queue()
    item = queue.get(review_id)

    if not item:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    result = item.to_display_dict()
    result["priority_label"] = get_priority_label(item.priority).split()[0]  # strip emoji
    result["status_label"] = get_status_label(item.status).split()[0]

    return JSONResponse(result)


@router.post("/items/{review_id}/approve")
async def approve_review_item(review_id: str, request: Request) -> JSONResponse:
    """Aprova ReviewItem para envio (resposta original do bot)."""
    _check_auth(request)

    # Optional edited_response body
    try:
        body = await request.json()
    except Exception:
        body = {}

    edited_response = body.get("edited_response")

    result = approve_item(review_id, edited_response=edited_response)

    if not result.success:
        return JSONResponse({"error": result.error, "message": result.message}, status_code=400)

    return JSONResponse({
        "success": True,
        "message": result.message,
        "review_item": result.review_item.to_display_dict() if result.review_item else None,
        "should_send": result.should_send,
    })


@router.post("/items/{review_id}/edit")
async def edit_review_item(review_id: str, request: Request) -> JSONResponse:
    """Edita resposta de ReviewItem e marca como edited."""
    _check_auth(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    new_response = body.get("new_response", "").strip()
    edited_by = body.get("edited_by", "human")

    result = edit_item(review_id, new_response, edited_by=edited_by)

    if not result.success:
        return JSONResponse({"error": result.error, "message": result.message}, status_code=400)

    return JSONResponse({
        "success": True,
        "message": result.message,
        "review_item": result.review_item.to_display_dict() if result.review_item else None,
        "should_send": result.should_send,
    })


@router.post("/items/{review_id}/reject")
async def reject_review_item(review_id: str, request: Request) -> JSONResponse:
    """Rejeita ReviewItem com motivo (não envia WhatsApp)."""
    _check_auth(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    reason = body.get("reason", "").strip()
    if not reason:
        return JSONResponse({"error": "empty_reason", "message": "Motivo obrigatório"}, status_code=400)

    result = reject_item(review_id, reason)

    if not result.success:
        return JSONResponse({"error": result.error, "message": result.message}, status_code=400)

    return JSONResponse({
        "success": True,
        "message": result.message,
        "review_item": result.review_item.to_display_dict() if result.review_item else None,
    })


@router.post("/items/{review_id}/send")
async def send_review_item(review_id: str, request: Request) -> JSONResponse:
    """Envia resposta aprovada via WhatsApp (via worker queue)."""
    _check_auth(request)

    result = send_item(review_id)

    if not result.success:
        return JSONResponse({"error": result.error, "message": result.message}, status_code=400)

    # Colocar envio na fila Redis para o worker processar
    if result.should_send and result.response_to_send:
        try:
            from runtime import get_redis, queue_key
            import json
            r = await get_redis()
            # O item tem phone_hash — mas precisamos do telefone real para enviar
            # O worker tem os mappings (msg_conv, msg_phone) para resolver
            # Por agora: enfileirar para o worker enviar com review_id como reference
            payload = {
                "action": "review_send",
                "review_id": review_id,
                "response": result.response_to_send,
            }
            await r.lpush(queue_key(), json.dumps(payload, ensure_ascii=False))
            logger.info("[REVIEW_API] queued send for review_id=%s", _mask_id(review_id))
        except Exception as e:
            logger.warning("[REVIEW_API] failed to queue send: %s", e)
            return JSONResponse({"error": "queue_failed", "message": f"Falha ao enfileirar: {e}"}, status_code=500)

    return JSONResponse({
        "success": True,
        "message": "Enviado",
        "review_item": result.review_item.to_display_dict() if result.review_item else None,
    })


@router.post("/items/{review_id}/mark-expired")
async def mark_item_expired(review_id: str, request: Request) -> JSONResponse:
    """Marca item como expirado manualmente."""
    _check_auth(request)

    result = mark_expired(review_id)

    if not result.success:
        return JSONResponse({"error": result.error, "message": result.message}, status_code=400)

    return JSONResponse({
        "success": True,
        "message": result.message,
        "review_item": result.review_item.to_display_dict() if result.review_item else None,
    })


@router.post("/expire-all")
async def expire_all_pending_items(request: Request) -> JSONResponse:
    """Expira todos os itens pendentes que ultrapassaram o expiry time."""
    _check_auth(request)

    count = expire_all_pending()

    return JSONResponse({
        "success": True,
        "expired_count": count,
        "message": f"{count} itens expirados",
    })