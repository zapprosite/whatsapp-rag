from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from agent_graph.services.playbook_loader import (
    get_ambiguity_lexicon,
    get_forbidden_context_drift,
    get_response_templates,
)


@dataclass(frozen=True)
class DisambiguationResult:
    original_query: str
    rewritten_query: str
    matched_terms: tuple[str, ...]
    applied_rules: tuple[str, ...]
    service_hint: str | None = None
    variant: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "rewritten_query": self.rewritten_query,
            "matched_terms": list(self.matched_terms),
            "applied_rules": list(self.applied_rules),
            "service_hint": self.service_hint,
            "variant": self.variant,
        }


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", folded).strip()


def _contains(text: str, term: str) -> bool:
    folded_term = _fold(term)
    if not folded_term:
        return False
    if len(folded_term.split()) > 1:
        return folded_term in text
    return re.search(rf"\b{re.escape(folded_term)}\b", text) is not None


def _term_aliases(term: str, rule: dict[str, Any]) -> list[str]:
    aliases = [term]
    aliases.extend(str(alias) for alias in rule.get("aliases") or [])
    return aliases


def _select_variant(folded_text: str, variants: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    best_name = None
    best_rule: dict[str, Any] = {}
    best_score = 0
    for name, variant_rule in variants.items():
        signals = [str(signal) for signal in variant_rule.get("signals") or []]
        score = sum(1 for signal in signals if _contains(folded_text, signal))
        if score > best_score:
            best_name = str(name)
            best_rule = variant_rule
            best_score = score
    return best_name, best_rule


def disambiguate_user_text(user_text: str, lead_state: dict[str, Any] | None = None) -> DisambiguationResult:
    """Expande termos ambíguos de HVAC antes do RAG, sem chamar LLM."""
    lead_state = lead_state or {}
    folded = _fold(user_text)
    lexicon = get_ambiguity_lexicon()
    expansions: list[str] = []
    matched_terms: list[str] = []
    applied_rules: list[str] = []
    service_hint = lead_state.get("tipo_servico")
    variant_name: str | None = None

    for term, rule in lexicon.items():
        if not isinstance(rule, dict):
            continue
        if not any(_contains(folded, alias) for alias in _term_aliases(str(term), rule)):
            continue
        matched_terms.append(str(term))
        if rule.get("disambiguation_rule"):
            applied_rules.append(str(rule["disambiguation_rule"]))

        variants = rule.get("variants") or {}
        if isinstance(variants, dict) and variants:
            selected_name, selected_rule = _select_variant(folded, variants)
            if selected_rule:
                variant_name = selected_name
                expansion = selected_rule.get("query_expansion")
                if expansion:
                    expansions.append(str(expansion))
                if selected_rule.get("service") and not service_hint:
                    service_hint = str(selected_rule["service"])
                continue

        if rule.get("query_expansion"):
            expansions.append(str(rule["query_expansion"]))

    state_bits = []
    for key in ("tipo_servico", "cidade_bairro", "btus", "marca", "modelo_aparelho"):
        value = lead_state.get(key)
        if value:
            state_bits.append(f"{key}={value}")

    base = " ".join(part for part in [user_text, " ".join(state_bits), " ".join(expansions)] if part).strip()
    rewritten = f"HVAC-R Refrimix Brasil atendimento ar-condicionado {base}".strip()
    return DisambiguationResult(
        original_query=user_text,
        rewritten_query=rewritten,
        matched_terms=tuple(dict.fromkeys(matched_terms)),
        applied_rules=tuple(dict.fromkeys(applied_rules)),
        service_hint=service_hint,
        variant=variant_name,
    )


def build_rag_query(user_text: str, lead_state: dict[str, Any] | None = None, recent_human: list[str] | None = None) -> tuple[str, dict[str, Any]]:
    result = disambiguate_user_text(user_text, lead_state)
    recent = " | ".join((recent_human or [])[-3:])
    query = result.rewritten_query
    if recent:
        query = f"{query} historico_recente={recent}"
    return query, result.as_dict()


def find_forbidden_context_drift(response: str) -> list[str]:
    folded = _fold(response)
    forbidden = get_forbidden_context_drift()
    hits: list[str] = []
    for group, terms in forbidden.items():
        if not isinstance(terms, list):
            continue
        for term in terms:
            if _contains(folded, str(term)):
                hits.append(f"{group}:{term}")
    return hits


def select_response_template(state: dict[str, Any], user_text: str = "") -> dict[str, Any] | None:
    lead_state = state.get("lead_state") or {}
    lead_mind = lead_state.get("lead_mind") if isinstance(lead_state, dict) else {}
    segment = ((lead_mind or {}).get("segment") or {}).get("id")
    relationship_type = lead_state.get("relationship_type")
    service = state.get("service") or lead_state.get("tipo_servico")
    goal = state.get("conversation_objective") or lead_state.get("conversation_goal")
    user_intent = ((lead_mind or {}).get("intent") or {}).get("last_user_intent")
    if not user_intent and any(term in _fold(user_text) for term in ("quanto", "preco", "preço", "valor", "orcamento", "orçamento")):
        user_intent = "price_question"

    facts = {
        "service": service,
        "goal": goal,
        "segment": segment,
        "relationship_type": relationship_type,
        "user_intent": user_intent,
    }

    for template_id, template in get_response_templates().items():
        when = template.get("when") or {}
        if all(facts.get(key) == value for key, value in when.items()):
            return {
                "id": template_id,
                "template": template.get("template", ""),
                "required_context": template.get("required_context") or [],
                "when": when,
            }
    return None


def template_context_for_prompt(template: dict[str, Any] | None) -> str:
    if not template:
        return "Nenhum template específico. Use as regras de estado e o contexto recuperado."
    required = ", ".join(template.get("required_context") or []) or "nenhum campo obrigatório adicional"
    return (
        f"Template recomendado: {template.get('id')}\n"
        f"Campos necessários: {required}\n"
        f"Modelo flexível:\n{template.get('template', '').strip()}"
    )
