"""Tests for risk_detector.py — pure, deterministic risk classification."""


from refrimix_core.domain.risk_detector import (
    detect_risk,
)


class TestHighRisk:
    """High-risk scenarios (keyword or intent → risk=high, handoff=True)."""

    def test_disjuntor_cai_high_risk(self) -> None:
        result = detect_risk(
            message="o disjuntor tá caindo",
            intent_key="generic",
            lead_context={},
        )
        assert result.risk_level == "high"
        assert result.human_handoff is True
        assert result.safety_alert is not None
        assert "disjuntor" in result.trigger_keywords or any(
            "disjuntor" in kw for kw in result.trigger_keywords
        )

    def test_fio_esquenta_high_risk(self) -> None:
        result = detect_risk(
            message="o fio esquenta quando ligo",
            intent_key="generic",
            lead_context={},
        )
        assert result.risk_level == "high"
        assert result.human_handoff is True
        assert result.safety_alert is not None
        assert any("fio esquenta" in kw or "fio" in kw for kw in result.trigger_keywords)

    def test_cheiro_queimado_high_risk(self) -> None:
        result = detect_risk(
            message="cheiro de queimado no ar",
            intent_key="generic",
            lead_context={},
        )
        assert result.risk_level == "high"
        assert result.human_handoff is True
        assert result.safety_alert is not None

    def test_tomada_derretendo_high_risk(self) -> None:
        result = detect_risk(
            message="tomada tá derretendo",
            intent_key="generic",
            lead_context={},
        )
        assert result.risk_level == "high"
        assert result.human_handoff is True
        assert result.safety_alert is not None

    def test_fascada_high_risk(self) -> None:
        result = detect_risk(
            message="saiu uma faísca",
            intent_key="generic",
            lead_context={},
        )
        assert result.risk_level == "high"
        assert result.human_handoff is True
        assert result.safety_alert is not None

    def test_generic_text_high_risk_bypasses_intent(self) -> None:
        """Keyword 'fio esquenta' fires high even when intent is generic."""
        result = detect_risk(
            message="o fio esquenta muito",
            intent_key="generic",
            lead_context={},
        )
        assert result.risk_level == "high"
        assert result.human_handoff is True

    def test_trigger_keywords_listed(self) -> None:
        """Multiple keywords in message → all listed in trigger_keywords."""
        result = detect_risk(
            message="o disjuntor cai e o fio esquenta",
            intent_key="generic",
            lead_context={},
        )
        assert result.risk_level == "high"
        keywords_found = [kw for kw in result.trigger_keywords]
        assert len(keywords_found) >= 2


class TestMediumRisk:
    """Medium-risk intents → risk=medium, no handoff."""

    def test_nao_gela_medium_risk(self) -> None:
        result = detect_risk(
            message="o ar não gela de jeito nenhum",
            intent_key="nao_gela",
            lead_context={},
        )
        assert result.risk_level == "medium"
        assert result.human_handoff is False
        assert result.safety_alert is None

    def test_barulho_medium_risk(self) -> None:
        result = detect_risk(
            message="está fazendo barulho estranho",
            intent_key="barulho",
            lead_context={},
        )
        assert result.risk_level == "medium"
        assert result.human_handoff is False

    def test_nao_liga_medium_risk(self) -> None:
        result = detect_risk(
            message="o split não liga",
            intent_key="nao_liga",
            lead_context={},
        )
        assert result.risk_level == "medium"
        assert result.human_handoff is False


class TestLowRisk:
    """Low-risk intents → risk=low, no handoff."""

    def test_welcome_low_risk(self) -> None:
        result = detect_risk(
            message="olá tudo bem",
            intent_key="welcome",
            lead_context={},
        )
        assert result.risk_level == "low"
        assert result.human_handoff is False

    def test_higienizacao_low_risk(self) -> None:
        result = detect_risk(
            message="quanto custa a higienização",
            intent_key="higienizacao",
            lead_context={},
        )
        assert result.risk_level == "low"
        assert result.human_handoff is False

    def test_orcamento_low_risk(self) -> None:
        result = detect_risk(
            message="gostaria de um orçamento",
            intent_key="orcamento",
            lead_context={},
        )
        assert result.risk_level == "low"
        assert result.human_handoff is False


class TestElectricContext:
    """electric_context flag is True when electrical hazard terms appear."""

    def test_electric_context_true_for_fio(self) -> None:
        result = detect_risk(
            message="o fio está quente",
            intent_key="generic",
            lead_context={},
        )
        assert result.electric_context is True

    def test_electric_context_true_for_disjuntor(self) -> None:
        result = detect_risk(
            message="o disjuntor caiu",
            intent_key="generic",
            lead_context={},
        )
        assert result.electric_context is True

    def test_electric_context_false_for_nao_gela(self) -> None:
        result = detect_risk(
            message="o ar não gela",
            intent_key="nao_gela",
            lead_context={},
        )
        # nao_gela has no electrical keyword by itself
        assert result.electric_context is False
