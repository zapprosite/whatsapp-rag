from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph.nodes.nodes as nodes


def run(coro):
    return asyncio.run(coro)


def base_state(text: str) -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content=text)],
        "intent": None,
        "service": None,
        "outcome": None,
        "handoff_mode": "none",
        "handoff_reason": None,
        "handoff_already_notified": False,
        "rag_context": [],
        "customer_data": {"phone": "5513999999999"},
        "is_human": False,
        "confidence": 1.0,
        "message_type": "conversation",
        "msg_id": "",
        "media_url": "",
        "media_base64": "",
        "instance": "test",
        "response_modality": None,
        "audio_bytes": None,
    }


def patch_classifier_llm(monkeypatch, label: str = "unknown") -> None:
    async def fake_qwen(messages: list[dict[str, str]], max_retries: int = 2) -> str:
        return label

    monkeypatch.setattr(nodes, "_call_local_qwen", fake_qwen)


def test_high_value_vrf_owner_alert(monkeypatch):
    patch_classifier_llm(monkeypatch)

    result = run(nodes.classify_service(base_state("preciso de VRF para prédio comercial")))

    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"] in {"high_value_vrf", "high_value_lead"}
    assert result["service"] == "projeto-central"


def test_high_value_duto_owner_alert(monkeypatch):
    patch_classifier_llm(monkeypatch)

    result = run(nodes.classify_service(base_state("projeto de duto para restaurante")))

    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"] == "high_value_duto"
    assert result["service"] in {"projeto-central", "consultoria"}


def test_splitao_owner_alert(monkeypatch):
    patch_classifier_llm(monkeypatch)

    result = run(nodes.classify_service(base_state("tenho um splitão de 60000 BTUs")))

    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"] == "high_value_splitao"


def test_pmoc_owner_alert(monkeypatch):
    patch_classifier_llm(monkeypatch)

    result = run(nodes.classify_service(base_state("preciso de PMOC com ART")))

    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"] == "high_value_pmoc"


def test_restaurant_vrf_pmoc_prefers_project_over_installation(monkeypatch):
    patch_classifier_llm(monkeypatch, "instalacao")

    result = run(nodes.classify_service(base_state("Tenho um restaurante e preciso ver VRF com PMOC")))

    assert result["service"] == "projeto-central"
    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"] in {"high_value_vrf", "high_value_pmoc", "high_value_lead"}


def test_regular_higienizacao_no_owner_high_value(monkeypatch):
    patch_classifier_llm(monkeypatch, "higienizacao")

    result = run(nodes.classify_service(base_state("quero limpar um split")))

    assert result["service"] == "higienizacao"
    assert not str(result["handoff_reason"] or "").startswith("high_value")


def test_owner_alert_dedup(monkeypatch):
    from app import worker

    class FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
            if nx and key in self.store:
                return None
            self.store[key] = value
            return True

    sent: list[dict[str, Any]] = []

    async def fake_notify_owner(lead_phone: str, lead_message: str, instance: str = "default", **kwargs: Any) -> bool:
        sent.append({"lead_phone": lead_phone, **kwargs})
        return True

    monkeypatch.setattr(worker, "notify_owner", fake_notify_owner)
    result = {
        "handoff_mode": "soft_alert",
        "handoff_reason": "high_value_vrf",
        "messages": [HumanMessage(content="VRF"), AIMessage(content="Me passa a cidade?")],
    }
    r = FakeRedis()

    first = run(worker.maybe_notify_owner_from_result(r, phone="5513999999999", message_text="VRF", result=result, instance="test"))
    second = run(worker.maybe_notify_owner_from_result(r, phone="5513999999999", message_text="VRF", result=result, instance="test"))

    assert first is True
    assert second is False
    assert len(sent) == 1
    assert "assumir" in sent[0]["next_step"].lower()
