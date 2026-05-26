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
        saudacao = ctx.greeting or "Olá"
        return f"{saudacao}, tudo joia?\n\nComo posso te ajudar hoje?"

    # 2. ask_lead_name
    elif action_type == "ask_lead_name":
        if ctx.greeting:
            prefix = f"{ctx.greeting}, tudo joia?\n\n"
        elif ctx.service:
            prefix = f"{_service_ack(ctx.service)}\n\n"
        else:
            prefix = "Perfeito.\n\n"
        return f"{prefix}Me passa seu nome pra eu deixar o atendimento certinho?"

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

    # 5, 6, 7. offer_technical_visit (depending on service)
    elif action_type == "offer_technical_visit":
        if ctx.service == "instalacao":
            return (
                "Sem problema.\n\n"
                "A foto ajuda a adiantar, mas não trava o atendimento.\n\n"
                "Como ainda falta confirmar o local completo, seguimos como visita técnica de R$50. Se o orçamento final for aprovado, esse valor pode ser abatido.\n\n"
                "Qual período fica melhor: manhã ou tarde?"
            )
        elif ctx.service == "manutencao":
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

    # 9. offer_project_visit
    elif action_type == "offer_project_visit":
        return (
            "Esse caso sai do escopo de serviço fixo.\n\n"
            "Para esse tipo de atendimento, fazemos visita técnica ou projeto a partir de R$50 nas proximidades, podendo ajustar conforme distância e complexidade.\n\n"
            "Me passa cidade/bairro e tipo de ambiente para direcionar certo?"
        )

    # 10, 11, 12. explain_last_offer (based on commercial_path / last_offer_path)
    elif action_type == "explain_last_offer":
        path = ctx.commercial_path or ctx.last_offer_path
        if path == "technical_visit_50":
            return (
                "Claro.\n\n"
                "Quando não dá para confirmar tudo por mensagem, a gente não trava o atendimento.\n\n"
                "Nesse caso fazemos uma visita técnica de R$50. O técnico avalia no local e, se você aprovar o orçamento final, esse valor pode ser abatido.\n\n"
                "Aí você não precisa ter todas as fotos ou informações agora.\n\n"
                "Podemos agendar a visita?"
            )
        elif path == "fixed_installation_simple":
            return (
                "Claro.\n\n"
                "Instalação simples é quando o aparelho fica costa/costa, até 3 metros, com acesso fácil e ponto elétrico individual.\n\n"
                "Nesse cenário, fica R$850 com material e mão de obra. Se no local tiver algo fora do padrão, o técnico explica antes de qualquer ajuste.\n\n"
                "Podemos seguir com o agendamento?"
            )
        elif path == "fixed_hygienization":
            return (
                "Claro.\n\n"
                "A higienização é uma limpeza mais completa do split, indicada para sujeira acumulada, cheiro ruim, mofo ou muito tempo sem manutenção.\n\n"
                "Em split padrão funcionando, fica R$200 por aparelho.\n\n"
                "Podemos agendar a higienização?"
            )
        else:
            # Fallback/processo
            return (
                "Funciona assim: primeiro identificamos se entra em instalação simples ou se precisa de visita técnica.\n\n"
                "Quando tem tudo dentro do padrão, como a evaporadora e a condensadora costa/costa, até 3 metros e acesso fácil, fica R$850.\n\n"
                "Quando falta foto, infraestrutura ou confirmação do local, seguimos como visita técnica de R$50, abatível se o orçamento final for aprovado.\n\n"
                "Podemos agendar a visita?"
            )

    # 13. explain_process
    elif action_type == "explain_process":
        return (
            "Funciona assim: primeiro identificamos se entra em instalação simples ou se precisa de visita técnica.\n\n"
            "Quando tem tudo dentro do padrão, como a evaporadora e a condensadora costa/costa, até 3 metros e acesso fácil, fica R$850.\n\n"
            "Quando falta foto, infraestrutura ou confirmação do local, seguimos como visita técnica de R$50, abatível se o orçamento final for aprovado.\n\n"
            "Podemos agendar a visita?"
        )

    # 14. answer_capability_question
    elif action_type == "answer_capability_question":
        if ctx.service == "higienizacao":
            return (
                "Sim, também trabalhamos com higienização.\n\n"
                "Em split padrão, fica R$200 por aparelho. Ajuda quando tem cheiro ruim, sujeira acumulada, mofo ou muito tempo sem limpeza.\n\n"
                "Se quiser incluir também, me confirma quantos aparelhos são."
            )
        else:
            return "Sim, também trabalhamos com esse serviço.\n\nSe você quiser, eu já te explico como funciona nesse caso."

    # 15. save_preferred_window
    elif action_type == "save_preferred_window":
        window = ctx.preferred_window or "esse período"
        if ctx.missing_field:
            return (
                f"Perfeito, deixei a preferência pela {window} anotada.\n\n"
                f"Antes disso, ainda preciso de {_missing_field_human(ctx.missing_field)}."
            )
        return f"Perfeito, deixei a preferência pela {window} anotada.\n\nAgora vou seguir com o atendimento por esse período."

    # 16. calendar_not_enabled
    elif action_type == "calendar_not_enabled":
        return "Consigo seguir com o agendamento por aqui.\n\nMe confirma o melhor período: manhã ou tarde?"

    # 17. fallback_recover_context
    elif action_type == "fallback_recover_context":
        return (
            "Consigo te ajudar sim. Você quer instalação, manutenção ou higienização?"
        )

    # Outras respostas estruturadas para manter compose_response limpa
    elif action_type == "reject_security":
        return "Não consigo seguir por esse caminho. Se a sua dúvida for sobre ar-condicionado, me fala em uma frase simples o que você precisa."

    elif action_type == "handoff_human":
        return "Entendi. Vou deixar isso sinalizado para atendimento humano e adiantar o contexto por aqui."

    elif action_type == "ask_optional_contact_info":
        return "Se tiver e-mail, pode me mandar também pra ficar registrado no atendimento."

    elif action_type == "ask_missing_field":
        field_questions = {
            "cidade_bairro": "Em qual cidade e bairro fica o atendimento?",
            "btus": "Qual é a capacidade do aparelho em BTUs?",
            "foto_local_interno": "Pode me mandar uma foto do ponto onde vai a unidade interna?",
            "foto_local_externo": "Pode me mandar uma foto do local da condensadora?",
            "foto_disjuntor": "Pode me mandar uma foto do quadro de luz?",
            "foto_aparelho": "Pode me mandar uma foto do aparelho?",
            "ponto_eletrico_exclusivo": "Já tem ponto elétrico exclusivo para o ar?",
            "distancia_aproximada": "A distância entre as unidades fica perto de quantos metros?",
            "tubulacao_existente": "Já existe tubulação/infra pronta no local?",
            "tempo_sem_manutencao": "Faz quanto tempo que não passa por manutenção?",
            "pinga_agua": "Ele está pingando água?",
            "nome": "Me passa seu nome pra eu deixar o atendimento certinho?",
            "address": "Pra deixar a visita certinha, me manda o endereço ou pelo menos bairro e referência?",
            "email": "Se tiver e-mail, pode me mandar também pra ficar registrado no atendimento.",
        }
        return field_questions.get(ctx.missing_field or "", "Me conta só o detalhe principal pra eu te orientar certo?")

    elif action_type == "confirm_calendar_slot":
        return f"Perfeito, deixei separada a opção de {ctx.preferred_window or 'horário escolhido'} para confirmação."

    # Se for uma ação desconhecida ou não listada
    return (
        "Consigo te ajudar sim. Você quer instalação, manutenção ou higienização?"
    )
