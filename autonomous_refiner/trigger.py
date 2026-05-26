#!/usr/bin/env python3
"""
trigger.py — Decide quando o loop de refinamento deve rodar.

Responsibilities:
- Avalia se uma interação merece ser refinada (threshold)
- Filtra cenários duplicados (hash dedup)
- Define se o refinamento é blocking (síncrono) ou async
"""
from __future__ import annotations
import os, hashlib, time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

# ── Config ────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
TRIGGER_LOG  = ROOT / ".context/trigger_log.jsonl"
MIN_SCORE_TRIGGER  = float(os.getenv("REFINAR_MIN_SCORE_TRIGGER", "7.0"))
MAX_REFINAMENTOS   = int(os.getenv("REFINAR_MAX_PER_DAY", "20"))
DEDUP_WINDOW_SECS  = int(os.getenv("REFINAR_DEDUP_WINDOW_SECS", "3600"))

# ── ANSI ──────────────────────────────────────────────────────────────────────
R  = "\033[0m"
GR = "\033[92m"
YL = "\033[93m"
RD = "\033[91m"
CY = "\033[96m"


def c(col, t): return f"{col}{t}{R}"


# ── Trigger result ────────────────────────────────────────────────────────────

@dataclass
class TriggerResult:
    should_refine: bool
    reason: str
    scenario_hash: str
    nivel_sugerido: int
    is_blocking: bool
    queue_position: Optional[int] = None


# ── Dedup & counter ───────────────────────────────────────────────────────────

def _read_trigger_log() -> list[dict]:
    if not TRIGGER_LOG.exists():
        return []
    entries = []
    with open(TRIGGER_LOG, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(__import__("json").loads(line.strip()))
            except Exception:
                pass
    return entries


def _count_recent_refinamentos() -> int:
    """Conta refinamentos nas últimas 24h."""
    entries = _read_trigger_log()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_str = cutoff.isoformat()
    return sum(1 for e in entries if e.get("timestamp", "") > cutoff_str)


def scenario_hash(scenario: str, intent: str, service: str) -> str:
    """Hash dedup para não refinar o mesmo cenário repetidamente."""
    normalized = f"{intent}:{service}:{scenario.lower().strip()}".encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:16]


def is_duplicate(scenario: str, intent: str, service: str) -> bool:
    """Verifica se este cenário foi refinado recentemente (dedup window)."""
    h = scenario_hash(scenario, intent, service)
    entries = _read_trigger_log()
    cutoff = time.time() - DEDUP_WINDOW_SECS
    for entry in entries:
        ts = entry.get("timestamp", "")
        try:
            # parse ISO
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.timestamp() < cutoff:
                continue
        except Exception:
            continue
        if entry.get("scenario_hash", "") == h:
            return True
    return False


def log_trigger(scenario: str, intent: str, service: str,
                should_refine: bool, reason: str, nivel: int) -> None:
    """Loga decisão do trigger."""
    TRIGGER_LOG.parent.mkdir(parents=True, exist_ok=True)
    h = scenario_hash(scenario, intent, service)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenario": scenario[:200],
        "intent": intent,
        "service": service,
        "scenario_hash": h,
        "should_refine": should_refine,
        "reason": reason,
        "nivel_sugerido": nivel,
    }
    with open(TRIGGER_LOG, "a", encoding="utf-8") as f:
        f.write(__import__("json").dumps(entry, ensure_ascii=False) + "\n")


# ── Main trigger logic ─────────────────────────────────────────────────────────

def should_refine(
    scenario: str,
    intent: str,
    service: str,
    current_score: float,
) -> TriggerResult:
    """
    Decide se o cenário deve entrar no loop de refinamento.

    Args:
        scenario: mensagem/cenário do lead
        intent: intent classificada
        service: serviço classificado
        current_score: score atual da resposta (se disponível)

    Returns:
        TriggerResult com decisão e metadados
    """
    h = scenario_hash(scenario, intent, service)

    # 1. Score baixo automático
    if current_score > 0 and current_score < MIN_SCORE_TRIGGER:
        log_trigger(scenario, intent, service, True,
                    f"score {current_score} < {MIN_SCORE_TRIGGER}", 1)
        return TriggerResult(
            should_refine=True,
            reason=f"Score {current_score} abaixo do limiar {MIN_SCORE_TRIGGER}",
            scenario_hash=h,
            nivel_sugerido=1,
            is_blocking=False,
        )

    # 2. Dup check
    if is_duplicate(scenario, intent, service):
        log_trigger(scenario, intent, service, False,
                    "cenário duplicado no dedup window", 0)
        return TriggerResult(
            should_refine=False,
            reason="Cenário já refinado recentemente",
            scenario_hash=h,
            nivel_sugerido=0,
            is_blocking=False,
        )

    # 3. Rate limit
    recent = _count_recent_refinamentos()
    if recent >= MAX_REFINAMENTOS:
        log_trigger(scenario, intent, service, False,
                    f"rate limit: {recent}/{MAX_REFINAMENTOS} já usados", 0)
        return TriggerResult(
            should_refine=False,
            reason=f"Rate limit atingido ({MAX_REFINAMENTOS}/dia)",
            scenario_hash=h,
            nivel_sugerido=0,
            is_blocking=False,
        )

    # 4. Score médio → non-blocking, coloca na fila
    if 0 < current_score < 8.0:
        log_trigger(scenario, intent, service, True,
                    f"score {current_score} justifica refinamento", 1)
        return TriggerResult(
            should_refine=True,
            reason=f"Score {current_score} < 8.0 — melhoria possível",
            scenario_hash=h,
            nivel_sugerido=1,
            is_blocking=False,
        )

    # 5. Nenhum gatilho
    return TriggerResult(
        should_refine=False,
        reason="Nenhum gatilho de refinamento ativado",
        scenario_hash=h,
        nivel_sugerido=0,
        is_blocking=False,
    )


# ── CLI self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("Quero instalar split em Santos", "instalacao", "instalacao", 5.5),
        ("Quero instalar split em Santos", "instalacao", "instalacao", 5.5),  # dup
        ("Manutenção do ar", "manutencao", "manutencao", 9.0),
    ]
    for s, i, svc, score in tests:
        r = should_refine(s, i, svc, score)
        status = c(GR, "REFINAR") if r.should_refine else c(RD, "PULAR")
        print(f"{status} | score={score} | {r.reason[:60]}")