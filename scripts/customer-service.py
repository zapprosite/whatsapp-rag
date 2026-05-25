#!/usr/bin/env python3
"""Gerencia serviços em andamento para o bot diferenciar pós-venda de lead novo."""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime

from prisma import Prisma


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cria/lista serviços em andamento da Refrimix.")
    sub = parser.add_subparsers(dest="command", required=True)

    upsert = sub.add_parser("upsert", help="Cria ou atualiza serviço ativo de um telefone.")
    upsert.add_argument("--phone", required=True)
    upsert.add_argument("--service", required=True)
    upsert.add_argument("--status", default="scheduled")
    upsert.add_argument("--address", default="")
    upsert.add_argument("--window", default="")
    upsert.add_argument("--notes", default="")

    close = sub.add_parser("close", help="Marca o serviço mais recente do telefone como completed.")
    close.add_argument("--phone", required=True)

    list_cmd = sub.add_parser("list", help="Lista serviços de um telefone.")
    list_cmd.add_argument("--phone", required=True)

    return parser.parse_args()


async def upsert_service(args: argparse.Namespace) -> None:
    db = Prisma()
    await db.connect()
    try:
        existing = await db.query_raw(
            """
            SELECT id
            FROM customer_services
            WHERE phone = $1
              AND status IN ('scheduled','in_progress','awaiting_parts','awaiting_customer','approved','active')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            args.phone,
        )
        if existing:
            service_id = existing[0]["id"]
            await db.execute_raw(
                """
                UPDATE customer_services
                SET service = $2,
                    status = $3,
                    address = NULLIF($4, ''),
                    scheduled_window = NULLIF($5, ''),
                    notes = NULLIF($6, ''),
                    updated_at = $7
                WHERE id = $1
                """,
                service_id,
                args.service,
                args.status,
                args.address,
                args.window,
                args.notes,
                datetime.utcnow(),
            )
            print(f"atualizado: {service_id}")
        else:
            service_id = str(uuid.uuid4())
            rows = await db.query_raw(
                """
                INSERT INTO customer_services (id, phone, service, status, address, scheduled_window, notes, created_at, updated_at)
                VALUES ($1, $2, $3, $4, NULLIF($5, ''), NULLIF($6, ''), NULLIF($7, ''), $8, $8)
                RETURNING id
                """,
                service_id,
                args.phone,
                args.service,
                args.status,
                args.address,
                args.window,
                args.notes,
                datetime.utcnow(),
            )
            print(f"criado: {rows[0]['id']}")
    finally:
        await db.disconnect()


async def close_service(args: argparse.Namespace) -> None:
    db = Prisma()
    await db.connect()
    try:
        updated = await db.execute_raw(
            """
            UPDATE customer_services
            SET status = 'completed', updated_at = $2
            WHERE id = (
                SELECT id
                FROM customer_services
                WHERE phone = $1
                ORDER BY updated_at DESC
                LIMIT 1
            )
            """,
            args.phone,
            datetime.utcnow(),
        )
        print(f"fechados: {updated}")
    finally:
        await db.disconnect()


async def list_services(args: argparse.Namespace) -> None:
    db = Prisma()
    await db.connect()
    try:
        rows = await db.query_raw(
            """
            SELECT phone, service, status, address, scheduled_window, notes, updated_at
            FROM customer_services
            WHERE phone = $1
            ORDER BY updated_at DESC
            LIMIT 10
            """,
            args.phone,
        )
        for row in rows:
            print(row)
    finally:
        await db.disconnect()


async def main() -> None:
    args = parse_args()
    if args.command == "upsert":
        await upsert_service(args)
    elif args.command == "close":
        await close_service(args)
    elif args.command == "list":
        await list_services(args)


if __name__ == "__main__":
    asyncio.run(main())
