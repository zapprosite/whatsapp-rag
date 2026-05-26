from __future__ import annotations

import os
from typing import Any


async def sync_lead_row_to_sheet(payload: dict[str, Any]) -> bool:
    del payload
    if os.getenv("LEADS_SHEET_ENABLED", "0") != "1":
        return False
    raise RuntimeError("Integração com Google Sheets ainda não configurada neste ambiente.")
