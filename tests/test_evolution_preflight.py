from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path("scripts/evolution-preflight.py")
spec = importlib.util.spec_from_file_location("evolution_preflight", MODULE_PATH)
assert spec and spec.loader
evolution_preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evolution_preflight)


def _write_env(path: Path, *, evolution_db: str = "postgresql://evolution.invalid/evolution_db") -> None:
    path.write_text(
        "\n".join(
            [
                "DATABASE_URL=postgresql://rag.invalid/rag_db",
                f"EVOLUTION_DATABASE_URL={evolution_db}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_compose(path: Path, image: str = "evoapicloud/evolution-api:v2.3.7") -> None:
    path.write_text(
        f"""
services:
  evolution-api:
    image: {image}
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_evolution_preflight_accepts_safe_contract(tmp_path):
    env_file = tmp_path / ".env"
    compose_file = tmp_path / "docker-compose.yml"
    _write_env(env_file)
    _write_compose(compose_file)

    errors = evolution_preflight.validate(env_file, compose_file, check_volumes=False)

    assert errors == []


def test_evolution_preflight_rejects_reused_rag_database(tmp_path):
    env_file = tmp_path / ".env"
    compose_file = tmp_path / "docker-compose.yml"
    _write_env(env_file, evolution_db="postgresql://rag.invalid/rag_db")
    _write_compose(compose_file)

    errors = evolution_preflight.validate(env_file, compose_file, check_volumes=False)

    assert "EVOLUTION_DATABASE_URL_nao_pode_reusar_DATABASE_URL" in errors


def test_evolution_preflight_rejects_latest_image(tmp_path):
    env_file = tmp_path / ".env"
    compose_file = tmp_path / "docker-compose.yml"
    _write_env(env_file)
    _write_compose(compose_file, "evoapicloud/evolution-api:latest")

    errors = evolution_preflight.validate(env_file, compose_file, check_volumes=False)

    assert "evolution_image_latest_proibida" in errors
