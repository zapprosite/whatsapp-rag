"""
Response Catalog — respostas determinísticas do Refrimix Core V2.
Todas as respostas devem estar aqui, nunca no LLM ou em nodes.py.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from refrimix_core.domain.types import NextActionType, LeadState


def welcome_onboarding() -> str:
    return "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?"


def answer_services_list() -> str:
    return (
        "Trabalhamos com instalação, manutenção, higienização e visita técnica para ar-condicionado.\n\n"
        "Também atendemos casos maiores, como infraestrutura, cassete, piso-teto, splitão, VRF/VRV, dutos e projetos comerciais ou residenciais de alto padrão.\n\n"
        "Os serviços mais comuns são:\n\n"
        "1. Instalação simples\n"
        "2. Higienização\n"
        "3. Manutenção ou conserto\n"
        "4. Visita técnica de análise\n\n"
        "Me fala qual desses você precisa hoje?"
    )


def answer_clarification() -> str:
    return (
        "Claro, vou explicar de forma simples.\n\n"
        "Se for instalação simples, o valor base é R$850.\n\n"
        "Se faltar alguma informação, foto ou precisar avaliar o local, seguimos como visita técnica de R$50. "
        "Esse valor pode ser abatido se o orçamento final for aprovado.\n\n"
        "Para higienização, split padrão funcionando fica R$200 por aparelho.\n\n"
        "Qual serviço você quer ver primeiro?"
    )


def ask_lead_name() -> str:
    return "Perfeito.\n\nMe passa seu nome pra eu deixar o atendimento certinho?"


def ask_basic_service() -> str:
    return "Entendi.\n\nIsso é instalação, manutenção, higienização ou conserto?"


def offer_fixed_installation() -> str:
    return (
        "Perfeito.\n\n"
        "Instalação simples costa/costa, até 3 metros e com acesso fácil, fica R$850 com material e mão de obra.\n\n"
        "Esse valor considera ponto elétrico individual e cenário dentro do padrão. "
        "Se no local tiver algo fora disso, o técnico explica antes e o valor pode ajustar.\n\n"
        "Qual período fica melhor: manhã ou tarde?"
    )


def offer_technical_visit_installation() -> str:
    return (
        "Sem problema.\n\n"
        "A foto ajuda a adiantar, mas não trava o atendimento.\n\n"
        "Como ainda falta confirmar o local completo, seguimos como visita técnica de R$50. "
        "Se o orçamento final for aprovado, esse valor pode ser abatido.\n\n"
        "Qual período fica melhor: manhã ou tarde?"
    )


def offer_technical_visit_maintenance() -> str:
    return (
        "Para manutenção, o caminho correto é visita/análise técnica.\n\n"
        "A visita fica R$50 e pode ser abatida se o orçamento final for aprovado.\n\n"
        "No local o técnico verifica o sintoma. Se der para resolver ali, passa o valor para aprovação. "
        "Se precisar retirar ou testar em laboratório, os valores são passados separados.\n\n"
        "Qual período fica melhor para a visita?"
    )


def offer_fixed_hygienization() -> str:
    return (
        "Higienização de split padrão fica R$200 por aparelho, "
        "desde que o equipamento esteja funcionando e instalado dentro do padrão.\n\n"
        "Se o aparelho não estiver climatizando, o atendimento pode virar análise de manutenção por R$50.\n\n"
        "Quantos aparelhos são?"
    )


def offer_hygienization_schedule(quantity: int) -> str:
    total = quantity * 200
    if quantity == 1:
        return (
            f"Perfeito, 1 aparelho.\n\n"
            f"A higienização fica R$200.\n\n"
            f"Qual período fica melhor para atendimento: manhã ou tarde?"
        )
    return (
        f"Perfeito, {quantity} aparelhos.\n\n"
        f"A higienização fica R${total}, considerando R$200 por aparelho.\n\n"
        f"Qual período fica melhor para atendimento: manhã ou tarde?"
    )


def offer_project_visit() -> str:
    return (
        "Esse caso sai do escopo de serviço fixo.\n\n"
        "Para esse tipo de atendimento, fazemos visita técnica ou projeto a partir de R$50 nas proximidades, "
        "podendo ajustar conforme distância e complexidade.\n\n"
        "Me passa cidade/bairro e tipo de ambiente para direcionar certo?"
    )


def save_preferred_window(window: str) -> str:
    return f"Perfeito, deixei a preferência pela {window} anotada.\n\nVou deixar isso separado para o atendimento."


def fallback_recover_context() -> str:
    return (
        "Desculpa, deixa eu organizar por aqui.\n\n"
        "Você quer seguir com instalação, manutenção, higienização ou visita técnica?"
    )


# ── Catálogo indexado por action ───────────────────────────────────────────────
_CATALOG: dict[str, callable] = {
    "welcome_onboarding": welcome_onboarding,
    "answer_services_list": answer_services_list,
    "answer_clarification": answer_clarification,
    "ask_lead_name": ask_lead_name,
    "ask_basic_service": ask_basic_service,
    "offer_fixed_installation": offer_fixed_installation,
    "offer_technical_visit_installation": offer_technical_visit_installation,
    "offer_technical_visit_maintenance": offer_technical_visit_maintenance,
    "offer_fixed_hygienization": offer_fixed_hygienization,
    "offer_hygienization_schedule": lambda q: offer_hygienization_schedule(q),
    "offer_project_visit": offer_project_visit,
    "save_preferred_window": lambda w: save_preferred_window(w),
    "fallback_recover_context": fallback_recover_context,
}


def get_response(action: str, **kwargs) -> str:
    """
    Retorna texto determinístico para uma action.
    Para offer_hygienization_schedule: passar quantity=N.
    Para save_preferred_window: passar window="manha|tarde".
    """
    fn = _CATALOG.get(action)
    if fn is None:
        return fallback_recover_context()

    # Special-cased actions that need parameters
    if action == "offer_hygienization_schedule":
        quantity = kwargs.get("quantity", 1)
        return fn(quantity)
    if action == "save_preferred_window":
        window = kwargs.get("window", "esse período")
        return fn(window)

    # No-arg actions
    try:
        return fn()
    except TypeError:
        # fallback if signature changed
        return fallback_recover_context()