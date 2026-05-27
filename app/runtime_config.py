"""Configuração de runtime e monitoring para o bot Refrimix.

Modes:
- shadow: gera resposta, salva métricas, NÃO envia ao cliente
- assisted: gera resposta, salva para aprovação humana, humanoaprova/edita/envia
- canary: responde automaticamente só intents permitidos + respeita CANARY_PERCENT

Nunca envia PDF, áudio para documento, contrato, PMOC, laudo ou proposta
sem aprovação humana.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RuntimeMode(str, Enum):
    """Modo de runtime do bot."""
    SHADOW = "shadow"
    ASSISTED = "assisted"
    CANARY = "canary"


class IntentFilter:
    """Filtros de intent para cada modo."""

    # Intents que podem auto-enviar em CANARY_MODE
    AUTO_REPLY_ALLOWED = frozenset(
        s.strip().lower()
        for s in os.getenv("BOT_AUTO_REPLY_ALLOWED_INTENTS", "welcome,higienizacao,visita_tecnica,servicos,agenda").split(",")
        if s.strip()
    )

    # Intents que SEMPRE vão para revisão humana
    HUMAN_REVIEW_REQUIRED = frozenset(
        s.strip().lower()
        for s in os.getenv("BOT_HUMAN_REVIEW_REQUIRED_INTENTS", "risco_eletrico,projeto,pmoc,laudo,contrato,reclamacao").split(",")
        if s.strip()
    )

    @classmethod
    def is_auto_allowed(cls, intent: Optional[str]) -> bool:
        if not intent:
            return False
        return intent.lower() in cls.AUTO_REPLY_ALLOWED

    @classmethod
    def requires_human_review(cls, intent: Optional[str]) -> bool:
        if not intent:
            return False
        return intent.lower() in cls.HUMAN_REVIEW_REQUIRED


@dataclass
class MonitoringConfig:
    """Configuração de monitoring."""
    # Runtime
    runtime_mode: RuntimeMode = RuntimeMode.SHADOW

    # Canary
    canary_percent: int = 0  # 0-100, só ativo em CANARY_MODE

    # Exportação
    feedback_min_cases: int = 30

    # Métricas (em memória — substitui por Postgres em produção)
    metrics_collector = None  # inicializado em runtime
    status_tracker = None
    feedback_store = None
    outcome_tracker = None

    @classmethod
    def from_env(cls) -> "MonitoringConfig":
        mode_str = os.getenv("BOT_RUNTIME_MODE", "shadow").strip().lower()
        try:
            mode = RuntimeMode(mode_str)
        except ValueError:
            mode = RuntimeMode.SHADOW

        return cls(
            runtime_mode=mode,
            canary_percent=max(0, min(100, int(os.getenv("BOT_CANARY_PERCENT", "0")))),
            feedback_min_cases=max(1, int(os.getenv("BOT_FEEDBACK_EXPORT_MIN_CASES", "30"))),
        )


def get_runtime_config() -> MonitoringConfig:
    """Retorna config de runtime (singleton simples)."""
    return MonitoringConfig.from_env()


def is_shadow_mode() -> bool:
    return get_runtime_config().runtime_mode == RuntimeMode.SHADOW


def is_assisted_mode() -> bool:
    return get_runtime_config().runtime_mode == RuntimeMode.ASSISTED


def is_canary_mode() -> bool:
    return get_runtime_config().runtime_mode == RuntimeMode.CANARY


def can_auto_reply(intent: Optional[str]) -> bool:
    """Verifica se intent pode auto-enviar em CANARY."""
    cfg = get_runtime_config()
    if cfg.runtime_mode != RuntimeMode.CANARY:
        return False
    if IntentFilter.requires_human_review(intent):
        return False
    if not IntentFilter.is_auto_allowed(intent):
        return False
    # Canary percent
    import random
    return random.random() * 100 < cfg.canary_percent