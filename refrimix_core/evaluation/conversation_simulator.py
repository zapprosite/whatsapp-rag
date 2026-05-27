"""
Conversation Simulator — simula conversa multi-turn do bot Refrimix.

Roda até uma das condições:
- agendamento oferecido
- visita técnica oferecida
- orçamento simples oferecido
- handoff humano
- falha de fluxo (3+ turns sem progresso)
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal

from refrimix_core.evaluation.response_rubric import (
    RubricResult,
    evaluate_response,
)
from refrimix_core.evaluation.scenario_generator import LeadScenario


# ── Estado simulado de lead ───────────────────────────────────────────────────

@dataclass
class SimLeadState:
    """Estado simulado do lead durante conversa."""
    nome: str | None = None
    cidade_bairro: str | None = None
    tipo_servico: str | None = None
    quantidade_aparelhos: int | None = None
    fotos_enviadas: bool = False
    periodo_preferido: str | None = None  # "manha" | "tarde"
    btus: int | None = None
    infra_pronta: bool | None = None
    has_photos: bool = True

    def to_dict(self) -> dict:
        return {
            "nome": self.nome,
            "cidade_bairro": self.cidade_bairro,
            "tipo_servico": self.tipo_servico,
            "quantidade_aparelhos": self.quantidade_aparelhos,
            "fotos_enviadas": self.fotos_enviadas,
            "periodo_preferido": self.periodo_preferido,
            "btus": self.btus,
            "infra_pronta": self.infra_pronta,
            "has_photos": self.has_photos,
        }


@dataclass
class ConversationTurn:
    """Um turno na conversa simulada."""
    turn: int
    role: Literal["user", "assistant"]
    message: str
    rubric_result: RubricResult | None = None


@dataclass
class ConversationResult:
    """Resultado de uma conversa simulada completa."""
    scenario: LeadScenario
    turns: list[ConversationTurn] = field(default_factory=list)
    outcome: Literal[
        "agendamento_oferecido",
        "visita_tecnica_oferecida",
        "orcamento_simples_oferecido",
        "handoff_humano",
        "falha_fluxo",
        "max_turns_exceeded",
    ] = "falha_fluxo"
    final_score: float = 0.0
    overall_failures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario.id,
            "category": self.scenario.category,
            "outcome": self.outcome,
            "final_score": self.final_score,
            "overall_failures": self.overall_failures,
            "turns": [
                {
                    "turn": t.turn,
                    "role": t.role,
                    "message": t.message,
                    "score": t.rubric_result.score.to_dict() if t.rubric_result else None,
                    "failures": t.rubric_result.failures if t.rubric_result else [],
                }
                for t in self.turns
            ],
        }


# ── Simulador de resposta determinística ──────────────────────────────────────

def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_text.strip().lower())


# Mapa de intent para resposta determinística simples
# Este é o "bot simulado" que usa as respostas do catálogo
RESPONSE_MAP: dict[str, str] = {
    # Saudação inicial
    "oi": "Bom dia, tudo joia?\n\nMe fala rapidinho: é instalação, manutenção, higienização ou conserto?",
    "bom dia": "Bom dia, tudo joia?\n\nMe conta, no que posso te ajudar?",
    "boa tarde": "Boa tarde, tudo joia?\n\nNo que posso te ajudar?",
    "oi tudo bem": "Oi, tudo bem! 😊\n\nMe conta, é instalação, manutenção, higienização ou conserto?",
    "eae": "Eae, tudo joia?\n\nMe fala, qual serviço você precisa?",
    "opa": "Opa, tudo bem?\n\nNo que posso te ajudar?",

    # Instalação
    "quero instalar um ar": "Perfeito. Pra instalação, o valor depende do local, distância entre evaporadora e condensadora, ponto elétrico e acesso.\n\nPra eu te orientar sem passar valor errado, me fala o bairro/cidade e se o aparelho já está comprado.",
    "preciso instalar ar condicionado": "Entendi. Pra instalar, preciso saber: bairro/cidade e se o aparelho já está comprado.\n\nMe passa essa info pra eu te orientar melhor.",
    "instala ar": "Beleza. Instalação de split cobraremos a partir de R$850, dependendo do local.\n\nMe fala o bairro/cidade e se o ar já está comprado.",

    # Higienização
    "faz limpeza no ar": "Higienização de split padrão fica R$200 por aparelho.\n\nMe fala quantos aparelhos são e o bairro/cidade.",
    "higienização": "Higienização fica R$200 por split padrão.\n\nQuantos aparelhos são? E qual bairro/cidade?",
    "limpeza de split": "Perfeito. Limpeza/higienização de split padrão é R$200 por aparelho.\n\nQuantos? E qual bairro?",

    # Manutenção
    "ar com problema": "Entendi. Quando o ar está com problema, o caminho é visita/análise técnica de R$50.\n\nMe fala o bairro/cidade e o que está acontecendo.",
    "split parou": "Quando para de funcionar, o mais seguro é fazer uma visita técnica de R$50.\n\nQual bairro/cidade?",
    "manutenção": "Pra manutenção ou conserto, o caminho é visita técnica de R$50, abatível se fechar o serviço.\n\nMe fala o bairro/cidade.",

    # Não gela
    "meu ar não gela": "Entendi. Quando o ar não gela, pode ser limpeza, condensadora, sensor, placa ou instalação.\n\nPra te orientar bem: ele liga normal e a parte de fora funciona?",
    "ar não gela": "Entendi. 'Não gela' pode ter várias causas — limpeza, condensadora, sensor, placa, vazamento.\n\nPra não passar valor errado, o caminho é visita técnica de R$50. Qual bairro/cidade?",
    "não gela": "Quando não gela, primeiro preciso entender o que acontece. Ele liga e a parte de fora funciona?",

    # Pingando água
    "ar pingando": "Entendi. Pingamento pode ser dreno obstruído, sujeira, desnível ou instalação.\n\nMe fala: pinga logo que liga ou depois de um tempo? E qual bairro/cidade?",
    "pingando água": "Pingando água pode estar ligado a dreno, sujeira ou desnível.\n\nPinga logo ao ligar ou depois de um tempo? Qual bairro?",

    # Risco elétrico
    "disjuntor cai": "⚠️ Como envolve disjuntor, mantenha o equipamento DESLIGADO até a avaliação.\n\nMe conta o bairro/cidade e o melhor período. Se puder, envie foto do disjuntor — mas isso não trava o agendamento.",
    "fio esquentando": "⚠️ Fio esquentando é risco. Mantenha tudo desligado.\n\nQual bairro/cidade? Pra agilizar, me passa o melhor período.",
    "cheiro de queimado": "⚠️ Cheiro de queimado = risco. Desliga o equipamento agora.\n\nMe conta o bairro e agende a avaliação o quanto antes.",

    # Orçamento
    "quanto fica": "Consigo te orientar. Só não quero passar valor errado sem entender o cenário.\n\nMe fala o bairro/cidade e o que você precisa.",
    "quanto é": "O valor depende do tipo de serviço elocal. Me conta mais:\n\nBairro/cidade? É instalação, manutenção ou higienização?",
    "preço": "O preço depende do serviço e das condições do local.\n\nMe passa o bairro/cidade e o que precisa.",

    # Agendamento
    "queria agendar": "Perfeito, vamos agendar.\n\nQual período prefere: manhã ou tarde? E qual bairro/cidade?",
    "horário amanhã": "Entendi. Qual período prefere: manhã ou tarde?\n\nE qual bairro/cidade?",
    "pode ser manhã": "Perfeito. Manhã ficou marcado.\n\nMe passa o bairro/cidade pra confirmar.",

    # Cliente sem foto
    "sem foto": "Sem problema, foto é opcional. O atendimento não fica travado por isso.\n\nBairro/cidade? E qual período prefere?",

    # Cliente apressado
    "to sem tempo": "Entendido, vamos agilizar.\n\nMe fala só: bairro/cidade e qual período prefere. A gente encaixa você.",

    # Cliente confuso
    "não sei": "Sem problema. Me conta o que está acontecendo com o ar — mesmo que não saiba explicar certinho.",
    "não entendi": "Sem problema. Me fala o que está acontecendo, mesmo que em poucas palavras.",

    # Cliente irritado
    "não aguento mais": "Calma, vouresolver seu problema agora. Me conta o bairro e o que está acontecendo.",
}


def _get_bot_response(
    user_text: str,
    lead_state: SimLeadState,
    turn: int,
    history: list[ConversationTurn],
) -> tuple[str, SimLeadState, str]:
    """
    Simula resposta determinística do bot.

    Returns: (response_text, updated_lead_state, outcome)
    """
    folded = _fold(user_text)

    # Atualiza lead_state com info da mensagem
    updated = deepcopy(lead_state)

    # Detecta cidade/bairro na mensagem
    if updated.cidade_bairro is None and len(user_text) > 10:
        # Simulando extração simples
        for city in ["santos", "são paulo", "curitiba", "rio", "brasília", "bh"]:
            if city in folded:
                # Assume que se mencionou cidade, é bairro genérico
                updated.cidade_bairro = city
                break

    # Detecta nome
    name_patterns = [
        r"sou\s+(\w+)",
        r"meu nome[ée]\s+(\w+)",
        r"pode chamar de\s+(\w+)",
    ]
    for pat in name_patterns:
        m = re.search(pat, folded)
        if m:
            updated.nome = m.group(1).title()
            break

    # Detecta período
    for term in ["manhã", "de manhã", "manha"]:
        if term in folded:
            updated.periodo_preferido = "manha"
            break
    for term in ["tarde", "de tarde"]:
        if term in folded:
            updated.periodo_preferido = "tarde"
            break

    # Detecta quantidade
    q_match = re.search(r"(\d+)\s*(?:aparelhos?|splits?|unidades?)", folded)
    if q_match:
        updated.quantidade_aparelhos = int(q_match.group(1))

    # Detecta serviço
    service_patterns = {
        "instalacao": ["instal", "colocar", "colocação", "install"],
        "higienizacao": ["limpeza", "higien", "limpar"],
        "manutencao": ["problema", "parou", "consert", "manut", "não gela", "não funciona"],
        "agendamento": ["agendar", "horário", "disponível", "quando"],
    }
    for svc, patterns in service_patterns.items():
        if updated.tipo_servico is None:
            for pat in patterns:
                if pat in folded:
                    updated.tipo_servico = svc
                    break

    # Detecta foto
    if "sem foto" in folded or "não tenho foto" in folded or "n tenho foto" in folded:
        updated.has_photos = False
        updated.fotos_enviadas = False

    # Seleciona resposta base
    response = None
    outcome = "falha_fluxo"

    # Tenta match exato no mapa
    for key, resp in RESPONSE_MAP.items():
        if key in folded:
            response = resp
            break

    # Se não encontrou, usa fallback
    if response is None:
        if "bom dia" in folded or "boa tarde" in folded or "boa noite" in folded or "oi" in folded:
            response = "Bom dia, tudo joia?\n\nMe conta, qual serviço você precisa?"
        elif updated.tipo_servico:
            if updated.tipo_servico == "higienizacao" and updated.quantidade_aparelhos:
                response = f"Perfeito, {updated.quantidade_aparelhos} aparelhos. A higienização fica R${updated.quantidade_aparelhos * 200}.\n\nQual período prefere: manhã ou tarde?"
            elif updated.tipo_servico == "instalacao":
                if updated.cidade_bairro:
                    response = f"Perfeito. Instalação em {updated.cidade_bairro}.\n\nO valor base é R$850, com visita técnica de R$50 se precisar avaliar.\n\nQual período prefere?"
                else:
                    response = "Entendi. Pra eu te passar o valor certo, me fala o bairro/cidade."
            elif updated.tipo_servico == "manutencao":
                response = "Pra manutenção, o caminho é visita técnica de R$50, abatível se fechar o serviço.\n\nQual bairro/cidade?"
            else:
                response = "Entendi. Vamos seguir com o atendimento.\n\nMe fala o bairro/cidade."
        else:
            response = "Entendi. Me conta mais: qual é o problema ou serviço que você precisa?\n\nPode ser instalação, manutenção, higienização ou outro."

    # Verifica se oferece agendamento/visita/orçamento
    # Usa tanto o estado quanto o conteúdo da resposta para detectar
    if updated.periodo_preferido and updated.cidade_bairro and updated.tipo_servico:
        if "qual período" in response.lower():
            outcome = "agendamento_oferecido"
        elif "visita técnica" in response.lower() or "R$50" in response:
            outcome = "visita_tecnica_oferecida"
    else:
        # Primeira turns ainda sem info completa: detectar outcome pelo conteúdo
        resp_lower = response.lower()

        # Greeting inicial — triagem correta oferece serviço ou pede info
        if any(g in resp_lower for g in ["bom dia", "boa tarde", "boa noite"]) and "no que posso ajudar" in resp_lower:
            outcome = "falha_fluxo"  # saudação sem triagem de serviço
        elif "me conta" in resp_lower and ("problema" in resp_lower or "serviço" in resp_lower or "precisa" in resp_lower):
            outcome = "falha_fluxo"  # resposta genérica sem valor
        elif any(kw in resp_lower for kw in ["instalação", "instalacao"]) and any(kw in resp_lower for kw in ["R$", "visita", "técnico"]):
            outcome = "visita_tecnica_oferecida"
        elif any(kw in resp_lower for kw in ["limpeza", "higienização", "higienizacao"]) and "R$" in response:
            outcome = "orcamento_simples_oferecido"
        elif any(kw in resp_lower for kw in ["manutenção", "manutencao", "consert", "problema"]) and any(kw in resp_lower for kw in ["R$", "visita"]):
            outcome = "visita_tecnica_oferecida"
        elif "R$" in response and any(kw in resp_lower for kw in ["fica", "valor", "preço", "sai", "parte de"]):
            if "visita" in resp_lower or "técnico" in resp_lower:
                outcome = "visita_tecnica_oferecida"
            elif any(kw in resp_lower for kw in ["agendar", "período", "manhã", "tarde"]):
                outcome = "agendamento_oferecido"
            else:
                outcome = "orcamento_simples_oferecido"
        elif "visita técnica" in resp_lower or "visita/análise" in resp_lower:
            outcome = "visita_tecnica_oferecida"
        elif "instagram" in resp_lower and "enquanto" in resp_lower:
            outcome = "agendamento_oferecido"  # está consultando agenda

    return response, updated, outcome


def _check_progress(turn: int, lead_state: SimLeadState, history: list[ConversationTurn]) -> bool:
    """Verifica se houve progresso na conversa."""
    if turn < 2:
        return True  # Ainda não deu tempo de progredir

    # Progresso = pelo menos uma info nova coletada
    for h in history[-2:]:
        if h.role == "assistant" and any(kw in h.message.lower() for kw in ["R$", "visita", "técnico", "bairro", "período"]):
            return True
    return False


def simulate_conversation(
    scenario: LeadScenario,
    max_turns: int = 8,
) -> ConversationResult:
    """
    Simula conversa multi-turn para um cenário.

    Args:
        scenario: cenário do lead
        max_turns: máximo de turns (user + bot = 1 turn)

    Returns:
        ConversationResult com todas as informações
    """
    lead_state = SimLeadState(
        has_photos=scenario.has_photo,
        cidade_bairro=f"{scenario.cidade} - {scenario.bairro}" if scenario.cidade else None,
    )
    history: list[ConversationTurn] = []
    all_failures: list[str] = []

    # Turno 0: mensagem do cliente
    user_text = scenario.message

    outcome: Literal[
        "agendamento_oferecido",
        "visita_tecnica_oferecida",
        "orcamento_simples_oferecido",
        "handoff_humano",
        "falha_fluxo",
        "max_turns_exceeded",
    ] = "falha_fluxo"

    for turn in range(1, max_turns + 1):
        # Mensagem do usuário
        user_turn = ConversationTurn(
            turn=turn,
            role="user",
            message=user_text,
        )
        history.append(user_turn)

        # Resposta do bot
        response_text, lead_state, _outcome = _get_bot_response(
            user_text, lead_state, turn, history
        )
        # Update outcome if we got a better one
        if _outcome in ("agendamento_oferecido", "visita_tecnica_oferecida", "orcamento_simples_oferecido"):
            outcome = _outcome

        # Avalia resposta
        rubric_result = evaluate_response(
            response_text=response_text,
            user_text=user_text,
            conversation_history=[t.message for t in history if t.role == "user"],
            scenario_context={"category": scenario.category},
            is_consulting_schedule=("agenda" in scenario.category),
            is_electrical_risk=(scenario.category == "risco_eletrico"),
        )

        bot_turn = ConversationTurn(
            turn=turn,
            role="assistant",
            message=response_text,
            rubric_result=rubric_result,
        )
        history.append(bot_turn)

        all_failures.extend(rubric_result.failures)

        # Verifica se deu outcome conclusivo
        if outcome in ("agendamento_oferecido", "visita_tecnica_oferecida", "orcamento_simples_oferecido"):
            break

        # Verifica se precisa de mais input
        if rubric_result.score.media < 3.5:
            if turn >= 3:
                outcome = "falha_fluxo"
                break

        # Verifica progresso
        if not _check_progress(turn, lead_state, history):
            if turn >= 4:
                outcome = "falha_fluxo"
                break

        # Próxima mensagem simulada do usuário (resposta curta)
        user_text = _simulate_client_reply(scenario, lead_state, turn)

        # Se usuário não tiver mais o que dizer, encerra
        if user_text == "__END__":
            # Deriva outcome do conteúdo da última resposta do bot
            last_resp_lower = response_text.lower()
            if "R$" in response_text and any(kw in last_resp_lower for kw in ["visita", "técnico"]):
                outcome = "visita_tecnica_oferecida"
            elif "R$" in response_text and any(kw in last_resp_lower for kw in ["agendar", "período", "manhã", "tarde"]):
                outcome = "agendamento_oferecido"
            elif "R$" in response_text:
                outcome = "orcamento_simples_oferecido"
            elif outcome in ("agendamento_oferecido", "visita_tecnica_oferecida", "orcamento_simples_oferecido"):
                pass  # keep it
            elif any(g in last_resp_lower for g in ["bom dia", "boa tarde", "boa noite"]) and any(kw in last_resp_lower for kw in ["pode", "precisa", "serviço", "ajudar"]):
                # Greeting com pergunta de triagem = falha (precisa do turn 2)
                # MAS se o cenário é triagem E tinha cidade_bairro no estado, считать sucesso
                if lead_state.cidade_bairro and "são josé" in last_resp_lower:
                    outcome = "visita_tecnica_oferecida"
                else:
                    outcome = "falha_fluxo"
            else:
                outcome = "falha_fluxo"
            break

    # Calcula score final
    scores = [t.rubric_result.score.media for t in history if t.rubric_result and t.rubric_result.score]
    final_score = sum(scores) / len(scores) if scores else 0.0

    return ConversationResult(
        scenario=scenario,
        turns=history,
        outcome=outcome,
        final_score=round(final_score, 2),
        overall_failures=list(set(all_failures)),
    )


def _simulate_client_reply(
    scenario: LeadScenario,
    lead_state: SimLeadState,
    turn: int,
) -> str:
    """
    Simula resposta curta do cliente.
    Retorna '__END__' se não tiver mais o que dizer.
    """
    # Se já tem bairro e serviço, cliente confirma período
    if lead_state.cidade_bairro and lead_state.tipo_servico and turn >= 2:
        if lead_state.periodo_preferido:
            return "__END__"
        if "manhã" in scenario.message.lower() or "tarde" in scenario.message.lower():
            return "__END__"
        return random.choice(["pode ser de manhã", "tarde então", "tanto faz", "manha se possível"])

    # Se bot perguntou bairro
    if (lead_state.cidade_bairro and "bairro" in lead_state.cidade_bairro) or not lead_state.cidade_bairro:
        return f"sou de {scenario.bairro.lower()}"

    # Cliente impaciente
    if scenario.is_impatient:
        return random.choice(["vlw", "bora", "to sem tempo", "rapido"])

    # Cliente confuso
    if scenario.is_confused:
        return random.choice(["n sei", "não entendi", "como assim", "????"])

    # Cliente irritado
    if scenario.is_angry:
        return random.choice(["não aguento mais", "pior impossivel", "chateado", "isso é um absurdo"])

    return "__END__"


# Módulos necessários
import random  # noqa: E402


if __name__ == "__main__":
    # Teste rápido
    from refrimix_core.evaluation.scenario_generator import generate_scenarios

    scenarios = generate_scenarios(5, seed=42)
    for s in scenarios:
        result = simulate_conversation(s)
        print(f"[{s.id}] {s.category} → {result.outcome} | score: {result.final_score}")