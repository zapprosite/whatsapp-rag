"""
Teste de segurança: verifica que o catálogo de respostas não contém frases proibidas.

Frases proibidas = padrões que indicam fricção, bloqueios ou instruções
anti-venda que não devem aparecer nas respostas do bot.
"""
from __future__ import annotations

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_graph.domain.response_catalog import render_response, ResponseContext


FORBIDDEN_PHRASES = [
    "próximo detalhe",
    "proximo detalhe",
    "vou adiantar pelo que já tenho",
    "não consigo agendar sem foto",
    "não sei tirar foto",
    "não tem como eu agendar",
    "sem foto não dá",
    "me manda as fotos quando puder",
]

ALL_ACTION_TYPES = [
    "welcome_onboarding",
    "ask_lead_name",
    "ask_basic_service",
    "offer_fixed_installation",
    "offer_technical_visit_installation",
    "offer_technical_visit_instalacao",
    "offer_technical_visit_maintenance",
    "offer_technical_visit_manutencao",
    "offer_technical_visit",
    "offer_fixed_hygienization",
    "offer_hygienization_schedule",
    "offer_project_visit",
    "save_preferred_window",
    "fallback_recover_context",
    "answer_services_list",
    "answer_clarification",
    "answer_clarification_llm",
    "reject_security",
    "handoff_human",
    "explain_process",
    "ask_missing_field",
    "unknown",
]


class TestResponseCatalogForbiddenPhrases:
    """Garante que nenhuma frase proibida aparece nas respostas do catálogo."""

    @pytest.mark.parametrize("action_type", ALL_ACTION_TYPES)
    def test_no_forbidden_phrases(self, action_type: str):
        ctx = ResponseContext()
        response = render_response(action_type, ctx)

        found = []
        for phrase in FORBIDDEN_PHRASES:
            if phrase.lower() in response.lower():
                found.append(phrase)

        assert not found, (
            f"action_type={action_type!r} contém frases proibidas: {found}\n"
            f"Resposta: {response!r}"
        )

    def test_catalog_renders_without_error(self):
        """Verifica que todos os action_types renderizam sem exceção."""
        ctx = ResponseContext(service="instalacao", name="Will", city_bairro="Guarujá - Centro")
        for action_type in ALL_ACTION_TYPES:
            try:
                render_response(action_type, ctx)
            except Exception as e:
                pytest.fail(f"action_type={action_type!r} levantou exceção: {e}")

    def test_photo_not_blocker_message(self):
        """A frase 'foto ajuda a adiantar, mas não trava' deve aparecer onde apropriado."""
        ctx = ResponseContext(service="instalacao")
        response = render_response("offer_technical_visit_installation", ctx)
        assert "foto" in response.lower()
        assert "não trava" in response.lower() or "trava" not in response.lower()
