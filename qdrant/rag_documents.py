"""Builder de documentos RAG semânticos da Refrimix.

Mantém o conhecimento reutilizável em chunks pequenos, com payload rico para
filtro, depuração e seed do Qdrant.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
REFRIMIX_KNOWLEDGE_DIR = ROOT_DIR / "knowledge" / "refrimix"
RAG_DOCUMENTS_JSONL = REFRIMIX_KNOWLEDGE_DIR / "rag_documents.jsonl"


def _slug(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9_\-]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_") or "geral"


def _doc_segment_from_name(name: str) -> tuple[str, str]:
    if "residential_high_end" in name:
        return "residential", "high_end"
    if "residential_common" in name:
        return "residential", "common"
    if "commercial_high" in name:
        return "commercial", "high_value"
    if "commercial_common" in name:
        return "commercial", "common"
    return "unknown", "unknown"


def _segment_from_key(key: str) -> tuple[str, str]:
    return {
        "residential_common": ("residential", "common"),
        "residential_high_end": ("residential", "high_end"),
        "commercial_common": ("commercial", "common"),
        "commercial_high_value": ("commercial", "high_value"),
    }.get(key, ("unknown", "unknown"))


def _service_from_key(key: str) -> str:
    if key in {"instalacao", "higienizacao", "manutencao", "pmoc", "consultoria", "projeto-central", "eletrica"}:
        return key
    if key == "conserto":
        return "manutencao"
    return "geral"


def _intent_for_stage(stage: str) -> str:
    return {
        "price": "price_question",
        "pricing": "price_question",
        "technical_triage": "technical_issue",
        "safety": "risk_report",
        "high_value_triage": "project_quote",
        "handoff": "human_handoff",
        "scheduling": "schedule_request",
    }.get(stage, "qualification")


def _cta_for_goal(goal: str, stage: str) -> str:
    if goal == "safety_warning" or stage == "safety":
        return "ask_safety_photos"
    if goal == "human_handoff":
        return "handoff"
    if goal == "high_value_project" or stage == "high_value_triage":
        return "ask_project_context"
    if stage in {"price", "pricing"}:
        return "ask_photos"
    if stage == "scheduling":
        return "ask_schedule_window"
    return "ask_next_relevant_field"


def _priority_for(doc_type: str, stage: str, goal: str, base: int = 40) -> int:
    if doc_type == "pricing_rule":
        return 90
    if goal == "safety_warning":
        return 88
    if goal == "high_value_project":
        return 82
    if stage in {"qualification", "technical_triage"}:
        return max(base, 65)
    if doc_type in {"guardrail", "response_template", "tts_style"}:
        return 55
    return base


def _text_from_value(title: str, value: Any) -> str:
    if isinstance(value, str):
        return f"{title}: {value}"
    dumped = yaml.safe_dump(value, allow_unicode=True, sort_keys=False).strip()
    return f"{title}:\n{dumped}"


def _doc(
    *,
    doc_id: str,
    doc_type: str,
    service: str = "geral",
    stage: str = "geral",
    goal: str = "qualify_quote",
    segment_market: str = "unknown",
    segment_tier: str = "unknown",
    intent: str | None = None,
    cta_type: str | None = None,
    priority: int | None = None,
    tags: Iterable[str] = (),
    source: str,
    title: str,
    text: str,
) -> dict[str, Any]:
    stage = stage or "geral"
    goal = goal or "qualify_quote"
    return {
        "doc_id": doc_id,
        "doc_type": doc_type,
        "service": service or "geral",
        "stage": stage,
        "goal": goal,
        "segment_market": segment_market or "unknown",
        "segment_tier": segment_tier or "unknown",
        "intent": intent or _intent_for_stage(stage),
        "cta_type": cta_type or _cta_for_goal(goal, stage),
        "priority": int(priority if priority is not None else _priority_for(doc_type, stage, goal)),
        "tags": sorted({str(tag) for tag in tags if str(tag).strip()}),
        "source": source,
        "title": title,
        "text": text.strip(),
    }


def _pricing_documents(data: dict[str, Any], source: str) -> list[dict[str, Any]]:
    policy = data.get("pricing_policy") or {}
    docs: list[dict[str, Any]] = []
    for rule_id, rule in policy.items():
        service = "instalacao" if "instalacao" in rule_id else "higienizacao" if "higienizacao" in rule_id else "manutencao"
        goal = "qualify_quote"
        stage = "price" if service in {"instalacao", "higienizacao"} else "technical_triage"
        tags = ["preco", service, rule_id]
        docs.append(
            _doc(
                doc_id=f"pricing_policy:{_slug(rule_id)}",
                doc_type="pricing_rule",
                service=service,
                stage=stage,
                goal=goal,
                segment_market="residential" if service in {"instalacao", "higienizacao"} else "unknown",
                segment_tier="common" if service in {"instalacao", "higienizacao"} else "unknown",
                intent="price_question",
                cta_type="ask_photos" if service == "instalacao" else "ask_quantity",
                tags=tags,
                source=source,
                title=f"Política de preço: {rule_id}",
                text=_text_from_value(f"Regra comercial {rule_id}", rule),
            )
        )
    return docs


def _qualification_documents(data: dict[str, Any], source: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for service, segments in data.items():
        if not isinstance(segments, dict):
            continue
        for segment_id, payload in segments.items():
            segment_market, segment_tier = _segment_from_key(str(segment_id))
            questions = (payload or {}).get("priority") or []
            docs.append(
                _doc(
                    doc_id=f"qualification:{_slug(str(service))}:{_slug(str(segment_id))}",
                    doc_type="qualification_rule",
                    service=_service_from_key(str(service)),
                    stage="qualification",
                    goal="high_value_project" if segment_tier == "high_value" else "qualify_quote",
                    segment_market=segment_market,
                    segment_tier=segment_tier,
                    cta_type="ask_project_context" if segment_tier == "high_value" else "ask_next_relevant_field",
                    tags=["qualificacao", str(service), str(segment_id), *[str(q) for q in questions]],
                    source=source,
                    title=f"Perguntas de qualificação: {service}/{segment_id}",
                    text=(
                        f"Para {service} no segmento {segment_id}, peça só o próximo dado útil, nesta ordem:\n"
                        + "\n".join(f"- {question}" for question in questions)
                    ),
                )
            )
    return docs


def _services_documents(data: dict[str, Any], source: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for service, payload in (data.get("services") or {}).items():
        stages = payload.get("stages") or ["qualification"]
        goal = payload.get("default_goal") or "qualify_quote"
        docs.append(
            _doc(
                doc_id=f"service:{_slug(str(service))}",
                doc_type="service_scope",
                service=_service_from_key(str(service)),
                stage=str(stages[0]),
                goal=goal,
                tags=["servico", str(service), *(str(stage) for stage in stages)],
                source=source,
                title=f"Escopo do serviço: {service}",
                text=_text_from_value(f"Serviço {service}", payload),
            )
        )
    return docs


def _response_template_documents(data: dict[str, Any], source: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for template_id, payload in (data.get("templates") or {}).items():
        when = payload.get("when") or {}
        segment_market, segment_tier = _segment_from_key(str(when.get("segment") or ""))
        service = _service_from_key(str(when.get("service") or "geral"))
        goal = str(when.get("goal") or "qualify_quote")
        intent = str(when.get("user_intent") or _intent_for_stage("qualification"))
        docs.append(
            _doc(
                doc_id=f"response_template:{_slug(str(template_id))}",
                doc_type="response_template",
                service=service,
                stage="price" if intent == "price_question" else "qualification",
                goal=goal,
                segment_market=segment_market,
                segment_tier=segment_tier,
                intent=intent,
                tags=["template", str(template_id), service, intent],
                source=source,
                title=f"Template flexível: {template_id}",
                text=_text_from_value(f"Template {template_id}", payload),
            )
        )
    return docs


def _generic_yaml_documents(path: Path, data: dict[str, Any]) -> list[dict[str, Any]]:
    source = str(path.relative_to(ROOT_DIR))
    stem = path.stem
    doc_type_by_name = {
        "tts_speech_policy": "tts_style",
        "ambiguity_lexicon": "ambiguity_lexicon",
        "forbidden_context_drift": "guardrail",
        "high_value_signals": "high_value_signal",
        "lead_segments": "segment_rule",
        "malicious_lead_policy": "security_policy",
        "objection_handling": "objection_rule",
        "scheduling_signals": "scheduling_rule",
        "brazil_hvac_glossary": "glossary",
        "consultative_sales_examples": "sales_example",
    }
    doc_type = doc_type_by_name.get(stem, "playbook")
    docs: list[dict[str, Any]] = []
    root = data.get(stem) if isinstance(data.get(stem), dict) else data
    for key, value in (root or {}).items():
        key_text = str(key)
        goal = "high_value_project" if "high_value" in key_text or stem == "high_value_signals" else "qualify_quote"
        stage = "high_value_triage" if goal == "high_value_project" else "geral"
        docs.append(
            _doc(
                doc_id=f"{stem}:{_slug(key_text)}",
                doc_type=doc_type,
                service=_service_from_key(key_text),
                stage=stage,
                goal=goal,
                priority=_priority_for(doc_type, stage, goal, 45),
                tags=[stem, key_text],
                source=source,
                title=f"{stem}: {key_text}",
                text=_text_from_value(key_text, value),
            )
        )
    if not docs:
        docs.append(
            _doc(
                doc_id=f"{stem}:geral",
                doc_type=doc_type,
                source=source,
                title=stem,
                text=_text_from_value(stem, data),
            )
        )
    return docs


def _markdown_documents(docs_dir: Path) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for path in sorted(docs_dir.glob("*.md")):
        source = str(path.relative_to(ROOT_DIR))
        segment_market, segment_tier = _doc_segment_from_name(path.stem)
        service = "eletrica" if "electrical" in path.stem else "instalacao" if "installation" in path.stem else "geral"
        goal = "safety_warning" if "electrical" in path.stem else "high_value_project" if segment_tier in {"high_end", "high_value"} else "qualify_quote"
        stage = "safety" if goal == "safety_warning" else "qualification"
        docs.append(
            _doc(
                doc_id=f"doc:{_slug(path.stem)}",
                doc_type="technical_rule" if service != "geral" else "playbook",
                service=service,
                stage=stage,
                goal=goal,
                segment_market=segment_market,
                segment_tier=segment_tier,
                tags=["documento", path.stem, service, segment_market, segment_tier],
                source=source,
                title=path.stem,
                text=path.read_text(encoding="utf-8").strip(),
            )
        )
    return docs


def build_refrimix_documents() -> list[dict[str, Any]]:
    """Transforma playbooks/docs versionados em documentos pequenos para Qdrant."""
    docs: list[dict[str, Any]] = []
    playbook_dir = REFRIMIX_KNOWLEDGE_DIR / "playbooks"
    docs_dir = REFRIMIX_KNOWLEDGE_DIR / "docs"

    for path in sorted(playbook_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        source = str(path.relative_to(ROOT_DIR))
        if path.stem == "pricing_policy":
            docs.extend(_pricing_documents(data, source))
        elif path.stem == "qualification_questions":
            docs.extend(_qualification_documents(data, source))
        elif path.stem == "services":
            docs.extend(_services_documents(data, source))
        elif path.stem == "response_templates":
            docs.extend(_response_template_documents(data, source))
        else:
            docs.extend(_generic_yaml_documents(path, data))

    ambiguity_cases = ROOT_DIR / "qdrant" / "refrimix_ambiguity_cases.jsonl"
    if ambiguity_cases.exists():
        for idx, line in enumerate(ambiguity_cases.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            docs.append(
                _doc(
                    doc_id=f"ambiguity_case:{idx}",
                    doc_type="ambiguity_case",
                    service="geral",
                    stage="qualification",
                    goal="qualify_quote",
                    priority=48,
                    tags=["ambiguidade", "caso", str(idx)],
                    source=f"qdrant/refrimix_ambiguity_cases.jsonl#{idx}",
                    title=f"ambiguity_case_{idx}",
                    text=line,
                )
            )

    docs.extend(_markdown_documents(docs_dir))
    return sorted(docs, key=lambda item: item["doc_id"])


def load_refrimix_documents(path: Path = RAG_DOCUMENTS_JSONL) -> list[dict[str, Any]]:
    """Carrega JSONL versionado quando existir; senão monta direto dos fontes."""
    if not path.exists():
        return build_refrimix_documents()
    docs: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            docs.append(json.loads(line))
    return docs


def write_refrimix_documents(path: Path = RAG_DOCUMENTS_JSONL) -> int:
    docs = build_refrimix_documents()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        for doc in docs:
            fp.write(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n")
    return len(docs)


def main() -> None:
    count = write_refrimix_documents()
    print(f"rag_documents gerado: {count} documentos em {RAG_DOCUMENTS_JSONL.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
