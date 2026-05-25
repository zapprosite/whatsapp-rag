from langchain_core.messages import AIMessage, HumanMessage

from agent_graph.services import conversation_memory


async def _fake_profile(phone: str):
    return {
        "lead_id": "lead-1",
        "phone": phone,
        "service_type": "instalacao",
        "pipeline_stage": "qualifying_lead",
        "city_bairro": "Santos",
        "lead_state": {"tipo_servico": "instalacao"},
        "conversation_summary": "Lead quer instalação.",
        "already_asked_fields": ["tipo_servico"],
        "missing_fields": ["foto_local_interno"],
        "do_not_ask": ["tipo_servico"],
        "last_user_message_at": None,
        "created_at": None,
        "updated_at": None,
    }


def test_build_canonical_history_uses_postgres_when_redis_empty(monkeypatch):
    async def fake_events(phone: str, limit: int = 12):
        return [HumanMessage(content="quero instalação"), AIMessage(content="Me manda a cidade?")]

    monkeypatch.setattr(conversation_memory, "load_lead_profile", _fake_profile)
    monkeypatch.setattr(conversation_memory, "load_recent_lead_events", fake_events)

    import asyncio

    history, meta = asyncio.run(conversation_memory.build_canonical_history("5513000000000", []))

    assert len(history) == 2
    assert meta["history_source"] == "postgres"
    assert meta["is_conversation_started"] is True
    assert meta["has_persistent_lead"] is True
    assert meta["postgres_event_count"] == 2


def test_build_canonical_history_merges_without_duplicates(monkeypatch):
    async def fake_events(phone: str, limit: int = 12):
        return [HumanMessage(content="quero instalação"), AIMessage(content="Me manda a cidade?")]

    monkeypatch.setattr(conversation_memory, "load_lead_profile", _fake_profile)
    monkeypatch.setattr(conversation_memory, "load_recent_lead_events", fake_events)

    import asyncio

    redis_history = [HumanMessage(content="quero instalação"), HumanMessage(content="Santos")]
    history, meta = asyncio.run(conversation_memory.build_canonical_history("5513000000000", redis_history))

    assert [type(message).__name__ for message in history].count("HumanMessage") == 2
    assert meta["history_source"] == "merged"
