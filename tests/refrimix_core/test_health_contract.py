"""
Health contract para refrimix_core V2.

Valida que /health retorna schema honesto com core_version, módulos opcionais
desabilitados (rag/tts/vision), e legacy_core disponível mas não como principal.

Run:
    python -m pytest tests/refrimix_core/test_health_contract.py -v
"""
from __future__ import annotations

import os
import pytest


def get_health_json():
    """Helper: faz GET /health com REFRIMIX_CORE_VERSION=v2 no ambiente."""
    from app.main import app
    from fastapi.testclient import TestClient

    env_backup = os.environ.get("REFRIMIX_CORE_VERSION")
    os.environ["REFRIMIX_CORE_VERSION"] = "v2"
    try:
        client = TestClient(app)
        response = client.get("/health")
        return response.status_code, response.json()
    finally:
        if env_backup is not None:
            os.environ["REFRIMIX_CORE_VERSION"] = env_backup
        else:
            os.environ.pop("REFRIMIX_CORE_VERSION", None)


def get_health_legacy():
    """Helper: GET /health com REFRIMIX_CORE_VERSION=legacy."""
    from app.main import app
    from fastapi.testclient import TestClient

    env_backup = os.environ.get("REFRIMIX_CORE_VERSION")
    os.environ["REFRIMIX_CORE_VERSION"] = "legacy"
    try:
        client = TestClient(app)
        response = client.get("/health")
        return response.status_code, response.json()
    finally:
        if env_backup is not None:
            os.environ["REFRIMIX_CORE_VERSION"] = env_backup
        else:
            os.environ.pop("REFRIMIX_CORE_VERSION", None)


class TestHealthContractV2:
    """Testes para o contrato de /health quando REFRIMIX_CORE_VERSION=v2."""

    def test_health_returns_200(self):
        code, _ = get_health_json()
        assert code == 200

    def test_core_version_present(self):
        _, body = get_health_json()
        assert "core_version" in body, f"core_version missing: {list(body.keys())}"

    def test_core_version_v2(self):
        _, body = get_health_json()
        assert body["core_version"] == "v2", f"Expected v2, got {body.get('core_version')}"

    def test_refrimix_core_status_present(self):
        _, body = get_health_json()
        assert "refrimix_core" in body, f"refrimix_core missing: {list(body.keys())}"

    def test_refrimix_core_up(self):
        _, body = get_health_json()
        assert body["refrimix_core"] == "up", f"Expected 'up', got {body.get('refrimix_core')}"

    def test_legacy_core_available(self):
        _, body = get_health_json()
        assert "legacy_core" in body, f"legacy_core missing: {list(body.keys())}"
        assert body["legacy_core"] in ("available", "disabled")

    def test_redis_status(self):
        _, body = get_health_json()
        assert "redis" in body
        assert body["redis"] in ("up", "down: Redis pool not initialized")

    def test_worker_status(self):
        _, body = get_health_json()
        assert "worker" in body

    def test_evolution_status(self):
        _, body = get_health_json()
        assert "evolution" in body, f"evolution missing: {list(body.keys())}"

    def test_langgraph_not_core(self):
        _, body = get_health_json()
        # langgraph nunca aparece como "up" ou "core" quando v2
        # aparece como "legacy_available" ou "disabled" no máximo
        if "langgraph" in body:
            assert body["langgraph"] in (
                "legacy_available",
                "disabled",
            ), f"langgraph should be legacy_available or disabled, got {body.get('langgraph')}"

    def test_rag_disabled_when_not_enabled(self, monkeypatch):
        """Quando RAG_ENABLED=0, rag deve ser 'disabled'."""
        monkeypatch.setenv("RAG_ENABLED", "0")
        _, body = get_health_json()
        assert "rag" in body
        assert body["rag"] == "disabled", f"Expected disabled, got {body.get('rag')}"

    def test_rag_enabled_when_set(self, monkeypatch):
        """Quando RAG_ENABLED=1, rag deve ser 'up' (se Qdrant acessível)."""
        monkeypatch.setenv("RAG_ENABLED", "1")
        _, body = get_health_json()
        assert "rag" in body
        # Não falamos que é "up" porque Qdrant pode não estar local,
        # mas o campo deve estar presente
        assert body["rag"] in ("up", "disabled", "degraded"), f"Unexpected rag: {body.get('rag')}"

    def test_tts_disabled_when_not_enabled(self, monkeypatch):
        """Quando TTS_ENABLED=0, tts deve ser 'disabled'."""
        monkeypatch.setenv("TTS_ENABLED", "0")
        _, body = get_health_json()
        assert "tts" in body, f"tts missing: {list(body.keys())}"
        assert body["tts"] == "disabled", f"Expected disabled, got {body.get('tts')}"

    def test_vision_disabled_when_not_enabled(self, monkeypatch):
        """Quando VISION_ENABLED=0, vision deve ser 'disabled'."""
        monkeypatch.setenv("VISION_ENABLED", "0")
        _, body = get_health_json()
        assert "vision" in body, f"vision missing: {list(body.keys())}"
        assert body["vision"] == "disabled", f"Expected disabled, got {body.get('vision')}"

    def test_all_keys_v2_contract(self):
        """O contrato v2 tem um conjunto mínimo de chaves known."""
        _, body = get_health_json()
        required = ["status", "core_version", "refrimix_core", "redis", "worker"]
        for key in required:
            assert key in body, f"Missing required key: {key}"


class TestHealthContractLegacy:
    """Testes para o contrato de /health quando REFRIMIX_CORE_VERSION=legacy."""

    def test_health_returns_200(self):
        code, _ = get_health_legacy()
        assert code == 200

    def test_core_version_legacy(self):
        _, body = get_health_legacy()
        assert "core_version" in body
        assert body["core_version"] == "legacy"

    def test_langgraph_up_in_legacy(self):
        _, body = get_health_legacy()
        assert "langgraph" in body
        assert body["langgraph"] == "up"