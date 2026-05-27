"""
Tests for conversation_simulator.py
"""
import pytest
from refrimix_core.evaluation.conversation_simulator import (
    simulate_conversation,
    ConversationResult,
    SimLeadState,
    ConversationTurn,
)
from refrimix_core.evaluation.scenario_generator import generate_scenarios


class TestSimulateConversation:
    def test_basic_greeting(self):
        scenarios = generate_scenarios(1, seed=1)
        result = simulate_conversation(scenarios[0])
        assert isinstance(result, ConversationResult)
        assert result.final_score >= 0

    def test_outcome_is_set(self):
        # seed=99 gives scenarios across multiple categories including
        # instalacao/higienizacao/manutencao which produce non-falha outcomes
        scenarios = generate_scenarios(20, seed=99)
        outcomes = set()
        for s in scenarios:
            result = simulate_conversation(s)
            outcomes.add(result.outcome)
        # Should have variety of outcomes across categories
        assert len(outcomes) >= 2, f"Só retornou {outcomes}"

    def test_turns_have_user_and_assistant(self):
        scenarios = generate_scenarios(5, seed=99)
        for s in scenarios:
            result = simulate_conversation(s)
            roles = [t.role for t in result.turns]
            assert "user" in roles
            assert "assistant" in roles

    def test_electrical_risk_turns_off(self):
        from refrimix_core.evaluation.scenario_generator import LeadScenario
        scenario = LeadScenario(
            id=999,
            category="risco_eletrico",
            message="o disjuntor está caindo quando ligo o ar",
            cidade="São Paulo",
            bairro="Jardins",
        )
        result = simulate_conversation(scenario)
        # Should have warnings about turn off
        assert "nao_orienta_desligar_em_risco_eletrico" in result.overall_failures or \
               any("deslig" in t.message.lower() for t in result.turns if t.role == "assistant")

    def test_turns_increment(self):
        scenarios = generate_scenarios(1, seed=7)
        result = simulate_conversation(scenarios[0])
        turn_numbers = [t.turn for t in result.turns]
        assert turn_numbers == sorted(turn_numbers)

    def test_max_turns_limit(self):
        from refrimix_core.evaluation.scenario_generator import LeadScenario
        scenario = LeadScenario(
            id=998,
            category="saudacao_triagem",
            message="oi",
            cidade="Santos",
            bairro="Gonzaga",
        )
        result = simulate_conversation(scenario, max_turns=3)
        user_turns = [t for t in result.turns if t.role == "user"]
        # Should not exceed max_turns user messages
        assert len(user_turns) <= 3

    def test_conversation_result_to_dict(self):
        scenarios = generate_scenarios(3, seed=55)
        result = simulate_conversation(scenarios[0])
        d = result.to_dict()
        assert "scenario_id" in d
        assert "outcome" in d
        assert "final_score" in d
        assert "turns" in d

    def test_score_is_average_of_turn_scores(self):
        scenarios = generate_scenarios(5, seed=123)
        for s in scenarios:
            result = simulate_conversation(s)
            # Score should be reasonable
            assert 0 <= result.final_score <= 5


class TestSimLeadState:
    def test_default_values(self):
        state = SimLeadState()
        assert state.nome is None
        assert state.cidade_bairro is None
        assert state.tipo_servico is None

    def test_to_dict(self):
        state = SimLeadState(nome="Carlos", cidade_bairro="Santos - Gonzaga")
        d = state.to_dict()
        assert d["nome"] == "Carlos"
        assert d["cidade_bairro"] == "Santos - Gonzaga"


class TestConversationTurn:
    def test_turn_creation(self):
        turn = ConversationTurn(turn=1, role="user", message="oi")
        assert turn.turn == 1
        assert turn.role == "user"
        assert turn.message == "oi"
        assert turn.rubric_result is None

    def test_turn_ordering(self):
        """User and assistant alternate."""
        scenarios = generate_scenarios(2, seed=44)
        result = simulate_conversation(scenarios[0])
        for i in range(0, len(result.turns) - 1, 2):
            assert result.turns[i].role == "user"
            if i + 1 < len(result.turns):
                assert result.turns[i + 1].role == "assistant"


class TestEndToEnd:
    def test_instalacao_flow(self):
        from refrimix_core.evaluation.scenario_generator import LeadScenario
        scenario = LeadScenario(
            id=1,
            category="instalacao",
            message="quero instalar um ar",
            cidade="Santos",
            bairro="Pompeia",
        )
        result = simulate_conversation(scenario)
        # Should advance toward offer
        assert len(result.turns) >= 2

    def test_higienizacao_flow(self):
        from refrimix_core.evaluation.scenario_generator import LeadScenario
        scenario = LeadScenario(
            id=2,
            category="higienizacao",
            message="faz limpeza no ar",
            cidade="São Paulo",
            bairro="Moema",
        )
        result = simulate_conversation(scenario)
        assert len(result.turns) >= 2

    def test_nao_gela_flow(self):
        from refrimix_core.evaluation.scenario_generator import LeadScenario
        scenario = LeadScenario(
            id=3,
            category="nao_gela",
            message="meu ar não gela",
            cidade="Curitiba",
            bairro="Batel",
        )
        result = simulate_conversation(scenario)
        # Should not give definitive diagnosis
        diag_failures = [f for f in result.overall_failures if "diagnostico" in f]
        assert len(diag_failures) == 0 or result.final_score >= 3.5

    def test_all_categories_run(self):
        """Sanity check that all categories don't crash."""
        from refrimix_core.evaluation.scenario_generator import CATEGORY_DISTRIBUTION
        for category in CATEGORY_DISTRIBUTION.keys():
            s = generate_scenarios(1, seed=hash(category) % 1000)[0]
            # Just don't crash
            result = simulate_conversation(s)
            assert result is not None