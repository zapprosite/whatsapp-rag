from __future__ import annotations

import asyncio

import agent_graph.nodes.nodes as nodes


def test_rag_layers_relax_filters_until_enough_context(monkeypatch):
    calls = []

    def fake_search(query, service, top_k, *, segment_market=None, segment_tier=None, goal=None, stage=None):
        calls.append(
            {
                "query": query,
                "service": service,
                "segment_market": segment_market,
                "segment_tier": segment_tier,
                "goal": goal,
                "stage": stage,
            }
        )
        if len(calls) == 1:
            return [{"id": "forte-1", "payload": {"text": "regra forte"}}]
        if len(calls) == 2:
            return [{"id": "servico-goal-1", "payload": {"text": "regra serviço objetivo"}}]
        return [{"id": "servico-1", "payload": {"text": "regra serviço"}}]

    monkeypatch.setattr(nodes, "_qdrant_search_with_filters", fake_search)

    result = asyncio.run(
        nodes._search_rag_layers(
            "query desambiguada",
            "quanto fica?",
            "instalacao",
            segment_market="residential",
            segment_tier="common",
            goal="qualify_quote",
            stage="qualification",
            top_k=5,
        )
    )

    assert [item["id"] for item in result] == ["forte-1", "servico-goal-1", "servico-1"]
    assert calls[0]["segment_market"] == "residential"
    assert calls[0]["stage"] == "qualification"
    assert calls[1]["segment_market"] is None
    assert calls[1]["goal"] == "qualify_quote"
    assert calls[2]["service"] == "instalacao"
    assert calls[2]["goal"] is None
