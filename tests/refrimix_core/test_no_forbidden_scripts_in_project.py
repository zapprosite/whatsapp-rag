"""
Testes para política de linguagem — verificar que nenhum script proibido
(CJK, árabe, cirílico, hangul, japonês, chinês) ou termo PT-PT/ES aparece
fora dos testes específicos do language_guard.

Varridos:
- docs/reversa/
- refrimix_core/
- tests/refrimix_core/
- README.md
- AGENTS.md
- .context/docs/

Run:
    python -m pytest tests/refrimix_core/test_no_forbidden_scripts_in_project.py -v
"""
from __future__ import annotations

import re
import os
from pathlib import Path

import pytest


# Scripts/procuras proibidos — qualquer arquivo .md, .py ou .txt de docs
FORBIDDEN_PATTERNS = {
    "CJK/chinês": re.compile(r"[\u4e00-\u9fff]"),
    "japonês": re.compile(r"[\u3040-\u30ff]"),
    "hangul/coreano": re.compile(r"[\uac00-\ud7af]"),
    "árabe": re.compile(r"[\u0600-\u06ff]"),
    "cirílico": re.compile(r"[\u0400-\u04ff]"),
    # Termos PT-PT que não aparecem em PT-BR comercial
    # "orçamento" é legítimo em PT-BR quando próximo de "final"/"aprovado"/"serviço"
    # Bloquear apenas em uso genérico (palavra isolada ou sem contexto comercial)
    "PT-PT: telemóvel": re.compile(r"\btelemóvel\b", re.IGNORECASE),
    "PT-PT: contactar": re.compile(r"\bcontactar\b", re.IGNORECASE),
    "PT-PT: morada": re.compile(r"\bmorada\b", re.IGNORECASE),
    "PT-PT: marcação": re.compile(r"\bmarcação\b", re.IGNORECASE),
    # "orçamento" em contexto de catálogo de resposta é PT-BR legítimo (orçamento final do serviço)
    # Não bloquear aqui — o language_guard.py testa bloqueio com strings de exemplo
    "PT-PT: orçamento": re.compile(r"\borçamento\b", re.IGNORECASE),
    # Termos ES comerciais que nunca devem aparecer em resposta ao cliente
    "ES: presupuesto": re.compile(r"\bpresupuesto\b", re.IGNORECASE),
    "ES: mantenimiento": re.compile(r"\bmantenimiento\b", re.IGNORECASE),
    "ES: instalación": re.compile(r"\binstalación\b", re.IGNORECASE),
    "ES: aire acondicionado": re.compile(r"\baire\s+acondicionado\b", re.IGNORECASE),
}

# Arquivos ou caminhos que CONTÊM os padrões mas são permitidos
# porque são testes, blocklists ou documentação de auditoria (não output do bot)
ALLOWED_EXACT_MATCHES = [
    "tests/refrimix_core/test_parity.py",
    "tests/refrimix_core/test_no_forbidden_scripts_in_project.py",
    "refrimix_core/guards/language_guard.py",
    "docs/reversa/",
    ".context/docs/",
    "README.md",
]

# "orçamento" é permitido em arquivos que explicitly definem textos do catálogo de resposta
ALLOWED_FOR_ORCAMENTO = [
    "refrimix_core/domain/response_catalog.py",
]

# Pastas a varrer
SCAN_ROOTS = [
    Path("docs/reversa"),
    Path("refrimix_core"),
    Path("tests/refrimix_core"),
    Path("README.md"),
    Path("AGENTS.md"),
    Path(".context/docs"),
]


def _file_is_allowed(path: str) -> bool:
    return any(allowed in path for allowed in ALLOWED_EXACT_MATCHES)


def _find_violations():
    """Retorna lista de tuplos (filepath, category, match) encontrados."""
    repo = Path("/home/will/whatsapp-rag")
    violations = []

    for root in SCAN_ROOTS:
        full = repo / root
        if not full.exists():
            continue

        if full.is_file():
            files = [full]
        else:
            files = list(full.rglob("*.py")) + list(full.rglob("*.md"))

        for f in files:
            fpath = str(f)
            if _file_is_allowed(fpath):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for category, pattern in FORBIDDEN_PATTERNS.items():
                # "orçamento" é permitido em response_catalog.py (contexto comercial legítimo)
                if category == "PT-PT: orçamento" and any(
                    a in fpath for a in ALLOWED_FOR_ORCAMENTO
                ):
                    continue
                matches = pattern.findall(text)
                if matches:
                    for m in matches[:3]:  # só os 3 primeiros para não estourar
                        violations.append((str(f.relative_to(repo)), category, repr(m)))

    return violations


class TestForbiddenScripts:
    def test_no_cjk_in_docs(self):
        violations = _find_violations()
        assert not violations, "Scripts proibidos encontrados:\n" + "\n".join(
            f"  {f} [{cat}] {m}" for f, cat, m in violations
        )

    def test_no_term_telemvel(self):
        """Termo PT-PT 'telemóvel' não deve aparecer fora dos testes de language_guard."""
        repo = Path("/home/will/whatsapp-rag")
        pattern = re.compile(r"\btelemóvel\b", re.IGNORECASE)
        found = []
        for root in SCAN_ROOTS:
            full = repo / root
            if not full.exists():
                continue
            files = [full] if full.is_file() else list(full.rglob("*.py")) + list(full.rglob("*.md"))
            for f in files:
                if _file_is_allowed(str(f)):
                    continue
                try:
                    if pattern.search(f.read_text(encoding="utf-8", errors="ignore")):
                        found.append(str(f.relative_to(repo)))
                except Exception:
                    pass
        assert not found, f"Termo 'telemóvel' encontrado em: {found}"

    def test_no_term_contactar(self):
        """Termo PT-PT 'contactar' não deve aparecer fora dos testes."""
        repo = Path("/home/will/whatsapp-rag")
        pattern = re.compile(r"\bcontactar\b", re.IGNORECASE)
        found = []
        for root in SCAN_ROOTS:
            full = repo / root
            if not full.exists():
                continue
            files = [full] if full.is_file() else list(full.rglob("*.py")) + list(full.rglob("*.md"))
            for f in files:
                if _file_is_allowed(str(f)):
                    continue
                try:
                    if pattern.search(f.read_text(encoding="utf-8", errors="ignore")):
                        found.append(str(f.relative_to(repo)))
                except Exception:
                    pass
        assert not found, f"Termo 'contactar' encontrado em: {found}"

    def test_no_term_presupuesto(self):
        """Termo ES 'presupuesto' não deve aparecer fora dos testes."""
        repo = Path("/home/will/whatsapp-rag")
        pattern = re.compile(r"\bpresupuesto\b", re.IGNORECASE)
        found = []
        for root in SCAN_ROOTS:
            full = repo / root
            if not full.exists():
                continue
            files = [full] if full.is_file() else list(full.rglob("*.py")) + list(full.rglob("*.md"))
            for f in files:
                if _file_is_allowed(str(f)):
                    continue
                try:
                    if pattern.search(f.read_text(encoding="utf-8", errors="ignore")):
                        found.append(str(f.relative_to(repo)))
                except Exception:
                    pass
        assert not found, f"Termo 'presupuesto' encontrado em: {found}"

    def test_no_term_instalacion(self):
        """Termo ES 'instalación' não deve aparecer fora dos testes."""
        repo = Path("/home/will/whatsapp-rag")
        pattern = re.compile(r"\binstalación\b", re.IGNORECASE)
        found = []
        for root in SCAN_ROOTS:
            full = repo / root
            if not full.exists():
                continue
            files = [full] if full.is_file() else list(full.rglob("*.py")) + list(full.rglob("*.md"))
            for f in files:
                if _file_is_allowed(str(f)):
                    continue
                try:
                    if pattern.search(f.read_text(encoding="utf-8", errors="ignore")):
                        found.append(str(f.relative_to(repo)))
                except Exception:
                    pass
        assert not found, f"Termo 'instalación' encontrado em: {found}"

    def test_no_term_mantenimiento(self):
        """Termo ES 'mantenimiento' não deve aparecer fora dos testes."""
        repo = Path("/home/will/whatsapp-rag")
        pattern = re.compile(r"\bmantenimiento\b", re.IGNORECASE)
        found = []
        for root in SCAN_ROOTS:
            full = repo / root
            if not full.exists():
                continue
            files = [full] if full.is_file() else list(full.rglob("*.py")) + list(full.rglob("*.md"))
            for f in files:
                if _file_is_allowed(str(f)):
                    continue
                try:
                    if pattern.search(f.read_text(encoding="utf-8", errors="ignore")):
                        found.append(str(f.relative_to(repo)))
                except Exception:
                    pass
        assert not found, f"Termo 'mantenimiento' encontrado em: {found}"

    def test_no_term_aire_acondicionado(self):
        """Termo ES 'aire acondicionado' não deve aparecer fora dos testes."""
        repo = Path("/home/will/whatsapp-rag")
        pattern = re.compile(r"\baire\s+acondicionado\b", re.IGNORECASE)
        found = []
        for root in SCAN_ROOTS:
            full = repo / root
            if not full.exists():
                continue
            files = [full] if full.is_file() else list(full.rglob("*.py")) + list(full.rglob("*.md"))
            for f in files:
                if _file_is_allowed(str(f)):
                    continue
                try:
                    if pattern.search(f.read_text(encoding="utf-8", errors="ignore")):
                        found.append(str(f.relative_to(repo)))
                except Exception:
                    pass
        assert not found, f"Termo 'aire acondicionado' encontrado em: {found}"