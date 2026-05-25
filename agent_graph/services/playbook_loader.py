from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


_ROOT = Path(__file__).resolve().parents[2]
_KNOWLEDGE_DIR = _ROOT / "knowledge" / "refrimix"
_PLAYBOOK_DIR = _KNOWLEDGE_DIR / "playbooks"


def _safe_name(name: str) -> str:
    candidate = name.strip().removesuffix(".yaml")
    if not candidate or "/" in candidate or "\\" in candidate or candidate.startswith("."):
        raise ValueError(f"Nome de playbook inválido: {name!r}")
    return candidate


@lru_cache(maxsize=64)
def load_playbook(name: str) -> dict[str, Any]:
    """Carrega um playbook YAML versionado de knowledge/refrimix/playbooks."""
    safe_name = _safe_name(name)
    path = _PLAYBOOK_DIR / f"{safe_name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Playbook não encontrado: {safe_name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Playbook precisa ser objeto YAML: {safe_name}")
    return data


def load_all_playbooks() -> dict[str, dict[str, Any]]:
    """Carrega todos os playbooks YAML conhecidos."""
    return {path.stem: load_playbook(path.stem) for path in sorted(_PLAYBOOK_DIR.glob("*.yaml"))}


def get_service_questions(service: str | None, segment: str | None) -> list[str]:
    """Retorna a ordem de perguntas para serviço/segmento, com fallback simples."""
    if not service:
        return ["tipo_servico", "cidade_bairro"]

    questions = load_playbook("qualification_questions")
    service_rules = questions.get(service) or questions.get(service.replace("-", "_")) or {}
    if not isinstance(service_rules, dict):
        return []

    segment_key = segment or "residential_common"
    rule = service_rules.get(segment_key) or service_rules.get("residential_common") or next(
        (value for value in service_rules.values() if isinstance(value, dict)),
        {},
    )
    priority = rule.get("priority") if isinstance(rule, dict) else []
    return [str(item) for item in priority or []]


def get_high_value_signals() -> dict[str, Any]:
    return load_playbook("high_value_signals").get("high_value", {})


def get_tts_policy(goal: str | None) -> dict[str, Any]:
    policy = load_playbook("tts_speech_policy").get("tts_policy", {})
    default = dict(policy.get("default") or {})
    by_goal = policy.get("by_goal") or {}
    if goal and isinstance(by_goal, dict):
        default.update(by_goal.get(goal) or {})
    return default
