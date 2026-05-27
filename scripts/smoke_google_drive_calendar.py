#!/usr/bin/env python3
"""
Smoke Test — Google Drive + Calendar Integration

Uso:
    # DRY-RUN (padrão — não toca API real)
    python scripts/smoke_google_drive_calendar.py

    # LIVE (requer confirmação explícita)
    GOOGLE_INTEGRATION_DRY_RUN=0 CONFIRM_GOOGLE_LIVE_TEST=1 \\
        python scripts/smoke_google_drive_calendar.py

    # LIVE com cleanup automático
    GOOGLE_INTEGRATION_DRY_RUN=0 CONFIRM_GOOGLE_LIVE_TEST=1 GOOGLE_SMOKE_CLEANUP=1 \\
        python scripts/smoke_google_drive_calendar.py

Regras:
- DRY_RUN=1 (default): simula sem chamar API real
- DRY_RUN=0 + CONFIRM_GOOGLE_LIVE_TEST=1: executa real
- Sandbox: pasta 99_SANDBOX_HERMES_TESTES
- Eventos começam com [TESTE HERMES]
- Nunca envia PDF por WhatsApp
- Nunca commita credenciais ou tokens
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Adiciona o diretório do projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from refrimix_core.tools.google_integration_smoke import run_full_smoke

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("smoke")


def main():
    dry_run = os.getenv("GOOGLE_INTEGRATION_DRY_RUN", "1") == "1"
    confirm = os.getenv("CONFIRM_GOOGLE_LIVE_TEST", "0") == "1"

    print()
    print("╔" + "═" * 58 + "╗")
    print("║" + " Google Drive + Calendar Smoke Test ".center(58) + "║")
    print("╚" + "═" * 58 + "╝")
    print()

    if dry_run:
        print("┌ Modo: DRY-RUN (simulação, sem chamadas reais à API) ─────────┐")
        print("│  GOOGLE_INTEGRATION_DRY_RUN=1                               │")
        print("└──────────────────────────────────────────────────────────────┘")
        print()
        print("Para executar teste real, configure:")
        print("  GOOGLE_INTEGRATION_DRY_RUN=0 CONFIRM_GOOGLE_LIVE_TEST=1")
        print()
    else:
        if not confirm:
            print("╔ AVISO ════════════════════════════════════════════════════╗")
            print("║                                                              ║")
            print("║  Você está prestes a executar um TESTE REAL no Google       ║")
            print("║  Drive e Calendar da Refrimix.                              ║")
            print("║                                                              ║")
            print("║  Para confirmar, execute com:                                ║")
            print("║    GOOGLE_INTEGRATION_DRY_RUN=0 CONFIRM_GOOGLE_LIVE_TEST=1  ║")
            print("║                                                              ║")
            print("╚═══════════════════════════════════════════════════════════╝")
            print()
            print("Abortando. Execute em modo DRY-RUN ou confirme.")
            sys.exit(1)

        print("┌ Modo: LIVE (chamadas reais à API) ───────────────────────────┐")
        print("│  GOOGLE_INTEGRATION_DRY_RUN=0 + CONFIRM_GOOGLE_LIVE_TEST=1    │")
        print("└──────────────────────────────────────────────────────────────┘")
        print()
        print("⚠  ATENÇÃO: Isto vai criar arquivos no Google Drive da Refrimix.")
        print()
        response = input("Continuar? (digite 'SIM' para confirmar): ").strip()
        if response != "SIM":
            print("Abortado pelo usuário.")
            sys.exit(1)

    # Executa smoke
    result = run_full_smoke()

    print()
    if result["success"]:
        print("✅ SMOKE PASS — Drive + Calendar integrados com sucesso.")
        sys.exit(0)
    else:
        print("❌ SMOKE FAIL — Verifique os erros acima.")
        sys.exit(1)


if __name__ == "__main__":
    main()
