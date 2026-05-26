#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

# Ajusta path para que imports relativos funcionem a partir da raiz do projeto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent_graph.services.whatsapp import normalize_whatsapp_number

async def reset_lead(phone: str, keep_phone: bool) -> None:
    normalized = normalize_whatsapp_number(phone) or phone
    print(f"Iniciando o reset do lead para o telefone: {normalized}")

    # 1. Limpeza do Redis
    redis_url = os.getenv("REDIS_URL")
    if redis_url:
        import redis.asyncio as aioredis
        print(f"Conectando ao Redis em {redis_url}...")
        try:
            r = aioredis.Redis.from_url(redis_url, decode_responses=True)
            
            keys_to_delete = [
                f"conv_history:{normalized}",
                f"manual_takeover:{normalized}",
                f"conv_lock:{normalized}",
                f"handoff_state:{normalized}",
            ]
            
            deleted_count = 0
            for key in keys_to_delete:
                if await r.delete(key):
                    print(f"  [Redis] Deletada chave: {key}")
                    deleted_count += 1
            
            side_effect_pattern = f"side_effect:*:{normalized}:*"
            async for key in r.scan_iter(match=side_effect_pattern):
                if await r.delete(key):
                    print(f"  [Redis] Deletada chave side_effect: {key}")
                    deleted_count += 1
            
            print(f"Redis limpo com sucesso. Total de chaves deletadas: {deleted_count}")
            await r.aclose()
        except Exception as e:
            print(f"Erro ao limpar o Redis: {e}", file=sys.stderr)
    else:
        print("REDIS_URL não está configurada no ambiente. Pulando limpeza do Redis.")

    # 2. Limpeza do Postgres
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from prisma import Prisma
        print("Conectando ao PostgreSQL via Prisma...")
        try:
            db = Prisma()
            await db.connect()
            try:
                lead = await db.lead.find_unique(where={"phone": normalized})
                if lead:
                    print(f"Lead localizado no banco de dados. ID: {lead.id}")
                    
                    # Deleta todos os eventos de conversa do lead
                    events_deleted = await db.query_raw(
                        "DELETE FROM lead_events WHERE lead_id = $1",
                        str(lead.id)
                    ) or 0
                    print(f"  [Postgres] Deletados {events_deleted} eventos de conversa (lead_events)")
                    
                    # Atualiza o lead definindo os valores nulos e padrões solicitados
                    await db.lead.update(
                        where={"phone": normalized},
                        data={
                            "lead_state": json.dumps({}),
                            "conversation_summary": None,
                            "already_asked_fields": json.dumps([]),
                            "missing_fields": json.dumps([]),
                            "do_not_ask": json.dumps([]),
                            "service_type": None,
                            "pipeline_stage": "new",
                            "name": None,
                            "service": None,
                            "address": None,
                            "window": None,
                            "city_bairro": None,
                            "urgency": None,
                            "last_user_message_at": None,
                        }
                    )
                    print(f"  [Postgres] Registro de Lead atualizado e zerado.")
                else:
                    print(f"Nenhum registro de Lead encontrado no Postgres para o fone {normalized}.")
            finally:
                await db.disconnect()
        except Exception as e:
            print(f"Erro ao conectar ou atualizar o Postgres: {e}", file=sys.stderr)
    else:
        print("DATABASE_URL não configurada no ambiente. Pulando Postgres.")

    print("Processo de reset concluído com sucesso!")

def main() -> None:
    parser = argparse.ArgumentParser(description="Zera e limpa o estado de um lead no banco de dados e no Redis.")
    parser.add_argument("--phone", required=True, help="Número do telefone do lead a ser resetado.")
    parser.add_argument("--keep-phone", action="store_true", help="Mantém o telefone intacto durante o reset.")
    
    args = parser.parse_args()
    
    # Carregar variáveis do arquivo .env se existir
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    asyncio.run(reset_lead(args.phone, args.keep_phone))

if __name__ == "__main__":
    main()
