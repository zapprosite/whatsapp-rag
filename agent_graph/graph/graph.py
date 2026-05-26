from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict
from langgraph.graph import StateGraph, add_messages, END
from langchain_core.messages import BaseMessage

from agent_graph.nodes.nodes import (
    preprocess_input,
    extract_lead_data,
    classify_service,
    retrieve_knowledge,
    language_guard_check,
    response_guard_check,
    format_whatsapp,
    decide_response_modality,
    tts_voice_clone,
    save_interaction,
)
from agent_graph.nodes.compose_response import compose_response
from agent_graph.nodes.dispatch_side_effects import dispatch_side_effects
from agent_graph.nodes.plan_next_action import plan_next_action
from agent_graph.nodes.reduce_lead_state import reduce_lead_state
from agent_graph.nodes.understand_message import understand_message

# Compatibilidade com testes e imports legados.
dispatch_appointment_alert = dispatch_side_effects


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
    tts_text: str | None
    # Memória operacional Postgres 17
    lead_state: dict[str, Any] | None
    already_asked_fields: list[str] | None
    missing_fields: list[str] | None
    do_not_ask: list[str] | None
    conversation_summary: str | None
    conversation_objective: str | None
    security_guard: dict[str, Any] | None
    safe_response: str | None
    continuation_response: str | None
    response_guard_violations: list[str] | None
    domain_disambiguation: dict[str, Any] | None
    selected_template: dict[str, Any] | None
    message_understanding: dict[str, Any] | None
    commercial_decision: dict[str, Any] | None
    next_action: dict[str, Any] | None
    conversation_stage: str | None
    calendar_stage: str | None
    vision_data: dict[str, Any] | None
    calendar_slots: list[dict[str, Any]] | None
    short_answer_applied: bool | None


def route_after_plan(state: AgentState) -> str:
    next_action = state.get("next_action") or {}
    if next_action.get("needs_rag"):
        return "retrieve_knowledge"
    return "compose_response"


def route_after_modality(state: AgentState) -> str:
    if state.get("response_modality") == "audio":
        return "tts_voice_clone"
    return "dispatch_side_effects"


def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    # ── Nós ────────────────────────────────────────────────────────────────────
    workflow.add_node("preprocess_input",         preprocess_input)
    workflow.add_node("extract_lead_data",        extract_lead_data)
    workflow.add_node("understand_message",       understand_message)
    workflow.add_node("reduce_lead_state",        reduce_lead_state)
    workflow.add_node("classify_service",         classify_service)
    workflow.add_node("plan_next_action",         plan_next_action)
    workflow.add_node("retrieve_knowledge",       retrieve_knowledge)
    workflow.add_node("compose_response",         compose_response)
    workflow.add_node("language_guard_check",     language_guard_check)
    workflow.add_node("response_guard_check",     response_guard_check)
    workflow.add_node("format_whatsapp",          format_whatsapp)
    workflow.add_node("decide_response_modality", decide_response_modality)
    workflow.add_node("tts_voice_clone",          tts_voice_clone)
    workflow.add_node("dispatch_side_effects",    dispatch_side_effects)
    workflow.add_node("save_interaction",         save_interaction)

    # ── Entrypoint ─────────────────────────────────────────────────────────────
    workflow.set_entry_point("preprocess_input")

    # ── Arestas ────────────────────────────────────────────────────────────────
    workflow.add_edge("preprocess_input", "extract_lead_data")
    workflow.add_edge("extract_lead_data", "understand_message")
    workflow.add_edge("understand_message", "reduce_lead_state")
    workflow.add_edge("reduce_lead_state", "classify_service")
    workflow.add_edge("classify_service", "plan_next_action")

    workflow.add_conditional_edges(
        "plan_next_action",
        route_after_plan,
        {
            "retrieve_knowledge": "retrieve_knowledge",
            "compose_response":   "compose_response",
        },
    )

    workflow.add_edge("retrieve_knowledge",   "compose_response")
    workflow.add_edge("compose_response",     "language_guard_check")
    workflow.add_edge("language_guard_check", "response_guard_check")
    workflow.add_edge("response_guard_check", "format_whatsapp")
    workflow.add_edge("format_whatsapp",      "decide_response_modality")

    workflow.add_conditional_edges(
        "decide_response_modality",
        route_after_modality,
        {
            "tts_voice_clone":            "tts_voice_clone",
            "dispatch_side_effects":      "dispatch_side_effects",
        },
    )

    workflow.add_edge("tts_voice_clone",            "dispatch_side_effects")
    workflow.add_edge("dispatch_side_effects",      "save_interaction")
    workflow.add_edge("save_interaction",           END)

    return workflow.compile()
