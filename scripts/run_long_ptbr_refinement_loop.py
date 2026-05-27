#!/usr/bin/env python3
"""
run_long_ptbr_refinement_loop.py

Loop longo de refinamento PT-BR — roda por horas em vez de 100 cenários únicos.

Uso:
    python scripts/run_long_ptbr_refinement_loop.py --hours 3 --batch-size 100 --dry-run
    APPLY_REFINEMENTS=1 python scripts/run_long_ptbr_refinement_loop.py --hours 3 --batch-size 100

Exit codes:
    0 = critérios de aceite atingidos
    1 = stopped early (falhas críticas) ou critérios não atingidos
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import random

# Adiciona projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from refrimix_core.evaluation.conversation_simulator import simulate_conversation
from refrimix_core.evaluation.scenario_generator import generate_scenarios


# ── métricas ───────────────────────────────────────────────────────────────────

@dataclass
class BatchMetrics:
    batch_index: int
    duration_seconds: float
    avg_score: float
    critical_failures: int = 0
    repeated_generic_fallback_count: int = 0
    generic_ask_basic_service_count: int = 0
    agenda_friction_failures: int = 0
    too_many_questions_count: int = 0
    price_invention_count: int = 0
    missing_electrical_shutdown_count: int = 0
    photo_blocking_count: int = 0
    name_blocking_count: int = 0
    pt_eu_terms_count: int = 0
    spanish_terms_count: int = 0
    audio_too_long_count: int = 0
    instagram_spam_count: int = 0

    def to_dict(self) -> dict:
        return {
            "batch_index": self.batch_index,
            "duration_seconds": round(self.duration_seconds, 1),
            "avg_score": round(self.avg_score, 3),
            "critical_failures": self.critical_failures,
            "repeated_generic_fallback_count": self.repeated_generic_fallback_count,
            "generic_ask_basic_service_count": self.generic_ask_basic_service_count,
            "agenda_friction_failures": self.agenda_friction_failures,
            "too_many_questions_count": self.too_many_questions_count,
            "price_invention_count": self.price_invention_count,
            "missing_electrical_shutdown_count": self.missing_electrical_shutdown_count,
            "photo_blocking_count": self.photo_blocking_count,
            "name_blocking_count": self.name_blocking_count,
            "pt_eu_terms_count": self.pt_eu_terms_count,
            "spanish_terms_count": self.spanish_terms_count,
            "audio_too_long_count": self.audio_too_long_count,
            "instagram_spam_count": self.instagram_spam_count,
        }


# ── detecção de falhas ─────────────────────────────────────────────────────────

FORBIDDEN_RESPONSE = "Entendi.\n\nIsso é installation, manutenção, higienização ou conserto?"
ASK_BASIC_SERVICE_PATTERNS = [
    "Entendi.\n\nIsso é instalação",
    "Entendi.\n\nIsso é manutenção",
    "Entendi.\n\nIsso é higienização",
    "Entendi.\n\nIsso é conserto",
    "Isso é instalação, manutenção",
]

ROUTE_FAILURE_TYPES = {
    "generic_ask_basic_service",
    "repeated_generic_fallback",
    "unknown_for_clear_intent",
    "wrong_service_route",
}

CONTENT_FAILURE_TYPES = {
    "inventou_preco",
    "diagnostico_definitivo",
    "nao_orienta_desligar_em_risco_eletrico",
    "como_posso_ajudar_depois_cliente_explicar",
    "too_many_questions",
    "agenda_friction",
    "photo_blocking",
    "name_blocking",
    "tone_too_robotic",
    "price_invention_count",
    "missing_electrical_shutdown_count",
    "pt_eu_terms_count",
    "spanish_terms_count",
    "audio_too_long_count",
    "instagram_spam_count",
}


def detect_failures(scenario, conversation_result) -> dict[str, int]:
    """Detecta tipos específicos de falha na conversa."""
    failures = conversation_result.overall_failures or []
    all_responses = [t.message for t in conversation_result.turns if t.role == "assistant"]

    counts = {
        "repeated_generic_fallback_count": 0,
        "generic_ask_basic_service_count": 0,
        "agenda_friction_failures": 0,
        "too_many_questions_count": 0,
        "price_invention_count": 0,
        "missing_electrical_shutdown_count": 0,
        "photo_blocking_count": 0,
        "name_blocking_count": 0,
        "pt_eu_terms_count": 0,
        "spanish_terms_count": 0,
        "audio_too_long_count": 0,
        "instagram_spam_count": 0,
    }

    # Detecta ask_basic_service repetido
    for resp in all_responses:
        for pattern in ASK_BASIC_SERVICE_PATTERNS:
            if pattern in resp:
                counts["generic_ask_basic_service_count"] += 1
                break

    # Detecta resposta repetida pro mesmo lead
    seen = {}
    for resp in all_responses:
        normalized = resp.strip()[:50]
        if normalized in seen:
            counts["repeated_generic_fallback_count"] += 1
        seen[normalized] = True

    # Falhas da rubric
    for f in failures:
        if f in counts:
            counts[f] += 1
        if f in ROUTE_FAILURE_TYPES:
            counts[f] = counts.get(f, 0) + 1
        elif f in CONTENT_FAILURE_TYPES:
            counts["content_failures"] = counts.get("content_failures", 0) + 1

    # Detecta terms proibidos
    pt_eu_terms = ["contactar", "morada", "telefone", "contacto"]
    spanish_terms = ["hola", "gracias", "cuánto cuesta", "buenos días"]
    for resp in all_responses:
        lower = resp.lower()
        for term in pt_eu_terms:
            if term in lower:
                counts["pt_eu_terms_count"] += 1
        for term in spanish_terms:
            if term in lower:
                counts["spanish_terms_count"] += 1

    # Risco elétrico sem orientação de desligar
    if scenario.category == "risco_eletrico":
        has_shutdown = any("deslig" in r.lower() or " desligue" in r.lower() for r in all_responses)
        if not has_shutdown:
            counts["missing_electrical_shutdown_count"] += 1

    return counts


# ── loop principal ────────────────────────────────────────────────────────────

def run_long_loop(
    hours: int = 3,
    batch_size: int = 100,
    seed: int = 42,
    dry_run: bool = True,
    focus: str = "ptbr_chat_sales",
) -> dict:
    """
    Executa loop longo por `hours` com batches de `batch_size`.
    Para cada batch: detecta falhas, verifica stop criteria.
    """
    apply_refinements = os.getenv("APPLY_REFINEMENTS", "0") == "1"
    if apply_refinements and not dry_run:
        print("⚠️  APPLY_REFINEMENTS=1 — applying mutations")

    end_time = datetime.now() + timedelta(hours=hours)
    random.seed(seed)

    batches: list[BatchMetrics] = []
    zero_critical_streak = 0
    stop_reason = ""

    print("\n🔄 Long PT-BR Loop iniciado")
    print(f"   Duração: {hours}h | Batch size: {batch_size} | Seed: {seed}")
    print(f"   Dry-run: {dry_run} | Apply: {apply_refinements}")
    print(f"   Ends at: {end_time.strftime('%H:%M:%S')}\n")

    batch_idx = 0
    while datetime.now() < end_time:
        batch_idx += 1
        batch_start = time.time()

        # Gera cenários
        scenarios = generate_scenarios(batch_size, seed=seed + batch_idx)
        random.shuffle(scenarios)

        # Para cada cenário, roda simulação
        total_score = 0.0
        all_failures: list[str] = []

        for scenario in scenarios:
            result = simulate_conversation(scenario)
            total_score += result.final_score
            all_failures.extend(result.overall_failures or [])

        avg_score = total_score / len(scenarios)
        batch_duration = time.time() - batch_start

        # Detecta falhas de roteamento
        route_failures = sum(
            1 for f in all_failures if f in ROUTE_FAILURE_TYPES
        )
        content_failures_total = sum(
            1 for f in all_failures if f in CONTENT_FAILURE_TYPES
        )

        metrics = BatchMetrics(
            batch_index=batch_idx,
            duration_seconds=batch_duration,
            avg_score=avg_score,
            critical_failures=route_failures,
        )

        # Detectar falhas específicas por cenário
        for scenario in scenarios:
            result = simulate_conversation(scenario)
            counts = detect_failures(scenario, result)
            for k, v in counts.items():
                if hasattr(metrics, k):
                    setattr(metrics, k, getattr(metrics, k) + v)

        batches.append(metrics)

        print(
            f"  Batch {batch_idx:3d} | "
            f"score: {avg_score:.3f} | "
            f"route_fail: {route_failures} | "
            f"ask_basic: {metrics.generic_ask_basic_service_count} | "
            f"fallback_rep: {metrics.repeated_generic_fallback_count} | "
            f"content_fail: {content_failures_total} | "
            f"{batch_duration:.1f}s"
        )

        # Verifica stop criteria — Routing Gate (Phase 2.10)
        # Content Quality é Phase 2.11, não bloqueia aqui
        routing_approved = (
            metrics.generic_ask_basic_service_count == 0
            and metrics.repeated_generic_fallback_count == 0
            and route_failures == 0
        )
        if routing_approved and avg_score >= 4.0:
            zero_critical_streak += 1
        else:
            zero_critical_streak = 0

        stop_reason = None
        if zero_critical_streak >= 3:
            stop_reason = f"Routing Gate approved (3 batches, score>={avg_score:.3f}, streak={zero_critical_streak})"
        elif routing_approved and avg_score >= 4.0:
            stop_reason = f"Routing Gate approved (score={avg_score:.3f}, route_fail={route_failures})"

        if stop_reason:
            print(f"\n✅ Stop criteria met: {stop_reason}")
            break

    # Calcula relatório final
    total_batches = len(batches)
    avg_scores = [b.avg_score for b in batches]
    final_avg = sum(avg_scores) / len(avg_scores) if avg_scores else 0.0
    total_critical = sum(b.critical_failures for b in batches)
    total_ask_basic = sum(b.generic_ask_basic_service_count for b in batches)
    total_fallback_rep = sum(b.repeated_generic_fallback_count for b in batches)

    report = {
        "hours_run": hours,
        "batches": total_batches,
        "final_avg_score": round(final_avg, 3),
        "total_critical_failures": total_critical,
        "total_ask_basic_service": total_ask_basic,
        "total_repeated_fallback": total_fallback_rep,
        "stop_reason": stop_reason or "time limit reached",
        "batches_data": [b.to_dict() for b in batches],
    }

    return report


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Long PT-BR Refinement Loop — Phase 2.10 (Routing) / Phase 2.11 (Content)",
    )
    parser.add_argument("--hours", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--focus", default="ptbr_chat_sales")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument(
        "--export-samples",
        default="",
        help="Path para salvar amostras de falhas de conteúdo (Phase 2.11)",
    )

    args = parser.parse_args()

    # dry-run default, apply only with APPLY_REFINEMENTS=1
    dry_run = os.getenv("APPLY_REFINEMENTS", "0") != "1"

    print("=" * 60)
    print("Long PT-BR Refinement Loop")
    print("  Phase 2.10: Routing Gate (bloqueante)")
    print("  Phase 2.11: Content Quality Gate (não bloqueia)")
    print("=" * 60)
    print(f"  Horas: {args.hours}")
    print(f"  Batch size: {args.batch_size}")
    print(f"  Seed: {args.seed}")
    print(f"  Focus: {args.focus}")
    print(f"  Dry-run: {dry_run}")
    if args.export_samples:
        print(f"  Export samples: {args.export_samples}")
    print("=" * 60)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True)

    report = run_long_loop(
        hours=args.hours,
        batch_size=args.batch_size,
        seed=args.seed,
        dry_run=dry_run,
        focus=args.focus,
    )

    # CalculaRouting Gate totals
    total_route_failures = sum(
        b.get("critical_failures", 0) for b in report["batches_data"]
    )
    total_ask_basic = sum(
        b.get("generic_ask_basic_service_count", 0) for b in report["batches_data"]
    )
    total_fallback_rep = sum(
        b.get("repeated_generic_fallback_count", 0) for b in report["batches_data"]
    )

    # Salva relatório com dois gates
    report_path = report_dir / f"long_ptbr_refinement_{ts}.md"

    routing_pass = (
        total_route_failures == 0
        and total_ask_basic == 0
        and total_fallback_rep == 0
    )
    content_score = report["final_avg_score"]

    lines = [
        f"# Long PT-BR Refinement Report — {ts}",
        f"",
        f"**Horas:** {report['hours_run']}h",
        f"**Batches:** {report['batches']}",
        f"",
        f"## Gate 1 — Routing (Phase 2.10)",
        f"",
        f"| Métrica | Valor | Gate |",
        f"|---------|-------|------|",
        f"| route_failures | {total_route_failures} | {'✅' if total_route_failures == 0 else '❌'} |",
        f"| ask_basic_service | {total_ask_basic} | {'✅' if total_ask_basic == 0 else '❌'} |",
        f"| repeated_fallback | {total_fallback_rep} | {'✅' if total_fallback_rep == 0 else '❌'} |",
        f"",
        f"**Routing Gate: {'✅ APROVADO' if routing_pass else '❌ REPROVADO'}**",
        f"",
        f"## Gate 2 — Content Quality (Phase 2.11)",
        f"",
        f"| Métrica | Valor |",
        f"|---------|-------|",
        f"| content_score | {content_score:.3f} |",
        f"",
        f"**Nota:** Content Quality não bloqueia Phase 2.10. Amostras em: {args.export_samples or 'não exportado'}",
        f"",
        f"## Stop reason: {report['stop_reason']}",
        f"",
        f"## Batches",
        f"",
        f"| Batch | Score | RouteFail | AskBasic | FallbackRep | ContentFail | Duração |",
        f"|-------|-------|-----------|----------|-------------|-------------|---------|",
    ]
    for b in report["batches_data"]:
        lines.append(
            f"| {b['batch_index']} | {b['avg_score']:.3f} | "
            f"{b['critical_failures']} | {b['generic_ask_basic_service_count']} | "
            f"{b['repeated_generic_fallback_count']} | "
            f"{b.get('content_failures', '-')} | "
            f"{b['duration_seconds']:.1f}s |"
        )

    report_path.write_text("\n".join(lines))
    print(f"\n📄 Relatório: {report_path}")

    # Critérios de aceite — Routing Gate (Phase 2.10)
    print(f"\n{'='*50}")
    print("Phase 2.10 — Routing Gate")
    print(f"{'='*50}")
    print(f"  {'✅' if total_route_failures == 0 else '❌'} route_failures: {total_route_failures}")
    print(f"  {'✅' if total_ask_basic == 0 else '❌'} ask_basic_service: {total_ask_basic}")
    print(f"  {'✅' if total_fallback_rep == 0 else '❌'} repeated_fallback: {total_fallback_rep}")
    print(f"  {'✅' if routing_pass else '❌'} Routing Gate: {'APROVADO' if routing_pass else 'REPROVADO'}")

    print(f"\n{'='*50}")
    print("Phase 2.11 — Content Quality (não bloqueia)")
    print(f"{'='*50}")
    print(f"  content_score: {content_score:.3f} (meta: 4.6)")

    sys.exit(0 if routing_pass else 1)


if __name__ == "__main__":
    main()