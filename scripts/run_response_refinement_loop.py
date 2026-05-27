#!/usr/bin/env python3
"""
run_response_refinement_loop.py

Uso:
    python scripts/run_response_refinement_loop.py --count 100 --dry-run
    APPLY_REFINEMENTS=1 python scripts/run_response_refinement_loop.py --count 100

Default: dry-run (não aplica mudanças).
Com APPLY_REFINEMENTS=1: aplica mudanças nos arquivos permitidos.

Relatório salvo em:
    reports/response_refinement_YYYYMMDD_HHMM.md
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Adiciona raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from refrimix_core.evaluation.response_refinement_loop import ResponseRefinementLoop


def main():
    parser = argparse.ArgumentParser(
        description="Response Refinement Loop — 100 simulações de leads brasileiros",
    )
    parser.add_argument(
        "--count", "-n", type=int, default=100,
        help="Número de cenários (default: 100)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="Não aplica mudanças (default: True)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Seed para reprodutibilidade (default: 42)",
    )
    parser.add_argument(
        "--output-dir", default="reports",
        help="Diretório para relatórios (default: reports)",
    )
    parser.add_argument(
        "--save-scenarios", action="store_true",
        help="Salvar cenários em JSONL",
    )

    args = parser.parse_args()

    # Verifica APPLY_REFINEMENTS
    apply_refinements = os.getenv("APPLY_REFINEMENTS", "0") == "1"
    dry_run = not apply_refinements

    print("=" * 60)
    print("Response Refinement Loop — Refrimix HVAC-R")
    print("=" * 60)
    print(f"  Cenários: {args.count}")
    print(f"  Dry-run: {dry_run}")
    print(f"  Seed: {args.seed}")
    print(f"  Output: {args.output_dir}")
    print(f"  Salvar cenários: {args.save_scenarios}")
    print("=" * 60)

    # Cria diretório de reports
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    # Executa loop
    loop = ResponseRefinementLoop(output_dir=str(output_dir))
    report = loop.run(
        count=args.count,
        dry_run=dry_run,
        seed=args.seed,
        save_scenarios=args.save_scenarios,
    )

    # Salva relatório
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"response_refinement_{timestamp}.md"
    report.save(str(report_path))

    print(f"\n📄 Relatório salvo: {report_path}")

    # Resumo
    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"  Score médio final: {report.final_avg_score:.2f}/5.0")
    print(f"  Score médio antes: {report.avg_score_before:.2f}/5.0")
    print(f"  Score médio depois: {report.avg_score_after:.2f}/5.0")
    print(f"  Mutacções aplicadas: {report.total_mutations}")
    print(f"  Falhas críticas: {report.critical_failures_count}")
    print(f"\nTop 5 falhas:")
    for i, (failure, count) in enumerate(report.top_failures[:5], 1):
        print(f"  {i}. {failure}: {count} ocorrências")

    print("\nCritérios de aceite:")
    criterios = [
        ("100 cenários gerados", report.total_scenarios >= 100),
        ("100 cenários avaliados", report.scenarios_evaluated >= 100),
        ("Top 20 falhas", len(report.top_failures) >= 20),
        ("Before/After presente", len(report.before_after_pairs) > 0),
        ("Score médio final >= 4.3", report.final_avg_score >= 4.3),
        ("Zero falhas críticas", report.critical_failures_count == 0),
    ]
    for nome, passou in criterios:
        status = "✅" if passou else "❌"
        print(f"  {status} {nome}")

    # Exit code baseado nos critérios
    all_passed = all(p for _, p in criterios)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()