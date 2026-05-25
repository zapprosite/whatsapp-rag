from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter
from langchain_core.messages import AIMessage, HumanMessage

try:
    from runtime import get_redis, queue_key, send_whatsapp_message, worker_module
except ModuleNotFoundError:
    from app.runtime import get_redis, queue_key, send_whatsapp_message, worker_module

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/test", tags=["diagnostics"])

E2E_SCENARIOS = [
    ("instalacao", "Quais marcas de ar condicionado split vocês instalam?"),
    ("instalacao", "Faz instalação de janela de vidro no salão comercial?"),
    ("instalacao", "Quanto tempo leva para instalar 3 splits no apartamento?"),
    ("instalacao", "Vocês instalam equipamento que eu já comprei?"),
    ("instalacao", "Preciso instalar 4 equipos e fazer tubulação no forro de gesso"),
    ("manutencao", "O ar está fazendo barulho de vibração quando liga"),
    ("manutencao", "O split gela demais e desliga sozinho"),
    ("manutencao", "O ar não esquenta no inverno, o que pode ser?"),
    ("manutencao", "Meu ar condicionado tem vazamento de água"),
    ("manutencao", "O split não liga mais, parece que queimou"),
    ("pmoc", "O que é PMOC e é obrigatório no meu prédio comercial?"),
    ("pmoc", "Preciso do laudo PMOC para o alvará do bombeiros"),
    ("pmoc", "Como funciona o programa de manutenção preventiva PMOC?"),
    ("pmoc", "Quanto custa o programa PMOC para 10 equipamentos?"),
    ("pmoc", "Empresa pedindo atestado PMOC, como solicitar?"),
    ("consultoria", "Qual capacidade de BTU preciso para sala de reunião?"),
    ("consultoria", "Vocês fazem projeto de ar condicionado para obra nova?"),
    ("consultoria", "Split ou cassete, o que é melhor para loja de 40m2?"),
    ("consultoria", "Dúvida sobre eficiência energética dos equipos"),
    ("consultoria", "Queria uma assessoria para climatizar o apartamento"),
    ("higienizacao", "Qual a diferença entre limpeza e higienização do split?"),
    ("higienizacao", "Faz higienização com ozônio para eliminar cheiro?"),
    ("higienizacao", "Quando devo fazer a higienização do ar condicionado?"),
    ("higienizacao", "Higienização remove ácaros e fungos dos dutos?"),
    ("higienizacao", "Vocês emitem certificado após a higienização?"),
    ("projeto-central", "Preciso de projeto central de climatização para escritório"),
    ("projeto-central", "Split central ou multisplit para 6 ambientes?"),
    ("projeto-central", "Faz dimensionamento de carga térmica para galpão industrial"),
    ("projeto-central", "Projeto para climatização de restaurante com cozinha"),
    ("projeto-central", "Sistema central com controle individual por ambiente"),
    ("explicit_handoff", "Quero falar com atendente humano, não estou conseguindo resolver"),
    ("sensitive_complaint", "Já liguei várias vezes e ninguém responde"),
    ("sensitive_complaint", "Fiz orçamento faz 10 dias e nunca retornaram"),
    ("sensitive_complaint", "Quero cancelamento e reembolso do serviço"),
]

TEST_MESSAGES = [
    "Olá, preciso de uma instalação de ar condicionado split",
    "Quanto custa manutenção preventiva do ar?",
    "Quero fazer PMOC do meu escritório",
    "Preciso de consultoria para projeto de climatização",
    "Vocês fazem higienização de split?",
    "O ar está fazendo barulho estranho",
    "Quero falar com atendente humano",
    "Qual a garantia dos serviços?",
    "Preciso instalar 5 equipos no projeto central",
]


def _build_state(
    message: str,
    *,
    phone: str,
    media_type: str = "conversation",
    media_url: str = "",
    media_base64: str = "",
    msg_id: str = "",
    instance: str = "test",
) -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content=message)],
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
        "message_type": media_type,
        "msg_id": msg_id,
        "media_url": media_url,
        "media_base64": media_base64,
        "instance": instance,
        "response_modality": None,
        "audio_bytes": None,
    }


def _last_ai_message(messages: list[Any]) -> str | None:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return str(message.content)
        if hasattr(message, "content") and message.__class__.__name__ == "AIMessage":
            return str(message.content)
    return None


async def _invoke_graph(state: dict[str, Any]) -> dict[str, Any]:
    if worker_module.GRAPH is None:
        return {"error": "Graph not ready — server starting up"}
    return await worker_module.GRAPH.ainvoke(state)


@router.post("/e2e")
async def test_e2e(start: int = 0, limit: int = 5, delay: float = 3.0) -> dict[str, Any]:
    results = []
    total = len(E2E_SCENARIOS)
    end = min(start + limit, total)

    for i in range(start, end):
        service_tag, message = E2E_SCENARIOS[i]
        result = await _invoke_graph(_build_state(message, phone=f"+55119000{i:04d}"))
        if "error" in result:
            return result

        intent = result.get("intent")
        item = {
            "index": i,
            "service_tag": service_tag,
            "input": message,
            "intent": intent,
            "service": result.get("service"),
            "handoff_mode": result.get("handoff_mode"),
            "handoff_reason": result.get("handoff_reason"),
            "rag_hits": len(result.get("rag_context", [])),
            "response": _last_ai_message(result.get("messages", [])),
            "correct": intent == service_tag,
        }
        results.append(item)
        logger.info("[e2e] %s/%s [%s] -> intent=%s correct=%s", i + 1, total, service_tag, intent, item["correct"])

        if delay > 0 and i < end - 1:
            await asyncio.sleep(delay)

    return {
        "total": total,
        "range": [start, end],
        "correct": sum(1 for item in results if item["correct"]),
        "results": results,
    }


@router.post("/e2e/loop")
async def test_e2e_loop(cycles: int = 1, delay: float = 3.0) -> dict[str, Any]:
    all_results = []

    for cycle in range(cycles):
        logger.info("[e2e loop] cycle %s/%s", cycle + 1, cycles)
        for i, (service_tag, message) in enumerate(E2E_SCENARIOS):
            result = await _invoke_graph(_build_state(message, phone=f"+55119000{cycle:02d}{i:02d}"))
            if "error" in result:
                return result

            intent = result.get("intent")
            all_results.append({
                "cycle": cycle + 1,
                "index": i,
                "input": message,
                "intent": intent,
                "service_tag": service_tag,
                "service": result.get("service"),
                "handoff_mode": result.get("handoff_mode"),
                "handoff_reason": result.get("handoff_reason"),
                "correct": intent == service_tag,
                "response": _last_ai_message(result.get("messages", [])),
            })

            if delay > 0:
                await asyncio.sleep(delay)

    correct = sum(1 for item in all_results if item["correct"])
    return {
        "cycles": cycles,
        "total": len(all_results),
        "correct": correct,
        "accuracy": round(correct / len(all_results) * 100, 1) if all_results else 0,
        "results": all_results,
    }


@router.post("/refine")
async def test_refine(message: str = "O ar está fazendo barulho") -> dict[str, Any]:
    responses = []
    for i in range(3):
        result = await _invoke_graph(_build_state(message, phone="+5511900000001"))
        if "error" in result:
            return result

        responses.append({
            "run": i + 1,
            "intent": result.get("intent"),
            "service": result.get("service"),
            "handoff_mode": result.get("handoff_mode"),
            "handoff_reason": result.get("handoff_reason"),
            "response": _last_ai_message(result.get("messages", [])),
        })
        await asyncio.sleep(1)

    return {"message": message, "runs": responses}


@router.post("/loop")
async def test_loop(count: int = 3, interval: float = 5.0) -> dict[str, Any]:
    r = await get_redis()
    sent = []
    target_queue = queue_key()
    for i in range(count):
        msg = TEST_MESSAGES[i % len(TEST_MESSAGES)]
        payload = {"phone": f"+55119000000{i:02d}", "message": msg, "instance": "test"}
        await r.lpush(target_queue, json.dumps(payload, ensure_ascii=False))
        sent.append(msg)
        logger.info("[test loop] queued %s/%s: %s", i + 1, count, msg[:60])
        if i < count - 1 and interval > 0:
            await asyncio.sleep(interval)

    return {"queued": count, "queue": target_queue, "messages": sent}


@router.post("/chat")
async def test_chat(
    message: str = "Olá, preciso de instalação de ar split",
    media_type: str = "conversation",
    media_url: str = "",
    send: bool = False,
) -> dict[str, Any]:
    result = await _invoke_graph(_build_state(message, phone="+5511900000001", media_type=media_type, media_url=media_url))
    if "error" in result:
        return result

    ai_message = _last_ai_message(result.get("messages", []))
    sent_to_whatsapp = False
    if send and ai_message:
        sent_to_whatsapp = await send_whatsapp_message("+5511900000001", ai_message, "test")

    return {
        "input": message,
        "intent": result.get("intent"),
        "service": result.get("service"),
        "handoff_mode": result.get("handoff_mode"),
        "handoff_reason": result.get("handoff_reason"),
        "rag_hits": len(result.get("rag_context", [])),
        "response": ai_message,
        "send_requested": send,
        "sent_to_whatsapp": sent_to_whatsapp,
    }
