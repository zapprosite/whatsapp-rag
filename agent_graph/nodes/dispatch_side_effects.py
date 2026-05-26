from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from typing import Any

from agent_graph.nodes.nodes import _latest_human_text, redis_get, redis_set
from agent_graph.services.alerts import send_agenda_group_message, send_owner_alert
from agent_graph.services.calendar import create_service_event
from agent_graph.services.tts import choose_voice_style, synthesize


def _dedup_key(effect_type: str, phone: str, payload: dict[str, Any]) -> str:
    payload_hash = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]
    return f"side_effect:{effect_type}:{phone}:{payload_hash}"


async def dispatch_side_effects(state: dict[str, Any]) -> dict[str, Any]:
    next_action = state.get("next_action") or {}
    side_effects = list(next_action.get("side_effects") or [])
    customer_data = state.get("customer_data") or {}
    phone = str(customer_data.get("phone") or "unknown")
    if bool(customer_data.get("diagnostic_mode")) and not bool(customer_data.get("send_requested")):
        return {}

    lead_state = deepcopy(state.get("lead_state") or {})
    appointment = lead_state.setdefault("appointment", {})
    executed: list[str] = []

    for effect in side_effects:
        effect_type = effect.get("type")
        payload = effect.get("payload") or {}
        key = _dedup_key(effect_type or "unknown", phone, payload)
        if await redis_get(key):
            continue

        if effect_type == "send_owner_alert":
            await send_owner_alert(
                {
                    "title": "ALERTA OPERACIONAL",
                    "phone": phone,
                    "name": customer_data.get("name"),
                    "reason": payload.get("reason") or next_action.get("type"),
                    "service": (lead_state.get("tipo_servico") or state.get("service")),
                    "city_bairro": lead_state.get("cidade_bairro"),
                    "last_message": _latest_human_text(state.get("messages") or []),
                }
            )
        elif effect_type == "send_agenda_group_alert":
            if next_action.get("type") in {"confirm_calendar_slot", "handoff_human"} or payload.get("reason") == "pending_manual_confirmation":
                await send_agenda_group_message(payload.get("text") or "Agenda Refrimix: confirmar atendimento manualmente.")
        elif effect_type == "google_calendar_insert":
            if os.getenv("GOOGLE_CALENDAR_CREATE_EVENTS", "0") == "1":
                result = await create_service_event(lead_state, next_action.get("selected_slot"))
                appointment["event_status"] = "created" if result else "failed"
                if result:
                    appointment["calendar_event"] = result
        elif effect_type == "tts_synthesize":
            if state.get("response_modality") == "audio" and not state.get("audio_bytes"):
                text = state.get("tts_text") or ""
                if text:
                    audio_bytes = await synthesize(text, choose_voice_style(state.get("conversation_objective"), state.get("outcome")))
                    if audio_bytes:
                        state["audio_bytes"] = audio_bytes

        await redis_set(key, "1", ex=6 * 60 * 60)
        executed.append(effect_type or "unknown")

    return {"lead_state": lead_state, "executed_side_effects": executed, "audio_bytes": state.get("audio_bytes")}
