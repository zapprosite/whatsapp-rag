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
    assert result["lead_state"]["relationship_type"] == "human_takeover"


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


def test_classify_preventive_multi_device_plan_is_pmoc(monkeypatch):
    patch_classifier_llm(monkeypatch, "manutencao")

    result = run(nodes.classify_service(base_state("tenho 12 aparelhos e preciso de manutenção preventiva")))

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


def test_classify_uses_recent_context_for_short_price_followup(monkeypatch):
    patch_classifier_llm(monkeypatch, "unknown")
    state = base_state("quanto fica?")
    state["messages"] = [
        HumanMessage(content="quero instalar um split no apartamento"),
        AIMessage(content="Me passa a cidade e a BTU do aparelho?"),
        HumanMessage(content="quanto fica?"),
    ]

    result = run(nodes.classify_service(state))

    assert result["intent"] == "instalacao"
    assert result["service"] == "instalacao"
    assert result["handoff_mode"] == "none"


def test_classify_common_sp_hvac_phrases_without_handoff(monkeypatch):
    patch_classifier_llm(monkeypatch, "unknown")

    no_cooling = run(nodes.classify_service(base_state("meu ar não tá gelando")))
    cleaning = run(nodes.classify_service(base_state("faz limpeza de split?")))

    assert no_cooling["intent"] == "manutencao"
    assert no_cooling["handoff_mode"] == "none"
    assert cleaning["intent"] == "higienizacao"
    assert cleaning["handoff_mode"] == "none"


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


def test_worker_normalizes_evolution_jid_to_number():
    from app import worker

    assert worker.normalize_whatsapp_number("5513999999999@s.whatsapp.net") == "5513999999999"
    assert worker.normalize_whatsapp_number("5513999999999:12@s.whatsapp.net") == "5513999999999"
    assert worker.normalize_whatsapp_number("+55 (13) 99999-9999") == "5513999999999"


def test_unknown_repeated_becomes_soft_alert(monkeypatch):
    patch_classifier_llm(monkeypatch, "unknown")
    state = base_state("não sei explicar")
    state["lead_state"] = {"unknown_context_count": 1}

    result = run(nodes.classify_service(state))

    assert result["lead_state"]["unknown_context_count"] == 2
    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"] == "no_context_needs_human_review"


def test_generate_no_context_soft_alert_response():
    state = base_state("não sei explicar")
    state.update({
        "intent": "unknown",
        "lead_state": {"unknown_context_count": 2, "relationship_type": "no_context"},
    })

    result = run(nodes.generate_response(state))
    response = last_ai(result["messages"])

    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"] == "no_context_needs_human_review"
    # Frase de gerente removida do copy ao cliente; verificar que resposta pede tipo de serviço
    assert "instalação" in response.lower() or "manutenção" in response.lower() or "higienização" in response.lower()


def test_appointment_score_ready_sets_soft_alert(monkeypatch):
    patch_classifier_llm(monkeypatch, "instalacao")
    state = base_state("sou João, quero agendar técnico amanhã em Santos para instalação")
    state["lead_state"] = {
        "tipo_servico": "instalacao",
        "nome": "João",
        "cidade_bairro": "Santos",
        "btus": "12000",
        # instalação requer ambas as fotos para appointment_ready
        "fotos": {"aparelho": False, "local_interno": True, "local_externo": True, "disjuntor": False, "erro_display": False},
    }

    result = run(nodes.classify_service(state))

    assert result["lead_state"]["appointment_score"] >= 5
    assert result["lead_state"]["appointment_ready"] is True
    assert result["handoff_mode"] == "soft_alert"
    assert result["handoff_reason"] == "appointment_ready"


def test_worker_manual_takeover_blocks_graph_and_response(monkeypatch):
    from app import worker

    class FakeRedis:
        async def get(self, key: str) -> str | None:
            if key.startswith("manual_takeover:"):
                return "1"
            if key == "whatsapp_rag:bot_enabled":
                return "1"
            return None

        async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
            return True

        async def eval(self, script: str, numkeys: int, key: str, token: str) -> int:
            return 1

    class FailingGraph:
        async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
            raise AssertionError("GRAPH não deve ser chamado quando humano assumiu")

    sent: list[tuple[str, str]] = []

    async def fake_send(phone: str, text: str, instance: str = "default") -> bool:
        sent.append((phone, text))
        return True

    monkeypatch.setattr(worker, "GRAPH", FailingGraph())
    monkeypatch.setattr(worker, "send_whatsapp_message", fake_send)

    payload = worker.QueueMessage(phone="5513999999999", message="oi", instance="test")
    run(worker._process_customer_message(payload, FakeRedis(), 1))

    assert sent == []


def test_appointment_ready_does_not_notify_owner_until_confirmed(monkeypatch):
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
        "handoff_reason": "appointment_ready",
        "messages": [
            HumanMessage(content="quero agendar técnico amanhã em Santos"),
            AIMessage(content="Vou sinalizar o gerente agora."),
        ],
    }

    notified = run(worker.maybe_notify_owner_from_result(
        FakeRedis(),
        phone="5513999999999",
        message_text="quero agendar técnico amanhã em Santos",
        result=result,
        instance="test",
    ))

    assert notified is False
    assert sent == []
