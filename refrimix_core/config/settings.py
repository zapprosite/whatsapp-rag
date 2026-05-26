"""
Configurações do Refrimix Core V2.
Lidas do ambiente via pydantic-settings.
"""
from __future__ import annotations

import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigConfig


class RefrimixSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Core ──────────────────────────────────────────────────────────────
    REFRIMIX_CORE_VERSION: Literal["legacy", "v2"] = "legacy"
    LOG_LEVEL: str = "INFO"

    # ── Evolution API ─────────────────────────────────────────────────────
    EVOLUTION_API_URL: str = "http://localhost:8080"
    EVOLUTION_API_KEY: str = ""
    EVOLUTION_INSTANCE: str = "default"

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"
    WHATSAPP_QUEUE_KEY: str = "whatsapp_rag:queue"
    WHATSAPP_PROCESSING_QUEUE_KEY: str = "whatsapp_rag:processing"
    WHATSAPP_DLQ_KEY: str = "whatsapp_rag:dead_letter"

    # ── Postgres / Prisma ─────────────────────────────────────────────────
    DATABASE_URL: str = ""

    # ── MiniMax (primário) ────────────────────────────────────────────────
    MINIMAX_API_KEY: str = ""
    MINIMAX_BASE_URL: str = "https://api.minimax.io/v1"
    MINIMAX_MODEL: str = "MiniMax-M2.7"
    MINIMAX_MAX_TOKENS: int = 400
    MINIMAX_TIMEOUT_SECONDS: float = 90.0
    MINIMAX_CONCURRENCY: int = 4

    # ── Groq (STT fallback) ───────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.1-8b-instant"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_MAX_TOKENS: int = 250
    GROQ_TIMEOUT_SECONDS: float = 15.0

    # ── Local Qwen (PC1) ──────────────────────────────────────────────────
    LOCAL_QWEN_BASE_URL: str = "http://127.0.0.1:8011/v1"
    LOCAL_QWEN_MODEL: str = "qwen2.5-vl-7b-instruct"
    LOCAL_QWEN_MAX_TOKENS: int = 300
    LOCAL_QWEN_CONTEXT_TOKENS: int = 4096
    LOCAL_QWEN_TIMEOUT_SECONDS: float = 45.0
    LOCAL_QWEN_CONCURRENCY: int = 1

    # ── TTS ────────────────────────────────────────────────────────────────
    TTS_ENABLED: int = 0
    TTS_ENGINE: str = "chatterbox"
    CHATTERBOX_URL: str = "http://127.0.0.1:8200"
    OMNIVOICE_URL: str = "http://127.0.0.1:8202"
    TTS_LOCALE: str = "pt-BR"
    TTS_CHATTERBOX_LANGUAGE: str = "pt"
    TTS_ALLOW_CHATTERBOX_PTBR: int = 1
    TTS_MAX_CHARS: int = 420

    # ── Vision ──────────────────────────────────────────────────────────────
    VISION_ENABLED: int = 0

    # ── RAG ────────────────────────────────────────────────────────────────
    RAG_ENABLED: int = 0
    QDRANT_URL: str = ""
    QDRANT_COLLECTION: str = "hermes_hvac_rag_service_staging"

    # ── Owner ──────────────────────────────────────────────────────────────
    OWNER_PHONE: str = ""
    OWNER_ALERTS_ENABLED: int = 1
    OWNER_HIGH_VALUE_ALERTS_ENABLED: int = 1

    # ── Worker ─────────────────────────────────────────────────────────────
    WORKER_CONCURRENCY: int = 4
    WORKER_QUEUE_POP_TIMEOUT_SECONDS: int = 5
    WORKER_MESSAGE_TIMEOUT_SECONDS: float = 180.0
    GRAPH_RESPONSE_TIMEOUT_SECONDS: float = 45.0
    WORKER_MAX_ATTEMPTS: int = 3
    CONV_TTL_SECONDS: int = 1800
    CONV_MAX_TURNS: int = 6
    CONV_LOCK_TTL_SECONDS: int = 240
    CONV_LOCK_WAIT_SECONDS: float = 20.0

    # ── Agenda ──────────────────────────────────────────────────────────────
    AGENDA_GROUP_ENABLED: int = 1
    AGENDA_GROUP_NAME: str = "Agenda Refrimix"
    AGENDA_GROUP_JID: str = ""

    @property
    def tts_enabled(self) -> bool:
        return self.TTS_ENABLED in (1, "1", "true")

    @property
    def vision_enabled(self) -> bool:
        return self.VISION_ENABLED in (1, "1", "true")

    @property
    def rag_enabled(self) -> bool:
        return self.RAG_ENABLED in (1, "1", "true")

    @property
    def is_core_v2(self) -> bool:
        return self.REFRIMIX_CORE_VERSION == "v2"


_settings: RefrimixSettings | None = None


def get_settings() -> RefrimixSettings:
    global _settings
    if _settings is None:
        _settings = RefrimixSettings()
    return _settings
