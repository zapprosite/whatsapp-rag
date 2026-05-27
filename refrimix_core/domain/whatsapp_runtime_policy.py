"""
whatsapp_runtime_policy.py — Regras de negócio do WhatsApp Runtime.

Invioláveis:
1. Nome, foto, marca, BTUs = dados úteis, não bloqueiam visita
2. Dados técnicos incompletos = preço fechado bloqueado, visita técnica NÃO bloqueada
3. Caso elétrico = primeiro orientamos desligar, depois analisamos
4. Instagram = momento útil SOMENTE (agendamento confirmado, cliente pediu)
5. Máximo 2 perguntas por resposta
6. No máximo 1 microcopy antes da resposta final
7. "Como posso ajudar?" proibido se cliente já falou o problema
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ElectricalRisk(Enum):
    NONE = "none"
    SUSPECTED = "suspected"   # mencionou disjuntor/fio/tomada
    CONFIRMED = "confirmed"   # cheira de queimado, faísca


@dataclass(frozen=True)
class RuntimePolicyResult:
    should_block: bool
    reason: str | None
    safe_directive: str | None  # Orientação de segurança se elétrico
    block_price: bool   # Bloqueia preço fechado mas não visita técnica


# ── Regras elétricas ─────────────────────────────────────────────────────────

ELECTRICAL_KEYWORDS = (
    "disjuntor",
    "fio",
    "fios",
    "tomada",
    "tomadas",
    "elétrico",
    "eletrico",
    "energia",
    "curto",
    "curto-circuito",
    "faísca",
    "faisca",
    "cheiro de queimado",
    "cheiro de queima",
    "rated",
    "tomada esquentando",
)


def check_electrical_risk(text: str) -> ElectricalRisk:
    """Avalia nível de risco elétrico na mensagem."""
    lowered = text.lower()
    critical = ("faísca", "faisca", "cheiro de queimado", "curto")
    warning = ("disjuntor", "fio", "tomada", "elétrico", "eletrico")

    if any(t in lowered for t in critical):
        return ElectricalRisk.CONFIRMED
    if any(t in lowered for t in warning):
        return ElectricalRisk.SUSPECTED
    return ElectricalRisk.NONE


def get_electrical_directive(risk: ElectricalRisk) -> str | None:
    """Retorna orientação de segurança para risco elétrico."""
    if risk == ElectricalRisk.CONFIRMED:
        return (
            "⚠️ **Orientações de segurança:**\n\n"
            "1. **Desligue o equipamento imediatamente** — retire o plugue da tomada.\n"
            "2. **Não religue** até a visita técnica.\n"
            "3. **Não toque em fios ou tomadas** se notar aquecimento.\n\n"
            "Já vou acionar nossa equipe técnica. Qual seu endereço completo?"
        )
    if risk == ElectricalRisk.SUSPECTED:
        return (
            "Entendi a situação. Por segurança, orientaria desligar o equipamento "
            "da tomada enquanto verificamos. Assim que puder, me passa seu endereço "
            "e bairro pra eu solicitar a visita técnica."
        )
    return None


# ── Regras de dados e bloqueio ─────────────────────────────────────────────────

BLOCK_PRICE_KEYWORDS = (
    "preço",
    "valor",
    "quanto custa",
    "quanto fica",
    "orcamento",
    "orçamento",
    "cotação",
    # Dados que faltam para preço fechado
)

ALLOW_VISIT_WITHOUT = frozenset({
    "nome",
    "foto",
    "marca",
    "modelo",
    "btus",
    "bTU",
    "BTU",
})


def should_block_price(text: str, lead_state: dict | None = None) -> tuple[bool, str | None]:
    """
    Retorna (bloquear_preço, motivo).
    Dados incompletos bloqueiam PREÇO FECHADO mas NÃO bloqueiam VISITA TÉCNICA.
    """
    lowered = text.lower()
    for kw in BLOCK_PRICE_KEYWORDS:
        if kw in lowered:
            # Verificar se tem dados mínimos
            has_city = _has_field(lead_state, "cidade_bairro")
            has_service = _has_field(lead_state, "tipo_servico")

            if not has_service:
                return True, "tipo_servico missing — bloqueia preço, não visita"
            if not has_city:
                return True, "cidade_bairro missing — bloqueia preço, não visita"
            # Tem o mínimo = permite preço
            return False, None
    return False, None


def _has_field(state: dict | None, field: str) -> bool:
    if not state:
        return False
    val = state.get(field) or state.get(field.replace("_", ""))
    return bool(val and str(val).strip())


# ── Regras Instagram ─────────────────────────────────────────────────────────

INSTAGRAM_MOMENTS = (
    "agendamento confirmado",
    "agendei",
    "ficou ótimo",
    "Combinado",
    "perfeito",
    "obrigado",
    "valeu",
    "show",
    "maravilhoso",
    "ficou show",
    "pode vim",
    "pode vir",
    "endereço correto",
    "confirmo",
)

INSTAGRAM_CONTEXT = (
    "quando",
    "qual horário",
    "que horas",
    "funciona",
    "funcionamento",
    "abre",
    "fecha",
    "horário",
    "agenda",
)


def can_show_instagram(last_messages: list[str] | None = None) -> bool:
    """
    Instagram só aparece em momento útil (não é spam).
    Momentos úteis: agendamento confirmado, cliente pergunta sobre funcionamento.
    """
    if not last_messages:
        return False
    combined = " ".join(last_messages[-3:]).lower()

    # Momento positivo/confirmação
    if any(m in combined for m in INSTAGRAM_MOMENTS):
        return True
    # Pergunta sobre horário/funcionamento
    if any(c in combined for c in INSTAGRAM_CONTEXT):
        return True
    return False


INSTAGRAM_COPY = (
    "Ah, e estamos no Instagram também — @refrimix — sempre publicamos dicas de manutenção!",
    "顺便一提, temos conteúdo no Instagram @refrimix com dicas de climatização 😊",
)


# ── Regras de perguntas por resposta ────────────────────────────────────────────

MAX_QUESTIONS_PER_TURN = 2


def count_questions(text: str) -> int:
    return text.count("?")


def enforce_question_limit(text: str) -> str:
    """Reduz perguntas para no máximo MAX_QUESTIONS_PER_TURN."""
    questions = text.split("?")
    if len(questions) <= MAX_QUESTIONS_PER_TURN:
        return text
    # Mantém só as primeiras N perguntas
    kept = "?".join(questions[:MAX_QUESTIONS_PER_TURN])
    # Se não terminava em ?, devolve pontuação
    if text.endswith("?") and not kept.endswith("?"):
        kept += "?"
    return kept


# ── Regra do "Como posso ajudar?" ───────────────────────────────────────────────

GREETING_ALONE_PATTERNS = (
    r"^oi\s*$",
    r"^olá?\s*$",
    r"^ola\s*$",
    r"^e\s*ai\s*$",
    r"^iai\s*$",
    r"^bom\s*d(ia|a|tarde|noite)\s*$",
    r"^boa\s*tarde\s*$",
    r"^boa\s*noite\s*$",
)


def client_already_explained_problem(text: str) -> bool:
    """Retorna True se cliente já explicou o que precisa (não mostrar 'Como posso ajudar?')."""
    import re
    folded = re.sub(r"\s+", " ", text.strip().lower())
    # Se é só saudação = ainda não explicou
    for p in GREETING_ALONE_PATTERNS:
        if re.match(p, folded):
            return False
    return True


# ── Validação final de resposta ────────────────────────────────────────────────

def validate_response(text: str) -> tuple[bool, str]:
    """
    Valida resposta final antes de enviar.
    Retorna (válida, mensagem_de_erro).
    """
    if not text or not text.strip():
        return False, "resposta vazia"

    if count_questions(text) > MAX_QUESTIONS_PER_TURN:
        return False, f"mais de {MAX_QUESTIONS_PER_TURN} perguntas"

    from refrimix_core.domain.conversation_style import contains_forbidden
    has_forbidden, term = contains_forbidden(text)
    if has_forbidden:
        return False, f"termo proibido: {term}"

    return True, ""
