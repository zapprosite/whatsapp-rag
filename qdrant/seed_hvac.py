"""Seed limpo do RAG HVAC da Refrimix no Qdrant.

Contrato:
- Fonte versionada do conhecimento: qdrant/hvac_top100.py.
- Coleção de produção: QDRANT_COLLECTION ou hermes_hvac_rag_service_staging.
- Rodar com --prune-legacy para excluir coleções antigas não usadas.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from fastembed import TextEmbedding
from qdrant_client import QdrantClient
from qdrant_client.http import models

try:
    from qdrant.hvac_top100 import TOP100_FAQ
except ModuleNotFoundError:
    from hvac_top100 import TOP100_FAQ


logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "hermes_hvac_rag_service_staging"
DEFAULT_QDRANT_URL = "http://localhost:6333"
EMBEDDING_MODEL = "nomic-ai/nomic-embed-text-v1.5"
VECTOR_DIM = 384
LEGACY_COLLECTIONS = ("whatsapp_rag", "hvac_r_sandbox_smoke")
ROOT_DIR = Path(__file__).resolve().parents[1]
REFRIMIX_KNOWLEDGE_DIR = ROOT_DIR / "knowledge" / "refrimix"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recria o RAG HVAC top100 no Qdrant.")
    parser.add_argument(
        "--qdrant-url",
        default=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL),
        help="URL do Qdrant.",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("QDRANT_COLLECTION", DEFAULT_COLLECTION),
        help="Coleção alvo do RAG.",
    )
    parser.add_argument(
        "--prune-legacy",
        action="store_true",
        help="Exclui coleções legadas/sandbox não usadas pelo runtime.",
    )
    return parser.parse_args()


def faq_to_text(item: dict[str, Any]) -> str:
    return (
        f"Pergunta do lead: {item['question']}\n"
        f"Resposta recomendada do Will/Refrimix: {item['answer']}"
    )


def _infer_stage(outcome: str | None) -> str:
    return {
        "onboarding": "onboarding",
        "analise_tecnica": "qualification",
        "higienizacao_preventiva": "qualification",
        "reuniao_projeto": "high_value_triage",
        "escalar_humano": "handoff",
        "duvida": "qualification",
    }.get(outcome or "", "geral")


def _infer_goal(outcome: str | None) -> str:
    return {
        "reuniao_projeto": "high_value_project",
        "escalar_humano": "human_handoff",
        "onboarding": "recover_context",
    }.get(outcome or "", "qualify_quote")


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


def build_refrimix_documents() -> list[dict[str, Any]]:
    """Transforma playbooks/docs versionados em documentos semânticos para Qdrant."""
    docs: list[dict[str, Any]] = []
    playbook_dir = REFRIMIX_KNOWLEDGE_DIR / "playbooks"
    docs_dir = REFRIMIX_KNOWLEDGE_DIR / "docs"

    for path in sorted(playbook_dir.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        doc_type = "tts_style" if path.stem == "tts_speech_policy" else "playbook"
        goal = "high_value_project" if path.stem == "high_value_signals" else "qualify_quote"
        docs.append(
            {
                "doc_type": doc_type,
                "service": "geral",
                "segment_market": "unknown",
                "segment_tier": "unknown",
                "stage": "geral",
                "goal": goal,
                "priority": 20,
                "source": str(path.relative_to(ROOT_DIR)),
                "title": path.stem,
                "text": f"Playbook Refrimix {path.stem}:\n{text}",
            }
        )

    for path in sorted(docs_dir.glob("*.md")):
        segment_market, segment_tier = _doc_segment_from_name(path.stem)
        service = "eletrica" if "electrical" in path.stem else "instalacao" if "installation" in path.stem else "geral"
        goal = "safety_warning" if "electrical" in path.stem else "qualify_quote"
        docs.append(
            {
                "doc_type": "technical_rule" if service != "geral" else "playbook",
                "service": service,
                "segment_market": segment_market,
                "segment_tier": segment_tier,
                "stage": "qualification",
                "goal": goal,
                "priority": 15,
                "source": str(path.relative_to(ROOT_DIR)),
                "title": path.stem,
                "text": path.read_text(encoding="utf-8").strip(),
            }
        )
    return docs


def recreate_collection(client: QdrantClient, collection: str) -> None:
    if client.collection_exists(collection):
        logger.info("Excluindo coleção alvo antiga '%s' para seed limpo", collection)
        client.delete_collection(collection_name=collection)

    logger.info("Criando coleção alvo '%s'", collection)
    client.create_collection(
        collection_name=collection,
        vectors_config=models.VectorParams(
            size=VECTOR_DIM,
            distance=models.Distance.COSINE,
        ),
    )


def build_points(model: TextEmbedding) -> list[models.PointStruct]:
    refrimix_docs = build_refrimix_documents()
    top100_texts = [faq_to_text(item) for item in TOP100_FAQ]
    doc_texts = [doc["text"] for doc in refrimix_docs]
    texts = top100_texts + doc_texts
    embeddings = list(model.embed(texts))

    points: list[models.PointStruct] = []
    for idx, (item, embedding, text) in enumerate(zip(TOP100_FAQ, embeddings[: len(TOP100_FAQ)], top100_texts), start=1):
        service = item["service_name"] or "geral"
        outcome = item["outcome"]
        points.append(
            models.PointStruct(
                id=idx,
                vector=embedding.tolist(),
                payload={
                    "service_name": item["service_name"],
                    "service": service,
                    "outcome": item["outcome"],
                    "segment_market": "unknown",
                    "segment_tier": "unknown",
                    "stage": _infer_stage(outcome),
                    "goal": _infer_goal(outcome),
                    "title": item["question"],
                    "question": item["question"],
                    "answer": item["answer"],
                    "doc_type": "faq_top100",
                    "priority": item["priority"],
                    "tags": list(item["tags"]),
                    "source": "qdrant/hvac_top100.py",
                    "text": text,
                },
            )
        )
    offset = len(points)
    for idx, (doc, embedding) in enumerate(zip(refrimix_docs, embeddings[len(TOP100_FAQ) :]), start=offset + 1):
        payload = dict(doc)
        points.append(models.PointStruct(id=idx, vector=embedding.tolist(), payload=payload))
    return points


def prune_legacy_collections(client: QdrantClient, target_collection: str) -> None:
    for collection in LEGACY_COLLECTIONS:
        if collection == target_collection:
            continue
        if not client.collection_exists(collection):
            continue
        logger.info("Excluindo coleção legada/sandbox '%s'", collection)
        client.delete_collection(collection_name=collection)


def main() -> None:
    args = parse_args()
    collection = args.collection or DEFAULT_COLLECTION

    logger.info("Qdrant: %s", args.qdrant_url)
    logger.info("Coleção alvo: %s", collection)
    logger.info("FAQ top100: %s itens", len(TOP100_FAQ))
    logger.info("Knowledge Refrimix: %s documentos", len(build_refrimix_documents()))
    logger.info("Modelo de embedding: %s", EMBEDDING_MODEL)

    model = TextEmbedding(model=EMBEDDING_MODEL, max_length=512)
    client = QdrantClient(url=args.qdrant_url)

    recreate_collection(client, collection)
    points = build_points(model)

    logger.info("Inserindo %s pontos top100", len(points))
    operation_info = client.upsert(collection_name=collection, points=points)
    logger.info("Upsert completo: %s", operation_info)

    if args.prune_legacy:
        prune_legacy_collections(client, collection)

    info = client.get_collection(collection)
    logger.info("Seed OK: '%s' com %s pontos", collection, info.points_count)


if __name__ == "__main__":
    main()
