from __future__ import annotations

import subprocess
import sys


REQUIRED_ENV = {
    "AUTHENTICATION_API_KEY": "secret-auth",
    "EVOLUTION_API_KEY": "secret-evo",
    "EVOLUTION_API_URL": "http://example.invalid",
    "EVOLUTION_DATABASE_URL": "postgresql://evolution.invalid/db",
    "EVOLUTION_INSTANCE": "instance",
    "REDIS_URL": "redis://localhost:6379",
    "QDRANT_URL": "http://localhost:6333",
    "QDRANT_COLLECTION": "collection",
    "DATABASE_URL": "postgresql://rag.invalid/db",
}


def _write_env(path, values):
    path.write_text("\n".join(f"{key}={value}" for key, value in values.items()) + "\n", encoding="utf-8")


def test_validate_env_rejects_reusing_rag_database_for_evolution(tmp_path):
    env_file = tmp_path / ".env"
    values = dict(REQUIRED_ENV)
    values["EVOLUTION_DATABASE_URL"] = values["DATABASE_URL"]
    _write_env(env_file, values)

    result = subprocess.run(
        [sys.executable, "scripts/validate-env.py", "--env-file", str(env_file)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "EVOLUTION_DATABASE_URL_nao_pode_reusar_DATABASE_URL" in result.stdout
    assert values["DATABASE_URL"] not in result.stdout


def test_validate_env_accepts_distinct_evolution_database(tmp_path):
    env_file = tmp_path / ".env"
    _write_env(env_file, REQUIRED_ENV)

    result = subprocess.run(
        [sys.executable, "scripts/validate-env.py", "--env-file", str(env_file)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Valores nao foram exibidos" in result.stdout
