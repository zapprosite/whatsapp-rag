from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict
from langgraph.graph import StateGraph, add_messages, END
from langchain_core.messages import BaseMessage

from agent_graph.nodes.nodes import (
    preprocess_input,
    extract_lead_data,
    classify_service,
    retrieve_knowledge,
    generate_response,
    language_guard_check,
    format_whatsapp,
    decide_response_modality,
    tts_voice_clone,
    dispatch_appointment_alert,
    save_interaction,
    route_human,
)


class RagContextItem(TypedDict, total=False):
    id: Any
    score: float | None
    priority: int
    payload: dict[str, Any]


class CustomerData(TypedDict, total=False):
    phone: str
    is_first_message: bool
    name: str
    active_service: dict[str, Any]
    last_service: dict[str, Any]


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    intent: str | None
    service: str | None
    outcome: str | None
    handoff_mode: Literal["none", "soft_alert", "hard_transfer"] | None
    handoff_reason: str | None
    handoff_already_notified: bool
    rag_context: list[RagContextItem]
    customer_data: CustomerData
    is_human: bool
    confidence: float
    # Multimodal
    message_type: Literal["conversation", "audioMessage", "imageMessage"] | str | None
    msg_id: str | None             # ID da mensagem para recuperar base64
    media_url: str | None          # URL da mídia inbound (áudio ou imagem)
    media_base64: str | None       # Base64 cacheado via webhook
    instance: str | None           # instância Evolution API
    # Resposta
    response_modality: Literal["text", "audio"] | None
    audio_bytes: bytes | None      # bytes WAV do TTS (não serializado no Redis)
    # Memória operacional Postgres 17
    lead_state: dict[str, Any] | None
    already_asked_fields: list[str] | None
    missing_fields: list[str] | None
    do_not_ask: list[str] | None
    conversation_summary: str | None


def route_after_classify(state: AgentState) -> str:
    handoff_mode = state.get("handoff_mode")
    intent = state.get("intent")
    if handoff_mode == "hard_transfer":
        return "route_human"
    if intent == "onboarding":
        # Saudação — pula RAG, vai direto pra geração (resposta de apresentação)
        return "generate_response"
    return "retrieve_knowledge"


def route_after_modality(state: AgentState) -> str:
    if state.get("response_modality") == "audio":
        return "tts_voice_clone"
    return "dispatch_appointment_alert"


def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # ── Nós ────────────────────────────────────────────────────────────────────
    workflow.add_node("preprocess_input",         preprocess_input)
    workflow.add_node("extract_lead_data",        extract_lead_data)
    workflow.add_node("classify_service",         classify_service)
    workflow.add_node("retrieve_knowledge",       retrieve_knowledge)
    workflow.add_node("generate_response",        generate_response)
    workflow.add_node("language_guard_check",     language_guard_check)
    workflow.add_node("format_whatsapp",          format_whatsapp)
    workflow.add_node("decide_response_modality", decide_response_modality)
    workflow.add_node("tts_voice_clone",          tts_voice_clone)
    workflow.add_node("dispatch_appointment_alert", dispatch_appointment_alert)
    workflow.add_node("save_interaction",         save_interaction)
    workflow.add_node("route_human",              route_human)

    # ── Entrypoint ─────────────────────────────────────────────────────────────
    workflow.set_entry_point("preprocess_input")

    # ── Arestas ────────────────────────────────────────────────────────────────
    workflow.add_edge("preprocess_input", "extract_lead_data")
    workflow.add_edge("extract_lead_data", "classify_service")

    workflow.add_conditional_edges(
        "classify_service",
        route_after_classify,
        {
            "route_human":        "route_human",
            "retrieve_knowledge": "retrieve_knowledge",
            "generate_response":  "generate_response",
        },
    )

    workflow.add_edge("retrieve_knowledge",   "generate_response")
    workflow.add_edge("generate_response",    "language_guard_check")
    workflow.add_edge("language_guard_check", "format_whatsapp")
    workflow.add_edge("format_whatsapp",      "decide_response_modality")

    workflow.add_conditional_edges(
        "decide_response_modality",
        route_after_modality,
        {
            "tts_voice_clone":            "tts_voice_clone",
            "dispatch_appointment_alert": "dispatch_appointment_alert",
        },
    )

    workflow.add_edge("tts_voice_clone",            "dispatch_appointment_alert")
    workflow.add_edge("dispatch_appointment_alert", "save_interaction")
    workflow.add_edge("save_interaction",           END)
    workflow.add_edge("route_human",                "save_interaction")

    return workflow.compile()
