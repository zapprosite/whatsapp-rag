#!/usr/bin/env python3
"""
Assisted Pilot Report — CLI para gerar relatório do piloto assistido.

Uso:
    python scripts/run_assisted_pilot_report.py
    python scripts/run_assisted_pilot_report.py --min-conversations 30
    python scripts/run_assisted_pilot_report.py --min-conversations 30 \
        --output reports/assisted_pilot_20260527.json
    python scripts/run_assisted_pilot_report.py --output reports/pilot.json --open
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from refrimix_core.monitoring.assisted_pilot_report import generate_report


def main():
    parser = argparse.ArgumentParser(
        description="Assisted Pilot Report — consolida métricas do piloto assistido",
    )
    parser.add_argument(
        "--min-conversations",
        type=int,
        default=int(os.getenv("BOT_PILOT_MIN_CONVERSATIONS", "30")),
        help="Mínimo de conversas para relatório válido (default: 30)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Caminho do arquivo JSON de saída "
        "(default: reports/assisted_pilot_YYYYMMDD_HHMMSS.json)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Abrir relatório Markdown gerado após o JSON",
    )
    parser.add_argument(
        "--reports-dir",
        default="reports",
        help="Diretório para relatórios (default: reports)",
    )
    args = parser.parse_args()

    # Default output path
    if args.output is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output = os.path.join(
            args.reports_dir, f"assisted_pilot_{timestamp}.json"
        )

    print("=" * 60)
    print("Assisted Pilot Report — Phase 2.9")
    print("=" * 60)

    result = generate_report(
        min_conversations=args.min_conversations,
        output_json=args.output,
        reports_dir=args.reports_dir,
    )

    # Print summary to stdout
    d = result
    crit = d["canary_criteria"]
    vol = d["volume"]
    rates = d["rates"]

    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"  Conversas reais:          {vol['total_conversations']}")
    print(f"  Review Items:            {vol['total_review_items']}")
    print(f"  Approval rate:           {rates['approval_without_edit_rate']:.1%}")
    print(f"  Edit rate:               {rates['edit_rate']:.1%}")
    print(f"  Reject rate:             {rates['reject_rate']:.1%}")
    print(f"  Expire rate:             {rates['expire_rate']:.1%}")
    print(f"  Appointment offer rate:  {d['appointments']['appointment_offer_rate']:.1%}")
    print(f"  Appointment scheduled:   {d['appointments']['appointment_scheduled_rate']:.1%}")
    print(f"  Human handoff rate:      {d['appointments']['human_handoff_rate']:.1%}")
    print(f"  WhatsApp sent:           {d['whatsapp_status']['status_sent']}")
    print(f"  WhatsApp delivered:      {d['whatsapp_status']['status_delivered']}")
    print(f"  WhatsApp read:           {d['whatsapp_status']['status_read']}")
    print(f"  WhatsApp failed:         {d['whatsapp_status']['status_failed']}")

    print("\nCritérios Canary:")
    checks = [
        ("Conversas >= 30", crit["meets_min_conversations"]),
        ("Approval rate >= 70%", crit["canary_approval_enough"]),
        ("Reject rate <= 10%", crit["canary_reject_acceptable"]),
        ("Zero falhas críticas", crit["zero_critical_failures"]),
        ("Risco elétrico OK", crit["risco_eletrico_safe"]),
        ("Documentos OK", crit["documentos_safe"]),
        ("Refinement loop feito", crit["refinement_loop_done"]),
    ]
    for nome, passou in checks:
        status = "✅" if passou else "❌"
        print(f"  {status} {nome}")

    print("\nRecomendação:")
    if crit["canary_recommended"]:
        print("  ✅ Liberar CANARY_PERCENT=10")
    elif not crit["meets_min_conversations"]:
        print(f"  ⏳ Aguardando mais conversas ({vol['total_conversations']}/{crit['min_conversations_required']})")
    elif not crit["canary_approval_enough"]:
        print(f"  ⚠️ Permanecer em ASSISTED — approval {rates['approval_without_edit_rate']:.1%} < 70%")
    elif not crit["canary_reject_acceptable"]:
        print(f"  ⚠️ Permanecer em ASSISTED — reject {rates['reject_rate']:.1%} > 10%")
    else:
        print("  ⚠️ Permanecer em ASSISTED — falhas críticas ou refinement incompleto")

    print(f"\n📄JSON: {args.output}")

    md_auto = str(Path(args.output).with_suffix(".md"))
    if Path(md_auto).exists():
        print(f"📄 Markdown: {md_auto}")
    if args.open:
        import webbrowser
        webbrowser.open(f"file://{Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
