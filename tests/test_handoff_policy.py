from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

import agent_graph.graph.graph as graph_module
import agent_graph.nodes.nodes as nodes


def run(coro):
    return asyncio.run(coro)


def last_ai(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return str(message.content)
    return ""


def base_state(text: str, phone: str = "+5513000000000") -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content=text)],
        "intent": None,
        "service": None,
        "outcome": None,
        "handoff_mode": "none",
        "handoff_reason": None,
        "handoff_already_notified": False,
        "rag_context": [],
        "customer_data": {"phone": phone},
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


def test_classify_unknown_does_not_handoff(monkeypatch):
    patch_classifier_llm(monkeypatch, "unknown")

    result = run(nodes.classify_service(base_state("não sei explicar, meu ar tá estranho")))

    assert result["intent"] == "unknown"
    assert result["handoff_mode"] == "none"
    assert result["service"] is None


def test_classify_explicit_handoff_is_hard_transfer(monkeypatch):
    patch_classifier_llm(monkeypatch)

    result = run(nodes.classify_service(base_state("quero falar com atendente humano")))

    assert result["intent"] == "explicit_handoff"
    assert result["handoff_mode"] == "hard_transfer"
    assert result["handoff_reason"] == "explicit_handoff"


def test_classify_sensitive_complaint_is_hard_transfer(monkeypatch):
    patch_classifier_llm(monkeypatch)

    result = run(nodes.classify_service(base_state("fiz orçamento e ninguém retornou")))

    assert result["intent"] == "sensitive_complaint"
    assert result["handoff_mode"] == "hard_transfer"
    assert result["handoff_reason"] == "sensitive_complaint"


def test_classify_pmoc_high_value_is_soft_alert(monkeypatch):
    patch_classifier_llm(monkeypatch, "unknown")

    result = run(nodes.classify_service(base_state("tenho 12 aparelhos e preciso de PMOC")))

    assert result["intent"] == "pmoc"
    assert result["service"] == "pmoc"
    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"].startswith("high_value")


def test_classify_restaurant_central_system_is_soft_alert(monkeypatch):
    patch_classifier_llm(monkeypatch, "unknown")

    result = run(nodes.classify_service(base_state("restaurante com sistema central")))

    assert result["intent"] == "projeto-central"
    assert result["service"] == "projeto-central"
    assert result["handoff_mode"] == "soft_alert"


def build_patched_graph(monkeypatch, qdrant_calls: dict[str, int] | None = None):
    async def passthrough(state: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def text_modality(state: dict[str, Any]) -> dict[str, Any]:
        return {"response_modality": "text"}

    async def fake_llm(messages: list[dict[str, str]], max_retries: int = 2) -> str:
        return "Entendi. Consigo te ajudar com isso. Me passa a cidade e quantos aparelhos são?"

    def fake_qdrant(query: str, service_name: str | None, top_k: int = 5) -> list[dict[str, Any]]:
        if qdrant_calls is not None:
            qdrant_calls["count"] = qdrant_calls.get("count", 0) + 1
        return []

    async def fake_prisma(data: dict[str, Any]) -> None:
        return None

    async def fake_redis_get(key: str) -> str | None:
        return None

    async def fake_redis_set(key: str, value: str, ex: int | None = None) -> None:
        return None

    patch_classifier_llm(monkeypatch, "unknown")
    monkeypatch.setattr(nodes, "qdrant_search", fake_qdrant)
    monkeypatch.setattr(nodes, "llm_chat", fake_llm)
    monkeypatch.setattr(nodes, "prisma_save_interaction", fake_prisma)
    monkeypatch.setattr(nodes, "redis_get", fake_redis_get)
    monkeypatch.setattr(nodes, "redis_set", fake_redis_set)

    monkeypatch.setattr(graph_module, "language_guard_check", passthrough)
    monkeypatch.setattr(graph_module, "decide_response_modality", text_modality)
    monkeypatch.setattr(graph_module, "dispatch_appointment_alert", passthrough)

    return graph_module.build_graph()


def test_graph_unknown_retrieves_and_generates_recovery(monkeypatch):
    qdrant_calls: dict[str, int] = {}
    graph = build_patched_graph(monkeypatch, qdrant_calls)

    result = run(graph.ainvoke(base_state("não sei explicar, meu ar tá estranho")))
    response = last_ai(result["messages"])

    assert result["intent"] == "unknown"
    assert result["handoff_mode"] == "none"
    assert qdrant_calls["count"] >= 1
    assert "não gela" in response or "instalação, manutenção ou higienização" in response
    assert "especialista" not in response.lower()


def test_graph_soft_alert_keeps_normal_bot_response(monkeypatch):
    graph = build_patched_graph(monkeypatch)

    result = run(graph.ainvoke(base_state("tenho 12 aparelhos e preciso de PMOC")))
    response = last_ai(result["messages"])

    assert result["intent"] == "pmoc"
    assert result["handoff_mode"] == "soft_alert"
    assert response
    assert "passar" not in response.lower()


def test_hard_transfer_response_is_not_repeated(monkeypatch):
    store: dict[str, str] = {}

    async def fake_get(key: str) -> str | None:
        return store.get(key)

    async def fake_set(key: str, value: str, ex: int | None = None) -> None:
        store[key] = value

    monkeypatch.setattr(nodes, "redis_get", fake_get)
    monkeypatch.setattr(nodes, "redis_set", fake_set)

    state = base_state("quero falar com atendente humano")
    state.update({"intent": "explicit_handoff", "handoff_mode": "hard_transfer", "handoff_reason": "explicit_handoff"})

    first = run(nodes.route_human(state))
    second = run(nodes.route_human(state))

    assert first["handoff_already_notified"] is False
    assert second["handoff_already_notified"] is True
    assert "Já deixei isso sinalizado" in last_ai(second["messages"])


def test_worker_soft_alert_is_deduped(monkeypatch):
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
        sent.append({"lead_phone": lead_phone, "lead_message": lead_message, **kwargs})
        return True

    monkeypatch.setattr(worker, "notify_owner", fake_notify_owner)
    result = {
        "handoff_mode": "soft_alert",
        "handoff_reason": "high_value_pmoc",
        "messages": [
            HumanMessage(content="tenho 12 aparelhos e preciso de PMOC"),
            AIMessage(content="Me passa a cidade e o tipo de estabelecimento?"),
        ],
    }
    fake_redis = FakeRedis()

    first = run(worker.maybe_notify_owner_from_result(
        fake_redis,
        phone="+5513999999999",
        message_text="tenho 12 aparelhos e preciso de PMOC",
        result=result,
        instance="test",
    ))
    second = run(worker.maybe_notify_owner_from_result(
        fake_redis,
        phone="+5513999999999",
        message_text="tenho 12 aparelhos e preciso de PMOC",
        result=result,
        instance="test",
    ))

    assert first is True
    assert second is False
    assert len(sent) == 1
    assert sent[0]["handoff_mode"] == "soft_alert"
    assert "high_value_pmoc" in sent[0]["reason"]
