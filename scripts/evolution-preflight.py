#!/usr/bin/env python3
"""Preflight seguro para subir a Evolution API sem quebrar sessão/QR."""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"
DEFAULT_COMPOSE = ROOT / "docker-compose.yml"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def present(value: str | None) -> bool:
    return bool(value and value.strip() and value.strip() != "{SECRET}")


def evolution_image(compose_file: Path) -> str:
    if not compose_file.exists():
        return ""
    text = compose_file.read_text(encoding="utf-8")
    match = re.search(r"^\s*image:\s*(evoapicloud/evolution-api:[^\s#]+)", text, re.MULTILINE)
    return match.group(1) if match else ""


def docker_volume_exists(name: str) -> bool:
    completed = subprocess.run(
        ["docker", "volume", "inspect", name],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def validate(env_file: Path = DEFAULT_ENV, compose_file: Path = DEFAULT_COMPOSE, check_volumes: bool = True) -> list[str]:
    env = {**os.environ, **load_env_file(env_file)}
    errors: list[str] = []

    if not present(env.get("EVOLUTION_DATABASE_URL")):
        errors.append("EVOLUTION_DATABASE_URL_ausente")
    if not present(env.get("DATABASE_URL")):
        errors.append("DATABASE_URL_ausente")
    if present(env.get("EVOLUTION_DATABASE_URL")) and env.get("EVOLUTION_DATABASE_URL") == env.get("DATABASE_URL"):
        errors.append("EVOLUTION_DATABASE_URL_nao_pode_reusar_DATABASE_URL")

    image = evolution_image(compose_file)
    if not image:
        errors.append("evolution_image_nao_encontrada")
    elif image.endswith(":latest"):
        errors.append("evolution_image_latest_proibida")
    elif image != "evoapicloud/evolution-api:v2.3.7":
        errors.append("evolution_image_diferente_da_pinada_v2_3_7")

    if check_volumes:
        for volume in ("whatsapp-rag_evolution_instances", "whatsapp-rag_evolution-data"):
            if not docker_volume_exists(volume):
                errors.append(f"volume_ausente:{volume}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida Evolution API antes de subir container.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV))
    parser.add_argument("--compose-file", default=str(DEFAULT_COMPOSE))
    parser.add_argument("--skip-volumes", action="store_true")
    args = parser.parse_args()

    errors = validate(Path(args.env_file), Path(args.compose_file), check_volumes=not args.skip_volumes)
    if errors:
        print("Preflight Evolution API falhou. Corrija sem expor valores:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Preflight Evolution API OK. Valores sensiveis nao foram exibidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
