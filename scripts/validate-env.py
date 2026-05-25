#!/usr/bin/env python3
"""Valida nomes obrigatorios do ambiente sem imprimir valores."""
from __future__ import annotations

import argparse
import os
from pathlib import Path


REQUIRED = {
    "AUTHENTICATION_API_KEY",
    "EVOLUTION_API_KEY",
    "EVOLUTION_API_URL",
    "EVOLUTION_DATABASE_URL",
    "EVOLUTION_INSTANCE",
    "REDIS_URL",
    "QDRANT_URL",
    "QDRANT_COLLECTION",
    "DATABASE_URL",
}

OPTIONAL_REQUIRED_BY_FLAG = {
    "GOOGLE_CALENDAR_ENABLED": {"1": {"GOOGLE_CALENDAR_ID", "GOOGLE_SERVICE_ACCOUNT_FILE"}},
    "PTBR_POLISH_ENABLED": {"1": {"LOCAL_PTBR_BASE_URL", "LOCAL_PTBR_MODEL"}},
}


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip('"').strip("'")
    return values


def is_present(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip() != "{SECRET}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida .env sem revelar valores.")
    parser.add_argument("--env-file", default=".env", help="Arquivo local ignorado pelo git.")
    args = parser.parse_args()

    env_file = Path(args.env_file)
    file_values = load_env_file(env_file)
    merged = {**os.environ, **file_values}

    required = set(REQUIRED)
    for flag, choices in OPTIONAL_REQUIRED_BY_FLAG.items():
        selected = merged.get(flag, "")
        required.update(choices.get(selected, set()))

    missing = sorted(name for name in required if not is_present(merged.get(name)))

    if missing:
        print("Ambiente incompleto. Variaveis ausentes ou mascaradas:")
        for name in missing:
            print(f"- {name}")
        return 1

    print("Ambiente valido: variaveis obrigatorias presentes. Valores nao foram exibidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
