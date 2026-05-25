from __future__ import annotations

import re
from typing import Any


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _asks_more_than_two_questions(text: str) -> bool:
    return text.count("?") > 2


def validate_response_before_send(response: str, state: dict[str, Any]) -> tuple[bool, list[str]]:
    lead_state = state.get("lead_state") or {}
    customer_data = state.get("customer_data") or {}
    memory = customer_data.get("memory") or {}
    do_not_ask = set(state.get("do_not_ask") or [])
    text = _fold(response)
    violations: list[str] = []
    service = lead_state.get("tipo_servico") or state.get("service")
    in_progress = bool(service or memory.get("has_persistent_lead") or memory.get("postgres_event_count"))

    if service and re.search(r"(qual|quais).{0,30}(servi[cç]o|precisa)|instala[cç][aã]o, manuten[cç][aã]o ou higieniza", text):
        violations.append("asked_service_type_again")
    if in_progress and ("oi, tudo bem" in text or "olá, tudo bem" in text or "ola, tudo bem" in text):
        violations.append("repeated_greeting")
    if service and ("como posso ajudar" in text or "qual serviço você precisa" in text):
        violations.append("generic_restart")

    field_patterns = {
        "cidade_bairro": ("cidade", "bairro", "onde fica"),
        "btus": ("btu", "capacidade"),
        "foto_local_interno": ("foto do local interno", "foto interna", "unidade interna"),
        "foto_local_externo": ("foto do local externo", "foto externa", "condensadora"),
        "ponto_eletrico_exclusivo": ("ponto elétrico", "ponto eletrico"),
        "distancia_aproximada": ("distância", "distancia", "metros"),
        "tubulacao_existente": ("tubulação", "tubulacao", "infra pronta"),
        "tempo_sem_manutencao": ("tempo sem manutenção", "ultima manutenção", "última manutenção"),
        "pinga_agua": ("pingando", "vazando água", "vazando agua"),
        "nome": ("seu nome", "qual é seu nome", "qual seu nome"),
    }
    ask_counts = lead_state.get("ask_count_by_field") or {}
    for field, patterns in field_patterns.items():
        if "?" not in text:
            continue
        if any(pattern in text for pattern in patterns):
            if field in do_not_ask:
                violations.append(f"asked_do_not_ask:{field}")
            if int(ask_counts.get(field) or 0) >= 2:
                violations.append(f"asked_repeated_field:{field}")

    forbidden = (
        "visita grátis",
        "visita gratis",
        "100% de desconto",
        "api key",
        "database url",
        "system prompt",
        "prompt interno",
    )
    if any(term in text for term in forbidden):
        violations.append("forbidden_claim_or_secret")
    try:
        from agent_graph.services.domain_disambiguation import find_forbidden_context_drift

        drift_hits = find_forbidden_context_drift(response)
        if drift_hits:
            violations.extend(f"context_drift:{hit}" for hit in drift_hits)
    except Exception:
        pass
    if _asks_more_than_two_questions(response):
        violations.append("too_many_questions")
    if len(response) > 1500:
        violations.append("too_long")
    if re.search(r"\bvos\b|\bteu aparelho avariado\b|\bpresupuesto\b|\bservicio\b", text):
        violations.append("non_ptbr")
    if "vou passar para um humano" in text and state.get("handoff_mode") in (None, "none"):
        violations.append("unwanted_handoff")

    return not violations, violations
