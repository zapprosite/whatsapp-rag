from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

CommercialPath = Literal[
    "fixed_installation_simple",
    "fixed_hygienization",
    "technical_visit_50",
    "project_quote",
    "ask_basic_service",
]


@dataclass(frozen=True)
class CommercialDecision:
    path: CommercialPath
    can_schedule_now: bool
    fixed_price: int | None = None
    visit_price: int | None = None
    owner_alert: bool = False
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PROJECT_KEYWORDS = (
    "multi",
    "multisplit",
    "cassete",
    "piso teto",
    "piso-teto",
    "vrf",
    "vrv",
    "splitao",
    "splitão",
    "duto",
    "dutado",
    "alto padrão",
    "alto padrao",
    "comercial",
    "galpao",
    "galpão",
    "eletrica",
    "elétrica",
    "restaurante",
    "projeto para",
    "projeto de",
)

_NO_PHOTO_TERMS = (
    "nao tenho foto",
    "não tenho foto",
    "sem foto",
    "nao tenho as fotos",
    "não tenho as fotos",
)

_NO_INFRA_TERMS = (
    "nao tenho infra",
    "não tenho infra",
    "sem infra",
    "nao tenho infraestrutura",
    "não tenho infraestrutura",
    "nao tenho tubulacao",
    "não tenho tubulação",
    "nao tem tubulacao",
    "não tem tubulação",
)

_NO_COOLING_TERMS = (
    "nao climatiza",
    "não climatiza",
    "nao gela",
    "não gela",
    "parou de gelar",
)


def _fold(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _normalize_service(service: str | None) -> str | None:
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


def _parse_btus(value: Any) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _distance_ok(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
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


def _is_project_scope(service: str | None, lead_state: dict[str, Any], text: str) -> tuple[bool, str | None]:
    btus = _parse_btus(lead_state.get("btus"))
    modelo = _fold(lead_state.get("modelo_aparelho"))
    combined = " ".join(filter(None, [text, modelo]))
    if service == "project_quote":
        return True, "service_project"
    if btus and btus > 18000:
        return True, "btus_above_18000"
    if _contains_any(combined, _PROJECT_KEYWORDS):
        return True, "project_keyword"
    return False, None


def decide_commercial_path(lead_state: dict[str, Any] | None, user_text: str | None = None) -> CommercialDecision:
    lead_state = lead_state or {}
    text = _fold(user_text)
    service = _normalize_service(lead_state.get("tipo_servico"))
    if not service:
        return CommercialDecision(path="ask_basic_service", can_schedule_now=False, reason="missing_service")

    is_project, project_reason = _is_project_scope(service, lead_state, text)
    if is_project:
        return CommercialDecision(
            path="project_quote",
            can_schedule_now=True,
            visit_price=50,
            owner_alert=True,
            reason=project_reason,
        )

    if service == "higienizacao":
        conserto = lead_state.get("conserto") or {}
        if _contains_any(text, _NO_COOLING_TERMS) or conserto.get("gela") is False:
            return CommercialDecision(path="technical_visit_50", can_schedule_now=True, visit_price=50, reason="no_cooling")
        return CommercialDecision(path="fixed_hygienization", can_schedule_now=True, fixed_price=200, reason="standard_hygienization")

    if service == "manutencao":
        return CommercialDecision(path="technical_visit_50", can_schedule_now=True, visit_price=50, reason="maintenance_default")

    if service == "instalacao":
        fotos = lead_state.get("fotos") or {}
        instalacao = lead_state.get("instalacao") or {}
        btus = _parse_btus(lead_state.get("btus"))
        if _contains_any(text, _NO_PHOTO_TERMS):
            return CommercialDecision(path="technical_visit_50", can_schedule_now=True, visit_price=50, reason="missing_photos")
        if _contains_any(text, _NO_INFRA_TERMS) or instalacao.get("tubulacao_existente") is False:
            return CommercialDecision(path="technical_visit_50", can_schedule_now=True, visit_price=50, reason="missing_infra")

        simple_ready = all(
            [
                btus is not None and btus <= 18000,
                bool(fotos.get("local_interno")),
                bool(fotos.get("local_externo")),
                instalacao.get("ponto_eletrico_exclusivo") is True,
                instalacao.get("tubulacao_existente") is True,
                _distance_ok(instalacao.get("distancia_aproximada")),
            ]
        )
        if simple_ready:
            return CommercialDecision(path="fixed_installation_simple", can_schedule_now=True, fixed_price=850, reason="simple_installation_validated")

        return CommercialDecision(path="technical_visit_50", can_schedule_now=True, visit_price=50, reason="installation_needs_visit")

    return CommercialDecision(path="project_quote", can_schedule_now=True, visit_price=50, reason="default_project")
