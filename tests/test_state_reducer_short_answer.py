from __future__ import annotations

import asyncio

from agent_graph.nodes.reduce_lead_state import reduce_lead_state
from agent_graph.nodes.nodes import _lead_state_copy


def run(coro):
    return asyncio.run(coro)


def test_short_answer_updates_last_asked_field():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["last_asked_field"] = "ponto_eletrico_exclusivo"

    result = run(
        reduce_lead_state(
            {
                "lead_state": lead_state,
                "message_understanding": {"kind": "short_answer", "short_answer": "yes"},
                "message_type": "conversation",
                "customer_data": {},
            }
        )
    )

    assert result["lead_state"]["instalacao"]["ponto_eletrico_exclusivo"] is True
    assert result["short_answer_applied"] is True


def test_image_mismatch_does_not_mark_external_photo():
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["last_asked_field"] = "foto_local_externo"

    result = run(
        reduce_lead_state(
            {
                "lead_state": lead_state,
                "message_understanding": {"kind": "image_upload"},
                "message_type": "imageMessage",
                "vision_data": {"image_type": "local_interno_instalacao"},
                "customer_data": {},
            }
        )
    )

    fotos = result["lead_state"]["fotos"]
    assert fotos.get("local_externo") is not True
    assert result["lead_state"]["image_mismatch"]["expected"] == "foto_local_externo"
