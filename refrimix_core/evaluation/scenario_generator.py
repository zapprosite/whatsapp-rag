"""
Scenario Generator — gera 100 cenários realistas de lead brasileiro.

Cada cenário inclui:
- mensagem inicial (texto ou áudio transcrito)
- distribuição por categoria
- erros de digitação, gírias, mensagens quebradas, cliente impaciente
- cidade/bairro brasileiro real
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Literal

# ── Distribuição dos 100 cenários ─────────────────────────────────────────────
CATEGORY_DISTRIBUTION = {
    "saudacao_triagem": 10,
    "instalacao": 12,
    "higienizacao": 12,
    "manutencao_conserto": 12,
    "nao_gela": 10,
    "pingando_agua": 8,
    "risco_eletrico": 8,
    "orcamento_preco": 6,
    "agendamento": 6,
    "sem_foto": 5,
    "cliente_apressado": 4,
    "cliente_confuso": 3,
    "cliente_irritado": 2,
    "alto_valor_projeto": 2,
}

# ── Cidades e bairros brasileiros ─────────────────────────────────────────────
BAIRROS_CIDADES = [
    ("São Paulo", "Jardins"),
    ("São Paulo", "Moema"),
    ("São Paulo", "Vila Madalena"),
    ("São Paulo", "Itaim Bibi"),
    ("São Paulo", "Pinheiros"),
    ("São Paulo", "Tatuapé"),
    ("São Paulo", "Santana"),
    ("São Paulo", "Campo Belo"),
    ("Rio de Janeiro", "Copacabana"),
    ("Rio de Janeiro", "Ipanema"),
    ("Rio de Janeiro", "Barra da Tijuca"),
    ("Rio de Janeiro", "Niterói"),
    ("Santos", " Gonzaga"),
    ("Santos", "Pompeia"),
    ("Santos", "José Menino"),
    ("Curitiba", "Batel"),
    ("Curitiba", "Água Verde"),
    ("Curitiba", "Centro"),
    ("Florianópolis", "Centro"),
    ("Florianópolis", "Jurerê"),
    ("Belo Horizonte", "Savassi"),
    ("Belo Horizonte", "Lourdes"),
    ("Porto Alegre", "Moinhos de Vento"),
    ("Porto Alegre", "Rio Branco"),
    ("Brasília", "Asa Sul"),
    ("Brasília", "Asa Norte"),
    ("Salvador", "Pituba"),
    ("Salvador", "Barra"),
    ("Recife", "Boa Viagem"),
    ("Fortaleza", "Meireles"),
    ("Natal", "Ponta Negra"),
    ("Goiânia", "Setor Bueno"),
    ("Campinas", "Cambuí"),
    ("Ribeirão Preto", "Centro"),
    ("São José dos Campos", "Centro"),
    ("Santo André", "Centro"),
    ("Guarulhos", "Centro"),
    ("Osasco", "Vila Yara"),
    ("Maceió", "Ponta Verde"),
    ("Aracaju", "Coroa do Meio"),
]

# ── Nomes brasileiros ─────────────────────────────────────────────────────────
NOMES = [
    "Carlos", "Mariana", "Roberto", "Fernanda", "André", "Patrícia",
    "Ricardo", "Juliana", "Paulo", "Camila", "Fernando", "Adriana",
    "Gustavo", "Renata", "Thiago", "Luciana", "Diego", "Vanessa",
    "Leandro", "Cristina", "Marcos", "Simone", "Rafael", "Beatriz",
    "Eduardo", "Aline", "Felipe", "Natália", "Daniel", "Priscila",
]

# ── Padrões de linguagem WhatsApp brasileira ──────────────────────────────────
# Erros de digitação comuns
TYPOS = {
    "quarto": "qto",
    "quanto": "qto",
    "estou": "to",
    "não": "n",
    "para": "pra",
    "você": "vc",
    "também": "tb",
    "está": "ta",
    "eles": "eles",
    "tenho": "tenhu",
    "pode": "pde",
    "mais": "ms",
    "vou": "vou",
    "hoje": "oj",
    "amanhã": "amnh",
    "agora": "agr",
    "então": "entao",
    "entendi": "enti",
    "problema": "pbl",
    "técnico": "tec",
    "técnica": "tec",
    "problema": "prob",
    "apareceu": "aprc",
    "ligou": "lig",
    "desligou": "deslig",
}

# Gírias e contrações brasileiras
GIRIAS = [
    "vlw", "tmj", "bgl", "krl", "pq", "oq", "msm", "td", "blz", "flw",
    "eh q", "n sei", "vou ver", "meu", "to aqui", "pode ser", "ah sim",
]

# Rubricas de mensagem por categoria
CATEGORY_MESSAGES: dict[str, list[tuple[str, str]]] = {
    # (mensagem_normalizada, intent_sintetico)
    "saudacao_triagem": [
        ("oi", "greeting"),
        ("bom dia", "greeting"),
        ("boa tarde", "greeting"),
        ("oi tudo bem", "greeting"),
        ("oi boa noite", "greeting"),
        ("olá", "greeting"),
        ("eae", "greeting"),
        ("opa", "greeting"),
        ("oi tudo joia", "greeting"),
        ("bom dia tudo bem", "greeting"),
    ],
    "instalacao": [
        ("quero instalar um ar", "service_request"),
        ("preciso instalar ar condicionado", "service_request"),
        ("instala ar", "service_request"),
        ("vou colocar um split", "service_request"),
        ("instala split", "service_request"),
        ("colocar ar", "service_request"),
        ("instalação de ar", "service_request"),
        ("fazer instalação", "service_request"),
        ("instalar split 12000", "service_request"),
        ("colocar split", "service_request"),
        ("install ar", "service_request"),
        ("quisera colocar um ar", "service_request"),
    ],
    "higienizacao": [
        ("faz limpeza no ar", "service_request"),
        ("higienização", "service_request"),
        ("limpeza de split", "service_request"),
        ("fazer limpeza do ar", "service_request"),
        ("limpar ar", "service_request"),
        ("higienizar split", "service_request"),
        ("limpeza do ar condicionado", "service_request"),
        ("faz limpeza", "service_request"),
        ("queria limpar o ar", "service_request"),
        ("limpeza de ar", "service_request"),
        ("preciso de limpeza", "service_request"),
        ("fazer hygiene", "service_request"),
    ],
    "manutencao_conserto": [
        ("ar com problema", "service_request"),
        ("split parou", "service_request"),
        ("manutenção", "service_request"),
        ("conserto", "service_request"),
        ("ar não funciona", "service_request"),
        ("equipamento com defeito", "service_request"),
        ("manutenção split", "service_request"),
        ("consertar ar", "service_request"),
        ("ar quebrou", "service_request"),
        ("problema no split", "service_request"),
        ("preciso de conserto", "service_request"),
        ("manutençao", "service_request"),
    ],
    "nao_gela": [
        ("meu ar não gela", "symptom"),
        ("ar não gela", "symptom"),
        ("não gela", "symptom"),
        ("ar frio fraco", "symptom"),
        ("não gela direito", "symptom"),
        ("não faz frio", "symptom"),
        ("quente", "symptom"),
        ("ar ligando mas não gela", "symptom"),
        ("quase não gela", "symptom"),
        ("gela pouco", "symptom"),
    ],
    "pingando_agua": [
        ("ar pingando", "symptom"),
        ("pingando água", "symptom"),
        ("ta pingando", "symptom"),
        ("gotejando", "symptom"),
        ("água caindo", "symptom"),
        ("pingo", "symptom"),
        ("ar está pingando", "symptom"),
        ("vazamento", "symptom"),
    ],
    "risco_eletrico": [
        ("disjuntor cai", "safety_risk"),
        ("disjuntor caindo", "safety_risk"),
        ("fio esquentando", "safety_risk"),
        ("cheiro de queimado", "safety_risk"),
        ("tomada derretendo", "safety_risk"),
        ("faísca", "safety_risk"),
        ("disjuntor desarmando", "safety_risk"),
        ("curto", "safety_risk"),
    ],
    "orcamento_preco": [
        ("quanto fica", "price_question"),
        ("quanto é", "price_question"),
        ("preço", "price_question"),
        ("valor", "price_question"),
        ("orcamento", "price_question"),
        ("manda o valor", "price_question"),
        ("qto fica", "price_question"),
        ("quanto", "price_question"),
        ("qual valor", "price_question"),
    ],
    "agendamento": [
        ("queria agendar", "scheduling"),
        ("horário amanhã", "scheduling"),
        ("pode ser manhã", "scheduling"),
        ("agendar", "scheduling"),
        ("quando dá", "scheduling"),
        ("tem horário", "scheduling"),
        ("disponibilidade", "scheduling"),
        ("agenda", "scheduling"),
    ],
}


@dataclass
class LeadScenario:
    """Um cenário de lead brasileiro realista."""
    id: int
    category: str
    message: str  # mensagem original (pode ter erro, gíria, etc)
    message_type: Literal["text", "audio_transcribed"] = "text"
    cidade: str = ""
    bairro: str = ""
    has_photo: bool = True
    is_urgent: bool = False
    is_impatient: bool = False
    is_confused: bool = False
    is_angry: bool = False
    is_audio_allowed: bool = True  # se pode receber resposta em áudio
    expected_outcome: Literal[
        "agendamento_oferecido", "visita_tecnica_oferecida",
        "orcamento_simples_oferecido", "handoff_humano", "falha_fluixo"
    ] = "visita_tecnica_oferecida"
    intent_sintetico: str = ""
    lead_name: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "message": self.message,
            "message_type": self.message_type,
            "cidade": self.cidade,
            "bairro": self.bairro,
            "has_photo": self.has_photo,
            "is_urgent": self.is_urgent,
            "is_impatient": self.is_impatient,
            "is_confused": self.is_confused,
            "is_angry": self.is_angry,
            "is_audio_allowed": self.is_audio_allowed,
            "expected_outcome": self.expected_outcome,
            "intent_sintetico": self.intent_sintetico,
            "lead_name": self.lead_name,
        }


def _apply_typo(text: str) -> str:
    """Aplica erros de digitação simulados ao texto."""
    words = text.split()
    result = []
    for word in words:
        if random.random() < 0.15:  # 15% chance de typo por palavra
            for old, new in TYPOS.items():
                if old in word.lower():
                    # Substitui de forma simples
                    pattern = re.compile(re.escape(old), re.IGNORECASE)
                    word = pattern.sub(new, word)
                    break
        result.append(word)
    return " ".join(result)


def _add_giria(text: str) -> str:
    """Adiciona gíria brasileira ao final da mensagem."""
    if random.random() < 0.3:
        giria = random.choice(GIRIAS)
        text = f"{text} {giria}"
    return text


def _maybe_drop_message(text: str) -> str:
    """Simula mensagem quebrada/incompleta."""
    if random.random() < 0.2:
        words = text.split()
        # Remove caracteres do meio ou encurta aleatoriamente
        if len(words) > 2:
            keep = random.randint(1, max(1, len(words) - 1))
            text = " ".join(words[:keep])
    return text


def _extract_intent(messages: list[tuple[str, str]], category: str) -> str:
    """Extrai intent sintético do par (mensagem, intent)."""
    if category in CATEGORY_MESSAGES:
        for msg, intent in CATEGORY_MESSAGES[category]:
            if random.random() < 0.3:
                return intent
    return "unknown"


def generate_scenarios(count: int = 100, seed: int | None = None) -> list[LeadScenario]:
    """
    Gera `count` cenários realistas de lead brasileiro.

    Cada cenário é desenhado da distribuição CATEGORY_DISTRIBUTION
    com possibilidade de aplicar modificadores (sem foto, apressado, etc).
    """
    if seed is not None:
        random.seed(seed)

    scenarios: list[LeadScenario] = []
    scenario_id = 1

    # Distribui cenários por categoria
    remaining = count
    category_quotas = dict(CATEGORY_DISTRIBUTION)

    for category, quota in category_quotas.items():
        n = min(quota, remaining)
        for _ in range(n):
            msg_list = CATEGORY_MESSAGES.get(category, [])

            # Seleciona mensagem base
            if msg_list:
                base_msg, intent_sintetico = random.choice(msg_list)
            else:
                base_msg = "oi"
                intent_sintetico = "greeting"

            # Aplica variação de linguagem
            message = base_msg
            if random.random() < 0.4:
                message = _apply_typo(message)
            if random.random() < 0.3:
                message = _add_giria(message)
            if random.random() < 0.2:
                message = _maybe_drop_message(message)

            # Atribui cidade/bairro
            cidade, bairro = random.choice(BAIRROS_CIDADES)

            # Atribui nome
            lead_name = random.choice(NOMES)

            # Define tipo de mensagem
            message_type: Literal["text", "audio_transcribed"] = "text"
            if random.random() < 0.08:  # 8% são áudio transcrito
                message_type = "audio_transcribed"
                # Áudio transcrito costuma ter mais ruído
                message = _apply_typo(message)

            # Aplica modificadores de cenário
            is_audio_allowed = True
            if category == "sem_foto" or random.random() < 0.05:
                is_audio_allowed = random.choice([True, False])

            # Define outcome esperado
            if category == "agendamento":
                outcome: Literal[
                    "agendamento_oferecido", "visita_tecnica_oferecida",
                    "orcamento_simples_oferecido", "handoff_humano", "falha_fluixo"
                ] = "agendamento_oferecido"
            elif category == "risco_eletrico":
                outcome = "visita_tecnica_oferecida"
            elif category == "orcamento_preco":
                outcome = "orcamento_simples_oferecido"
            else:
                outcome = "visita_tecnica_oferecida"

            scenario = LeadScenario(
                id=scenario_id,
                category=category,
                message=message,
                message_type=message_type,
                cidade=cidade,
                bairro=bairro,
                has_photo=(category != "sem_foto"),
                is_urgent=(category == "risco_eletrico"),
                is_impatient=(category == "cliente_apressado"),
                is_confused=(category == "cliente_confuso"),
                is_angry=(category == "cliente_irritado"),
                is_audio_allowed=is_audio_allowed,
                expected_outcome=outcome,
                intent_sintetico=intent_sintetico,
                lead_name=lead_name,
            )
            scenarios.append(scenario)
            scenario_id += 1
            remaining -= 1

    # Se ainda faltam cenários, preenche com categorias gerais
    while remaining > 0:
        category = "saudacao_triagem" if remaining <= 5 else random.choice(list(CATEGORY_DISTRIBUTION.keys()))
        quota = CATEGORY_DISTRIBUTION.get(category, 1)
        if remaining < quota:
            category = "saudacao_triagem"

        msg_list = CATEGORY_MESSAGES.get(category, [("oi", "greeting")])
        base_msg, intent_sintetico = random.choice(msg_list)

        cidade, bairro = random.choice(BAIRROS_CIDADES)
        lead_name = random.choice(NOMES)

        scenario = LeadScenario(
            id=scenario_id,
            category=category,
            message=base_msg,
            message_type="text",
            cidade=cidade,
            bairro=bairro,
            has_photo=True,
            expected_outcome="visita_tecnica_oferecida",
            intent_sintetico=intent_sintetico,
            lead_name=lead_name,
        )
        scenarios.append(scenario)
        scenario_id += 1
        remaining -= 1

    return scenarios[:count]


def scenarios_to_jsonl(scenarios: list[LeadScenario], path: str) -> None:
    """Salva cenários em formato JSONL."""
    with open(path, "w", encoding="utf-8") as f:
        for scenario in scenarios:
            import json
            f.write(json.dumps(scenario.to_dict(), ensure_ascii=False) + "\n")


def load_scenarios_from_jsonl(path: str) -> list[LeadScenario]:
    """Carrega cenários de um arquivo JSONL."""
    scenarios = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            import json
            data = json.loads(line)
            scenarios.append(LeadScenario(**data))
    return scenarios


if __name__ == "__main__":
    scenarios = generate_scenarios(100, seed=42)
    print(f"Gerados {len(scenarios)} cenários")
    for s in scenarios[:5]:
        print(f"  [{s.id}] {s.category}: {s.message}")