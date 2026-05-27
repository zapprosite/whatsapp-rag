"""
Assisted Pilot Report — métricas consolidadas do piloto com conversas reais.

Agrega dados de:
- ReviewQueue (review items)
- ProductionFeedbackStore (before/after)
- WhatsAppStatusTracker (sent/delivered/read/failed)
- LeadOutcomeTracker (agendado, handoff)

Gera relatório JSON com todos os KPIs do piloto.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Adiciona raiz ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@dataclass
class PilotMetrics:
    """Métricas consolidadas do piloto assistido."""

    # Volume
    total_conversations: int = 0
    total_review_items: int = 0

    # Ação humana
    approvals_without_edit: int = 0
    human_edits: int = 0
    rejections: int = 0
    expired: int = 0
    sent: int = 0

    # Taxas
    approval_without_edit_rate: float = 0.0
    edit_rate: float = 0.0
    reject_rate: float = 0.0
    expire_rate: float = 0.0

    # Tempo
    avg_time_to_human_action_seconds: float = 0.0
    avg_time_to_first_response_seconds: float = 0.0

    # Intents
    intents_most_edited: dict[str, int] = field(default_factory=dict)
    intents_most_rejected: dict[str, int] = field(default_factory=dict)

    # Before/After
    before_after_examples: list[dict] = field(default_factory=list)

    # Appointment / Conversion
    appointment_offered_count: int = 0
    appointment_scheduled_count: int = 0
    appointment_offer_rate: float = 0.0
    appointment_scheduled_rate: float = 0.0
    human_handoff_count: int = 0
    human_handoff_rate: float = 0.0

    # Status WhatsApp
    status_sent: int = 0
    status_delivered: int = 0
    status_read: int = 0
    status_failed: int = 0

    # Audio
    audio_candidate_count: int = 0
    audio_sent_count: int = 0

    # Critical guards
    critical_guardrail_blocks: int = 0
    risco_eletrico_autoenviado: bool = False
    documentos_autoenviados: bool = False

    # Refinement
    refinement_loop_run: bool = False
    real_cases_exported: bool = False

    # Critérios canary
    meets_min_conversations: bool = False
    canary_approval_enough: bool = False
    canary_reject_acceptable: bool = False
    zero_critical_failures: bool = False
    risco_eletrico_safe: bool = False
    documentos_safe: bool = False
    refinement_loop_done: bool = False
    canary_recommended: bool = False

    # Timestamp
    generated_at: str = ""


@dataclass
class AnonymizedExample:
    """Exemplo before/after anonimizado para o relatório."""

    conversation_id_masked: str
    intent: str
    priority: str
    suggested_response: str
    human_response: str
    action: str  # "approved", "edited", "rejected"
    edit_reason: Optional[str] = None


# ── Constants ─────────────────────────────────────────────────────────────────

_REPORT_VERSION = "2.9"
_MIN_CANARY_CONVERSATIONS = 30
_MIN_CANARY_APPROVAL_RATE = 0.70
_MAX_CANARY_REJECT_RATE = 0.10
_MAX_CANARY_EXPIRE_RATE = 0.05

_HIGH_VALUE_INTENTS = frozenset([
    "projeto", "pmoc", "laudo", "contrato", "proposta",
    "sla", "proposta_tecnica", "orcamento",
])
_URGENT_INTENTS = frozenset([
    "risco_eletrico", "risco", "eletrico", "choque",
    "curto", "fumaca", "cheiro_queimado", "desligando",
    "reclamacao", "problema",
])


# ── Report Generator ────────────────────────────────────────────────────────────

class AssistedPilotReport:
    """Gera relatório consolidado do piloto assistido."""

    def __init__(self, reports_dir: str = "reports"):
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(exist_ok=True, parents=True)
        self._metrics = PilotMetrics()

    def generate(self) -> PilotMetrics:
        """Coleta métricas de todas as fontes e gera relatório."""
        self._collect_review_queue_metrics()
        self._collect_feedback_metrics()
        self._collect_outcome_metrics()
        self._collect_status_metrics()
        self._evaluate_canary_criteria()
        return self._metrics

    def _compute_rates(self) -> None:
        """Calcula taxas derivadas do total de review items."""
        total = self._metrics.total_review_items
        if total == 0:
            return

        total_f = float(total)
        self._metrics.approval_without_edit_rate = round(
            self._metrics.approvals_without_edit / total_f, 3)
        self._metrics.edit_rate = round(self._metrics.human_edits / total_f, 3)
        self._metrics.reject_rate = round(self._metrics.rejections / total_f, 3)
        self._metrics.expire_rate = round(self._metrics.expired / total_f, 3)

        # Outcomes
        if self._metrics.total_conversations > 0:
            conv_f = float(self._metrics.total_conversations)
            self._metrics.appointment_offer_rate = round(
                self._metrics.appointment_offered_count / conv_f, 3)
            self._metrics.appointment_scheduled_rate = round(
                self._metrics.appointment_scheduled_count / conv_f, 3)
            self._metrics.human_handoff_rate = round(
                self._metrics.human_handoff_count / conv_f, 3)

    def _collect_review_queue_metrics(self) -> None:
        """Coleta métricas da ReviewQueue."""
        from refrimix_core.review.review_queue import get_review_queue, ReviewQueueFilter
        from refrimix_core.review.review_models import ReviewPriority, ReviewStatus

        queue = get_review_queue()
        all_items = queue.list_items(limit=10000)

        self._metrics.total_review_items = len(all_items)

        # Count by status
        status_counts: dict[str, int] = {}
        for item in all_items:
            status_counts[item.status.value] = status_counts.get(item.status.value, 0) + 1

        self._metrics.approvals_without_edit = status_counts.get("approved", 0)
        self._metrics.human_edits = status_counts.get("edited", 0)
        self._metrics.rejections = status_counts.get("rejected", 0)
        self._metrics.expired = status_counts.get("expired", 0)
        self._metrics.sent = status_counts.get("sent", 0)

        # Unique conversations
        conv_ids = {item.conversation_id for item in all_items}
        self._metrics.total_conversations = len(conv_ids)

        # Audio candidates
        from refrimix_core.review.review_models import ProposedChannel
        audio_items = [
            i for i in all_items
            if i.proposed_channel == ProposedChannel.AUDIO
        ]
        self._metrics.audio_candidate_count = len(audio_items)
        self._metrics.audio_sent_count = sum(
            1 for i in audio_items if i.status == ReviewStatus.SENT)

        # Tempo médio até ação humana
        action_times: list[float] = []
        for item in all_items:
            if item.updated_at is not None:
                delta = (item.updated_at - item.created_at).total_seconds()
                action_times.append(delta)
        if action_times:
            self._metrics.avg_time_to_human_action_seconds = round(
                sum(action_times) / len(action_times), 1)

        # Intents mais editados e rejeitados
        edit_intents: dict[str, int] = {}
        reject_intents: dict[str, int] = {}
        for item in all_items:
            if item.status == ReviewStatus.EDITED:
                edit_intents[item.intent] = edit_intents.get(item.intent, 0) + 1
            if item.status == ReviewStatus.REJECTED:
                reject_intents[item.intent] = reject_intents.get(item.intent, 0) + 1

        # Sort desc
        self._metrics.intents_most_edited = dict(
            sorted(edit_intents.items(), key=lambda x: -x[1])[:5])
        self._metrics.intents_most_rejected = dict(
            sorted(reject_intents.items(), key=lambda x: -x[1])[:5])

        # Antes/depois exemplos (anonimizados)
        from refrimix_core.evaluation.real_case_exporter import RealCaseExporter
        exporter = RealCaseExporter()
        before_after: list[dict] = []
        for item in all_items:
            if item.status in {ReviewStatus.EDITED, ReviewStatus.REJECTED}:
                if not item.suggested_response and not item.approved_response:
                    continue
                response = item.approved_response or item.suggested_response
                human_resp = item.approved_response if item.status == ReviewStatus.EDITED else ""
                before_after.append({
                    "conversation_id_masked": f"MASCARA_CONV_{item.conversation_id[:8]}",
                    "intent": item.intent,
                    "priority": item.priority.value,
                    "suggested_response": item.suggested_response[:300],
                    "human_response": human_resp[:300] if human_resp else "",
                    "action": item.status.value,
                    "edit_reason": item.edit_reason or None,
                })
        self._metrics.before_after_examples = before_after[:10]  # max 10 examples

        # Check risco_eletrico autoenviado
        risco_items = [i for i in all_items if "risco" in i.intent.lower() or "eletrico" in i.intent.lower()]
        if risco_items:
            autoenviados = [
                i for i in risco_items
                if i.status == ReviewStatus.SENT and i.edit_reason is None
            ]
            self._metrics.risco_eletrico_autoenviado = len(autoenviados) > 0

        # Documentos autoenviados
        doc_items = [
            i for i in all_items
            if i.proposed_channel == ProposedChannel.PDF
        ]
        if doc_items:
            doc_auto = [i for i in doc_items if i.status == ReviewStatus.SENT]
            self._metrics.documentos_autoenviados = len(doc_auto) > 0

    def _collect_feedback_metrics(self) -> None:
        """Coleta métricas do ProductionFeedbackStore."""
        from refrimix_core.monitoring.production_feedback import ProductionFeedbackStore

        store = ProductionFeedbackStore()
        stats = store.get_feedback_stats()
        # Feedback store is append-only; for real usage this needs singleton
        # Integration with review_actions._save_feedback_before_after is the feed

    def _collect_outcome_metrics(self) -> None:
        """Coleta métricas do LeadOutcomeTracker."""
        from refrimix_core.monitoring.lead_outcome_tracker import LeadOutcomeTracker, OutcomeType

        tracker = LeadOutcomeTracker()
        all_outcomes = tracker.get_all_outcomes()

        offer_count = 0
        sched_count = 0
        handoff_count = 0
        for outcome in all_outcomes:
            if outcome.outcome == OutcomeType.AGENDADO:
                sched_count += 1
            elif outcome.outcome == OutcomeType.ORCAMENTO_FEITO:
                offer_count += 1
            elif outcome.outcome == OutcomeType.HANDOFF_HUMANO:
                handoff_count += 1

        conv_ids = {o.conversation_id for o in all_outcomes}
        total_conv = self._metrics.total_conversations or max(len(conv_ids), 1)

        self._metrics.appointment_offered_count = offer_count
        self._metrics.appointment_scheduled_count = sched_count
        self._metrics.human_handoff_count = handoff_count
        self._metrics.appointment_scheduled_rate = round(sched_count / total_conv, 3)
        self._metrics.human_handoff_rate = round(handoff_count / total_conv, 3)

    def _collect_status_metrics(self) -> None:
        """Coleta métricas do WhatsAppStatusTracker."""
        from refrimix_core.monitoring.whatsapp_status_tracker import WhatsAppStatusTracker, StatusType

        tracker = WhatsAppStatusTracker()
        all_statuses = tracker.get_all_statuses()

        sent = delivered = read = failed = 0
        for entry in all_statuses:
            if entry.status == StatusType.SENT:
                sent += 1
            elif entry.status == StatusType.DELIVERED:
                delivered += 1
            elif entry.status == StatusType.READ:
                read += 1
            elif entry.status == StatusType.FAILED:
                failed += 1

        self._metrics.status_sent = sent
        self._metrics.status_delivered = delivered
        self._metrics.status_read = read
        self._metrics.status_failed = failed

    def _evaluate_canary_criteria(self) -> None:
        """Avalia se o piloto atende aos critérios para liberar canary."""
        m = self._metrics

        m.meets_min_conversations = m.total_conversations >= _MIN_CANARY_CONVERSATIONS
        m.canary_approval_enough = m.approval_without_edit_rate >= _MIN_CANARY_APPROVAL_RATE
        m.canary_reject_acceptable = m.reject_rate <= _MAX_CANARY_REJECT_RATE
        m.zero_critical_failures = m.critical_guardrail_blocks == 0
        m.risco_eletrico_safe = not m.risco_eletrico_autoenviado
        m.documentos_safe = not m.documentos_autoenviados
        m.refinement_loop_done = m.refinement_loop_run and m.real_cases_exported

        m.canary_recommended = all([
            m.meets_min_conversations,
            m.canary_approval_enough,
            m.canary_reject_acceptable,
            m.zero_critical_failures,
            m.risco_eletrico_safe,
            m.documentos_safe,
            m.refinement_loop_done,
        ])

        self._compute_rates()

    def to_dict(self) -> dict:
        """Converte métricas para dict serializável."""
        m = self._metrics
        return {
            "report_version": _REPORT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "volume": {
                "total_conversations": m.total_conversations,
                "total_review_items": m.total_review_items,
            },
            "human_action": {
                "approvals_without_edit": m.approvals_without_edit,
                "human_edits": m.human_edits,
                "rejections": m.rejections,
                "expired": m.expired,
                "sent": m.sent,
            },
            "rates": {
                "approval_without_edit_rate": m.approval_without_edit_rate,
                "edit_rate": m.edit_rate,
                "reject_rate": m.reject_rate,
                "expire_rate": m.expire_rate,
            },
            "timing": {
                "avg_time_to_human_action_seconds": m.avg_time_to_human_action_seconds,
                "avg_time_to_first_response_seconds": m.avg_time_to_first_response_seconds,
            },
            "intents": {
                "intents_most_edited": m.intents_most_edited,
                "intents_most_rejected": m.intents_most_rejected,
            },
            "before_after_examples": m.before_after_examples,
            "appointments": {
                "appointment_offered_count": m.appointment_offered_count,
                "appointment_scheduled_count": m.appointment_scheduled_count,
                "appointment_offer_rate": m.appointment_offer_rate,
                "appointment_scheduled_rate": m.appointment_scheduled_rate,
                "human_handoff_count": m.human_handoff_count,
                "human_handoff_rate": m.human_handoff_rate,
            },
            "whatsapp_status": {
                "status_sent": m.status_sent,
                "status_delivered": m.status_delivered,
                "status_read": m.status_read,
                "status_failed": m.status_failed,
            },
            "audio": {
                "audio_candidate_count": m.audio_candidate_count,
                "audio_sent_count": m.audio_sent_count,
            },
            "critical_safety": {
                "critical_guardrail_blocks": m.critical_guardrail_blocks,
                "risco_eletrico_autoenviado": m.risco_eletrico_autoenviado,
                "documentos_autoenviados": m.documentos_autoenviados,
            },
            "canary_criteria": {
                "meets_min_conversations": m.meets_min_conversations,
                "min_conversations_required": _MIN_CANARY_CONVERSATIONS,
                "canary_approval_enough": m.canary_approval_enough,
                "min_approval_rate_required": _MIN_CANARY_APPROVAL_RATE,
                "canary_reject_acceptable": m.canary_reject_acceptable,
                "max_reject_rate": _MAX_CANARY_REJECT_RATE,
                "zero_critical_failures": m.zero_critical_failures,
                "risco_eletrico_safe": m.risco_eletrico_safe,
                "documentos_safe": m.documentos_safe,
                "refinement_loop_done": m.refinement_loop_done,
                "canary_recommended": m.canary_recommended,
            },
        }

    def to_markdown(self) -> str:
        """Gera relatório em Markdown legível."""
        m = self._metrics
        d = self.to_dict()
        crit = d["canary_criteria"]

        # Recommendation
        if crit["canary_recommended"]:
            rec = "✅ RECOMENDADO: Liberar CANARY_PERCENT=10"
        elif not crit["meets_min_conversations"]:
            rec = "⏳ Aguardando: mínimo de 30 conversas reais"
        elif not crit["canary_approval_enough"]:
            rec = f"⚠️ Permanecer em ASSISTED: approval_rate={m.approval_without_edit_rate:.1%} < 70%"
        elif not crit["canary_reject_acceptable"]:
            rec = f"⚠️ Permanecer em ASSISTED: reject_rate={m.reject_rate:.1%} > 10%"
        else:
            rec = "⚠️ Permanecer em ASSISTED: falhas críticas ou refinement não executado"

        lines = [
            f"# Assisted Pilot Report — Phase 2.9",
            f"",
            f"**Gerado em:** {d['generated_at']}",
            f"",
            f"## Resumo",
            "",
            f"| Métrica | Valor |",
            f"|---------|-------|",
            f"| Conversas reais | {m.total_conversations} |",
            f"| Review Items | {m.total_review_items} |",
            f"| Aprovações sem edição | {m.approvals_without_edit} ({m.approval_without_edit_rate:.1%}) |",
            f"| Edições humanas | {m.human_edits} ({m.edit_rate:.1%}) |",
            f"| Rejeições | {m.rejections} ({m.reject_rate:.1%}) |",
            f"| Expirados | {m.expired} ({m.expire_rate:.1%}) |",
            f"| Tempo médio até ação | {m.avg_time_to_human_action_seconds:.0f}s |",
            f"|",
            f"",
            f"## Appointment / Conversion",
            f"",
            f"| Métrica | Valor |",
            f"|---------|-------|",
            f"| Offer rate | {m.appointment_offer_rate:.1%} ({m.appointment_offered_count}) |",
            f"| Scheduled rate | {m.appointment_scheduled_rate:.1%} ({m.appointment_scheduled_count}) |",
            f"| Human handoff rate | {m.human_handoff_rate:.1%} ({m.human_handoff_count}) |",
            f"|",
            f"",
            f"## WhatsApp Status",
            f"",
            f"| Status | Count |",
            f"|---------|-------|",
            f"| Sent | {m.status_sent} |",
            f"| Delivered | {m.status_delivered} |",
            f"| Read | {m.status_read} |",
            f"| Failed | {m.status_failed} |",
            f"|",
            f"",
            f"## Intents com Mais Edição",
            f"```",
        ]
        for intent, count in m.intents_most_edited.items():
            lines.append(f"  {intent}: {count}")
        lines.extend([
            f"```",
            f"",
            f"## Intents com Mais Rejeição",
            f"```",
        ])
        for intent, count in m.intents_most_rejected.items():
            lines.append(f"  {intent}: {count}")
        lines.extend([
            f"```",
            f"",
            f"## Segurança Crítica",
            f"",
            f"| Check | Status |",
            f"|--------|--------|",
            f"| Risco elétrico autoenviado | {'❌ AUTOENVIADO' if m.risco_eletrico_autoenviado else '✅ NÃO'} |",
            f"| Documentos autoenviados | {'❌ AUTOENVIADO' if m.documentos_autoenviados else '✅ NÃO'} |",
            f"| Falhas críticas | {m.critical_guardrail_blocks} |",
            f"|",
            f"",
            f"## Critérios Canary",
            f"",
            f"| Critério | Limiar | Atual | Status |",
            f"|---------|-------|-------|--------|",
            f"| Conversas | >= {_MIN_CANARY_CONVERSATIONS} | {m.total_conversations} | {'✅' if crit['meets_min_conversations'] else '❌'} |",
            f"| Approval rate | >= {_MIN_CANARY_APPROVAL_RATE:.0%} | {m.approval_without_edit_rate:.1%} | {'✅' if crit['canary_approval_enough'] else '❌'} |",
            f"| Reject rate | <= {_MAX_CANARY_REJECT_RATE:.0%} | {m.reject_rate:.1%} | {'✅' if crit['canary_reject_acceptable'] else '❌'} |",
            f"| Falhas críticas | 0 | {m.critical_guardrail_blocks} | {'✅' if crit['zero_critical_failures'] else '❌'} |",
            f"| Risco elétrico | não autoenviado | {'OK' if crit['risco_eletrico_safe'] else 'FAIL'} | {'✅' if crit['risco_eletrico_safe'] else '❌'} |",
            f"| Documentos | não autoenviados | {'OK' if crit['documentos_safe'] else 'FAIL'} | {'✅' if crit['documentos_safe'] else '❌'} |",
            f"| Refinement loop | executado | {'SIM' if m.refinement_loop_run else 'NÃO'} | {'✅' if m.refinement_loop_run else '❌'} |",
            f"|",
            f"",
            f"## Recomendação",
            f"",
            f"{rec}",
            f"",
        ])

        # Before/After examples
        if m.before_after_examples:
            lines.extend([
                f"## Exemplos Before/After (Anonimizados)",
                f"",
            ])
            for ex in m.before_after_examples[:5]:
                lines.extend([
                    f"### [{ex['intent']}] {ex['action']} (priority: {ex['priority']})",
                    f"",
                    f"> **Sugerido:** {ex['suggested_response'][:200]}",
                    f"",
                ])
                if ex['human_response']:
                    lines.append(f"> **Humano:** {ex['human_response'][:200]}")
                if ex['edit_reason']:
                    lines.append(f"> **Motivo:** {ex['edit_reason']}")
                lines.append(f"> ID: {ex['conversation_id_masked']}")
                lines.append("")

        return "\n".join(lines)


def generate_report(
    min_conversations: int = 30,
    output_json: Optional[str] = None,
    output_md: Optional[str] = None,
    reports_dir: str = "reports",
) -> dict:
    """
    Gera relatório consolidado do piloto assistido.

    Args:
        min_conversations: mínimo de conversas para considerar relatório válido
        output_json: opcional — caminho para salvar JSON
        output_md: opcional — caminho para salvar Markdown
        reports_dir: diretório de reports (default: reports)

    Returns:
        Dict com métricas consolidadas
    """
    report_gen = AssistedPilotReport(reports_dir=reports_dir)
    metrics = report_gen.generate()

    if metrics.total_conversations < min_conversations:
        print(
            f"⚠️  Aviso: {metrics.total_conversations}/{min_conversations} conversas. "
            f"Relatório parcial — aguardando mais dados."
        )

    result = report_gen.to_dict()

    if output_json:
        import json
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"✅ Relatório JSON: {output_json}")

    if output_md:
        md = report_gen.to_markdown()
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        with open(output_md, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"✅ Relatório Markdown: {output_md}")
    elif output_json:  # Auto-generate md if json given
        auto_md = str(Path(output_json).with_suffix(".md"))
        md = report_gen.to_markdown()
        with open(auto_md, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"✅ Relatório Markdown: {auto_md}")

    return result
