#!/usr/bin/env python3
"""Exporta casos reais anonimizados para alimentar o loop de refinamento Phase 2.5.

Uso:
    python scripts/export_real_cases_to_refinement_loop.py
    python scripts/export_real_cases_to_refinement_loop.py --min-cases 30 --output reports/real_cases_YYYYMMDD.jsonl
"""

import argparse
import os
import sys
from datetime import datetime

# Adiciona o diretório do projeto ao path para imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from refrimix_core.evaluation.real_case_exporter import RealCaseExporter
from refrimix_core.monitoring.production_feedback import ProductionFeedbackStore
from refrimix_core.monitoring.lead_outcome_tracker import LeadOutcomeTracker


def main():
    parser = argparse.ArgumentParser(
        description="Exporta casos reais anonimizados para o loop de refinamento.",
    )
    parser.add_argument(
        "--min-cases",
        type=int,
        default=int(os.getenv("BOT_FEEDBACK_EXPORT_MIN_CASES", "30")),
        help="Número mínimo de casos para exportar (default: 30)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Caminho do arquivo de saída (default: reports/real_cases_YYYYMMDD_HHMMSS.jsonl)",
    )
    args = parser.parse_args()

    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        reports_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "reports",
        )
        os.makedirs(reports_dir, exist_ok=True)
        args.output = os.path.join(reports_dir, f"real_cases_{timestamp}.jsonl")

    # Em produção, substituir por conexão real ao banco de dados
    feedback_store = ProductionFeedbackStore()
    outcome_tracker = LeadOutcomeTracker()

    exporter = RealCaseExporter()
    dataset = exporter.export_real_cases(
        feedback_store=feedback_store,
        outcome_tracker=outcome_tracker,
        min_cases=args.min_cases,
    )

    if not dataset:
        print(f"Nenhum caso real disponível para exportar (mínimo: {args.min_cases}).")
        print("Execute o bot em produção para收集 mais casos.")
        sys.exit(0)

    count = exporter.export_to_jsonl(dataset, args.output)
    print(f"Exportados {count} casos anonimizados para: {args.output}")
    print(f"Telefone, nome e endereço foram mascarados.")
    print(f"Para usar no loop de refinamento, mescle ao arquivo de cenários.")


if __name__ == "__main__":
    main()