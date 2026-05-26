from __future__ import annotations

import logging
import os
import re
from typing import Any

from agent_graph.services.whatsapp import send_whatsapp_group_text, send_whatsapp_text

logger = logging.getLogger(__name__)


def _enabled(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip() == "1"


def _format_owner_alert(alert: dict[str, Any]) -> str:
    title = str(alert.get("title") or "ALERTA OPERACIONAL").strip()
    lines = [f"*{title}*"]

    fields = (
        ("Telefone", alert.get("phone")),
        ("Cliente", alert.get("name")),
        ("Motivo", alert.get("reason")),
        ("Serviço provável", alert.get("service")),
        ("Relação", alert.get("relationship_type")),
        ("Local", alert.get("city_bairro")),
        ("Última mensagem", alert.get("last_message")),
        ("Resumo", alert.get("summary")),
        ("Próximo passo recomendado", alert.get("next_step")),
        ("Prioridade", alert.get("priority")),
    )
    for label, value in fields:
        if value:
            lines.append(f"{label}: {value}")
    command = alert.get("takeover_command")
    release_command = alert.get("release_command")
    if command:
        lines.append("")
        lines.append("Comando no WhatsApp:")
        lines.append(f"- Assumir só este lead: {command}")
        if release_command:
            lines.append(f"- Liberar a IA neste lead: {release_command}")
    return "\n".join(lines)[:3500]


def _normalize_phone_digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


async def send_owner_alert(alert: dict[str, Any]) -> bool:
    if not _enabled("OWNER_ALERTS_ENABLED", "1"):
        logger.info("OWNER_ALERTS_ENABLED=0; alerta owner não enviado")
        return False

    reason = str(alert.get("reason") or "")
    if reason.startswith("high_value") and not _enabled("OWNER_HIGH_VALUE_ALERTS_ENABLED", "1"):
        logger.info("OWNER_HIGH_VALUE_ALERTS_ENABLED=0; alerta alto valor não enviado")
        return False

    owner_phone = os.getenv("OWNER_PHONE", "")
    if not owner_phone:
        logger.warning("OWNER_PHONE não configurado; alerta owner não enviado")
        return False

    # Guarda: nunca enviar mensagem operacional para o próprio lead
    lead_phone = str(alert.get("phone") or "")
    if lead_phone and _normalize_phone_digits(owner_phone) == _normalize_phone_digits(lead_phone):
        logger.warning(
            "OWNER_PHONE igual ao lead %s; alerta owner suprimido para não vazar mensagem operacional ao cliente",
            lead_phone,
        )
        return False

    instance = str(alert.get("instance") or "default")
    return await send_whatsapp_text(owner_phone, _format_owner_alert(alert), instance)


async def send_agenda_group_message(text: str) -> bool:
    if not _enabled("AGENDA_GROUP_ENABLED", "1"):
        logger.info("AGENDA_GROUP_ENABLED=0; mensagem de agenda não enviada")
        return False

    group_jid = os.getenv("AGENDA_GROUP_JID", "").strip()
    if not group_jid:
        logger.warning("AGENDA_GROUP_ENABLED=1, mas AGENDA_GROUP_JID está vazio; agenda não enviada")
        return False
    return await send_whatsapp_group_text(group_jid, text, os.getenv("EVOLUTION_INSTANCE", "default"))


_SERVICE_LABELS: dict[str, str] = {
    "instalacao": "instalação",
    "manutencao": "manutenção",
    "higienizacao": "higienização",
    "projeto-central": "projeto de climatização",
    "pmoc": "PMOC",
    "consultoria": "consultoria técnica",
    "conserto": "conserto",
    "eletrica": "análise elétrica",
}


def _agenda_service_label(service: str | None) -> str:
    return _SERVICE_LABELS.get(service or "", service or "serviço não classificado")


def _format_agenda_alert(lead_data: dict) -> str:
    """Resumo estruturado de agendamento — sem histórico de conversa."""
    service = _agenda_service_label(lead_data.get("service"))
    address = lead_data.get("address") or "local não informado"
    window = lead_data.get("window") or "horário a combinar"
    phone = lead_data.get("phone") or "sem telefone"
    name = lead_data.get("name") or "sem nome"
    lines = [
        "*AGENDAMENTO CONFIRMADO*",
        f"Telefone: {phone}",
        f"Cliente: {name}",
        f"Serviço: {service}",
        f"Local: {address}",
        f"Janela: {window}",
        "Próximo passo: Confirmar execução no WhatsApp do cliente.",
    ]
    return "\n".join(lines)


async def send_appointment_alert(lead_data: dict) -> bool:
    """Envia alerta de agendamento confirmado para o grupo de agenda (fallback: owner)."""
    text = _format_agenda_alert(lead_data)
    if _enabled("AGENDA_GROUP_ENABLED", "1"):
        group_jid = os.getenv("AGENDA_GROUP_JID", "").strip()
        if group_jid:
            return await send_agenda_group_message(text)
        logger.warning("AGENDA_GROUP_ENABLED=1 mas AGENDA_GROUP_JID vazio; usando fallback owner")

    # Fallback: owner (se grupo não configurado)
    return await send_owner_alert(
        {
            "title": "AGENDAMENTO CONFIRMADO",
            "phone": lead_data.get("phone"),
            "name": lead_data.get("name"),
            "reason": "appointment_confirmed",
            "service": lead_data.get("service"),
            "city_bairro": lead_data.get("address"),
            "last_message": lead_data.get("last_message") or "não informada",
            "summary": text,
            "next_step": "Confirmar execução e janela diretamente no WhatsApp do cliente.",
            "priority": "normal",
            "instance": lead_data.get("instance") or "default",
        }
    )


async def prisma_upsert_lead(lead_data: dict) -> None:
    """Cria ou atualiza Lead no PostgreSQL via Prisma."""
    from prisma import Prisma

    phone = lead_data.get("phone", "unknown")
    prisma = Prisma()
    await prisma.connect()
    try:
        await prisma.lead.upsert(
            where={"phone": phone},
            data={
                "create": {
                    "phone": phone,
                    "name": lead_data.get("name"),
                    "service": lead_data.get("service"),
                    "address": lead_data.get("address"),
                    "window": lead_data.get("window"),
                },
                "update": {
                    "name": lead_data.get("name"),
                    "service": lead_data.get("service"),
                    "address": lead_data.get("address"),
                    "window": lead_data.get("window"),
                },
            },
        )
        logger.info("Lead upserted: %s", phone)
    except Exception as exc:
        logger.error("Prisma upsert lead falhou: %s", exc)
    finally:
        await prisma.disconnect()
