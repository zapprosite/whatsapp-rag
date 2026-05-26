from __future__ import annotations

import logging
import os
from typing import Any

from agent_graph.services.google_sheets import sync_lead_row_to_sheet

logger = logging.getLogger(__name__)


async def sync_lead_sheet(state: dict[str, Any]) -> dict[str, Any]:
    if os.getenv("LEADS_SHEET_ENABLED", "0") != "1":
        return {}
    try:
        await sync_lead_row_to_sheet(
            {
                "phone": (state.get("customer_data") or {}).get("phone"),
                "lead_state": state.get("lead_state") or {},
                "next_action": state.get("next_action") or {},
            }
        )
    except Exception as exc:
        logger.warning("Falha ao sincronizar lead sheet: %s", exc)
    return {}
