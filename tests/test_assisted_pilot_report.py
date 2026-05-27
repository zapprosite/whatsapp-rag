"""Testes para assisted_pilot_report.py."""

import os
from unittest.mock import MagicMock, patch

import pytest

from refrimix_core.monitoring.assisted_pilot_report import (
    AssistedPilotReport,
    PilotMetrics,
    _MIN_CANARY_APPROVAL_RATE,
    _MIN_CANARY_CONVERSATIONS,
    _MAX_CANARY_REJECT_RATE,
    generate_report,
)


class TestPilotMetrics:
    """Testes para PilotMetrics dataclass."""

    def test_pilot_metrics_defaults(self):
        m = PilotMetrics()
        assert m.total_conversations == 0
        assert m.total_review_items == 0
        assert m.approval_without_edit_rate == 0.0
        assert m.canary_recommended is False

    def test_pilot_metrics_settable(self):
        m = PilotMetrics(
            total_conversations=30,
            total_review_items=90,
            approvals_without_edit=63,
            human_edits=15,
            rejections=9,
            expired=3,
            sent=50,
        )
        assert m.total_conversations == 30
        assert m.total_review_items == 90
        assert m.approvals_without_edit == 63


class TestAssistedPilotReportGenerate:
    """Testes para AssistedPilotReport.generate()."""

    def _mock_all_sources(self, mock_queue, mock_fb, mock_ot, mock_st):
        """Helper: patch all source modules used inside generate()."""
        return (
            patch("refrimix_core.review.review_queue.get_review_queue", mock_queue),
            patch("refrimix_core.monitoring.production_feedback.ProductionFeedbackStore", mock_fb),
            patch("refrimix_core.monitoring.lead_outcome_tracker.LeadOutcomeTracker", mock_ot),
            patch("refrimix_core.monitoring.whatsapp_status_tracker.WhatsAppStatusTracker", mock_st),
        )

    def test_generate_empty_returns_zeros(self):
        """Com store vazia, métricas são todas zero."""
        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = []

        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            report = AssistedPilotReport()
            metrics = report.generate()

            assert metrics.total_conversations == 0
            assert metrics.total_review_items == 0
            assert metrics.approvals_without_edit == 0
            assert metrics.human_edits == 0
            assert metrics.rejections == 0
            assert metrics.canary_recommended is False

    def test_generate_calculates_rates(self):
        """Taxas são calculadas corretamente com items."""
        mock_item = MagicMock()
        mock_item.conversation_id = "conv_1"
        mock_item.status.value = "approved"
        mock_item.proposed_channel.value = "text"
        mock_item.intent = "welcome"
        mock_item.priority.value = "low"
        mock_item.suggested_response = "Olá"
        mock_item.approved_response = None
        mock_item.edit_reason = None
        mock_item.updated_at = None

        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = [mock_item]

        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            report = AssistedPilotReport()
            metrics = report.generate()
            assert metrics.total_review_items == 1
            assert metrics.approvals_without_edit == 1

    def test_generate_meets_min_conversations_false_under_30(self):
        """Abaixo de 30 conversas, meets_min_conversations é False."""
        mock_item = MagicMock()
        mock_item.conversation_id = "conv_1"
        mock_item.status.value = "approved"
        mock_item.proposed_channel.value = "text"
        mock_item.intent = "welcome"
        mock_item.priority.value = "low"
        mock_item.suggested_response = "Olá"
        mock_item.approved_response = None
        mock_item.edit_reason = None
        mock_item.updated_at = None

        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = [mock_item] * 5

        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            report = AssistedPilotReport()
            metrics = report.generate()
            assert metrics.meets_min_conversations is False


class TestAssistedPilotReportCanaryCriteria:
    """Testes para avaliação de critérios canary."""

    def _mock_report_with_metrics(self, **kwargs) -> PilotMetrics:
        """Cria report com métricas mockadas e avalia critérios."""
        # Create mock queue returning empty list (no real data)
        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = []

        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        with patch("refrimix_core.review.review_queue.get_review_queue", mock_queue), \
             patch("refrimix_core.monitoring.production_feedback.ProductionFeedbackStore", mock_fb), \
             patch("refrimix_core.monitoring.lead_outcome_tracker.LeadOutcomeTracker", mock_ot), \
             patch("refrimix_core.monitoring.whatsapp_status_tracker.WhatsAppStatusTracker", mock_st):
            report = AssistedPilotReport()
            # Inject metrics manually then evaluate
            report._metrics = PilotMetrics(**kwargs)
            report._compute_rates()
            report._evaluate_canary_criteria()
            return report._metrics

    def test_canary_recommended_all_true(self):
        """Todos os critérios True → canary_recommended = True."""
        m = self._mock_report_with_metrics(
            total_conversations=30,
            total_review_items=30,
            approvals_without_edit=24,
            human_edits=4,
            rejections=2,
            expired=0,
            sent=26,
            approval_without_edit_rate=0.80,
            reject_rate=0.07,
            critical_guardrail_blocks=0,
            risco_eletrico_autoenviado=False,
            documentos_autoenviados=False,
            refinement_loop_run=True,
            real_cases_exported=True,
        )
        assert m.canary_recommended is True

    def test_canary_not_recommended_low_approval(self):
        """Approval rate < 70% → canary NOT recommended."""
        m = self._mock_report_with_metrics(
            total_conversations=30,
            total_review_items=30,
            approvals_without_edit=15,
            human_edits=10,
            rejections=5,
            expired=0,
            sent=25,
            approval_without_edit_rate=0.50,
            reject_rate=0.17,
            critical_guardrail_blocks=0,
            risco_eletrico_autoenviado=False,
            documentos_autoenviados=False,
            refinement_loop_run=True,
            real_cases_exported=True,
        )
        assert m.canary_recommended is False
        assert m.canary_approval_enough is False

    def test_canary_not_recommended_high_reject(self):
        """Reject rate > 10% → canary NOT recommended."""
        m = self._mock_report_with_metrics(
            total_conversations=30,
            total_review_items=30,
            approvals_without_edit=22,
            human_edits=2,
            rejections=6,
            expired=0,
            sent=24,
            approval_without_edit_rate=0.73,
            reject_rate=0.20,
            critical_guardrail_blocks=0,
            risco_eletrico_autoenviado=False,
            documentos_autoenviados=False,
            refinement_loop_run=True,
            real_cases_exported=True,
        )
        assert m.canary_recommended is False
        assert m.canary_reject_acceptable is False

    def test_canary_not_recommended_risco_autoenviado(self):
        """Risco elétrico autoenviado → canary NOT recommended."""
        m = self._mock_report_with_metrics(
            total_conversations=30,
            total_review_items=30,
            approvals_without_edit=24,
            human_edits=4,
            rejections=2,
            expired=0,
            sent=28,
            approval_without_edit_rate=0.80,
            reject_rate=0.07,
            critical_guardrail_blocks=0,
            risco_eletrico_autoenviado=True,
            documentos_autoenviados=False,
            refinement_loop_run=True,
            real_cases_exported=True,
        )
        assert m.canary_recommended is False
        assert m.risco_eletrico_safe is False

    def test_canary_not_recommended_documentos_autoenviados(self):
        """Documentos autoenviados → canary NOT recommended."""
        m = self._mock_report_with_metrics(
            total_conversations=30,
            total_review_items=30,
            approvals_without_edit=24,
            human_edits=4,
            rejections=2,
            expired=0,
            sent=28,
            approval_without_edit_rate=0.80,
            reject_rate=0.07,
            critical_guardrail_blocks=0,
            risco_eletrico_autoenviado=False,
            documentos_autoenviados=True,
            refinement_loop_run=True,
            real_cases_exported=True,
        )
        assert m.canary_recommended is False
        assert m.documentos_safe is False

    def test_canary_not_recommended_without_refinement_loop(self):
        """Refinement loop não executado → canary NOT recommended."""
        m = self._mock_report_with_metrics(
            total_conversations=30,
            total_review_items=30,
            approvals_without_edit=24,
            human_edits=4,
            rejections=2,
            expired=0,
            sent=28,
            approval_without_edit_rate=0.80,
            reject_rate=0.07,
            critical_guardrail_blocks=0,
            risco_eletrico_autoenviado=False,
            documentos_autoenviados=False,
            refinement_loop_run=False,
            real_cases_exported=False,
        )
        assert m.canary_recommended is False

    def test_canary_not_recommended_under_30_conversations(self):
        """Menos de 30 conversas → canary NOT recommended."""
        m = self._mock_report_with_metrics(
            total_conversations=10,
            total_review_items=10,
            approvals_without_edit=9,
            human_edits=0,
            rejections=1,
            expired=0,
            sent=9,
            approval_without_edit_rate=0.90,
            reject_rate=0.10,
            critical_guardrail_blocks=0,
            risco_eletrico_autoenviado=False,
            documentos_autoenviados=False,
            refinement_loop_run=True,
            real_cases_exported=True,
        )
        assert m.canary_recommended is False
        assert m.meets_min_conversations is False


class TestGenerateReportFunction:
    """Testes para a função generate_report()."""

    def _mock_all_sources(self, mock_queue, mock_fb, mock_ot, mock_st):
        return (
            patch("refrimix_core.review.review_queue.get_review_queue", mock_queue),
            patch("refrimix_core.monitoring.production_feedback.ProductionFeedbackStore", mock_fb),
            patch("refrimix_core.monitoring.lead_outcome_tracker.LeadOutcomeTracker", mock_ot),
            patch("refrimix_core.monitoring.whatsapp_status_tracker.WhatsAppStatusTracker", mock_st),
        )

    def test_generate_report_creates_reports_dir(self, tmp_path):
        """generate_report cria diretório de reports se não existir."""
        report_file = tmp_path / "subdir" / "report.json"
        assert not report_file.parent.exists()

        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = []
        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            generate_report(
                min_conversations=30,
                output_json=str(report_file),
                reports_dir=str(tmp_path / "subdir"),
            )

        assert report_file.exists()

    def test_generate_report_returns_dict(self, tmp_path):
        """generate_report retorna dict com todas as chaves necessárias."""
        report_file = tmp_path / "report.json"

        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = []
        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            result = generate_report(
                min_conversations=30,
                output_json=str(report_file),
                reports_dir=str(tmp_path),
            )

        assert "report_version" in result
        assert "generated_at" in result
        assert "volume" in result
        assert "human_action" in result
        assert "rates" in result
        assert "canary_criteria" in result
        assert "whatsapp_status" in result
        assert "appointments" in result

    def test_generate_report_warns_under_min_conversations(self, tmp_path, capsys):
        """Aviso quando conversas < min_conversations."""
        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = []
        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            generate_report(
                min_conversations=30,
                output_json=str(tmp_path / "report.json"),
                reports_dir=str(tmp_path),
            )

        captured = capsys.readouterr()
        assert "conversas" in captured.out or "Aguardando" in captured.out


class TestAssistedPilotReportToDict:
    """Testes para to_dict()."""

    def _mock_all_sources(self, mock_queue, mock_fb, mock_ot, mock_st):
        return (
            patch("refrimix_core.review.review_queue.get_review_queue", mock_queue),
            patch("refrimix_core.monitoring.production_feedback.ProductionFeedbackStore", mock_fb),
            patch("refrimix_core.monitoring.lead_outcome_tracker.LeadOutcomeTracker", mock_ot),
            patch("refrimix_core.monitoring.whatsapp_status_tracker.WhatsAppStatusTracker", mock_st),
        )

    def test_to_dict_contains_all_required_keys(self):
        """to_dict() contém todas as chaves requeridas."""
        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = []
        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            report = AssistedPilotReport()
            report.generate()
            d = report.to_dict()

        required_keys = [
            "report_version",
            "generated_at",
            "volume",
            "human_action",
            "rates",
            "timing",
            "intents",
            "before_after_examples",
            "appointments",
            "whatsapp_status",
            "audio",
            "critical_safety",
            "canary_criteria",
        ]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_canary_criteria_contains_threshold_values(self):
        """canary_criteria inclui os limiares usados na avaliação."""
        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = []
        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            report = AssistedPilotReport()
            report.generate()
            d = report.to_dict()

        crit = d["canary_criteria"]
        assert crit["min_conversations_required"] == _MIN_CANARY_CONVERSATIONS
        assert crit["min_approval_rate_required"] == _MIN_CANARY_APPROVAL_RATE
        assert crit["max_reject_rate"] == _MAX_CANARY_REJECT_RATE


class TestAssistedPilotReportToMarkdown:
    """Testes para to_markdown()."""

    def _mock_all_sources(self, mock_queue, mock_fb, mock_ot, mock_st):
        return (
            patch("refrimix_core.review.review_queue.get_review_queue", mock_queue),
            patch("refrimix_core.monitoring.production_feedback.ProductionFeedbackStore", mock_fb),
            patch("refrimix_core.monitoring.lead_outcome_tracker.LeadOutcomeTracker", mock_ot),
            patch("refrimix_core.monitoring.whatsapp_status_tracker.WhatsAppStatusTracker", mock_st),
        )

    def test_to_markdown_contains_sections(self):
        """Markdown gerado contém seções esperadas."""
        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = []
        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            report = AssistedPilotReport()
            report.generate()
            md = report.to_markdown()

        sections = [
            "# Assisted Pilot Report — Phase 2.9",
            "## Resumo",
            "## Appointment / Conversion",
            "## WhatsApp Status",
            "## Segurança Crítica",
            "## Critérios Canary",
            "## Recomendação",
        ]
        for section in sections:
            assert section in md, f"Missing section: {section}"

    def test_to_markdown_markdown_table_format(self):
        """Tabelas em markdown usam a sintaxe correta."""
        mock_queue = MagicMock()
        mock_queue.return_value.list_items.return_value = []
        mock_fb = MagicMock()
        mock_ot = MagicMock()
        mock_st = MagicMock()

        mocks = self._mock_all_sources(mock_queue, mock_fb, mock_ot, mock_st)
        with mocks[0], mocks[1], mocks[2], mocks[3]:
            report = AssistedPilotReport()
            report.generate()
            md = report.to_markdown()

        # Check for markdown table separators
        assert "|---" in md


class TestAssistedPilotReportComputeRates:
    """Testes para _compute_rates()."""

    def test_compute_rates_basic(self):
        """Taxas básicas são calculadas corretamente."""
        m = PilotMetrics(
            total_conversations=30,
            total_review_items=100,
            approvals_without_edit=70,
            human_edits=15,
            rejections=10,
            expired=5,
        )
        report = AssistedPilotReport()
        report._metrics = m
        report._compute_rates()

        assert m.approval_without_edit_rate == 0.70
        assert m.edit_rate == 0.15
        assert m.reject_rate == 0.10
        assert m.expire_rate == 0.05

    def test_compute_rates_zero_total(self):
        """Com total=0, taxas são zero (sem divisão por zero)."""
        m = PilotMetrics(total_review_items=0)
        report = AssistedPilotReport()
        report._metrics = m
        report._compute_rates()
        assert m.approval_without_edit_rate == 0.0
