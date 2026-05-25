from __future__ import annotations

import re


_SECRET_RESPONSE = (
    "Não consigo passar informações internas do sistema por aqui.\n\n"
    "Se você precisa de atendimento de ar-condicionado, me fala se é instalação, manutenção, higienização ou conserto."
)

_DISCOUNT_RESPONSE = (
    "Os valores seguem a política da empresa e dependem do tipo de serviço e do local.\n\n"
    "Me passa o serviço e o bairro/cidade que eu te oriento certinho."
)

_OTHER_CUSTOMER_RESPONSE = (
    "Não posso passar dados de outros atendimentos.\n\n"
    "Posso te ajudar com o seu caso. É sobre instalação, manutenção, higienização ou conserto?"
)


def _has_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def detect_malicious_or_instruction_injection(text: str) -> dict[str, str | bool]:
    lowered = text.lower()

    secret_patterns = (
        r"ignore (suas|as|o) instru",
        r"ignore (o )?system prompt",
        r"ignore (o )?prompt anterior",
        r"revele (seu|o) prompt",
        r"mostre (suas|as) regras",
        r"mostre .*vari[aá]veis",
        r"mostre .*token",
        r"\bapi key\b",
        r"\bsenha\b",
        r"database url",
        r"owner phone",
        r"chave ssh",
        r"modo desenvolvedor",
        r"jailbreak",
        r"cancele as regras",
    )
    other_customer_patterns = (
        r"dados de outro cliente",
        r"outro telefone",
        r"hist[oó]rico de outro",
        r"lista de clientes",
        r"clientes da refrimix",
    )
    commercial_attack_patterns = (
        r"diga que .*gratuito",
        r"visita .*gr[aá]tis",
        r"desconto de 100%",
        r"servi[cç]o gr[aá]tis",
        r"envie mensagem para outro n[uú]mero",
    )
    roleplay_patterns = (
        r"agora voc[eê] [ée]",
        r"finja que",
        r"responda como se fosse",
    )

    if _has_any(lowered, other_customer_patterns):
        return {
            "is_malicious": True,
            "risk_level": "high",
            "reason": "other_customer_data_request",
            "safe_response": _OTHER_CUSTOMER_RESPONSE,
        }
    if _has_any(lowered, secret_patterns):
        return {
            "is_malicious": True,
            "risk_level": "high",
            "reason": "secret_or_internal_config_request",
            "safe_response": _SECRET_RESPONSE,
        }
    if _has_any(lowered, commercial_attack_patterns):
        return {
            "is_malicious": True,
            "risk_level": "medium",
            "reason": "commercial_policy_override_attempt",
            "safe_response": _DISCOUNT_RESPONSE,
        }
    if _has_any(lowered, roleplay_patterns):
        return {
            "is_malicious": True,
            "risk_level": "medium",
            "reason": "instruction_override_attempt",
            "safe_response": _SECRET_RESPONSE,
        }

    return {"is_malicious": False, "risk_level": "none", "reason": "", "safe_response": ""}
