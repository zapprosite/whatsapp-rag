from __future__ import annotations

try:
    import worker as worker_module
except ModuleNotFoundError:
    from app import worker as worker_module

lifespan = worker_module.lifespan
get_redis = worker_module.get_redis
send_whatsapp_message = worker_module.send_whatsapp_message
normalize_whatsapp_number = worker_module.normalize_whatsapp_number
manual_takeover_key = worker_module.manual_takeover_key
is_manual_takeover = worker_module.is_manual_takeover
set_manual_takeover = worker_module.set_manual_takeover


def queue_key() -> str:
    return getattr(worker_module, "_QUEUE_KEY", "whatsapp_rag:queue")
