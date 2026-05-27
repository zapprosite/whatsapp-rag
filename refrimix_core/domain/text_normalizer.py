"""
Text Normalizer — normaliza input do usuário para o pipeline.
"""
from __future__ import annotations

import re


def fold(text: str | None) -> str:
    """Normaliza texto: lowercase, collapse spaces, expande abreviações negativas PT-BR."""
    raw = str(text or "").strip().lower()
    # Normalizar quebras de linha e tabs
    raw = re.sub(r"[\n\r\t]+", " ", raw)
    # Expandir abreviações negativas comuns em WhatsApp/áudio PT-BR
    # só quando aparecem ANTES de verbos/sinais técnicos (contexto de negação)
    # Padrão: " n " antes de verbo → " não "
    raw = re.sub(r"\bn\s+(ta|tá)\b", r" não \1", raw)          # n ta, n tá → não ta/tá
    raw = re.sub(r"\bn\s+gela\b", " não gela", raw)           # n gela → não gela
    raw = re.sub(r"\bn\s+resfria\b", " não resfria", raw)     # n resfria → não resfria
    raw = re.sub(r"\bn\s+liga\b", " não liga", raw)           # n liga → não liga
    raw = re.sub(r"\bn\s+funciona\b", " não funciona", raw)  # n funciona → não funciona
    raw = re.sub(r"\bn\s+esfria\b", " não esfria", raw)       # n esfria → não esfria
    raw = re.sub(r"\bn\s+trova\b", " não trova", raw)         # n trova → não trova
    raw = re.sub(r"\bñ\s+", " não ", raw)                     # ñ → não (no início ou após espaço)
    raw = re.sub(r"\bnao\b", " não ", raw)                    # nao → não
    raw = re.sub(r"\bnum\b", " não ", raw)                    # num → não
    raw = re.sub(r"\bn\b(?=\s+[\w]{3,})", " não", raw)       # n Isolated antes de palavra ≥3 chars → "não" (precaução)
    return re.sub(r"\s+", " ", raw).strip()


def normalize_service(service: str | None) -> str | None:
    """Normaliza tipo de serviço para canonical form."""
    if not service:
        return None
    folded = fold(service)
    mapping = {
        "instalacao": "instalacao",
        "instalação": "instalacao",
        "manutencao": "manutencao",
        "manutenção": "manutencao",
        "conserto": "manutencao",
        "higienizacao": "higienizacao",
        "higienização": "higienizacao",
    }
    return mapping.get(folded, folded or None)


def detect_service_mentioned(text: str) -> str | None:
    """Detecta tipo de serviço mencionado no texto."""
    t = fold(text)
    mapping = (
        ("higienizacao", ("higienizacao", "higienização", "limpeza")),
        ("instalacao", ("instalacao", "instalação", "instalar")),
        ("manutencao", ("manutencao", "manutenção", "conserto", "reparo")),
    )
    for service, terms in mapping:
        if any(term in t for term in terms):
            return service
    return None


def detect_window(text: str) -> str | None:
    """Detecta preferência de janela (manhã/tarde)."""
    t = fold(text)
    if any(term in t for term in ("manhã", "manha", "de manhã", "pela manhã", "de manha")):
        return "manha"
    if any(term in t for term in ("tarde", "de tarde", "pela tarde", "à tarde")):
        return "tarde"
    return None


def detect_quantity(text: str) -> int | None:
    """
    Detecta quantidade de aparelhos.
    Aceita: '1', 'um', 'uma', 'só um', 'apenas um'.
    STT transcript passa pelo mesmo normalizador.
    """
    t = fold(text).strip()

    # Números written por extenso
    spelled = {
        "um": 1, "uma": 1,
        "dois": 2, "duas": 2,
        "três": 3, "tres": 3,
        "quatro": 4,
        "cinco": 5,
        "seis": 6,
        "sete": 7,
        "oito": 8,
        "nove": 9,
        "dez": 10,
    }
    for word, num in spelled.items():
        if t == word or t == f"só {word}" or t == f"apenas {word}" or t == f"só um {word}":
            return num

    # Dígitos simples
    if re.fullmatch(r"[1-9][0-9]?", t):
        return int(t)

    # "1 aparelho", "2 equipos", "3 splits"
    m = re.search(r"\b([1-9])\b", t)
    if m:
        return int(m.group(1))

    return None


def short_answer_kind(text: str) -> str | None:
    """Detecta resposta curta tipo sim/não."""
    t = fold(text).strip()
    yes_terms = {"sim", "s", "isso", "tem", "tem sim", "já", "ja", "pode ser", "ok", "positivo"}
    no_terms = {"nao", "não", "n", "negativo", "nao tem", "não tem"}

    if t in yes_terms:
        return "yes"
    if t in no_terms:
        return "no"
    return None


def is_greeting(text: str) -> bool:
    """Detecta se texto é saudação."""
    t = fold(text)
    greetings = ("oi", "ola", "olá", "opa", "bom dia", "boa tarde", "boa noite", "e aí", "eai", "e ai")
    # Exact match
    if any(t == g for g in greetings):
        return True
    # Starts with greeting + short rest (e.g., "Bom dia, tudo bem?")
    if any(t.startswith(f"{g} ") for g in greetings):
        return True
    # "tudo bem?" or "tudo joia?" alone (very common Brazilian greeting)
    if t in ("tudo bem?", "tudo joia?", "td bem?", "td joia?"):
        return True
    return False


def extract_name(text: str) -> str | None:
    """Extrai nome próprio do texto."""
    cleaned = text.strip()
    if not cleaned or "@" in cleaned or any(ch.isdigit() for ch in cleaned):
        return None
    # Padrão: frases que introduzem nome
    patterns = [
        r"^meu nome é (.+)",
        r"^sou (.+)",
        r"^chamo(?:s)? (.+)",
        r"^me chamo (.+)",
        r"^é (.+?)[\s,.!]",
    ]
    for pat in patterns:
        m = re.search(pat, cleaned, re.I)
        if m:
            name = m.group(1).strip()
            parts = name.split()
            if 1 <= len(parts) <= 3 and all(p[0].isupper() for p in parts if len(p) > 1):
                return " ".join(parts)
    return None