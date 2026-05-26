from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ResponseContext:
    greeting: str | None = None
    service: str | None = None
    name: str | None = None
    city_bairro: str | None = None
    commercial_path: str | None = None
    price: int | None = None
    deductible_if_approved: bool = False
    preferred_window: str | None = None
    missing_field: str | None = None
    last_offer_path: str | None = None
    quantidade_aparelhos: int | None = None

def _service_ack(service: str | None) -> str:
    mapping = {
        "instalacao": "Consigo te ajudar com instalação sim.",
        "higienizacao": "Consigo te ajudar com higienização sim.",
        "manutencao": "Consigo te ajudar com manutenção sim.",
        "conserto": "Consigo te ajudar com conserto sim.",
    }
    return mapping.get(service or "", "Consigo te ajudar sim.")

def _missing_field_human(field: str | None) -> str:
    mapping = {
        "foto_local_externo": "a foto do local externo onde ficaria a condensadora",
        "foto_local_interno": "a foto do local interno onde ficaria a evaporadora",
        "ponto_eletrico_exclusivo": "a confirmação do ponto elétrico exclusivo",
        "cidade_bairro": "a cidade e o bairro",
        "btus": "a capacidade em BTUs ou o modelo do aparelho",
    }
    return mapping.get(field or "", "um detalhe importante")

def render_response(action_type: str, ctx: ResponseContext) -> str:
    # 1. welcome_onboarding
    if action_type == "welcome_onboarding":
        return "Bom dia, tudo joia?\n\nComo posso te ajudar hoje?"

    # 2. ask_lead_name
    elif action_type == "ask_lead_name":
        return "Perfeito.\n\nMe passa seu nome pra eu deixar o atendimento certinho?"

    # 3. ask_basic_service
    elif action_type == "ask_basic_service":
        return "Entendi.\n\nIsso é instalação, manutenção, higienização ou conserto?"

    # 4. offer_fixed_installation
    elif action_type == "offer_fixed_installation":
        return (
            "Perfeito.\n\n"
            "Instalação simples costa/costa, até 3 metros e com acesso fácil, fica R$850 com material e mão de obra.\n\n"
            "Esse valor considera ponto elétrico individual e cenário dentro do padrão. Se no local tiver algo fora disso, o técnico explica antes e o valor pode ajustar.\n\n"
            "Qual período fica melhor: manhã ou tarde?"
        )

    # 5. offer_technical_visit_installation
    elif action_type in ("offer_technical_visit_installation", "offer_technical_visit_instalacao"):
        return (
            "Sem problema.\n\n"
            "A foto ajuda a adiantar, mas não trava o atendimento.\n\n"
            "Como ainda falta confirmar o local completo, seguimos como visita técnica de R$50. Se o orçamento final for aprovado, esse valor pode ser abatido.\n\n"
            "Qual período fica melhor: manhã ou tarde?"
        )

    # 6. offer_technical_visit_maintenance
    elif action_type in ("offer_technical_visit_maintenance", "offer_technical_visit_manutencao"):
        return (
            "Para manutenção, o caminho correto é visita/análise técnica.\n\n"
            "A visita fica R$50 e pode ser abatida se o orçamento final for aprovado.\n\n"
            "No local o técnico verifica o sintoma. Se der para resolver ali, passa o valor para aprovação. Se precisar retirar ou testar em laboratório, os valores são passados separados.\n\n"
            "Qual período fica melhor para a visita?"
        )

    # Generic offer_technical_visit fallback
    elif action_type == "offer_technical_visit":
        if ctx.service == "instalacao":
            return (
                "Sem problema.\n\n"
                "A foto ajuda a adiantar, mas não trava o atendimento.\n\n"
                "Como ainda falta confirmar o local completo, seguimos como visita técnica de R$50. Se o orçamento final for aprovado, esse valor pode ser abatido.\n\n"
                "Qual período fica melhor: manhã ou tarde?"
            )
        elif ctx.service in ("manutencao", "conserto"):
            return (
                "Para manutenção, o caminho correto é visita/análise técnica.\n\n"
                "A visita fica R$50 e pode ser abatida se o orçamento final for aprovado.\n\n"
                "No local o técnico verifica o sintoma. Se der para resolver ali, passa o valor para aprovação. Se precisar retirar ou testar em laboratório, os valores são passados separados.\n\n"
                "Qual período fica melhor para a visita?"
            )
        else:
            return (
                "Seguimos como visita técnica de R$50.\n\n"
                "Esse valor pode ser abatido se o orçamento final for aprovado.\n\n"
                "Qual período fica melhor: manhã ou tarde?"
            )

    # 8. offer_fixed_hygienization
    elif action_type == "offer_fixed_hygienization":
        return (
            "Higienização de split padrão fica R$200 por aparelho, desde que o equipamento esteja funcionando e instalado dentro do padrão.\n\n"
            "Se o aparelho não estiver climatizando, o atendimento pode virar análise de manutenção por R$50.\n\n"
            "Quantos aparelhos são?"
        )

    # 8b. offer_hygienization_schedule
    elif action_type == "offer_hygienization_schedule":
        qty = ctx.quantidade_aparelhos or 1
        total = qty * 200
        plural = "s" if qty > 1 else ""
        if not ctx.city_bairro:
            return (
                f"Perfeito, {qty} aparelho{plural}.\n\n"
                f"Me passa a cidade e bairro para eu direcionar o atendimento?"
            )
        else:
            if qty == 1:
                return (
                    "Perfeito, 1 aparelho.\n\n"
                    "A higienização fica R$200.\n\n"
                    "Qual período fica melhor para atendimento: manhã ou tarde?"
                )
            else:
                return (
                    f"Perfeito, {qty} aparelhos.\n\n"
                    f"A higienização fica R${total}, considerando R$200 por aparelho.\n\n"
                    f"Qual período fica melhor para atendimento: manhã ou tarde?"
                )

    # 9. offer_project_visit
    elif action_type == "offer_project_visit":
        return (
            "Esse caso sai do escopo de serviço fixo.\n\n"
            "Para esse tipo de atendimento, fazemos visita técnica ou projeto a partir de R$50 nas proximidades, podendo ajustar conforme distância e complexidade.\n\n"
            "Me passa cidade/bairro e tipo de ambiente para direcionar certo?"
        )

    # 10. save_preferred_window
    elif action_type == "save_preferred_window":
        window = ctx.preferred_window or "manhã ou tarde"
        return (
            f"Perfeito, deixei a preferência pela {window} anotada.\n\n"
            "Vou deixar isso separado para o atendimento."
        )

    # 11. fallback_recover_context
    elif action_type == "fallback_recover_context":
        return (
            "Desculpa, deixa eu organizar por aqui.\n\n"
            "Você quer seguir com instalação, manutenção, higienização ou visita técnica?"
        )

    # 12. answer_services_list
    elif action_type == "answer_services_list":
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

    # 13. answer_clarification / answer_clarification_llm
    elif action_type in ("answer_clarification", "answer_clarification_llm"):
        return (
            "Claro, vou explicar de forma simples.\n\n"
            "Se for instalação simples, o valor base é R$850.\n\n"
            "Se faltar alguma informação, foto ou precisar avaliar o local, seguimos como visita técnica de R$50. Esse valor pode ser abatido se o orçamento final for aprovado.\n\n"
            "Para higienização, split padrão funcionando fica R$200 por aparelho.\n\n"
            "Qual serviço você quer ver primeiro?"
        )

    # Extra fallbacks and side actions to keep imports safe
    elif action_type == "reject_security":
        return "Não consigo seguir por esse caminho. Se a sua dúvida for sobre ar-condicionado, me fala em uma frase simples o que você precisa."

    elif action_type == "handoff_human":
        return "Entendi. Vou deixar isso sinalizado para atendimento humano e adiantar o contexto por aqui."

    elif action_type == "explain_process":
        return (
            "Funciona assim: primeiro identificamos se entra em instalação simples ou se precisa de visita técnica.\n\n"
            "Quando tem tudo dentro do padrão, como a evaporadora e a condensadora costa/costa, até 3 metros e acesso fácil, fica R$850.\n\n"
            "Quando falta foto, infraestrutura ou confirmação do local, seguimos como visita técnica de R$50, abatível se o orçamento final for aprovado.\n\n"
            "Podemos agendar a visita?"
        )

    elif action_type == "ask_missing_field":
        field_questions = {
            "cidade_bairro": "Em qual cidade e bairro fica o atendimento?",
            "btus": "Qual é a capacidade do aparelho em BTUs?",
            "nome": "Me passa seu nome pra eu deixar o atendimento certinho?",
            "address": "Pra deixar a visita certinha, me manda o endereço ou pelo menos bairro e referência?",
        }
        return field_questions.get(ctx.missing_field or "", "Me conta só o detalhe principal pra eu te orientar certo?")

    return "Desculpa, deixa eu organizar por aqui.\n\nVocê quer seguir com instalação, manutenção, higienização ou visita técnica?"
