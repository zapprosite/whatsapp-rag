from __future__ import annotations

import re
from typing import Any

from agent_graph.domain.commercial_router import decide_commercial_path


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
    decision = decide_commercial_path({**lead_state, "tipo_servico": service})
    return bool(decision.can_schedule_now)


def _has_installation_minimum_for_window_question(lead_state: dict[str, Any]) -> bool:
    fotos = lead_state.get("fotos") or {}
    equipment_ok = any(
        [
            lead_state.get("btus"),
            lead_state.get("modelo_aparelho"),
            lead_state.get("aparelho_ja_comprado") is not None,
        ]
    )
    return bool(lead_state.get("cidade_bairro")) and bool(fotos.get("local_interno")) and bool(fotos.get("local_externo")) and bool(equipment_ok)


def _validate_next_action_contract(response: str, state: dict[str, Any], text: str) -> list[str]:
    next_action = state.get("next_action") or {}
    action_type = next_action.get("type")
    violations: list[str] = []
    if not action_type:
        return violations

    if action_type == "explain_process":
        if not any(term in text for term in ("funciona assim", "primeiro", "processo")):
            violations.append("action_missing_process_explanation")
        if (
            "período registrado" in text
            or "periodo registrado" in text
            or ("deixei o período da" in text and "registrado" in text)
            or ("deixei o periodo da" in text and "registrado" in text)
        ):
            violations.append("action_process_contains_window_confirmation")

    if action_type == "answer_capability_question":
        if not any(term in text for term in ("sim", "não", "nao")):
            violations.append("action_capability_missing_yes_no")
        if re.search(r"instala[cç][aã]o, manuten[cç][aã]o ou higieniza", text):
            violations.append("action_capability_asked_service_again")

    if action_type == "ask_missing_field":
        missing_field = next_action.get("missing_field")
        if missing_field:
            field_patterns = {
                "cidade_bairro": ("cidade", "bairro"),
                "foto_local_externo": ("condensadora", "local externo"),
                "foto_local_interno": ("local interno", "unidade interna"),
                "ponto_eletrico_exclusivo": ("ponto elétrico", "ponto eletrico"),
                "btus": ("btu", "capacidade"),
            }
            patterns = field_patterns.get(missing_field, ())
            if patterns and not any(pattern in text for pattern in patterns):
                violations.append("action_missing_correct_field")
        if "agendamento confirmado" in text or "deixei separada a opção" in text:
            violations.append("action_missing_field_confirmed_schedule")

    if action_type == "offer_calendar_slots":
        slots = state.get("calendar_slots") or ((state.get("lead_state") or {}).get("appointment") or {}).get("offered_slots") or []
        if not slots:
            violations.append("action_offer_slots_without_state_slots")
        if not re.search(r"1\..+2\..+3\.", response, re.S):
            violations.append("action_offer_slots_without_numbered_options")

    if action_type != "confirm_calendar_slot":
        if "agendamento confirmado" in text:
            violations.append("action_unexpected_schedule_confirmation")
        if action_type != "save_preferred_window" and ("período registrado" in text or "periodo registrado" in text):
            violations.append("action_unexpected_window_confirmation")

    return violations


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
    next_action_type = ((state.get("next_action") or {}).get("type"))
    if (
        in_progress
        and "?" not in response
        and state.get("conversation_objective") not in {"security_reject", "human_handoff"}
        and next_action_type not in {"confirm_calendar_slot", "save_preferred_window", "offer_calendar_slots"}
    ):
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

    # Confirmação de janela repetida: janela já existe no estado mas a mensagem atual não perguntou sobre agendamento
    latest_user_text = _fold(state.get("latest_user_text") or "")
    window_confirmation_phrases = (
        "deixei o periodo da", "deixei o período da",
        "registrado", "vou encaminhar para confirmacao", "vou encaminhar para confirmação",
    )
    schedule_request_terms = ("manha", "tarde", "noite", "agendar", "agenda", "horario", "horário", "marcar", "periodo", "período")
    if (
        appointment.get("preferred_window")
        and appointment.get("confirmed_window")
        and any(phrase in text for phrase in window_confirmation_phrases)
        and not any(term in latest_user_text for term in schedule_request_terms)
    ):
        violations.append("repeated_window_confirmation")

    # Pergunta de processo ignorada: cliente perguntou "como funciona" mas recebeu confirmação de janela
    process_question_terms = ("como funciona", "como e ", "como é ", "me explica", "qual o processo", "o que inclui")
    if (
        any(term in latest_user_text for term in process_question_terms)
        and any(phrase in text for phrase in ("deixei o periodo", "deixei o período", "vou encaminhar para confirmacao", "vou encaminhar para confirmação"))
    ):
        violations.append("answer_ignored_process_question")

    # Pergunta de agenda antes dos requisitos mínimos de instalação
    schedule_ask_phrases = ("melhor periodo: manha ou tarde", "melhor período: manhã ou tarde", "manha ou tarde?", "manhã ou tarde?")
    if service == "instalacao" and any(phrase in text for phrase in schedule_ask_phrases):
        if not _has_installation_minimum_for_window_question(lead_state):
            violations.append("schedule_before_requirements")

    violations.extend(_validate_next_action_contract(response, state, text))

    return not violations, violations
