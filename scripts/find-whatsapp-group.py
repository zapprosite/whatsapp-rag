#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent_graph.services.whatsapp import list_whatsapp_groups  # noqa: E402


def _group_name(group: dict) -> str:
    return str(group.get("subject") or group.get("name") or group.get("pushName") or group.get("title") or "")


def _group_jid(group: dict) -> str:
    return str(group.get("id") or group.get("jid") or group.get("remoteJid") or group.get("groupJid") or "")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Lista grupos da Evolution API e localiza o JID por nome.")
    parser.add_argument("--name", default=os.getenv("AGENDA_GROUP_NAME", "Agenda Refrimix"))
    parser.add_argument("--instance", default=os.getenv("EVOLUTION_INSTANCE", "default"))
    args = parser.parse_args()

    groups = await list_whatsapp_groups(args.instance)
    needle = args.name.casefold()
    found = [group for group in groups if needle in _group_name(group).casefold()]

    if not groups:
        print("Nenhum grupo retornado pela Evolution API.")
        return

    for group in found or groups:
        name = _group_name(group) or "sem nome"
        jid = _group_jid(group) or "JID não retornado"
        participants = group.get("participants") or []
        count = len(participants) if isinstance(participants, list) else "não informado"
        print(f"Nome: {name}")
        print(f"JID: {jid}")
        print(f"Participantes: {count}")
        if "@g.us" in jid:
            print(f"Configure no .env: AGENDA_GROUP_JID={jid}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
