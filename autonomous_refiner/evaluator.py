#!/usr/bin/env python3
"""
evaluator.py — Juiz LLM que avalia respostas do bot contra o playbook.

Responsibilities:
- Recebe (cenario, resposta_original, playbook_text)
- Pede ao LLM juiz para dar nota 0-10 e justificar
- Gera versão ideal da resposta
- Retorna ScoreResult com nota, justificativa e resposta ideal
"""
from __future__ import annotations
import os, json, re, textwrap
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from openai import OpenAI
except ImportError:
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "openai", "-q"])
    from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).parent.parent
PLAYBOOK     = os.getenv("REFINAR_PLAYBOOK", str(ROOT / ".context/docs/playbook_vendas.md"))
LOCAL_QWEN_BASE_URL = os.getenv("LOCAL_QWEN_BASE_URL", "http://127.0.0.1:8010/v1").rstrip("/")
LOCAL_QWEN_MODEL    = os.getenv("LOCAL_QWEN_MODEL", "qwen2.5-vl-7b-instruct")
JUDGE_MODEL_GROQ    = os.getenv("JUDGE_MODEL_GROQ", "llama-3.3-70b-versatile")
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
QWEN_API_KEY        = os.getenv("QWEN_API_KEY", "dummy")

# ── ANSI ───────────────────────────────────────────────────────────────────────
R  = "\033[0m"
GR = "\033[92m"
YL = "\033[93m"
RD = "\033[91m"


def c(col, t): return f"{col}{t}{R}"


# ── Result structs ─────────────────────────────────────────────────────────────

class ScoreLevel(Enum):
    EXCELLENT = "excellent"   # 9-10
    GOOD      = "good"        # 7-8.9
    FAIR      = "fair"        # 5-6.9
    POOR      = "poor"        # 0-4.9

@dataclass
class ScoreResult:
    score: float              # 0-10
    level: ScoreLevel
    justification: str        # razão da nota
    ideal_response: str       # versão ideal gerada pelo juiz
    improvements: list[str]  # pontos de melhoria
    judge_model: str          # qual modelo ouviu como juiz

    def to_dict(self) -> dict:
        d = asdict(self)
        d["level"] = self.level.value
        return d

    @property
    def passed(self) -> bool:
        return self.score >= 7.0


# ── Judge LLM client ───────────────────────────────────────────────────────────

class JudgeClient:
    """Cliente LLM que atua como juiz das respostas."""

    def __init__(self, provider: str = "groq"):
        self.provider = provider
        if provider == "groq" and GROQ_API_KEY:
            self.client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
            self.model = JUDGE_MODEL_GROQ
        else:
            # Qwen local
            self.client = OpenAI(api_key=QWEN_API_KEY, base_url=LOCAL_QWEN_BASE_URL)
            self.model = LOCAL_QWEN_MODEL

    def _system_prompt(self, playbook: str) -> str:
        return textwrap.dedent(f"""\
        Você é um法官 (juiz) especialista no playbook de vendas da Refrimix.
        Sua tarefa é avaliar respostas do assistente virtual WhatsApp e dar nota 0-10.

        REGRAS DE AVALIAÇÃO:
        1. Responda SOMENTE em JSON válido, sem nenhum texto fora do JSON.
        2. Dê nota 0-10, sendo:
           - 9-10: Perfeita, segue playbook, tom correto, próximo passo claro
           - 7-8.9: Boa, pequenos ajustes necessários
           - 5-6.9: Razoável, falhas de tom ou informação
           - 0-4.9: Ruim, viola playbook ou não responde aintent
        3. Justifique a nota com pontos específicos.
        4. Gere uma versão ideal da resposta (sem marcação, só texto WhatsApp).
        5. Liste pontos de melhoria concretos.

        PLAYBOOK DA REFRIMIX:
        {playbook[:6000]}

        OUTPUT (somente JSON):
        {{
          "score": <float 0-10>,
          "justification": "<razão da nota>",
          "ideal_response": "<resposta ideal WhatsApp>",
          "improvements": ["<ponto 1>", "<ponto 2>"]
        }}
        """)

    def evaluate(
        self,
        scenario: str,
        original_response: str,
        intent: str = "unknown",
        service: str = "unknown",
    ) -> ScoreResult:
        """Evalua uma resposta e retorna ScoreResult."""
        playbook_text = ""
        if Path(PLAYBOOK).exists():
            playbook_text = Path(PLAYBOOK).read_text()

        user_msg = textwrap.dedent(f"""\
        CENÁRIO: {scenario}
        INTENT DETECTADO: {intent}
        SERVIÇO: {service}
        RESPOSTA ORIGINAL DO BOT:
        {original_response}

        Avalie e retorne SOMENTE JSON.
        """)

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt(playbook_text)},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=1024,
            )
            raw = (resp.choices[0].message.content or "").strip()
        except Exception as e:
            return ScoreResult(
                score=0.0,
                level=ScoreLevel.POOR,
                justification=f"Erro ao chamar juiz: {e}",
                ideal_response=original_response,
                improvements=["Falha no judge LLM"],
                judge_model=self.model,
            )

        # Parse JSON
        try:
            # Tenta extrair bloco de código se houver
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                data = json.loads(raw)
        except json.JSONDecodeError as e:
            return ScoreResult(
                score=5.0,
                level=ScoreLevel.FAIR,
                justification=f"Juiz retornou JSON inválido: {e}. Raw: {raw[:200]}",
                ideal_response=original_response,
                improvements=["JSON mal formado do judge"],
                judge_model=self.model,
            )

        score = float(data.get("score", 5.0))
        if score >= 9:
            level = ScoreLevel.EXCELLENT
        elif score >= 7:
            level = ScoreLevel.GOOD
        elif score >= 5:
            level = ScoreLevel.FAIR
        else:
            level = ScoreLevel.POOR

        return ScoreResult(
            score=score,
            level=level,
            justification=data.get("justification", ""),
            ideal_response=data.get("ideal_response", original_response),
            improvements=data.get("improvements", []),
            judge_model=self.model,
        )


# ── Main entrypoint (self-test) ───────────────────────────────────────────────

if __name__ == "__main__":
    import textwrap
    judge = JudgeClient()
    test_response = "Obrigado! Sua solicitação foi registrada. Entraremos em contato em breve."
    result = judge.evaluate(
        scenario="Lead pede orçamento de instalação de split",
        original_response=test_response,
        intent="instalacao",
        service="instalacao",
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    print(f"\nScore: {result.score}/10 — {'APROVADO' if result.passed else 'REPROVADO'}")