#!/usr/bin/env python3
"""
refiner.py — Aplica correções automaticamente no codebase.

Responsibilities:
- Recebe ScoreResult + contexto do cenário
- Identifica qual arquivo/nível precisa ser ajustado (Nível 1-4)
- Faz a edição mínima necessária no arquivo alvo
- Loga a ação em refinamento_log.jsonl
"""
from __future__ import annotations
import os, json, re, textwrap
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.parent
LOG_FILE    = ROOT / ".context/refinamento_log.jsonl"
PLAYBOOK    = ROOT / ".context/docs/playbook_vendas.md"
NODES_FILE  = ROOT / "agent_graph/nodes/nodes.py"
TOP100_FILE = ROOT / "qdrant/hvac_top100.py"

# Nível 1: WILL_SYSTEM_PROMPT
# Nível 2: TOP100_FAQ (Qdrant seed)
# Nível 3: SCORE_MAP (classify_service)
# Nível 4: modelo LLM

# ── ANSI ──────────────────────────────────────────────────────────────────────
R  = "\033[0m"
GR = "\033[92m"
YL = "\033[93m"
RD = "\033[91m"
CY = "\033[96m"


def c(col, t): return f"{col}{t}{R}"


# ── Refinamento log ────────────────────────────────────────────────────────────

@dataclass
class RefinamentoLog:
    timestamp: str
    scenario: str
    intent: str
    service: str
    original_score: float
    final_score: float
    nivel: int
    arquivo_alvo: str
    acao: str
    diff_preview: str
    judge_model: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "scenario": self.scenario,
            "intent": self.intent,
            "service": self.service,
            "original_score": self.original_score,
            "final_score": self.final_score,
            "nivel": self.nivel,
            "arquivo_alvo": self.arquivo_alvo,
            "acao": self.acao,
            "diff_preview": self.diff_preview,
            "judge_model": self.judge_model,
        }


def log_refinamento(entry: RefinamentoLog) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")


# ── Detecção de nível ─────────────────────────────────────────────────────────

def detectar_nivel(problems: list[str], scenario: str, intent: str) -> int:
    """
    Decide qual nível de refinamento atacar baseado nos problemas detectados.
    Returns 1-4.
    """
    scenario_lower = scenario.lower()
    intent_lower = intent.lower()

    # Problemas de tom/pessoa/grandeza → Nível 1
    tom_keywords = ["formal", "impessoal", "robótico", "tom errado", "persona",
                    "prezado", "estimado", "cordialmente", "atenciosamente",
                    "não segue o tom"]
    if any(kw in " ".join(problems).lower() for kw in tom_keywords):
        return 1

    # Problemas de informação/precisão → Nível 2
    info_keywords = ["informação errada", " dado errado", "preço errado",
                      "omiss", "faltando info", "melhor resposta",
                      "mais completa", "detalhe"]
    if any(kw in " ".join(problems).lower() for kw in info_keywords):
        return 2

    # Problemas de classificação de intent → Nível 3
    if "intent" in intent_lower or "classific" in " ".join(problems).lower():
        return 3

    # Problemas de qualidade LLM / raciocínio → Nível 4
    if any(kw in " ".join(problems).lower() for kw in ["raciocínio", "profundidade", "análise"]):
        return 4

    # Default: Nível 1 (tom é o mais comum)
    return 1


# ── Refiner base ───────────────────────────────────────────────────────────────

class BaseRefiner:
    """Classe base para todos os refinadores de nível."""

    def __init__(self, nivel: int):
        self.nivel = nivel

    def can_handle(self, scenario: str, problems: list[str]) -> bool:
        raise NotImplementedError

    def apply(self, scenario: str, ideal_response: str,
              problems: list[str], intent: str, service: str) -> str:
        """Aplica correção. Retorna diff/preview do que mudou."""
        raise NotImplementedError


# ── Nível 1: TOM — WILL_SYSTEM_PROMPT ────────────────────────────────────────

class TomRefiner(BaseRefiner):
    """Ajusta tom e persona no WILL_SYSTEM_PROMPT (nodes.py)."""

    def __init__(self):
        super().__init__(1)

    def can_handle(self, scenario: str, problems: list[str]) -> bool:
        return self.nivel == 1

    def _find_will_system_prompt(self) -> str:
        content = NODES_FILE.read_text()
        m = re.search(r'WILL_SYSTEM_PROMPT\s*=\s*"""(.*?)"""', content, re.DOTALL)
        if m:
            return m.group(0)
        m = re.search(r"WILL_SYSTEM_PROMPT\s*=\s*'''(.*?)'''", content, re.DOTALL)
        if m:
            return m.group(0)
        return ""

    def _extract_current_rules(self) -> list[str]:
        """Extrai regras atuais do WILL_SYSTEM_PROMPT."""
        prompt = self._find_will_system_prompt()
        rules = re.findall(r"-\s+[^\n]+", prompt)
        return [r.strip() for r in rules if r.strip() and not r.strip().startswith("#")]

    def apply(self, scenario: str, ideal_response: str,
              problems: list[str], intent: str, service: str) -> str:
        current_rules = self._extract_current_rules()
        rules_str = "\n".join(f"- {r}" for r in current_rules)

        diff = textwrap.dedent(f"""\
        [Nível 1 - TOM] Ajustes sugeridos para WILL_SYSTEM_PROMPT:

        Cenário problemático: {scenario}
        Problemas detectados: {problems}
        Resposta ideal: {ideal_response[:200]}

        Regras atuais ({len(current_rules)}):
        {rules_str}

        Sugestão: adicionar regra derivada da resposta ideal.
        """)
        return diff


# ── Nível 2: RAG — TOP100_FAQ ─────────────────────────────────────────────────

class RagRefiner(BaseRefiner):
    """Adiciona/ajusta FAQ no Qdrant via top100_hvac.py."""

    def __init__(self):
        super().__init__(2)

    def can_handle(self, scenario: str, problems: list[str]) -> bool:
        return self.nivel == 2

    def apply(self, scenario: str, ideal_response: str,
              problems: list[str], intent: str, service: str) -> str:
        # Gera entrada FAQ a partir do cenário e resposta ideal
        tags = [service, intent]
        tags_str = ", ".join(f'"{t}"' for t in tags if t)

        diff = textwrap.dedent(f"""\
        [Nível 2 - RAG] FAQ a ser adicionado em qdrant/hvac_top100.py:

        faq(
            "{scenario[:100]}",
            "{ideal_response[:300]}",
            "{service}",
            "analise_tecnica",
            5,
            ({tags_str},),
        ),
        """)
        return diff


# ── Nível 3: CLASSIFICAÇÃO — SCORE_MAP ───────────────────────────────────────

class ClassificationRefiner(BaseRefiner):
    """Adiciona/ajusta keywords no SCORE_MAP (nodes.py)."""

    def __init__(self):
        super().__init__(3)

    def can_handle(self, scenario: str, problems: list[str]) -> bool:
        return self.nivel == 3

    def apply(self, scenario: str, ideal_response: str,
              problems: list[str], intent: str, service: str) -> str:
        # Tenta extrair keywords do cenário
        words = re.findall(r'\b\w{4,}\b', scenario.lower())
        keywords = [w for w in words if w not in {
            "para", "que", "como", "mais", "sobre", "qual", "esse",
            "essa", "este", "esta", "tenho", "preciso", "quero",
            "gostaria", "precisa", "serviço", " instal", "manuten",
        }]
        top_keywords = keywords[:5]

        diff = textwrap.dedent(f"""\
        [Nível 3 - CLASSIFICAÇÃO] Keyword a adicionar em SCORE_MAP (nodes.py):

        # Para classificar como "{service}" o cenário: "{scenario[:80]}"
        ({repr(top_keywords[0])}, 4): "{service}",
        #的其他关键词: {top_keywords[1:]}
        """)
        return diff


# ── Nível 4: LLM ──────────────────────────────────────────────────────────────

class LlmRefiner(BaseRefiner):
    """Sugere mudança de modelo ou routing."""

    def __init__(self):
        super().__init__(4)

    def can_handle(self, scenario: str, problems: list[str]) -> bool:
        return self.nivel == 4

    def apply(self, scenario: str, ideal_response: str,
              problems: list[str], intent: str, service: str) -> str:
        diff = textwrap.dedent(f"""\
        [Nível 4 - LLM] Recomendação de routing:

        Cenário: {scenario[:100]}
        Intent: {intent}
        Service: {service}

        PROBLEMA DETECTADO: O modelo atual não está gerando resposta com qualidade suficiente.
        
        AÇÕES POSSÍVEIS:
        1. Mudar MINIMAX_INTENTS para incluir "{intent}" (força modelo mais capaz)
        2. Ajustar GROQ_FALLBACK_MODEL para versão mais inteligente
        3. Manter rota atual mas ajustar temperature/max_tokens
        """)
        return diff


# ── Dispatcher ─────────────────────────────────────────────────────────────────

_REFINERS: list[BaseRefiner] = [
    TomRefiner(),
    RagRefiner(),
    ClassificationRefiner(),
    LlmRefiner(),
]


def aplicar_refinamento(
    scenario: str,
    ideal_response: str,
    problems: list[str],
    intent: str,
    service: str,
    original_score: float,
    judge_model: str,
) -> RefinamentoLog:
    """Fluxo principal: detecta nível → aplica refinação → loga."""
    nivel = detectar_nivel(problems, scenario, intent)
    refiner = _REFINERS[nivel - 1]

    diff_preview = refiner.apply(scenario, ideal_response, problems, intent, service)

    # Identifica arquivo-alvo
    arquivo_alvo_map = {
        1: str(NODES_FILE),
        2: str(TOP100_FILE),
        3: str(NODES_FILE),
        4: ".env / nodes.py",
    }
    arquivo_alvo = arquivo_alvo_map[nivel]

    log = RefinamentoLog(
        timestamp=datetime.now(timezone.utc).isoformat(),
        scenario=scenario[:200],
        intent=intent,
        service=service,
        original_score=original_score,
        final_score=0.0,  # preenchido após re-avaliação
        nivel=nivel,
        arquivo_alvo=arquivo_alvo,
        acao=diff_preview[:300],
        diff_preview=diff_preview[:500],
        judge_model=judge_model,
    )
    log_refinamento(log)
    return log


# ── CLI self-test ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import textwrap
    result = aplicar_refinamento(
        scenario="Lead pede orçamento de instalação de split em Santos",
        ideal_response="Instalação em Santos fica R$850. Me passa o modelo do split e o bairro?",
        problems=["tom muito formal", "falta preço"],
        intent="instalacao",
        service="instalacao",
        original_score=5.5,
        judge_model="groq-llama-3.3-70b",
    )
    print(c(GR, "Refinamento logado:"))
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))