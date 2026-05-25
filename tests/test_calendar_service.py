from __future__ import annotations

import asyncio

from agent_graph.services.calendar import get_availability_summary


def test_calendar_disabled_returns_empty(monkeypatch):
    monkeypatch.setenv("GOOGLE_CALENDAR_ENABLED", "0")

    result = asyncio.run(get_availability_summary())

    assert result == ""
