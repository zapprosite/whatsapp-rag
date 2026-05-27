"""
Response Rubric — avalia cada resposta do bot com notas de 0 a 5.

Critérios:
- naturalidade_ptbr: parece brasileiro de WhatsApp
- clareza: entende-se sem esforço
- conversao: avança em direção a agendamento/visita/orçamento
- baixo_atrito: não frustra o cliente
- seguranca_tecnica: não inventa preço, não diagnostica sem avaliar
- nao_inventa_preco: não passa valor sem contexto validado
- nao_diagnostica_sem_avaliar: não dá diagnóstico definitivo
- agenda_facil: facilita agendamento quando possível
- limite_perguntas: máximo 2 perguntas por resposta
- tom_whatsapp: curto, direto, não é FAQ nem robô
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RubricScore:
    """Nota individual por critério (0 a 5)."""
    naturalidade_ptbr: float = 0.0
    clareza: float = 0.0
    conversao: float = 0.0
    baixo_atrito: float = 0.0
    seguranca_tecnica: float = 0.0
    nao_inventa_preco: float = 0.0
    nao_diagnostica_sem_avaliar: float = 0.0
    agenda_facil: float = 0.0
    limite_perguntas: float = 0.0
    tom_whatsapp: float = 0.0

    @property
    def media(self) -> float:
        total = (
            self.naturalidade_ptbr + self.clareza + self.conversao +
            self.baixo_atrito + self.seguranca_tecnica +
            self.nao_inventa_preco + self.nao_diagnostica_sem_avaliar +
            self.agenda_facil + self.limite_perguntas + self.tom_whatsapp
        )
        return round(total / 10, 2)

    def to_dict(self) -> dict:
        return {
            "naturalidade_ptbr": self.naturalidade_ptbr,
            "clareza": self.clareza,
            "conversao": self.conversao,
            "baixo_atrito": self.baixo_atrito,
            "seguranca_tecnica": self.seguranca_tecnica,
            "nao_inventa_preco": self.nao_inventa_preco,
            "nao_diagnostica_sem_avaliar": self.nao_diagnostica_sem_avaliar,
            "agenda_facil": self.agenda_facil,
            "limite_perguntas": self.limite_perguntas,
            "tom_whatsapp": self.tom_whatsapp,
            "media": self.media,
        }


@dataclass
class RubricResult:
    """Resultado completo da avaliação de uma resposta."""
    score: RubricScore
    failures: list[str] = field(default_factory=list)  # falhas automáticas
    warnings: list[str] = field(default_factory=list)  # avisos
    is_critical_failure: bool = False  # falha que bloqueia
    notes: str = ""

    @property
    def passou(self) -> bool:
        return not self.is_critical_failure and self.score.media >= 3.5

    def to_dict(self) -> dict:
        return {
            "score": self.score.to_dict(),
            "failures": self.failures,
            "warnings": self.warnings,
            "is_critical_failure": self.is_critical_failure,
            "notes": self.notes,
            "passou": self.passou,
        }


# ── Falhas automáticas (críticas) ──────────────────────────────────────────────

CRITICAL_FAILURES = [
    "usa_portugues_europeu",
    "usa_espanhol",
    "inventou_preco",
    "diagnostico_definitivo",
    "nao_orienta_desligar_em_risco_eletrico",
    "mais_de_2_perguntas",
    "foto_obrigatoria",
    "nome_bloqueando_agendamento",
    "como_posso_ajudar_depois_cliente_explicar",
    "audio_longo",
    "instagram_fora_de_contexto",
    "texto_longo_demais",
    "offer_fixed_price_without_context",
]

# Termos proibidos (português europeu)
PT_EU_TERMS = [
    "telefone", "contactar", "morada", "marcação", "por favor",
    "obrigado", "muito obrigado", "de nada",
    "presupuesto", "mantenimiento", "instalación", "aire acondicionado",
    "gracias", "datos", "información",
]

PT_EU_PHRASES = [
    "como posso ajudá-lo",
    "em que posso ajudá-lo",
    "posso ajudá-lo",
    "como posso ajudar",
    "estou aqui para ajudar",
    "como posso ser útil",
    "por favor, clique",
]

# Termos espanhol
ES_TERMS = [
    "hola", "gracias", "por favor", "cuánto cuesta", "cuánto vale",
    "necesito", "quiero", "tengo", "está funcionando",
    "el aire", "la instalación", "el servicio", "el técnico",
]


def _count_questions(text: str) -> int:
    """Conta perguntas (? ou pergunta direta)."""
    return text.count("?")


def _has_checklist(text: str) -> bool:
    """Detecta lista gigante (mais de 3 items)."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    numbered = [l for l in lines if l[0].isdigit() and "." in l[:3]]
    return len(numbered) > 3


def _is_faq_style(text: str) -> bool:
    """Detecta se parece FAQ engessado."""
    if "faq" in text.lower():
        return True
    if "perguntas frequentes" in text.lower():
        return True
    # Mais de 2 perguntas
    if text.count("?") > 2:
        return True
    # Lista grande (linhas separadas)
    if _has_checklist(text):
        return True
    # Lista grande inline: "1. item 2. item 3. item"
    inline_items = re.findall(r'\b\d+\.\s+\w', text)
    if len(inline_items) > 3:
        return True
    return False


def _has_pt_eu(text: str) -> bool:
    """Detecta português europeu."""
    text_lower = text.lower()
    for term in PT_EU_TERMS:
        if term in text_lower:
            return True
    for phrase in PT_EU_PHRASES:
        if phrase in text_lower:
            return True
    return False


def _has_es(text: str) -> bool:
    """Detecta espanhol."""
    text_lower = text.lower()
    for term in ES_TERMS:
        if term in text_lower:
            return True
    return False


def _has_invented_price(text: str, user_text: str) -> bool:
    """Detecta preço inventado sem contexto válido."""
    # Preços válidos do comercial router
    VALID_PRICES = {"850": True, "200": True, "50": True}
    price_pattern = r"R\$\s*(\d+)"
    prices = re.findall(price_pattern, text)
    for price in prices:
        if price not in VALID_PRICES:
            return True
    return False


def _has_definitive_diagnosis(text: str) -> bool:
    """Detecta diagnóstico definitivo (sem 'provavelmente', 'pode ser', etc)."""
    DIAGNOSTIC_PATTERNS = [
        r"\b(conserto|reparar|trocar|substituir|troca|reposição)\s+",
        r"\b(é|foi|está)\s+(quebrado|defeituoso|com defeito|queimado)\b",
        r"\b(o problema é|causa é|você precisa|tem que|tem de)\b",
        r"\b(solução|resolver)\s+é\b",
    ]
    for pattern in DIAGNOSTIC_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            # Allow hedging words
            if any(hedge in text.lower() for hedge in ["provavelmente", "pode ser", "talvez", "pode ser que"]):
                continue
            return True
    return False


def _has_photo_obligation(text: str) -> bool:
    """Detecta que foto é obrigatória (bloqueia fluxo)."""
    # Padrão que pega: "manda foto", "manda uma foto", "mande foto", "envie foto", etc.
    if re.search(r"(envie|mande|enviar|manda|mandar)\b.*foto", text, re.IGNORECASE):
        if "opcional" not in text.lower() and "se puder" not in text.lower() and "se conseguir" not in text.lower():
            return True
        if re.search(r"precis[ao]\s+d[ae]\s+foto", text, re.IGNORECASE):
            return True
    if re.search(r"sem\s+foto", text, re.IGNORECASE):
        if "não trava" not in text.lower() and "não bloqueia" not in text.lower():
            return True
    return False


def _has_name_blocking(text: str) -> bool:
    """Detecta que nome bloqueia agendamento."""
    if re.search(r"me\s+passa\s+(seu\s+)?nome", text, re.IGNORECASE):
        if "agendar" in text.lower() or "horário" in text.lower() or "manhã" in text.lower() or "tarde" in text.lower():
            # Check if it's blocking vs optional
            if not any(opt in text.lower() for opt in ["opcional", "se quiser", "se preferir"]):
                return True
    return False


def _has_how_can_i_help(text: str, user_text: str) -> bool:
    """Detecta 'Como posso ajudar?' depois do cliente já explicar."""
    client_explained = len(user_text.strip()) > 15
    how_can_i_patterns = [
        "como posso ajudar", "como posso te ajudar",
        "em que posso ajudá", "posso ajudá-lo",
        "como posso ser útil", "no que posso ajudar",
    ]
    if client_explained:
        for pattern in how_can_i_patterns:
            if pattern in text.lower():
                return True
    return False


def _is_text_too_long(text: str) -> bool:
    """Detecta texto longo demais para WhatsApp."""
    # WhatsApp ideal: até ~800 caracteres por mensagem
    return len(text) > 800


def _has_audio_long(text: str) -> bool:
    """Detecta áudio longo (não deve ser gerado para laudo, orçamento longo, etc)."""
    AUDIO_LONG_CONTEXT = [
        "laudo", "orçamento detalhado", "contrato", "pmoc",
        "relatório", "especificação técnica", "memorial descritivo",
    ]
    for context in AUDIO_LONG_CONTEXT:
        if context in text.lower():
            return True
    return False


def _has_instagram_out_of_context(text: str, is_consulting_schedule: bool) -> bool:
    """Detecta Instagram enviado fora de contexto."""
    has_instagram = "instagram" in text.lower() or "insta" in text.lower()
    if has_instagram and not is_consulting_schedule:
        return True
    return False


def _should_tell_to_turn_off(text: str, user_text: str) -> bool:
    """Verifica se risco elétrico deveria ter orientação de desligar."""
    RISK_TERMS = ["disjuntor", "fio quente", "cheiro", "queimado", "faísca", "curto"]
    if any(term in user_text.lower() for term in RISK_TERMS):
        if "deslig" not in text.lower() and "desligue" not in text.lower() and "mantenha desligado" not in text.lower():
            return True
    return False


# ── Avaliador principal ─────────────────────────────────────────────────────────

def evaluate_response(
    response_text: str,
    user_text: str,
    conversation_history: list[str] | None = None,
    scenario_context: dict | None = None,
    is_consulting_schedule: bool = False,
    is_electrical_risk: bool = False,
) -> RubricResult:
    """
    Avalia uma resposta do bot segundo os 10 critérios da rubrica.

    Args:
        response_text: resposta gerada pelo bot
        user_text: última mensagem do cliente
        conversation_history: histórico de mensagens do cliente (para detectar repetição)
        scenario_context: contexto do cenário (category, etc)
        is_consulting_schedule: se está consultando agenda (Instagram ok)
        is_electrical_risk: se o cenário é risco elétrico

    Returns:
        RubricResult com notas e falhas
    """
    history = conversation_history or []

    failures: list[str] = []
    warnings: list[str] = []

    # ── Verificações críticas (falhas automáticas) ──────────────────────────

    if _has_pt_eu(response_text):
        failures.append("usa_portugues_europeu")

    if _has_es(response_text):
        failures.append("usa_espanhol")

    if _is_text_too_long(response_text):
        failures.append("texto_longo_demais")

    if not response_text.strip():
        failures.append("resposta_vazia")

    if _has_invented_price(response_text, user_text):
        failures.append("inventou_preco")

    if _has_definitive_diagnosis(response_text):
        failures.append("diagnostico_definitivo")

    if _count_questions(response_text) > 2:
        failures.append("mais_de_2_perguntas")

    if _has_photo_obligation(response_text):
        failures.append("foto_obrigatoria")

    if _has_name_blocking(response_text):
        failures.append("nome_bloqueando_agendamento")

    if _has_how_can_i_help(response_text, user_text):
        failures.append("como_posso_ajudar_depois_cliente_explicar")

    if is_electrical_risk and _should_tell_to_turn_off(response_text, user_text):
        failures.append("nao_orienta_desligar_em_risco_eletrico")

    # ── Notas por critério ───────────────────────────────────────────────────

    score = RubricScore()

    # naturalidade_ptbr
    if _has_pt_eu(response_text) or _has_es(response_text):
        score.naturalidade_ptbr = 1.0
    elif _is_faq_style(response_text):
        score.naturalidade_ptbr = 2.0
    else:
        score.naturalidade_ptbr = 4.5

    # clareza
    if len(response_text) < 20:
        score.clareza = 5.0
    elif len(response_text) > 400:
        score.clareza = 3.0
    else:
        score.clareza = 4.5

    # conversao
    conversion_signals = [
        "manhã", "tarde", "horário", "agendar",
        "visita", "técnico", "R$", "período",
    ]
    conv = sum(1 for sig in conversion_signals if sig in response_text.lower())
    if conv >= 2:
        score.conversao = 5.0
    elif conv == 1:
        score.conversao = 4.0
    else:
        score.conversao = 3.0

    # baixo_atrito
    high_friction = ["aguarde", "aguarda", "espere", "infelizmente", "não é possível"]
    friction_count = sum(1 for sig in high_friction if sig in response_text.lower())
    if _is_faq_style(response_text):
        score.baixo_atrito = 2.0
    elif friction_count > 0:
        score.baixo_atrito = 3.5
    else:
        score.baixo_atrito = 4.5

    # seguranca_tecnica
    if not _has_definitive_diagnosis(response_text) and not _has_invented_price(response_text, user_text):
        score.seguranca_tecnica = 5.0
    elif _has_invented_price(response_text, user_text):
        score.seguranca_tecnica = 1.0
    else:
        score.seguranca_tecnica = 3.0

    # nao_inventa_preco
    if _has_invented_price(response_text, user_text):
        score.nao_inventa_preco = 1.0
    elif "R$" not in response_text:
        score.nao_inventa_preco = 5.0
    else:
        score.nao_inventa_preco = 4.5

    # nao_diagnostica_sem_avaliar
    if _has_definitive_diagnosis(response_text):
        score.nao_diagnostica_sem_avaliar = 1.0
    else:
        score.nao_diagnostica_sem_avaliar = 4.5

    # agenda_facil
    agenda_signals = ["manhã", "tarde", "período", "horário", "agendar"]
    if any(sig in response_text.lower() for sig in agenda_signals):
        score.agenda_facil = 5.0
    elif "visita" in response_text.lower() or "técnico" in response_text.lower():
        score.agenda_facil = 4.0
    else:
        score.agenda_facil = 3.5

    # limite_perguntas
    q_count = _count_questions(response_text)
    if q_count == 0:
        score.limite_perguntas = 4.0
    elif q_count == 1:
        score.limite_perguntas = 5.0
    elif q_count == 2:
        score.limite_perguntas = 4.5
    else:
        score.limite_perguntas = 2.0

    # tom_whatsapp
    if _is_faq_style(response_text):
        score.tom_whatsapp = 2.0
    elif len(response_text) > 600:
        score.tom_whatsapp = 3.0
    else:
        score.tom_whatsapp = 4.5

    # ── Identifica falha crítica ────────────────────────────────────────────

    is_critical = len(failures) > 0

    # ── Gera notas ─────────────────────────────────────────────────────────

    notes_parts = []
    if failures:
        notes_parts.append(f"Falhas: {', '.join(failures)}")
    if warnings:
        notes_parts.append(f"Avisos: {', '.join(warnings)}")
    notes_parts.append(f"Score médio: {score.media:.2f}")
    notes = " | ".join(notes_parts)

    return RubricResult(
        score=score,
        failures=failures,
        warnings=warnings,
        is_critical_failure=is_critical,
        notes=notes,
    )


# ── Avaliação rápida por categoria ─────────────────────────────────────────────

def quick_evaluate(
    response_text: str,
    category: str,
    user_text: str = "",
) -> tuple[float, list[str]]:
    """
    Avaliação rápida que retorna (media, falhas).
    Usado em loops de muitas avaliações.
    """
    result = evaluate_response(
        response_text=response_text,
        user_text=user_text,
        scenario_context={"category": category},
        is_consulting_schedule=False,
        is_electrical_risk=(category == "risco_eletrico"),
    )
    return result.score.media, result.failures