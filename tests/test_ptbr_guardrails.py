from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "orcamento_teste.pdf"
TEMPLATE_DIR = ROOT / "app/services/refrimix_data/templates"

CLIENT_COPY_BANNED_TERMS = (
    "Breakdown",
    "budget",
    "labor",
    "client-ready",
    "Must ",
    "Required",
    "Optional",
    "technical proposals",
    "material budgets",
    "labor budgets",
)


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(_strings(item))
        return result
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(_strings(item))
        return result
    return []


def test_ptbr_rule_is_mandatory_for_agents():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    rules = (ROOT / ".rules/pt-br.md").read_text(encoding="utf-8")

    assert "Regra Zero: Português Brasileiro" in agents
    assert ".rules/pt-br.md" in agents
    assert "português brasileiro" in rules.lower()
    assert "5513974139382" in rules
    assert "5513996659382" in rules


def test_document_templates_do_not_use_english_copy_terms():
    texts: list[str] = []
    for path in sorted(TEMPLATE_DIR.glob("*.json")):
        texts.extend(_strings(json.loads(path.read_text(encoding="utf-8"))))

    joined = "\n".join(texts)

    for term in CLIENT_COPY_BANNED_TERMS:
        assert term not in joined


def test_budget_pdf_copy_is_ptbr():
    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext não está instalado neste ambiente")

    result = subprocess.run(
        ["pdftotext", str(PDF_PATH), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    text = result.stdout

    assert "ORÇAMENTO DE MATERIAIS E INSUMOS" in text
    assert "DETALHAMENTO DE MATERIAIS E INSUMOS ESPECIAIS" in text
    for term in CLIENT_COPY_BANNED_TERMS:
        assert term not in text
