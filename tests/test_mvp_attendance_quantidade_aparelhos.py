from __future__ import annotations

import asyncio
import os
from unittest.mock import MagicMock

from agent_graph.nodes.reduce_lead_state import reduce_lead_state
from agent_graph.nodes.plan_next_action import plan_next_action
from agent_graph.nodes.nodes import _lead_state_copy
from agent_graph.services.tts import should_respond_with_audio


def run(coro):
    return asyncio.run(coro)


def test_reduce_lead_state_quantidade_aparelhos_number():
    # Test number string "1"
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "higienizacao"
    lead_state["last_asked_field"] = "quantidade_aparelhos"

    result = run(
        reduce_lead_state(
            {
                "lead_state": lead_state,
                "messages": [MagicMock(content="1")],
                "message_understanding": {"kind": "unknown"},
                "message_type": "conversation",
                "customer_data": {},
            }
        )
    )

    assert result["lead_state"]["higienizacao"]["quantidade_aparelhos"] == 1
    assert result["short_answer_applied"] is True

    # Test word string "um"
    lead_state_2 = _lead_state_copy()
    lead_state_2["tipo_servico"] = "higienizacao"
    lead_state_2["last_asked_field"] = "quantidade_aparelhos"

    result_2 = run(
        reduce_lead_state(
            {
                "lead_state": lead_state_2,
                "messages": [MagicMock(content="um")],
                "message_understanding": {"kind": "unknown"},
                "message_type": "conversation",
                "customer_data": {},
            }
        )
    )

    assert result_2["lead_state"]["higienizacao"]["quantidade_aparelhos"] == 1
    assert result_2["short_answer_applied"] is True

    # Test longer string with number "3 aparelhos"
    lead_state_3 = _lead_state_copy()
    lead_state_3["tipo_servico"] = "higienizacao"
    lead_state_3["last_asked_field"] = "quantidade_aparelhos"

    result_3 = run(
        reduce_lead_state(
            {
                "lead_state": lead_state_3,
                "messages": [MagicMock(content="são 3 aparelhos split")],
                "message_understanding": {"kind": "unknown"},
                "message_type": "conversation",
                "customer_data": {},
            }
        )
    )

    assert result_3["lead_state"]["higienizacao"]["quantidade_aparelhos"] == 3
    assert result_3["short_answer_applied"] is True


def test_plan_next_action_hygienization_routing():
    # When quantidade_aparelhos is missing, should ask for it
    lead_state = _lead_state_copy()
    lead_state["nome"] = "João"
    lead_state["tipo_servico"] = "higienizacao"
    lead_state["cidade_bairro"] = "São Paulo"

    result = run(
        plan_next_action(
            {
                "lead_state": lead_state,
                "message_understanding": {"kind": "answer_question"},
                "messages": [],
            }
        )
    )

    action = result.get("next_action") or {}
    assert action.get("type") == "offer_fixed_hygienization"
    assert action.get("asks_field") == "quantidade_aparelhos"

    # When quantidade_aparelhos is satisfied, should ask for window / schedule
    lead_state_satisfied = _lead_state_copy()
    lead_state_satisfied["nome"] = "João"
    lead_state_satisfied["tipo_servico"] = "higienizacao"
    lead_state_satisfied["cidade_bairro"] = "São Paulo"
    lead_state_satisfied.setdefault("higienizacao", {})["quantidade_aparelhos"] = 2

    result_sat = run(
        plan_next_action(
            {
                "lead_state": lead_state_satisfied,
                "message_understanding": {"kind": "answer_question"},
                "messages": [],
            }
        )
    )

    action_sat = result_sat.get("next_action") or {}
    assert action_sat.get("type") == "offer_hygienization_schedule"
    assert action_sat.get("asks_field") == "preferred_window"


def test_should_respond_with_audio_respects_tts_enabled():
    # TTS_ENABLED = 0 -> should not respond with audio
    os.environ["TTS_ENABLED"] = "0"
    assert should_respond_with_audio("audioMessage", None, None) is False

    # TTS_ENABLED = 1 -> should respond with audio for audioMessage
    os.environ["TTS_ENABLED"] = "1"
    assert should_respond_with_audio("audioMessage", None, None) is True
    assert should_respond_with_audio("conversation", None, None) is False
