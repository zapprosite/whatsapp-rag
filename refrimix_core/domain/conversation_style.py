"""
conversation_style.py — Estilo conversacional WhatsApp da Refrimix.

Princípios:
- Brasileiro educado, informalidade respeitosa
-Pessoa técnica que vende com confiança, não robô
- Curto e direto — frases curtas, uma ideia por vez
- Emoji sparing — nunca decorativo, só quando tem função
"""
from __future__ import annotations

# ── Voz e tom ─────────────────────────────────────────────────────────────────

BR_COMMON = {
    # Contrações e expressões brasileiras naturais
    "vc ": "você ",
    "vc,": "você,",
    "tb ": "também ",
    "tb,": "também,",
    "msm ": "mesmo ",
    "pq ": "porque ",
    "pq,": "porque,",
    "td ": "tudo ",
    "td,": "tudo,",
    "agr ": "agora ",
    "blz ": "beleza ",
    "flw ": "falou ",
    "obg": "obrigado",
    "vlw": "valeu",
    "tmj": "tamo junto",
    "s": "sim",
    "n": "não",
}

# ── O que NÃO dizer (bloqueio de estilo) ─────────────────────────────────────

FORBIDDEN_PATTERNS = (
    # FAQ engessado
    "como posso ajudar?",
    "em que posso ajudá-lo?",
    "segue abaixo",
    "listamos abaixo",
    "conforme solicitado",
    # Pressure de venda
    "últimas vagas",
    "promoção imperdível",
    "só até hoje",
    "fechando agora",
    "garanto sua vaga",
    # Diagnóstico elétrico perigoso
    "eu te recomendo que você ligue",
    "ligue o disjuntor e",
    "pode ligar direto",
    # Termos internos/segmentação
    "segment_market",
    "lead alto valor",
    "perfil interno",
    "residential_high_end",
)

# ── Terms técnicos permitidos (tradução para cliente) ─────────────────────────

TECH_SIMPLIFIED = {
    "BTU": "capacidade de refrigeração",
    "BTUs": "capacidade de refrigeração",
    "evaporadora": "unidade interna do ar",
    "condensadora": "unidade externa do ar",
    "split": "ar-condicionado tipo split",
    "inverter": "tecnologia inverter (mais econômico)",
    "vrf": "sistema de climatização centralizado",
    "vrv": "sistema de refrigeração de volume variável",
    "cassete": "ar de teto (cassete)",
    "gás refrigerante": "fluído refrigerante",
    "PMOC": "Plano de Manutenção, Operação e Controle",
    "pontência": "potência",
}

# ── Regras de formatação ─────────────────────────────────────────────────────

MAX_CHARS_PER_MESSAGE =  1_500  # proteção contra mensagem longa
MAX_QUESTIONS_PER_TURN = 2

# ── Funções utilitárias ───────────────────────────────────────────────────────

def normalize_br_slang(text: str) -> str:
    """Corrige abreviações brasileiras comuns para forma completa."""
    result = text.lower()
    for slang, full in BR_COMMON.items():
        result = result.replace(slang, full)
    return result


def contains_forbidden(text: str) -> tuple[bool, str | None]:
    """Retorna (True, termo) se texto contém padrão proibido."""
    lowered = text.lower()
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in lowered:
            return True, pattern
    return False, None


def translate_technical_terms(text: str) -> str:
    """Substitui jargão técnico por linguagem acessível."""
    result = text
    for term, simple in TECH_SIMPLIFIED.items():
        # Substituição case-insensitive
        import re
        result = re.sub(re.escape(term), simple, result, flags=re.IGNORECASE)
    return result


def truncate_message(text: str, max_chars: int = MAX_CHARS_PER_MESSAGE) -> str:
    """Trunca mensagem longa com indicador."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


def sanitize_output(text: str) -> str:
    """Aplica todas as sanitizações de saída."""
    text = normalize_br_slang(text)
    text = translate_technical_terms(text)
    text = truncate_message(text)
    return text.strip()
