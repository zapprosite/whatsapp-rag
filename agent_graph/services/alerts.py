from __future__ import annotations

import os
import logging
import httpx

logger = logging.getLogger(__name__)

_EVO_TIMEOUT = 15.0


async def send_appointment_alert(lead_data: dict) -> bool:
    """
    Envia alerta de novo agendamento para o dono (Will) via WhatsApp.
    lead_data deve conter: phone, name, service, address, window.
    """
    owner_phone = os.getenv("OWNER_PHONE", "")
    if not owner_phone:
        logger.warning("OWNER_PHONE não configurado — alerta não enviado")
        return False

    evo_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    evo_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
    instance = os.getenv("EVOLUTION_INSTANCE", "RefrimixLead")

    name = lead_data.get("name") or "não informado"
    service = lead_data.get("service") or "não classificado"
    address = lead_data.get("address") or "não informado"
    window = lead_data.get("window") or "a combinar"
    phone = lead_data.get("phone", "")

    text = (
        f"🔔 *Novo lead agendado*\n\n"
        f"👤 Nome: {name}\n"
        f"📱 Contato: {phone}\n"
        f"🔧 Serviço: {service}\n"
        f"📍 Endereço: {address}\n"
        f"🕐 Janela: {window}\n\n"
        f"Responda direto no WhatsApp do lead."
    )

    try:
        async with httpx.AsyncClient(timeout=_EVO_TIMEOUT) as client:
            resp = await client.post(
                f"{evo_url}/message/sendText/{instance}",
                headers={"apikey": evo_key, "Content-Type": "application/json"},
                json={"number": owner_phone, "text": text},
            )
            if resp.status_code in (200, 201):
                logger.info(f"Alerta de agendamento enviado para dono: {owner_phone}")
                return True
            logger.warning(f"Falha ao enviar alerta: {resp.status_code} {resp.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"Erro ao enviar alerta de agendamento: {e}")
        return False


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
        logger.info(f"Lead upserted: {phone}")
    except Exception as e:
        logger.error(f"Prisma upsert lead falhou: {e}")
    finally:
        await prisma.disconnect()
