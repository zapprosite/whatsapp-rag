"""
natural_microcopy.py — Microcopy natural para WhatsApp da Refrimix.

Regras:
- Uma microcopy por interação (nunca duas antes da resposta final)
- Máximo 2 perguntas por resposta
- Não parece FAQ — voz humana, técnica, acolhedora
- Não inventar preço, não diagnosticar, não chamar tool
"""
from __future__ import annotations

# ── Tipos de intenção que ativam fast lane ───────────────────────────────────
FAST_LANE_INTENTS = frozenset({
    "greeting",
    "greeting_short",
    "affirmative",
    "negative",
    "offensive",
})

# ── Microcopy: saudações e acolhimento ──────────────────────────────────────

GREETING_MICROCOPY = (
    "Oi! Tudo bem? 😊",
    "Bom dia! Como posso te ajudar?",
    "Olá! No que posso ser útil?",
    "Oi, tudo joia?",
)

SELF_INTRO_MICROCOPY = (
    "Sou a assistente virtual da Refrimix, especializada em climatização. Em que posso ajudar?",
    "Oi! Aqui é a Refrimix HVAC-R. Vamosresolver seu problema de ar-condicionado?",
)

# ── Microcopy: confirmações curtas (fast lane) ────────────────────────────────

AFFIRMATIVE_MICROCOPY = (
    "Perfeito! 👍",
    "Ótimo!",
    "Combinado!",
    "Show!",
    "Certo!",
)

NEGATIVE_MICROCOPY = (
    "Sem problemas!",
    "Entendi!",
    "Ok!",
)

# ── Microcopy: transição para slow lane ───────────────────────────────────────

SLOW_LANE_TRANSITION = (
    "Deixa eu verificar isso pra você...",
    "Um momento, vou consultar aqui...",
    "Hmm, preciso checar isso. Só um instante...",
    "Boa pergunta! Deixa eu ver o que tenho aqui...",
)

# ── Microcopy: espera + typing indicator ─────────────────────────────────────

TYPING_PLACEHOLDER = "[TYPING]"

# ── Microcopy: fallback de erro ───────────────────────────────────────────────

ERROR_MICROCOPY = (
    "Opa, tive um probleminha aqui. Me dá um instante que já volto com você!",
    "Desculpa, travei um pouco. Deixa eu retomar... 🤔",
)

FALLBACK_RESPONSE = (
    "Recebi sua mensagem. Isso é instalação, manutenção ou higienização? "
    "Me passa também sua cidade e bairro.",
)


# ── Seletor de microcopy ──────────────────────────────────────────────────────

def select_greeting(client_name: str | None = None) -> str:
    """Retorna saudação que pode usar nome do cliente se disponível."""
    import random
    base = random.choice(GREETING_MICROCOPY)
    if client_name:
        # Substitui "tudo bem?" por algo mais pessoal se nome existe
        import random as _r
        variants = (
            f"Oi {client_name.split()[0]}! Tudo bem? 😊",
            f"Olá, {client_name.split()[0]}! Como posso te ajudar?",
        )
        return _r.choice(variants)
    return base


def select_transition() -> str:
    """Seleciona microcopy de transição para slow lane."""
    import random
    return random.choice(SLOW_LANE_TRANSITION)


def select_error() -> str:
    """Seleciona microcopy de erro amigável."""
    import random
    return random.choice(ERROR_MICROCOPY)


def count_questions(text: str) -> int:
    """Conta quantas perguntas tem na mensagem."""
    return text.count("?")


def is_faq_rigged(text: str) -> bool:
    """Detecta se o texto parece FAQ engessado (vários '?' ou estrutura robótica)."""
    # FAQ tende a ter perguntas encadeadas
    if text.count("?") > 2:
        return True
    # Padrões robóticos
    if "faq" in text.lower():
        return True
    if "perguntas frequentes" in text.lower():
        return True
    # Lista numerada
    if len([l for l in text.split("\n") if l.strip() and l[0].isdigit()]) > 2:
        return True
    return False
