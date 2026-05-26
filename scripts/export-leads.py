#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime

from agent_graph.services.leads_export import export_leads_csv


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta leads do PostgreSQL para CSV operacional.")
    parser.add_argument("--today", action="store_true", help="Exporta apenas os leads criados hoje.")
    parser.add_argument("--from", dest="start_date", type=_parse_date, help="Data inicial no formato YYYY-MM-DD.")
    parser.add_argument("--to", dest="end_date", type=_parse_date, help="Data final no formato YYYY-MM-DD.")
    parser.add_argument("--output", dest="output", help="Caminho do CSV de saída.")
    args = parser.parse_args()

    start_date = args.start_date
    end_date = args.end_date
    if args.today:
        today = date.today()
        start_date = today
        end_date = today

    output = asyncio.run(export_leads_csv(start_date=start_date, end_date=end_date, path=args.output))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
