"""
Commercial Router — autoridade final para decisões comerciais.
Nunca deve ser sobrescrito pelo LLM.
"""
from __future__ import annotations

import re
from refrimix_core.domain.types import CommercialPath, CommercialDecision


_PROJECT_KEYWORDS = (
    "multi", "multisplit", "cassete", "piso teto", "piso-teto",
    "vrf", "vrv", "splitao", "splitão", "duto", "dutado",
    "alto padrão", "alto padrao", "comercial", "galpao", "galpão",
    "elétrica", "eletrica",
)

_NO_PHOTO_TERMS = (
    "nao tenho foto", "não tenho foto", "sem foto",
    "nao tenho as fotos", "não tenho as fotos",
)

_NO_INFRA_TERMS = (
    "nao tenho infra", "não tenho infra", "sem infra",
    "nao tenho infraestrutura", "não tenho infraestrutura",
    "nao tenho tubulacao", "não tenho tubulação",
    "nao tem tubulacao", "não tem tubulação",
)

_NO_COOLING_TERMS = (
    "nao climatiza", "não climatiza",
    "nao gela", "não gela", "parou de gelar",
)


def _fold(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _normalize_service(service: str | None) -> str | None:
    if not service:
        return None
    folded = _fold(service)
    mapping = {
        "instalacao": "instalacao",
        "instalação": "instalacao",
        "manutencao": "manutencao",
        "manutenção": "manutencao",
        "conserto": "manutencao",
        "higienizacao": "higienizacao",
        "higienização": "higienizacao",
        "pmoc": "project_quote",
        "consultoria": "project_quote",
        "projeto-central": "project_quote",
        "projeto": "project_quote",
        "eletrica": "project_quote",
        "elétrica": "project_quote",
    }
    return mapping.get(folded, folded or None)


def _parse_btus(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    digits = re.sub(r"\D", "", str(value))
    return int(digits) if digits else None


def _text_has_maintenance_signal(text: str) -> bool:
    """True if text contains maintenance signals."""
    _SIGNALS = (
        "nao gela", "não gela", "nao liga", "não liga",
        "nao funciona", "não funciona", "parou de funcionar",
        "pinga", "pingando", "gotejando",
        "cheiro ruim", "cheiro mal",
        "barulho", "barulhento", "vibrando",
        "nao esfria", "não esfria", "nao resfria", "não resfria",
        "disjuntor cai", "disjuntor caindo",
        "codigo erro", "codigo de erro", "erro no visor",
    )
    return any(sig in text for sig in _SIGNALS)


def _distance_ok(value: float | int | str | None) -> bool:
    if value is None:
        return False
    if isinstance((value), (float, int)):
        return float(value) <= 3.0
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value))
    if not match:
        return False
    try:
        return float(match.group(1).replace(",", ".")) <= 3.0
    except ValueError:
        return False


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _is_project_scope(
    service: str | None,
    lead_state: dict,
    text: str,
) -> tuple[bool, str | None]:
    if service == "project_quote":
        return True, "service_project"
    btus = _parse_btus(lead_state.get("installation", {}).get("btus"))
    if btus and btus > 18000:
        return True, "btus_above_18000"
    combined = " ".join(filter(None, [text, str(lead_state.get("service", {}).get("type", ""))]))
    if _contains_any(combined, _PROJECT_KEYWORDS):
        return True, "project_keyword"
    return False, None


def decide_commercial_path(
    lead_state: dict,
    user_text: str | None = None,
) -> CommercialDecision:
    """
    Autoridade final para path comercial.
    Chamado pelo pipeline antes de plan_next_action.
    O LLM nunca decide o preço — commercial_router é a autoridade final.
    """
    service = _normalize_service(lead_state.get("service", {}).get("type"))
    text = _fold(user_text)

    # ── No service yet: detect from text ───────────────────────────────
    if not service:
        # Try project keywords first
        if _is_project_scope(None, lead_state, text)[0]:
            return {
                "path": "project_quote",
                "can_schedule_now": True,
                "fixed_price": None,
                "visit_price": 50,
                "owner_alert": True,
                "reason": "project_keyword_from_text",
            }
        # Try maintenance signals in text
        if _text_has_maintenance_signal(text):
            return {
                "path": "technical_visit_50",
                "can_schedule_now": True,
                "fixed_price": None,
                "visit_price": 50,
                "owner_alert": False,
                "reason": "maintenance_signal_from_text",
            }
        # Still nothing → ask
        return {
            "path": "ask_basic_service",
            "can_schedule_now": False,
            "fixed_price": None,
            "visit_price": None,
            "owner_alert": False,
            "reason": "missing_service",
        }

    is_project, project_reason = _is_project_scope(service, lead_state, text)
    if is_project:
        return {
            "path": "project_quote",
            "can_schedule_now": True,
            "fixed_price": None,
            "visit_price": 50,
            "owner_alert": True,
            "reason": project_reason,
        }

    if service == "higienizacao":
        if _contains_any(text, _NO_COOLING_TERMS):
            return {
                "path": "technical_visit_50",
                "can_schedule_now": True,
                "fixed_price": None,
                "visit_price": 50,
                "owner_alert": False,
                "reason": "no_cooling",
            }
        return {
            "path": "fixed_hygienization",
            "can_schedule_now": True,
            "fixed_price": 200,
            "visit_price": None,
            "owner_alert": False,
            "reason": "standard_hygienization",
        }

    if service == "manutencao":
        return {
            "path": "technical_visit_50",
            "can_schedule_now": True,
            "fixed_price": None,
            "visit_price": 50,
            "owner_alert": False,
            "reason": "maintenance_default",
        }

    if service == "instalacao":
        instalacao = lead_state.get("installation", {})
        fotos = lead_state.get("fotos", {})
        btus = _parse_btus(instalacao.get("btus"))

        if _contains_any(text, _NO_PHOTO_TERMS):
            return {
                "path": "technical_visit_50",
                "can_schedule_now": True,
                "fixed_price": None,
                "visit_price": 50,
                "owner_alert": False,
                "reason": "missing_photos",
            }
        if _contains_any(text, _NO_INFRA_TERMS) or instalacao.get("infra_pronta") is False:
            return {
                "path": "technical_visit_50",
                "can_schedule_now": True,
                "fixed_price": None,
                "visit_price": 50,
                "owner_alert": False,
                "reason": "missing_infra",
            }

        simple_ready = all([
            btus is not None and btus <= 18000,
            fotos.get("local_interno") is True,
            fotos.get("local_externo") is True,
            instalacao.get("ponto_eletrico_exclusivo") is True,
            instalacao.get("infra_pronta") is True,
            _distance_ok(instalacao.get("distancia_aproximada")),
        ])
        if simple_ready:
            return {
                "path": "fixed_installation_simple",
                "can_schedule_now": True,
                "fixed_price": 850,
                "visit_price": None,
                "owner_alert": False,
                "reason": "simple_installation_validated",
            }

        return {
            "path": "technical_visit_50",
            "can_schedule_now": True,
            "fixed_price": None,
            "visit_price": 50,
            "owner_alert": False,
            "reason": "installation_needs_visit",
        }

    return {
        "path": "project_quote",
        "can_schedule_now": True,
        "fixed_price": None,
        "visit_price": 50,
        "owner_alert": False,
        "reason": "default_project",
    }