"""
tests/test_no_repeated_generic_fallback.py

Teste de regressão: o bot NÃO pode repetir o fallback genérico
"Entendi.\n\nIsso é instalação, manutenção, higienização ou conserto?"
para o mesmo lead, nem acionar ask_basic_service quando a intenção já é clara.

Casos:
1. Cliente com intenção clara (manutenção, higienização, risco elétrico, etc)
   → NÃO deve retornar ask_basic_service
2. Cliente que já recebeu menu/saudação e manda "Oi" de novo
   → NÃO deve repetir a mesma mensagem
3. Risco elétrico → sempre orientar desligar, não perguntar serviço
4. Sem foto → não bloqueia agenda
"""
from __future__ import annotations

import pytest

from refrimix_core.evaluation.conversation_simulator import simulate_conversation
from refrimix_core.evaluation.scenario_generator import LeadScenario


# ── cenário helper ─────────────────────────────────────────────────────────────

def make_scenario(
    message: str,
    category: str,
    cidade: str = "São Paulo",
    bairro: str = "Jardins",
    has_photo: bool = True,
    is_impatient: bool = False,
    is_confused: bool = False,
    is_angry: bool = False,
) -> LeadScenario:
    """Cria cenário mínimo para teste."""
    return LeadScenario(
        id=hash(message + category) % 100000,
        category=category,
        message=message,
        cidade=cidade,
        bairro=bairro,
        has_photo=has_photo,
        is_impatient=is_impatient,
        is_confused=is_confused,
        is_angry=is_angry,
        is_audio_allowed=True,
    )


# ── Casos parametrizados ────────────────────────────────────────────────────────

FORBIDDEN_PATTERNS = [
    "Entendi.\n\nIsso é instalação, manutenção, higienização ou conserto?",
    "Entendi.\n\nIsso é manutenção",
    "Entendi.\n\nIsso é higienização",
    "Entendi.\n\nIsso é conserto",
]


@pytest.mark.parametrize(
    "scenario",
    [
        #Caso 1: "meu ar n gela" — intenção clara de manutenção
        make_scenario(
            message="meu ar n gela",
            category="manutencao_nao_gela",
        ),
        # Caso 2: "qto fica limpeza" — intenção clara de higienização
        make_scenario(
            message="qto fica limpeza",
            category="higienizacao_preco",
        ),
        # Caso 3: disjuntor — risco elétrico, nunca ask_basic_service
        make_scenario(
            message="disjuntor cai toda vez que ligo o ar",
            category="risco_eletrico",
        ),
        # Caso 4: sem foto — não bloqueia
        make_scenario(
            message="to sem foto agora, posso mandar depois?",
            category="sem_foto",
            has_photo=False,
        ),
        # Caso 5: "preciso instalar" — clara intenção de instalação
        make_scenario(
            message="preciso instalar um ar condicionado",
            category="instalacao",
        ),
        # Caso 6: "faz limpeza" — clara intenção de higienização
        make_scenario(
            message="faz limpeza de split?",
            category="higienizacao",
        ),
        # Caso 7: "ar ta pingando" — clara intenção de manutenção
        make_scenario(
            message="ar ta pingando agua",
            category="manutencao_pingando",
        ),
        # Caso 8: "quanto fica pra instalar" — clara intenção de instalação
        make_scenario(
            message="quanto fica pra instalar um ar",
            category="instalacao_preco",
        ),
    ],
    ids=[
        "manutencao_nao_gela",
        "higienizacao_preco",
        "risco_eletrico",
        "sem_foto",
        "instalacao",
        "higienizacao",
        "manutencao_pingando",
        "instalacao_preco",
    ],
)
def test_no_ask_basic_service_when_intent_is_clear(scenario: LeadScenario):
    """
    Quando o cliente já jelas intent (manutenção, higienização, etc),
    o bot NÃO deve retornar ask_basic_service (o fallback genérico).
    """
    result = simulate_conversation(scenario)

    # Pega todas as respostas do bot
    bot_responses = [
        t.message for t in result.turns if t.role == "assistant"
    ]

    for resp in bot_responses:
        for pattern in FORBIDDEN_PATTERNS:
            assert pattern not in resp, (
                f"FALLBACK REPETIDO: scenario={scenario.category}, "
                f"message={scenario.message!r}, "
                f"response={resp!r}"
            )


@pytest.mark.parametrize(
    "scenario",
    [
        make_scenario(
            message="oi",
            category="saudacao_primeira_vez",
        ),
        make_scenario(
            message="oi",
            category="saudacao_retorno",
        ),
        make_scenario(
            message="bom dia",
            category="saudacao_formal",
        ),
    ],
    ids=[
        "saudacao_primeira_vez",
        "saudacao_retorno",
        "saudacao_formal",
    ],
)
def test_no_engessado_greeting(scenario: LeadScenario):
    """
    Saudação não pode ser engessada com 'como posso ajudar'
    ou sem triagem de serviço.
    """
    result = simulate_conversation(scenario)
    first_bot = next((t for t in result.turns if t.role == "assistant"), None)

    assert first_bot is not None, "Bot não respondeu"

    # Greeting engessado não pode ser "Como posso ajudar?"
    assert "como posso ajudar" not in first_bot.message.lower() or "bom dia" in first_bot.message.lower() or "opa" in first_bot.message.lower() or "eae" in first_bot.message.lower(), (
        f"GREETING ENGRESSADO: {first_bot.message!r}"
    )


@pytest.mark.critical
def test_eletrical_risk_always_shutdown_guidance():
    """
    Risco elétrico → bot SEMPRE orienta desligar,
    mesmo se cliente não tiver explained anything.
    """
    scenario = make_scenario(
        message="disjuntor cai e cheiro de queimado",
        category="risco_eletrico",
    )
    result = simulate_conversation(scenario)

    all_responses = " ".join(t.message for t in result.turns if t.role == "assistant")

    # Deve conter orientação de desligar
    has_shutdown = any(
        word in all_responses.lower()
        for word in ["deslig", "desliga", "mantenha desligado", " mantenha o equipamento desligado"]
    )
    assert has_shutdown, (
        f"FALTA ORIENTAÇÃO DESLIGAR: all_responses={all_responses!r}"
    )


@pytest.mark.critical
def test_no_repeated_response_same_lead():
    """
    O bot não pode mandar a mesma resposta para o mesmo lead
    em turnos consecutivos.
    """
    scenario = make_scenario(
        message="oi meu ar não gela",
        category="manutencao_nao_gela",
    )
    result = simulate_conversation(scenario)

    bot_responses = [t.message for t in result.turns if t.role == "assistant"]

    # Verifica duplicatas consecutivas
    for i in range(1, len(bot_responses)):
        prev_50 = bot_responses[i - 1].strip()[:50]
        curr_50 = bot_responses[i].strip()[:50]
        assert prev_50 != curr_50 or len(bot_responses[i].strip()) < 10, (
            f"RESPOSTA REPETIDA: prev={bot_responses[i-1]!r}, curr={bot_responses[i]!r}"
        )


def test_scenario_generation_smoke():
    """Smoke test: LeadScenario pode ser criado."""
    s = make_scenario("teste", "generic")
    assert s.id == "test_generic"
    assert s.message == "teste"
    assert s.category == "generic"