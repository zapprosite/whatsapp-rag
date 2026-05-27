"""
Testes para understand_message com variantes PT-BR informais.
Garante que abreviações negativas (n, ñ, nao, num) não quebram detecção de intent.
"""
from __future__ import annotations

import pytest

from refrimix_core.nodes.understand_message import understand_message
from refrimix_core.domain.text_normalizer import fold


class TestFoldNegations:
    """fold() deve normalizar abreviações negativas comuns."""

    @pytest.mark.parametrize("input_text,expected_substr", [
        ("meu ar n gela", "não gela"),
        ("ar n gela", "não gela"),
        ("ar ñ gela", "não gela"),
        ("ar nao gela", "não"),
        ("ar num gela", "não gela"),
        ("n ta gelando", "não ta"),
        ("n tá gelando", "não tá"),
        ("ar n resfria", "não resfria"),
        ("ar n funciona", "não funciona"),
        ("nao tem foto", "não"),
        ("ñ sei", "não"),
        ("n sei", "não"),
    ])
    def test_fold_expands_negations(self, input_text, expected_substr):
        result = fold(input_text)
        assert expected_substr in result, f"fold('{input_text}') = '{result}', expected '{expected_substr}'"


class TestMaintenanceSignalDetection:
    """Variações de 'não gela' devem ser detectadas como maintenance_signal."""

    @pytest.mark.parametrize("text", [
        "meu ar n gela",
        "ar n gela",
        "ar ñ gela",
        "ar nao gela",
        "ar num gela",
        "n ta gelando",
        "n tá gelando",
        "só ventila",
        "ventila mas não gela",
        "parou de gelar",
        "ar não gela",
        "ar não gela mais",
        "n resfria",
        "condensadora n liga",
        "parte de fora n liga",
    ])
    def test_maintenance_signal_variant(self, text):
        result = understand_message(text, "conversation", None, None)
        assert result["kind"] == "maintenance_signal", (
            f"'{text}' → kind={result['kind']}, maintenance_signal={result.get('maintenance_signal')}"
        )
        assert result["maintenance_signal"] is not None


class TestNonMaintenanceIntents:
    """Mensagens que NÃO são manutenção devem continuar funcionando."""

    @pytest.mark.parametrize("text,expected_kind", [
        ("qto fica limpeza", "service_new"),           # limpeza → higienizacao
        ("dijuntor cai", "maintenance_signal"),         # disjuntor cai → manutenção
        ("oi", "greeting"),
        ("bom dia", "greeting"),
        ("quanto custa instalação", "service_new"),    # instalação
        ("manutenção quanto custa", "service_new"),  # sem service_in_state → service_new (correcto)
    ])
    def test_non_maintenance(self, text, expected_kind):
        result = understand_message(text, "conversation", None, None)
        assert result["kind"] == expected_kind, (
            f"'{text}' → kind={result['kind']}, expected={expected_kind}"
        )