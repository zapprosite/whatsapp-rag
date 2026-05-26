from __future__ import annotations

from typing import Any


BLOCKING_FIELDS_GLOBAL = ["nome"]

BLOCKING_FIELDS_BY_STAGE = {
    "before_calendar_event": ["nome"],
    "before_google_event_insert": ["nome", "address"],
}

USEFUL_FIELDS_BY_SERVICE = {
    "instalacao": [
        "cidade_bairro",
        "btus",
        "foto_local_interno",
        "foto_local_externo",
        "ponto_eletrico_exclusivo",
        "distancia_aproximada",
        "tubulacao_existente",
        "aparelho_ja_comprado",
    ],
    "higienizacao": [
        "cidade_bairro",
        "quantidade_aparelhos",
        "foto_aparelho",
        "aparelho_funcionando",
    ],
    "manutencao": [
        "cidade_bairro",
        "sintoma",
        "marca",
        "btus",
        "codigo_erro",
        "foto_ou_video",
    ],
}


def _identity(lead_state: dict[str, Any] | None) -> dict[str, Any]:
    return (lead_state or {}).get("lead_identity") or {}


def needs_name(lead_state: dict[str, Any] | None) -> bool:
    identity = _identity(lead_state)
    return not bool(identity.get("full_name") or identity.get("first_name") or (lead_state or {}).get("nome"))


def next_identity_field(lead_state: dict[str, Any] | None) -> str | None:
    identity = _identity(lead_state)
    if not (identity.get("phone") or (lead_state or {}).get("phone")):
        return "phone"
    if needs_name(lead_state):
        return "nome"
    if not identity.get("email"):
        return "email"
    if not identity.get("address"):
        return "address"
    return None


def next_useful_field(service: str | None, missing_fields: list[str]) -> str | None:
    if not service:
        return None
    for field in USEFUL_FIELDS_BY_SERVICE.get(service, []):
        if field in missing_fields:
            return field
    return None
