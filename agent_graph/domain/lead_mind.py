from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from agent_graph.services.playbook_loader import get_high_value_signals, get_service_questions, load_playbook


SEGMENT_UNKNOWN = {
    "id": "unknown",
    "market": "unknown",
    "tier": "unknown",
    "confidence": 0.0,
    "signals": [],
    "do_not_say_to_customer": True,
}


def _fold_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _contains_signal(text: str, signal: str) -> bool:
    folded_signal = _fold_text(signal)
    if len(folded_signal.split()) > 1:
        return folded_signal in text
    return re.search(rf"\b{re.escape(folded_signal)}\b", text) is not None


def default_lead_mind(phone: str | None = None) -> dict[str, Any]:
    return {
        "version": 1,
        "lead_profile": {
            "phone": phone,
            "name": None,
            "relationship_type": "new_lead",
            "conversation_goal": "recover_context",
            "pipeline_stage": "new",
            "customer_type": "new_lead",
        },
        "intent": {
            "primary_service": None,
            "service_confidence": 0.0,
            "explicit_correction_detected": False,
            "last_user_intent": None,
        },
        "segment": deepcopy(SEGMENT_UNKNOWN),
        "commercial_context": {
            "price_sensitivity": "unknown",
            "urgency": "unknown",
            "decision_stage": "unknown",
            "objection": None,
            "next_best_action": "ask_service_and_city",
        },
        "technical_context": {
            "equipment_type": None,
            "btus": None,
            "brand": None,
            "city_bairro": None,
            "installation": {
                "indoor_photo": False,
                "outdoor_photo": False,
                "dedicated_electrical_point": None,
                "drain_path": None,
                "access_difficulty": "unknown",
            },
        },
        "memory": {
            "conversation_summary": "",
            "facts": [],
            "do_not_ask": [],
            "missing_fields": [],
            "last_asked_field": None,
            "ask_count_by_field": {},
        },
        "risk": {
            "malicious_prompt_attempt": False,
            "electrical_risk": False,
            "complaint_risk": False,
            "needs_human": False,
            "handoff_reason": None,
        },
        "tts": {
            "preferred_mode": "text",
            "voice_style": "calm_consultative",
            "speech_summary": "",
        },
        "compaction": {
            "version": 1,
            "last_compacted_at": None,
            "raw_chars_estimate": 0,
        },
    }


def merge_lead_mind(existing: dict[str, Any] | None, patch: dict[str, Any] | None) -> dict[str, Any]:
    base = deepcopy(existing or default_lead_mind())
    if not patch:
        return base
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            nested = deepcopy(base[key])
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, dict) and isinstance(nested.get(nested_key), dict):
                    nested[nested_key] = merge_lead_mind(nested[nested_key], nested_value)
                elif nested_value is not None:
                    nested[nested_key] = deepcopy(nested_value)
            base[key] = nested
        elif value is not None:
            base[key] = deepcopy(value)
    return base


def classify_segment(lead_mind: dict[str, Any], user_text: str) -> dict[str, Any]:
    """Classifica segmento interno sem produzir copy para cliente."""
    folded = _fold_text(user_text)
    segment_rules = load_playbook("lead_segments").get("segments", {})
    best_id = "unknown"
    best_score = 0
    best_signals: list[str] = []
    best_rule: dict[str, Any] = {}

    for segment_id, rule in segment_rules.items():
        signals = [str(item) for item in rule.get("signals") or []]
        hits = [signal for signal in signals if _contains_signal(folded, signal)]
        score = len(hits)
        if score > best_score:
            best_id = str(segment_id)
            best_score = score
            best_signals = hits
            best_rule = rule

    high_value = get_high_value_signals()
    hard_signals = high_value.get("hard_signals") or {}
    hard_hits = [signal for signal in hard_signals if _contains_signal(folded, str(signal))]
    context_hits = [signal for signal in high_value.get("context_signals") or [] if _contains_signal(folded, str(signal))]
    multiple_devices_min = int((high_value.get("numeric_rules") or {}).get("multiple_devices_min") or 3)
    numeric_high_value = bool(re.search(rf"\b(?:{multiple_devices_min}|[4-9]|[1-9]\d+)\s+(?:aparelhos|maquinas|máquinas|splits)\b", folded))

    if hard_hits or (context_hits and numeric_high_value):
        best_id = "commercial_high_value"
        best_signals = list(dict.fromkeys(hard_hits + context_hits + best_signals))
        best_rule = segment_rules.get(best_id, best_rule)
        best_score = max(best_score, len(best_signals) + 2)

    if best_id == "unknown":
        segment = deepcopy(SEGMENT_UNKNOWN)
    else:
        confidence = min(0.95, 0.45 + (best_score * 0.12))
        segment = {
            "id": best_id,
            "market": best_rule.get("market", "unknown"),
            "tier": best_rule.get("tier", "unknown"),
            "confidence": round(confidence, 2),
            "signals": best_signals[:10],
            "do_not_say_to_customer": True,
            "strategy": best_rule.get("strategy") or {},
        }

    lead_mind["segment"] = segment
    return segment


def compute_next_best_action(lead_mind: dict[str, Any]) -> str:
    service = lead_mind.get("intent", {}).get("primary_service")
    segment = lead_mind.get("segment", {}).get("id")
    missing = list(lead_mind.get("memory", {}).get("missing_fields") or [])
    questions = get_service_questions(service, segment)
    for field in questions:
        if field in missing:
            return f"ask_{field}"
    if service:
        return "offer_schedule_or_owner_review"
    return "ask_service_and_city"


def _facts_from_lead_state(lead_state: dict[str, Any]) -> list[str]:
    facts: list[str] = []
    mapping = {
        "tipo_servico": "serviço",
        "cidade_bairro": "cidade",
        "btus": "btus",
        "marca": "marca",
        "modelo_aparelho": "modelo",
    }
    for key, label in mapping.items():
        value = lead_state.get(key)
        if value:
            facts.append(f"{label}={value}")
    return facts


def update_from_lead_state(
    lead_mind: dict[str, Any] | None,
    lead_state: dict[str, Any],
    user_text: str,
    *,
    phone: str | None = None,
    conversation_goal: str | None = None,
    conversation_summary: str | None = None,
    do_not_ask: list[str] | None = None,
    missing_fields: list[str] | None = None,
) -> dict[str, Any]:
    mind = merge_lead_mind(default_lead_mind(phone), lead_mind or {})
    profile = mind.setdefault("lead_profile", {})
    profile["phone"] = phone or profile.get("phone")
    profile["name"] = lead_state.get("nome") or profile.get("name")
    profile["relationship_type"] = lead_state.get("relationship_type") or profile.get("relationship_type")
    profile["conversation_goal"] = conversation_goal or profile.get("conversation_goal")
    profile["pipeline_stage"] = lead_state.get("pipeline_stage") or profile.get("pipeline_stage")

    intent = mind.setdefault("intent", {})
    intent["primary_service"] = lead_state.get("tipo_servico") or intent.get("primary_service")
    intent["service_confidence"] = 0.9 if lead_state.get("tipo_servico") else intent.get("service_confidence", 0.0)
    if "quanto" in _fold_text(user_text) or "preco" in _fold_text(user_text) or "preço" in user_text.lower():
        intent["last_user_intent"] = "price_question"

    technical = mind.setdefault("technical_context", {})
    technical["btus"] = lead_state.get("btus") or technical.get("btus")
    technical["brand"] = lead_state.get("marca") or technical.get("brand")
    technical["city_bairro"] = lead_state.get("cidade_bairro") or technical.get("city_bairro")
    technical["equipment_type"] = lead_state.get("modelo_aparelho") or technical.get("equipment_type")
    installation = technical.setdefault("installation", {})
    fotos = lead_state.get("fotos") or {}
    installation["indoor_photo"] = bool(fotos.get("local_interno"))
    installation["outdoor_photo"] = bool(fotos.get("local_externo"))
    inst = lead_state.get("instalacao") or {}
    installation["dedicated_electrical_point"] = inst.get("ponto_eletrico_exclusivo")
    installation["drain_path"] = inst.get("precisa_dreno")

    memory = mind.setdefault("memory", {})
    memory["conversation_summary"] = conversation_summary or memory.get("conversation_summary", "")
    memory["facts"] = list(dict.fromkeys((memory.get("facts") or []) + _facts_from_lead_state(lead_state)))
    memory["do_not_ask"] = list(dict.fromkeys(do_not_ask or memory.get("do_not_ask") or []))
    memory["missing_fields"] = list(dict.fromkeys(missing_fields or memory.get("missing_fields") or []))
    memory["last_asked_field"] = lead_state.get("last_asked_field") or memory.get("last_asked_field")
    memory["ask_count_by_field"] = lead_state.get("ask_count_by_field") or memory.get("ask_count_by_field") or {}

    folded = _fold_text(user_text)
    risk = mind.setdefault("risk", {})
    electrical_risk = any(term in folded for term in ("disjuntor cai", "fio esquenta", "cheiro de queimado", "tomada derret"))
    risk["electrical_risk"] = bool(risk.get("electrical_risk") or electrical_risk)

    classify_segment(mind, " ".join([user_text, " ".join(memory["facts"])]))
    next_action = compute_next_best_action(mind)
    mind.setdefault("commercial_context", {})["next_best_action"] = next_action
    mind.setdefault("tts", {})["speech_summary"] = _build_speech_summary(mind)
    mind.setdefault("compaction", {})["raw_chars_estimate"] = len(json.dumps(mind, ensure_ascii=False))
    return mind


def _build_speech_summary(lead_mind: dict[str, Any]) -> str:
    service = lead_mind.get("intent", {}).get("primary_service") or "atendimento"
    city = lead_mind.get("technical_context", {}).get("city_bairro")
    next_action = lead_mind.get("commercial_context", {}).get("next_best_action")
    parts = [f"Continuar {service}"]
    if city:
        parts.append(f"em {city}")
    if next_action:
        parts.append(f"com próximo passo {next_action}")
    return " ".join(parts) + "."


def compact_lead_mind_if_needed(lead_mind: dict[str, Any], max_chars: int = 8000) -> dict[str, Any]:
    raw = json.dumps(lead_mind, ensure_ascii=False, sort_keys=True)
    if len(raw) <= max_chars:
        lead_mind.setdefault("compaction", {})["raw_chars_estimate"] = len(raw)
        return lead_mind

    memory = lead_mind.get("memory") or {}
    technical = lead_mind.get("technical_context") or {}
    compacted = {
        "version": lead_mind.get("version", 1),
        "lead_profile": lead_mind.get("lead_profile", {}),
        "intent": lead_mind.get("intent", {}),
        "segment": lead_mind.get("segment", deepcopy(SEGMENT_UNKNOWN)),
        "commercial_context": {
            "next_best_action": (lead_mind.get("commercial_context") or {}).get("next_best_action"),
            "objection": (lead_mind.get("commercial_context") or {}).get("objection"),
        },
        "technical_context": {
            "btus": technical.get("btus"),
            "brand": technical.get("brand"),
            "city_bairro": technical.get("city_bairro"),
            "equipment_type": technical.get("equipment_type"),
            "installation": technical.get("installation", {}),
        },
        "memory": {
            "conversation_summary": memory.get("conversation_summary", ""),
            "facts": list(dict.fromkeys(memory.get("facts") or []))[-30:],
            "do_not_ask": list(dict.fromkeys(memory.get("do_not_ask") or [])),
            "missing_fields": list(dict.fromkeys(memory.get("missing_fields") or [])),
            "last_asked_field": memory.get("last_asked_field"),
            "ask_count_by_field": memory.get("ask_count_by_field") or {},
            "last_messages": list(memory.get("last_messages") or [])[-8:],
        },
        "risk": lead_mind.get("risk", {}),
        "tts": lead_mind.get("tts", {}),
        "compaction": {
            "version": 1,
            "last_compacted_at": datetime.now(timezone.utc).isoformat(),
            "raw_chars_estimate": len(raw),
        },
    }
    return compacted
