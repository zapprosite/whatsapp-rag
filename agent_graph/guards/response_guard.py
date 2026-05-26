from __future__ import annotations

import re
from typing import Any


def _fold(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _asks_more_than_two_questions(text: str) -> bool:
    return text.count("?") > 2


def _contains_segment_leak(text: str) -> bool:
    leaks = (
        "segment_market",
        "segment_tier",
        "lead alto valor",
        "lead de alto valor",
        "commercial_high_value",
        "residential_high_end",
        "residential_common",
        "commercial_common",
        "segmento interno",
        "perfil interno",
    )
    return any(term in text for term in leaks)


def _contains_pushy_sales(text: str) -> bool:
    pressure_terms = (
        "últimas vagas",
        "ultimas vagas",
        "promoção imperdível",
        "promocao imperdivel",
        "só até agora",
        "so ate agora",
        "só hoje",
        "so hoje",
        "fechando agora",
        "fechando hoje",
        "vamos fechar",
        "posso fechar",
        "garanto sua vaga",
        "garantir sua vaga",
        "melhor preço",
        "melhor preco",
    )
    return any(term in text for term in pressure_terms)


def _is_invalid_value(value: Any) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    if not s:
        return True
    folded = _fold(s)
    invalid_exact = {"[audio]", "audio", "[imagem]", "imagem", "[image]", "local informado", "nao informado", "unknown", "none", "null"}
    if folded in invalid_exact:
        return True
    if folded.startswith("[audio") or folded.startswith("[imagem"):
        return True
    return False


def _has_minimum_data_for_appointment_guard(lead_state: dict[str, Any], service: str | None) -> bool:
    city = lead_state.get("cidade_bairro")
    if _is_invalid_value(city):
        return False
    fotos = lead_state.get("fotos") or {}
    manutencao = lead_state.get("manutencao") or {}
    conserto = lead_state.get("conserto") or {}
    instalacao = lead_state.get("instalacao") or {}
    if service in {"manutencao", "higienizacao"}:
        return any([fotos.get("aparelho"), manutencao.get("pinga_agua") is not None, manutencao.get("cheiro_ruim") is not None, manutencao.get("tempo_sem_manutencao") is not None, conserto.get("liga") is not None, conserto.get("gela") is not None])
    if service == "instalacao":
        return any([lead_state.get("btus"), fotos.get("local_interno"), fotos.get("local_externo"), instalacao.get("ponto_eletrico_exclusivo") is not None])
    return True


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
    if _contains_pushy_sales(text):
        violations.append("pushy_sales_pressure")
    if _contains_segment_leak(text):
        violations.append("internal_segment_leak")
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
    if response.strip() and response.strip()[-1] not in ".?!":
        violations.append("possible_truncated_response")
    if in_progress and "?" not in response and state.get("conversation_objective") not in {"security_reject", "human_handoff"}:
        violations.append("missing_next_step")
    if re.search(r"\bvos\b|\bteu aparelho avariado\b|\bpresupuesto\b|\bservicio\b", text):
        violations.append("non_ptbr")
    if "vou passar para um humano" in text and state.get("handoff_mode") in (None, "none"):
        violations.append("unwanted_handoff")

    # Novas violations para bugs de loop/placeholder/copy interna
    appointment = lead_state.get("appointment") or {}
    if appointment.get("preferred_window") and any(phrase in text for phrase in ("manhã ou tarde", "manha ou tarde", "qual período", "qual periodo", "melhor período", "melhor periodo")):
        violations.append("asked_preferred_window_again")

    if "[áudio]" in response or "[audio]" in response or "[imagem]" in response:
        violations.append("leaked_media_placeholder")

    if any(phrase in text for phrase in ("ja tenho dados suficientes", "dados suficientes para encaminhar")):
        if not _has_minimum_data_for_appointment_guard(lead_state, service):
            violations.append("appointment_claim_without_minimum_data")

    _safe_handoff_reasons = {"explicit_handoff", "sensitive_complaint", "complaint_or_risk", "electrical_risk"}
    if any(phrase in text for phrase in ("sinalizar o gerente", "vou sinalizar o gerente", "gerente agora")):
        if state.get("handoff_reason") not in _safe_handoff_reasons:
            violations.append("unwanted_internal_process")

    return not violations, violations
