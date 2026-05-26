from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph.nodes.nodes as nodes


def run(coro):
    return asyncio.run(coro)


def last_ai(messages: list[Any]) -> str:
    for m in reversed(messages):
        if isinstance(m, AIMessage):
            return str(m.content)
    return ""


def _no_bad_phrases(resp: str) -> None:
    assert "[áudio]" not in resp, f"Placeholder de áudio vazou: {resp!r}"
    assert "[imagem]" not in resp, f"Placeholder de imagem vazou: {resp!r}"
    assert "sinalizar o gerente" not in resp.lower(), f"Copy interna vazou: {resp!r}"
    assert "já tenho dados suficientes" not in resp.lower(), f"Copy prematura: {resp!r}"


def base_state(text: str, ls: dict | None = None) -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content=text)],
        "intent": "onboarding",
        "service": ls.get("tipo_servico") if ls else None,
        "outcome": "duvida",
        "handoff_mode": "none",
        "handoff_reason": None,
        "rag_context": [],
        "lead_state": ls or nodes._lead_state_copy(),
        "customer_data": {"phone": "+5513000000009"},
        "is_human": False,
        "message_type": "conversation",
        "msg_id": "",
        "media_url": "",
        "media_base64": "",
        "instance": "test",
        "missing_fields": ["tipo_servico", "cidade_bairro"],
        "do_not_ask": [],
        "already_asked_fields": [],
        "conversation_summary": "",
    }


def test_print_regression_full_flow(monkeypatch):
    """Reproduz exatamente a sequência do print: orçamento → manutenção → tarde → tarde."""

    async def fake_llm(*args, **kwargs):
        return "{}"

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_llm)

    # Turno 1: orçamento genérico → não deve ser high_value
    state1 = base_state("Boa noite. Gostaria de fazer um orçamento para o meu ar condicionado")
    result1 = run(nodes.generate_response(state1))
    resp1 = last_ai(result1["messages"])
    _no_bad_phrases(resp1)
    assert "esse caso é mais técnico" not in resp1.lower(), f"High-value prematuro: {resp1!r}"

    # Turno 2: manutenção pura → deve perguntar sintoma, não agendar
    ls2 = nodes._lead_state_copy()
    state2 = base_state("Manutenção", ls2)
    result2 = run(nodes.generate_response(state2))
    resp2 = last_ai(result2["messages"])
    _no_bad_phrases(resp2)
    ls2_out = result2.get("lead_state") or {}
    assert ls2_out.get("appointment_ready") is False, f"appointment_ready prematuro após 'Manutenção': {ls2_out}"
    assert "manhã ou tarde" not in resp2.lower(), f"Perguntou janela prematuramente: {resp2!r}"

    # Turno 3: cliente diz "Tarde" ainda sem dados mínimos → registra preferência mas não envia alerta
    ls3 = nodes._lead_state_copy()
    ls3["tipo_servico"] = "manutencao"
    state3 = base_state("Tarde", ls3)
    result3 = run(nodes.generate_response(state3))
    resp3 = last_ai(result3["messages"])
    _no_bad_phrases(resp3)
    assert "manhã ou tarde" not in resp3.lower(), f"Loop de janela no turno 3: {resp3!r}"

    # Turno 4: cliente diz "Tarde" de novo → não pode repetir a mesma pergunta
    ls4 = result3.get("lead_state") or nodes._lead_state_copy()
    ls4["tipo_servico"] = "manutencao"
    state4 = base_state("Tarde", ls4)
    result4 = run(nodes.generate_response(state4))
    resp4 = last_ai(result4["messages"])
    _no_bad_phrases(resp4)
    assert "manhã ou tarde" not in resp4.lower(), f"Loop de janela no turno 4: {resp4!r}"
