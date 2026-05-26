"""Tests for guardrail_validator.py — pure, deterministic response validation."""


from refrimix_core.domain.guardrail_validator import (
    validate_response,
    MAX_TEXT_LENGTH,
)


class TestValidResponses:
    """Responses that should pass validation cleanly."""

    def test_valid_canonical_response(self) -> None:
        result = validate_response(
            response_text="Olá! Como posso ajudar? Preciso de mais detalhes sobre o equipamento.",
            intent_key="welcome",
            risk_level="low",
            lead_context={},
        )
        assert result.is_valid is True
        assert result.violations == []
        assert result.corrected_text is None


class TestPrecoInventado:
    """Responses that invent prices are blocked."""

    def test_preco_inventado_blocked(self) -> None:
        result = validate_response(
            response_text="Custa R$500 para arrumar.",
            intent_key="orcamento",
            risk_level="low",
            lead_context={},
        )
        assert result.is_valid is False
        assert "preco_inventado" in result.violations

    def test_valor_fechado_blocked(self) -> None:
        result = validate_response(
            response_text="Fazemos valor fechado de R$800.",
            intent_key="orcamento",
            risk_level="low",
            lead_context={},
        )
        assert result.is_valid is False
        assert "preco_inventado" in result.violations

    def test_fica_r_blocked(self) -> None:
        result = validate_response(
            response_text="Fica R$200 o serviço.",
            intent_key="orcamento",
            risk_level="low",
            lead_context={},
        )
        assert result.is_valid is False
        assert "preco_inventado" in result.violations


class TestDiagnosticoDefinitivo:
    """Responses that claim definite diagnoses are blocked."""

    def test_diagnostico_definitivo_blocked(self) -> None:
        result = validate_response(
            response_text="É falta de gás com certeza, vou encher.",
            intent_key="nao_gela",
            risk_level="medium",
            lead_context={},
        )
        assert result.is_valid is False
        assert "diagnostico_definitivo" in result.violations

    def test_falta_de_gas_blocked(self) -> None:
        result = validate_response(
            response_text="O compressor queimou, precisa trocar.",
            intent_key="nao_liga",
            risk_level="medium",
            lead_context={},
        )
        assert result.is_valid is False
        assert "diagnostico_definitivo" in result.violations

    def test_placa_queimou_blocked(self) -> None:
        result = validate_response(
            response_text="A placa queimou, vou substituir.",
            intent_key="nao_liga",
            risk_level="medium",
            lead_context={},
        )
        assert result.is_valid is False
        assert "diagnostico_definitivo" in result.violations


class TestPortuguesEuropeu:
    """Responses using European Portuguese forms are blocked."""

    def test_portugues_europeu_blocked(self) -> None:
        result = validate_response(
            response_text="Então, preciso te ajudar com isso.",
            intent_key="welcome",
            risk_level="low",
            lead_context={},
        )
        assert result.is_valid is False
        assert "portugues_europeu" in result.violations

    def test_preciso_te_ajudar_blocked(self) -> None:
        result = validate_response(
            response_text="Então, preciso-te ajudar com a instalação.",
            intent_key="servicos",
            risk_level="low",
            lead_context={},
        )
        assert result.is_valid is False
        assert "portugues_europeu" in result.violations


class TestEspanhol:
    """Responses containing Spanish are blocked."""

    def test_espanhol_blocked(self) -> None:
        result = validate_response(
            response_text="¿Necesito ayuda con el splits?",
            intent_key="welcome",
            risk_level="low",
            lead_context={},
        )
        assert result.is_valid is False
        assert "espanhol" in result.violations


class TestLengthAndQuestions:
    """Responses exceeding length or question limits are blocked."""

    def test_texto_muito_longo_blocked(self) -> None:
        long_text = "a" * (MAX_TEXT_LENGTH + 1)
        result = validate_response(
            response_text=long_text,
            intent_key="welcome",
            risk_level="low",
            lead_context={},
        )
        assert result.is_valid is False
        assert "texto_muito_longo" in result.violations

    def test_texto_dentro_limite_ok(self) -> None:
        normal_text = "a" * MAX_TEXT_LENGTH
        result = validate_response(
            response_text=normal_text,
            intent_key="welcome",
            risk_level="low",
            lead_context={},
        )
        assert result.is_valid is True

    def test_excesso_perguntas_blocked(self) -> None:
        text = "pergunta? pergunta2? pergunta3? pergunta4?"
        result = validate_response(
            response_text=text,
            intent_key="nao_gela",
            risk_level="medium",
            lead_context={},
        )
        assert result.is_valid is False
        assert "excesso_de_perguntas" in result.violations

    def test_tres_perguntas_ok(self) -> None:
        text = "primeira? segunda? terceira?"
        result = validate_response(
            response_text=text,
            intent_key="nao_gela",
            risk_level="medium",
            lead_context={},
        )
        assert result.is_valid is True


class TestHighRiskSafetyAlert:
    """High-risk responses must contain a safety alert or are blocked."""

    def test_high_risk_missing_safety_alert(self) -> None:
        result = validate_response(
            response_text="Vou mandar um técnico amanhã.",
            intent_key="disjuntor_cai",
            risk_level="high",
            lead_context={},
        )
        assert result.is_valid is False
        assert "falta_alerta_seguranca" in result.violations

    def test_high_risk_with_safety_alert_ok(self) -> None:
        result = validate_response(
            response_text="Manter desligado até avaliação profissional. Vou acionar um técnico.",
            intent_key="disjuntor_cai",
            risk_level="high",
            lead_context={},
        )
        assert result.is_valid is True
        assert result.violations == []

    def test_high_risk_with_avaliacao_ok(self) -> None:
        """Contains 'avaliação' → satisfies safety alert requirement."""
        result = validate_response(
            response_text="Chama um profissional para avaliação.",
            intent_key="cheiro_queimado",
            risk_level="high",
            lead_context={},
        )
        assert result.is_valid is True

    def test_high_risk_with_profissional_ok(self) -> None:
        """Contains 'profissional' → satisfies safety alert requirement."""
        result = validate_response(
            response_text="Consulta um profissional especializado.",
            intent_key="fio_esquenta",
            risk_level="high",
            lead_context={},
        )
        assert result.is_valid is True
