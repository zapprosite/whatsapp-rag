#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from agent_graph.services.agenda_digest import send_agenda_digest  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera preview ou envia digest da agenda Refrimix.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("today", "tomorrow"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--send", action="store_true")
        cmd.add_argument("--preview", action="store_true")
        cmd.add_argument("--target", choices=("group", "owner", "preview"), default="group")
    date_cmd = sub.add_parser("date")
    date_cmd.add_argument("value")
    date_cmd.add_argument("--send", action="store_true")
    date_cmd.add_argument("--preview", action="store_true")
    date_cmd.add_argument("--target", choices=("group", "owner", "preview"), default="group")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    today = datetime.now().date()
    if args.command == "today":
        target_date = today
        kind = "morning_today"
    elif args.command == "tomorrow":
        target_date = today + timedelta(days=1)
        kind = "night_tomorrow"
    else:
        target_date = datetime.strptime(args.value, "%Y-%m-%d").date()
        kind = "manual"

    should_send = bool(args.send and not args.preview)
    target = args.target if should_send else "preview"
    result = await send_agenda_digest(target_date, kind, force=True, target=target)
    print(result["message"])
    print()
    print(f"sent={result['sent']} count={result['count']} target_date={result['target_date']}")


if __name__ == "__main__":
    asyncio.run(main())
