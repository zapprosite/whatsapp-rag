from langchain_core.messages import HumanMessage

import agent_graph.nodes.nodes as nodes


def test_sales_cache_key_depends_on_lead_state():
    first = nodes._sales_cache_key(
        "instalacao",
        "quanto fica?",
        {"tipo_servico": "instalacao", "cidade_bairro": "Santos", "relationship_type": "new_lead"},
        ["foto_local_interno"],
        ["tipo_servico", "cidade_bairro"],
    )
    second = nodes._sales_cache_key(
        "instalacao",
        "quanto fica?",
        {"tipo_servico": "instalacao", "cidade_bairro": "Guarujá", "relationship_type": "new_lead"},
        ["foto_local_interno"],
        ["tipo_servico", "cidade_bairro"],
    )

    assert first != second
    assert first.startswith("sales_reply:v2:instalacao:")


def test_save_interaction_uses_last_human_message(monkeypatch):
    saved = {}

    async def fake_prisma_save_interaction(data):
        saved.update(data)

    monkeypatch.setattr(nodes, "prisma_save_interaction", fake_prisma_save_interaction)

    async def fake_save():
        state = {
            "messages": [
                HumanMessage(content="primeira mensagem"),
                HumanMessage(content="mensagem atual"),
            ],
            "customer_data": {"phone": "unknown"},
            "lead_state": {},
        }
        await nodes.save_interaction(state)

    import asyncio

    asyncio.run(fake_save())

    assert saved["user_message"] == "mensagem atual"


def test_active_customer_relationship_never_new_lead():
    relationship = nodes.compute_relationship_type(
        {
            "messages": [HumanMessage(content="oi")],
            "customer_data": {"active_service": {"id": "1", "status": "scheduled"}},
            "lead_state": {},
        }
    )

    assert relationship == "active_customer"
