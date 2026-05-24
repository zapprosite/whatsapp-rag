from __future__ import annotations

import json
import re
from typing import Any, TypeVar, overload

from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)

_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?(?:</think>|$)", re.IGNORECASE | re.DOTALL)
_CODE_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)
_ROLE_PREFIX_RE = re.compile(r"^\s*(?:assistant|model|resposta|response|json)\s*:\s*", re.IGNORECASE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_JSON_DECODER = json.JSONDecoder()


class LLMOutputParseError(ValueError):
    """Raised when a model response cannot be normalized into valid JSON."""


def strip_llm_markup(text: str | None) -> str:
    """Remove reasoning tags, markdown fences and common chat-template residue."""
    if text is None:
        return ""

    cleaned = str(text).replace("\ufeff", "")
    cleaned = _THINK_BLOCK_RE.sub("", cleaned)
    cleaned = cleaned.replace("<|assistant|>", "").replace("<|user|>", "")
    cleaned = cleaned.replace("<|im_start|>", "").replace("<|im_end|>", "")
    cleaned = _CODE_FENCE_RE.sub(lambda match: match.group(1).strip(), cleaned)
    cleaned = cleaned.replace("```json", "").replace("```JSON", "").replace("```", "")
    cleaned = _ROLE_PREFIX_RE.sub("", cleaned.strip())
    cleaned = _CONTROL_RE.sub("", cleaned)
    return cleaned.strip()


def _repair_json_text(candidate: str) -> str:
    repaired = candidate.strip()
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(r"\bNone\b", "null", repaired)
    repaired = re.sub(r"\bTrue\b", "true", repaired)
    repaired = re.sub(r"\bFalse\b", "false", repaired)
    return repaired


def _json_loads_lenient(candidate: str) -> Any:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return json.loads(_repair_json_text(candidate))


def _iter_balanced_json_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    opening = {"{": "}", "[": "]"}

    for start, char in enumerate(text):
        if char not in opening:
            continue

        stack = [opening[char]]
        in_string = False
        escaped = False

        for index in range(start + 1, len(text)):
            current = text[index]

            if escaped:
                escaped = False
                continue

            if current == "\\":
                escaped = True
                continue

            if current == '"':
                in_string = not in_string
                continue

            if in_string:
                continue

            if current in opening:
                stack.append(opening[current])
                continue

            if stack and current == stack[-1]:
                stack.pop()
                if not stack:
                    candidates.append(text[start : index + 1])
                    break

    return candidates


def extract_json_text(raw: str | bytes) -> str:
    """Return the first valid JSON object/array embedded in an LLM response."""
    text = strip_llm_markup(raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw)
    if not text:
        raise LLMOutputParseError("Resposta vazia do LLM")

    try:
        _json_loads_lenient(text)
        return _repair_json_text(text)
    except json.JSONDecodeError:
        pass

    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            _, end = _JSON_DECODER.raw_decode(text[index:])
            return text[index : index + end]
        except json.JSONDecodeError:
            continue

    for candidate in _iter_balanced_json_candidates(text):
        try:
            _json_loads_lenient(candidate)
            return _repair_json_text(candidate)
        except json.JSONDecodeError:
            continue

    preview = text[:220].replace("\n", "\\n")
    raise LLMOutputParseError(f"Nenhum JSON válido encontrado na resposta: {preview}")


def parse_llm_json_value(raw: str | bytes) -> Any:
    """Parse dirty LLM output into a Python JSON value."""
    return _json_loads_lenient(extract_json_text(raw))


@overload
def parse_llm_json(raw: str | bytes, model: type[ModelT]) -> ModelT:
    ...


@overload
def parse_llm_json(raw: str | bytes, model: None = None) -> Any:
    ...


def parse_llm_json(raw: str | bytes, model: type[ModelT] | None = None) -> ModelT | Any:
    """Parse dirty LLM output and optionally validate it with a Pydantic model."""
    data = parse_llm_json_value(raw)
    if model is None:
        return data
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise LLMOutputParseError(f"JSON do LLM não respeita o schema {model.__name__}: {exc}") from exc

