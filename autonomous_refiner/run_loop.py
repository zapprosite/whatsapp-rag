#!/usr/bin/env python3
"""
run_loop.py — Loop principal de refinamento automático.

Responsibilities:
- Carrega cenários da case_library.json
- Para cada cenário: chama o bot, avalia com judge, decide refinar
- Pode rodar em modo contínuo (--loop) ou único (single-shot)
- Para cada cenário que precisa de refino: aplica correção e re-avalia

Uso:
  python3 autonomous_refiner/run_loop.py                  # 1 ciclo em todos os cenários
  python3 autonomous_refiner/run_loop.py --loop 50       # até 50 ciclos ou convergência
  python3 autonomous_refiner/run_loop.py --auto          # loop até score médio >= 8.0
  python3 autonomous_refiner/run_loop.py --cena inst_001 # cenário específico
"""
from __future__ import annotations
import os, sys, json, argparse, time, subprocess
from pathlib import Path
from typing import Optional

# Adiciona parent ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from autonomous_refiner.evaluator import JudgeClient, ScoreResult, ScoreLevel
from autonomous_refiner.refiner import aplicar_refinamento
from autonomous_refiner.trigger import should_refine, TriggerResult

# ── Config ────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
CASE_LIBRARY = ROOT / "autonomous_refiner/case_library.json"
BASE_URL     = os.getenv("REFINAR_BASE_URL", "http://localhost:8000").rstrip("/")
TARGET_SCORE = float(os.getenv("REFINAR_TARGET_SCORE", "8.0"))
LOG_FILE     = ROOT / ".context/refinamento_log.jsonl"

# ── ANSI ──────────────────────────────────────────────────────────────────────
R  = "\033[0m"
GR = "\033[92m"
YL = "\033[93m"
RD = "\033[91m"
CY = "\033[96m"
B  = "\033[1m"


def c(col, t): return f"{col}{t}{R}"


# ── Case library ───────────────────────────────────────────────────────────────

def load_cases() -> list[dict]:
    """Carrega casos da case_library.json."""
    if not CASE_LIBRARY.exists():
        print(c(RD, f"CASE_LIBRARY não encontrada: {CASE_LIBRARY}"))
        return []
    with open(CASE_LIBRARY, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


# ── Bot caller ─────────────────────────────────────────────────────────────────

def call_bot(message: str) -> dict:
    """Chama o bot via HTTP e retorna a resposta."""
    try:
        import httpx
        r = httpx.post(
            f"{BASE_URL}/test/chat",
            params={
                "message": message,
                "media_type": "conversation",
                "media_url": "",
                "send": "false",
            },
            timeout=90,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {
            "error": str(e),
            "response": "",
            "intent": "?",
            "handoff_mode": "none"
        }


# ── Run single scenario ────────────────────────────────────────────────────────

def run_scenario(
    case: dict,
    judge: JudgeClient,
    verbose: bool = False,
) -> tuple[ScoreResult, TriggerResult]:
    """Roda um cenário: bot → judge → trigger."""
    scenario   = case["scenario"]
    intent     = case.get("intent", "unknown")
    service    = case.get("service", "unknown")

    # 1. Chama bot
    bot_resp = call_bot(scenario)
    response = bot_resp.get("response", "")
    if verbose:
        print(f"  Bot resposta: {response[:100]}...")

    # 2. Avalia com judge
    score_result = judge.evaluate(
        scenario=scenario,
        original_response=response,
        intent=intent,
        service=service,
    )

    if verbose:
        lvl_colors = {
            ScoreLevel.EXCELLENT: GR,
            ScoreLevel.GOOD: YL,
            ScoreLevel.FAIR: YL,
            ScoreLevel.POOR: RD,
        }
        lvl = c(lvl_colors[score_result.level], score_result.level.value)
        print(f"  Score: {score_result.score:.1f}/10 [{lvl}] — {score_result.justification[:80]}")

    # 3. Trigger
    trigger_result = should_refine(
        scenario=scenario,
        intent=intent,
        service=service,
        current_score=score_result.score,
    )

    return score_result, trigger_result


# ── Run full loop ─────────────────────────────────────────────────────────────

def run_loop(
    max_cycles: int = 1,
    target_avg: float = TARGET_SCORE,
    verbose: bool = False,
    case_ids: Optional[list[str]] = None,
) -> dict:
    """
    Loop principal de refinamento.
    
    Args:
        max_cycles: número máximo de ciclos de refinamento
        target_avg: score médio alvo para convergência
        verbose:打印 detalhado
        case_ids: se setado, roda só esses IDs
    
    Returns:
        dict com estatísticas finais
    """
    cases = load_cases()
    if case_ids:
        cases = [c for c in cases if c.get("id") in case_ids]

    if not cases:
        print(c(RD, "Nenhum caso encontrado."))
        return {}

    print(c(CY, f"=== LOOP DE REFINAMENTO ==="))
    print(f"  Casos: {len(cases)} | Max ciclos: {max_cycles} | Alvo: {target_avg}/10")
    print()

    judge = JudgeClient()
    cycle_stats = []
    all_scores = []

    for cycle in range(1, max_cycles + 1):
        print(c(B, f"\n--- Ciclo {cycle}/{max_cycles} ---"))
        cycle_scores = []
        refined = 0

        for case in cases:
            cid = case.get("id", "?")
            scenario = case.get("scenario", "")

            print(f"\n  [{cid}] {scenario[:60]}")
            score_result, trigger_result = run_scenario(case, judge, verbose=verbose)
            cycle_scores.append(score_result.score)
            all_scores.append(score_result.score)

            if not trigger_result.should_refine:
                status = c(GR, "OK")
                print(f"    {status} score={score_result.score:.1f} — não precisa refinar")
                continue

            # Refinar
            print(f"    {c(YL, 'REFINAR')} score={score_result.score:.1f}")
            if verbose:
                for imp in score_result.improvements:
                    print(f"      • {imp}")

            # Aplica refinação e loga
            log_entry = aplicar_refinamento(
                scenario=scenario,
                ideal_response=score_result.ideal_response,
                problems=score_result.improvements,
                intent=case.get("intent", "unknown"),
                service=case.get("service", "unknown"),
                original_score=score_result.score,
                judge_model=score_result.judge_model,
            )
            refined += 1
            print(f"    {c(CY, 'LOG')} nivel={log_entry.nivel} → {log_entry.arquivo_alvo}")

        # Stats do ciclo
        avg = sum(cycle_scores) / len(cycle_scores) if cycle_scores else 0
        cycle_stats.append({"cycle": cycle, "avg": avg, "refined": refined})
        print(c(B, f"\n  Ciclo {cycle} — avg={avg:.2f} refined={refined}/{len(cases)}"))

        if avg >= target_avg:
            print(c(GR, f"\n  ✓ Convergência! Score médio {avg:.2f} >= {target_avg}"))
            break

    # Resumo final
    final_avg = sum(all_scores) / len(all_scores) if all_scores else 0
    summary = {
        "cycles_run": len(cycle_stats),
        "total_cases": len(cases) * len(cycle_stats),
        "final_avg_score": round(final_avg, 2),
        "target_reached": final_avg >= target_avg,
        "cycles": cycle_stats,
    }

    print(c(B, "\n=== RESUMO FINAL ==="))
    print(f"  Ciclos executados: {summary['cycles_run']}")
    print(f"  Score médio final: {summary['final_avg_score']}/10")
    print(f"  Alvo atingido: {c(GR if summary['target_reached'] else RD, str(summary['target_reached']))}")

    # Salva resumo
    summary_file = ROOT / ".context/refinamento_summary.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"\n  Resumo salvo em: {summary_file}")

    return summary


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Loop de refinamento automático")
    parser.add_argument("--loop", type=int, default=1,
                        help="Número de ciclos (default: 1)")
    parser.add_argument("--auto", action="store_true",
                        help="Loop até convergência (avg >= 8.0)")
    parser.add_argument("--cena", type=str, default=None,
                        help="Rodar cenário específico (case ID)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    max_cycles = 999 if args.auto else args.loop
    case_ids = [args.cena] if args.cena else None

    run_loop(
        max_cycles=max_cycles,
        verbose=args.verbose,
        case_ids=case_ids,
    )


if __name__ == "__main__":
    main()