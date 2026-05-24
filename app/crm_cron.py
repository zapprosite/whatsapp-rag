#!/usr/bin/env python3
"""
crm_cron.py — Script de follow-up automático para orçamentos "frios".
Deve ser rodado via crontab a cada 1 hora.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timedelta

from dotenv import load_dotenv
load_dotenv()

from prisma import Prisma
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def send_whatsapp_message(phone: str, text: str) -> bool:
    api_key = os.getenv("EVOLUTION_API_KEY", os.getenv("AUTHENTICATION_API_KEY", ""))
    api_url = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
    instance_name = os.getenv("EVOLUTION_INSTANCE", "RefrimixLead")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{api_url}/message/sendText/{instance_name}",
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"number": phone, "text": text},
            )
            return resp.status_code in (200, 201)
    except Exception as e:
        logger.error(f"Falha ao enviar followup para {phone}: {e}")
        return False

async def run_followups():
    prisma = Prisma()
    await prisma.connect()
    
    try:
        # Busca leads que tiveram a última interação entre 24h e 26h atrás
        # para evitar mandar mensagem 2x
        now = datetime.utcnow()
        start_time = now - timedelta(hours=26)
        end_time = now - timedelta(hours=24)
        
        # SQL simplificado para pegar o último contato de cada telefone no intervalo
        # (Em produção, o ideal é usar um campo "last_followup" ou tabela dedicada)
        rows = await prisma.query_raw(
            """
            SELECT phone, MAX(created_at) as last_contact
            FROM interactions
            GROUP BY phone
            HAVING MAX(created_at) BETWEEN $1::timestamp AND $2::timestamp
            """,
            start_time, end_time
        )
        
        for row in rows:
            phone = row["phone"]
            logger.info(f"Fazendo follow-up para: {phone}")
            msg = "Oi! Tudo bem? Will da Refrimix aqui. Conseguiu pensar sobre a nossa conversa de ontem? Nossa agenda dessa semana tá quase fechando, quer que eu reserve um horário pra você? Qualquer dúvida me avisa!"
            success = await send_whatsapp_message(phone, msg)
            if success:
                logger.info(f"Follow-up enviado com sucesso para {phone}.")
                
    finally:
        await prisma.disconnect()

if __name__ == "__main__":
    asyncio.run(run_followups())
