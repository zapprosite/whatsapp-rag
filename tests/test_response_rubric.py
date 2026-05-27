"""
Tests for response_rubric.py
"""
import pytest
from refrimix_core.evaluation.response_rubric import (
    evaluate_response,
    quick_evaluate,
    RubricScore,
    RubricResult,
)


class TestRubricScore:
    def test_media_calculation(self):
        score = RubricScore(
            naturalidade_ptbr=5.0,
            clareza=5.0,
            conversao=4.0,
            baixo_atrito=4.5,
            seguranca_tecnica=5.0,
            nao_inventa_preco=5.0,
            nao_diagnostica_sem_avaliar=5.0,
            agenda_facil=4.0,
            limite_perguntas=5.0,
            tom_whatsapp=4.5,
        )
        assert score.media == 4.7

    def test_to_dict(self):
        score = RubricScore(naturalidade_ptbr=4.0, clareza=4.0)
        d = score.to_dict()
        assert "naturalidade_ptbr" in d
        assert "media" in d


class TestEvaluateResponse:
    def test_portuguese_europeu_detected(self):
        result = evaluate_response(
            response_text="Como posso ajudá-lo? Por favor, envie uma foto.",
            user_text="quto fica",
        )
        assert "usa_portugues_europeu" in result.failures

    def test_spanish_detected(self):
        result = evaluate_response(
            response_text="Hola, cuánto cuesta la instalación?",
            user_text="quiero instalar",
        )
        assert "usa_espanhol" in result.failures

    def test_more_than_2_questions(self):
        result = evaluate_response(
            response_text="Qual o bairro? Qual o problema? Qual horário prefere? Qual seu nome?",
            user_text="meu ar não gela",
        )
        assert "mais_de_2_perguntas" in result.failures

    def test_photo_obligation(self):
        result = evaluate_response(
            response_text="Me manda uma foto do local para eu passar o valor.",
            user_text="instala ar",
        )
        assert "foto_obrigatoria" in result.failures

    def test_definitive_diagnosis(self):
        result = evaluate_response(
            response_text="O problema é a placa. Você precisa trocar a placa.",
            user_text="ar não gela",
        )
        assert "diagnostico_definitivo" in result.failures

    def test_how_can_i_help_after_client_explained(self):
        result = evaluate_response(
            response_text="Entendi. Como posso ajudá-lo?",
            user_text="meu ar não gela faz 3 dias e está marcando erro no visor",
        )
        assert "como_posso_ajudar_depois_cliente_explicar" in result.failures

    def test_electrical_risk_without_turn_off(self):
        result = evaluate_response(
            response_text="Vamos agendar uma visita técnica.",
            user_text="o disjuntor está caindo",
            is_electrical_risk=True,
        )
        assert "nao_orienta_desligar_em_risco_eletrico" in result.failures

    def test_electrical_risk_with_turn_off_ok(self):
        result = evaluate_response(
            response_text="⚠️ Mantenha o equipamento desligado. Me conta o bairro e agendemos.",
            user_text="o disjuntor está caindo",
            is_electrical_risk=True,
        )
        assert "nao_orienta_desligar_em_risco_eletrico" not in result.failures

    def test_good_response_low_score(self):
        result = evaluate_response(
            response_text="Bom dia! Higienização de split fica R$200 por aparelho. Quantos são?",
            user_text="faz limpeza",
        )
        assert result.score.media >= 4.0

    def test_faq_style_low_score(self):
        result = evaluate_response(
            response_text="Nosso serviço de limpeza inclui: 1. filtro 2. serpentina 3. dreno 4. verificação 5. testes",
            user_text="limpeza",
        )
        assert result.score.naturalidade_ptbr <= 2.5

    def test_text_too_long(self):
        result = evaluate_response(
            response_text="A" * 900,
            user_text="teste",
        )
        assert "texto_longo_demais" in result.failures

    def test_quick_evaluate(self):
        score, failures = quick_evaluate(
            response_text="Bom dia, quanto fica a limpeza?",
            category="higienizacao",
            user_text="faz limpeza",
        )
        assert score >= 3.5
        assert len(failures) < 3

    def test_invented_price(self):
        result = evaluate_response(
            response_text="Fica R$1500 a instalação.",
            user_text="instala ar",
        )
        assert "inventou_preco" in result.failures

    def test_valid_price_not_invented(self):
        result = evaluate_response(
            response_text="Instalação simples fica R$850 com material e mão de obra.",
            user_text="instala ar",
        )
        # R$850 is valid price
        assert "inventou_preco" not in result.failures

    def test_name_blocking(self):
        result = evaluate_response(
            response_text="Pra agendar, me passa seu nome primeiro.",
            user_text="queria agendar",
        )
        assert "nome_bloqueando_agendamento" in result.failures

    def test_name_not_blocking_if_optional(self):
        result = evaluate_response(
            response_text="Pra agendar, me passa seu nome se quiser (opcional). Qual período prefere?",
            user_text="queria agendar",
        )
        assert "nome_bloqueando_agendamento" not in result.failures


class TestRubricResult:
    def test_passou_true(self):
        score = RubricScore(
            naturalidade_ptbr=4.0, clareza=4.0, conversao=4.0,
            baixo_atrito=4.0, seguranca_tecnica=4.0, nao_inventa_preco=4.0,
            nao_diagnostica_sem_avaliar=4.0, agenda_facil=4.0,
            limite_perguntas=4.0, tom_whatsapp=4.0,
        )
        result = RubricResult(score=score, failures=[], is_critical_failure=False)
        assert result.passou

    def test_passou_false_critical(self):
        score = RubricScore(
            naturalidade_ptbr=4.0, clareza=4.0, conversao=4.0,
            baixo_atrito=4.0, seguranca_tecnica=4.0, nao_inventa_preco=4.0,
            nao_diagnostica_sem_avaliar=4.0, agenda_facil=4.0,
            limite_perguntas=4.0, tom_whatsapp=4.0,
        )
        result = RubricResult(score=score, failures=["inventou_preco"], is_critical_failure=True)
        assert not result.passou

    def test_passou_false_low_score(self):
        score = RubricScore(
            naturalidade_ptbr=2.0, clareza=2.0, conversao=2.0,
            baixo_atrito=2.0, seguranca_tecnica=2.0, nao_inventa_preco=2.0,
            nao_diagnostica_sem_avaliar=2.0, agenda_facil=2.0,
            limite_perguntas=2.0, tom_whatsapp=2.0,
        )
        result = RubricResult(score=score, failures=[], is_critical_failure=False)
        assert not result.passou


class TestEdgeCases:
    def test_empty_response(self):
        result = evaluate_response(response_text="", user_text="oi")
        assert result.is_critical_failure or result.score.media < 3.5

    def test_very_short_response(self):
        result = evaluate_response(response_text="Oi.", user_text="oi")
        assert result.score.media >= 3.5

    def test_client_just_said_oi(self):
        result = evaluate_response(
            response_text="Bom dia, tudo joia?\n\nMe conta: é instalação, manutenção, higienização ou conserto?",
            user_text="oi",
        )
        assert result.score.media >= 4.0

    def test_audio_transcribed_no_typo(self):
        result = evaluate_response(
            response_text="Ola bom dia meu ar nao esta gelando",
            user_text="Ola bom dia meu ar nao esta gelando",
            scenario_context={"message_type": "audio_transcribed"},
        )
        # Should not penalize transcribed audio for natural language style
        assert result.score.naturalidade_ptbr >= 4.0