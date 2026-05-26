from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from agent_graph.nodes.nodes import _lead_state_copy
from app import lead_repository, mvp_attendance
from app.main import app


def run(coro):
    return asyncio.run(coro)


def _last_text(result: dict) -> str:
    return str(result["messages"][-1].content)


def _mock_repo(monkeypatch, lead_state: dict | None = None, *, event_count: int = 0):
    async def fake_load(phone: str, name: str | None = None) -> dict:
        del name
        return {
            "id": "lead-1",
            "phone": phone,
            "name": None,
            "service_type": (lead_state or {}).get("tipo_servico") if lead_state else None,
            "pipeline_stage": "new",
            "city_bairro": None,
            "lead_state": lead_state or _lead_state_copy(),
            "event_count": event_count,
            "available_columns": set(),
        }

    async def fake_update(phone: str, lead_state: dict, *, pipeline_stage: str, service_type: str | None, city_bairro: str | None = None) -> None:
        del phone, lead_state, pipeline_stage, service_type, city_bairro

    async def fake_event(phone: str, role: str, message: str, extracted_data: dict | None = None) -> None:
        del phone, role, message, extracted_data

    monkeypatch.setattr(mvp_attendance, "load_or_create_lead", fake_load)
    monkeypatch.setattr(mvp_attendance, "update_lead_state", fake_update)
    monkeypatch.setattr(mvp_attendance, "create_lead_event", fake_event)


def _mock_repo_stateful(monkeypatch, lead_state: dict | None = None, *, event_count: int = 0):
    store = {
        "lead_state": lead_state or _lead_state_copy(),
        "event_count": event_count,
        "events": [],
        "pipeline_stage": "new",
        "service_type": (lead_state or {}).get("tipo_servico") if lead_state else None,
    }

    async def fake_load(phone: str, name: str | None = None) -> dict:
        del name
        return {
            "id": "lead-1",
            "phone": phone,
            "name": store["lead_state"].get("nome"),
            "service_type": store["service_type"],
            "pipeline_stage": store["pipeline_stage"],
            "city_bairro": store["lead_state"].get("cidade_bairro"),
            "lead_state": store["lead_state"],
            "event_count": store["event_count"],
            "available_columns": set(),
        }

    async def fake_update(phone: str, lead_state: dict, *, pipeline_stage: str, service_type: str | None, city_bairro: str | None = None) -> None:
        del phone, city_bairro
        store["lead_state"] = lead_state
        store["pipeline_stage"] = pipeline_stage
        store["service_type"] = service_type

    async def fake_event(phone: str, role: str, message: str, extracted_data: dict | None = None) -> None:
        del phone, extracted_data
        store["events"].append({"role": role, "message": message})
        store["event_count"] += 1

    monkeypatch.setattr(mvp_attendance, "load_or_create_lead", fake_load)
    monkeypatch.setattr(mvp_attendance, "update_lead_state", fake_update)
    monkeypatch.setattr(mvp_attendance, "create_lead_event", fake_event)
    return store


def _simulate_bootstrap(monkeypatch, turns: list[str], lead_state: dict | None = None) -> tuple[list[str], dict]:
    store = _mock_repo_stateful(monkeypatch, lead_state, event_count=0)
    history = []
    responses: list[str] = []
    for message in turns:
        result = run(
            mvp_attendance.process_mvp_message(
                phone="5513999999999",
                message_text=message,
                instance="default",
                history=history,
            )
        )
        history = result["messages"]
        responses.append(_last_text(result))
    return responses, store


def test_bom_dia_responde_onboarding(monkeypatch):
    _mock_repo(monkeypatch)
    result = run(
        mvp_attendance.process_mvp_message(
            phone="5513999999999",
            message_text="bom dia",
            instance="default",
            history=[],
        )
    )

    assert _last_text(result) == "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?"


def test_instalacao_responde_caminho_comercial(monkeypatch):
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    lead_state["btus"] = "12000"
    lead_state["fotos"]["local_interno"] = True
    lead_state["fotos"]["local_externo"] = True
    lead_state["instalacao"]["ponto_eletrico_exclusivo"] = True
    lead_state["instalacao"]["tubulacao_existente"] = True
    lead_state["instalacao"]["distancia_aproximada"] = "3"
    _mock_repo(monkeypatch, lead_state, event_count=1)

    result = run(
        mvp_attendance.process_mvp_message(
            phone="5513999999999",
            message_text="quero instalar",
            instance="default",
            history=[],
        )
    )

    assert _last_text(result) == (
        "Instalação simples costa/costa, até 3 metros e com acesso fácil, fica R$850 com material e mão de obra.\n\n"
        "Se no local tiver algo fora do padrão, o técnico explica antes e o valor pode ajustar.\n\n"
        "Qual período fica melhor: manhã ou tarde?"
    )


def test_nao_tenho_foto_oferece_visita_50(monkeypatch):
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    _mock_repo(monkeypatch, lead_state, event_count=1)

    result = run(
        mvp_attendance.process_mvp_message(
            phone="5513999999999",
            message_text="não tenho foto",
            instance="default",
            history=[],
        )
    )

    assert "visita técnica de R$50" in _last_text(result)


def test_manutencao_oferece_visita_50(monkeypatch):
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "manutencao"
    _mock_repo(monkeypatch, lead_state, event_count=1)

    result = run(
        mvp_attendance.process_mvp_message(
            phone="5513999999999",
            message_text="preciso de manutenção",
            instance="default",
            history=[],
        )
    )

    assert _last_text(result) == (
        "Para manutenção, o caminho correto é visita/análise técnica.\n\n"
        "A visita fica R$50 e pode ser abatida se o orçamento final for aprovado.\n\n"
        "Qual período fica melhor para a visita?"
    )


def test_higienizacao_oferece_200(monkeypatch):
    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "higienizacao"
    _mock_repo(monkeypatch, lead_state, event_count=1)

    result = run(
        mvp_attendance.process_mvp_message(
            phone="5513999999999",
            message_text="quero higienização",
            instance="default",
            history=[],
        )
    )

    assert "R$200" in _last_text(result)


def test_nao_depende_de_colunas_novas(monkeypatch):
    lead_repository._COLUMN_CACHE.clear()
    executed: list[str] = []

    class FakePrisma:
        async def connect(self) -> None:
            return None

        async def disconnect(self) -> None:
            return None

        async def query_raw(self, query: str, *params):
            if "information_schema.columns" in query:
                table = params[0]
                if table == "leads":
                    return [
                        {"column_name": "id"},
                        {"column_name": "phone"},
                        {"column_name": "name"},
                        {"column_name": "service"},
                        {"column_name": "service_type"},
                        {"column_name": "pipeline_stage"},
                        {"column_name": "city_bairro"},
                        {"column_name": "lead_state"},
                        {"column_name": "already_asked_fields"},
                        {"column_name": "missing_fields"},
                        {"column_name": "do_not_ask"},
                        {"column_name": "last_user_message_at"},
                        {"column_name": "updated_at"},
                    ]
                if table == "lead_events":
                    return []
            if query.startswith("SELECT id, phone"):
                return [{"id": "lead-1", "phone": params[0], "name": None, "service": None, "service_type": None, "pipeline_stage": "new", "city_bairro": None, "lead_state": "{}"}]
            if "COUNT(*)::int AS count" in query:
                return [{"count": 0}]
            raise AssertionError(query)

        async def execute_raw(self, query: str, *params):
            del params
            executed.append(query)
            return 1

    monkeypatch.setattr(lead_repository, "Prisma", FakePrisma)

    lead_state = _lead_state_copy()
    lead_state["tipo_servico"] = "instalacao"
    run(
        lead_repository.update_lead_state(
            "5513999999999",
            lead_state,
            pipeline_stage="quoted",
            service_type="instalacao",
        )
    )

    assert executed
    query = executed[0]
    assert "lead_state =" in query
    assert "email" not in query
    assert "address" not in query
    assert "commercial_path" not in query
    assert "appointment_window" not in query
    assert "appointment_slot_start" not in query
    assert "appointment_slot_end" not in query


def test_health_falha_se_postgres_quebra(monkeypatch):
    class FakeRedis:
        async def ping(self) -> bool:
            return True

    async def fake_get_redis():
        return FakeRedis()

    async def fake_postgres_status():
        raise RuntimeError("postgres offline")

    async def fake_worker_status(r=None):
        del r
        return {"status": "up", "phase": "idle"}

    monkeypatch.setattr("app.api.health.get_redis", fake_get_redis)
    monkeypatch.setattr("app.api.health.postgres_status", fake_postgres_status)
    monkeypatch.setattr("app.api.health.worker_heartbeat_status", fake_worker_status)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "degraded"
    assert payload["postgres"].startswith("down:")


def test_bootstrap_instalacao_completo(monkeypatch):
    lead_state = _lead_state_copy()
    lead_state["btus"] = "12000"
    lead_state["fotos"]["local_interno"] = True
    lead_state["fotos"]["local_externo"] = True
    lead_state["instalacao"]["ponto_eletrico_exclusivo"] = True
    lead_state["instalacao"]["tubulacao_existente"] = True
    lead_state["instalacao"]["distancia_aproximada"] = "3"

    responses, store = _simulate_bootstrap(
        monkeypatch,
        ["bom dia", "instalação", "Will"],
        lead_state=lead_state,
    )

    assert responses == [
        "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?",
        "Perfeito.\n\nMe passa seu nome pra eu deixar o atendimento certinho?",
        "Instalação simples costa/costa, até 3 metros e com acesso fácil, fica R$850 com material e mão de obra.\n\nSe no local tiver algo fora do padrão, o técnico explica antes e o valor pode ajustar.\n\nQual período fica melhor: manhã ou tarde?",
    ]
    assert store["lead_state"]["nome"] == "Will"
    assert store["lead_state"]["tipo_servico"] == "instalacao"
    assert store["lead_state"]["pipeline_stage"] == "quoted"
    assert len(store["events"]) == 6


def test_bootstrap_instalacao_sem_foto(monkeypatch):
    responses, store = _simulate_bootstrap(
        monkeypatch,
        ["bom dia", "instalação", "William", "não tenho foto"],
        lead_state=_lead_state_copy(),
    )

    assert responses[0] == "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?"
    assert responses[1] == "Perfeito.\n\nMe passa seu nome pra eu deixar o atendimento certinho?"
    assert "visita técnica de R$50" in responses[3]
    assert store["lead_state"]["nome"] == "William"
    assert store["lead_state"]["tipo_servico"] == "instalacao"


def test_bootstrap_manutencao_completo(monkeypatch):
    responses, store = _simulate_bootstrap(
        monkeypatch,
        ["bom dia", "manutenção", "Will"],
        lead_state=_lead_state_copy(),
    )

    assert responses == [
        "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?",
        "Perfeito.\n\nMe passa seu nome pra eu deixar o atendimento certinho?",
        "Para manutenção, o caminho correto é visita/análise técnica.\n\nA visita fica R$50 e pode ser abatida se o orçamento final for aprovado.\n\nQual período fica melhor para a visita?",
    ]
    assert store["lead_state"]["tipo_servico"] == "manutencao"
    assert store["lead_state"]["nome"] == "Will"


def test_bootstrap_higienizacao_completo(monkeypatch):
    responses, store = _simulate_bootstrap(
        monkeypatch,
        ["bom dia", "higienização", "Will"],
        lead_state=_lead_state_copy(),
    )

    assert responses == [
        "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?",
        "Perfeito.\n\nMe passa seu nome pra eu deixar o atendimento certinho?",
        "Higienização de split padrão fica R$200 por aparelho, desde que o equipamento esteja funcionando e instalado dentro do padrão.\n\nSe o aparelho não estiver climatizando, o atendimento pode virar análise de manutenção por R$50.\n\nQuantos aparelhos são?",
    ]
    assert store["lead_state"]["tipo_servico"] == "higienizacao"
    assert store["lead_state"]["nome"] == "Will"
