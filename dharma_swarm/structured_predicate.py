"""Structured predicate evaluation for PolicyCompiler.

Replaces naive keyword matching with deterministic predicate evaluation
(Tier 1) and hash-based semantic similarity (Tier 2/3).

The hash-embed approach is borrowed from engine/knowledge_store.py --
SHA-256 per token projected to a 256-dim vector, then cosine similarity.
This is *not* real embeddings, but it's deterministic, zero-dependency,
and vastly better than "all keywords present in string."
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Structured Predicate (Tier 1 -- deterministic field evaluation)
# ---------------------------------------------------------------------------

ComparisonOp = Literal[
    "lt", "gt", "eq", "gte", "lte",
    "contains", "not_contains", "matches",
]


class StructuredPredicate(BaseModel):
    """A single deterministic condition evaluated against action metadata.

    Examples:
        {"field": "evaluator_count", "op": "lt", "value": 2}
        {"field": "action_type", "op": "eq", "value": "destructive"}
        {"field": "confidence", "op": "gte", "value": 0.95}
    """

    model_config = ConfigDict(frozen=True)

    field: str
    op: ComparisonOp
    value: Any


class CompoundPredicate(BaseModel):
    """AND/OR composition of structured predicates.

    If ``mode`` is "all", every predicate must match (AND).
    If ``mode`` is "any", at least one must match (OR).
    """

    model_config = ConfigDict(frozen=True)

    mode: Literal["all", "any"] = "all"
    predicates: list[StructuredPredicate] = Field(default_factory=list)


def evaluate_predicate(predicate: StructuredPredicate, context: dict[str, Any]) -> bool:
    """Evaluate a single structured predicate against a context dict.

    Returns False (no match) if the field is missing from context --
    a missing field cannot violate a constraint.
    """
    if predicate.field not in context:
        return False

    actual = context[predicate.field]
    expected = predicate.value

    match predicate.op:
        case "eq":
            return actual == expected
        case "lt":
            return _numeric(actual) < _numeric(expected)
        case "gt":
            return _numeric(actual) > _numeric(expected)
        case "lte":
            return _numeric(actual) <= _numeric(expected)
        case "gte":
            return _numeric(actual) >= _numeric(expected)
        case "contains":
            return str(expected).lower() in str(actual).lower()
        case "not_contains":
            return str(expected).lower() not in str(actual).lower()
        case "matches":
            try:
                return bool(re.search(str(expected), str(actual)))
            except re.error:
                return False


def evaluate_compound(compound: CompoundPredicate, context: dict[str, Any]) -> bool:
    """Evaluate a compound (AND/OR) predicate against context."""
    if not compound.predicates:
        return False

    results = [evaluate_predicate(p, context) for p in compound.predicates]
    if compound.mode == "all":
        return all(results)
    return any(results)


# ---------------------------------------------------------------------------
# Hash-based semantic similarity (Tier 2/3)
# ---------------------------------------------------------------------------
# Lifted from engine/knowledge_store.py._hash_embed -- deterministic,
# zero-dependency, works offline.  Not real embeddings, but captures
# token overlap in a way that "all keywords in string" does not.

_EMBED_DIM = 256


def _tokenize(text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from text."""
    return set(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


def _hash_embed(text: str, dim: int = _EMBED_DIM) -> list[float]:
    """Deterministic lightweight embedding via SHA-256 token hashing."""
    vec = [0.0] * max(8, dim)
    for token in _tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % len(vec)
        sign = -1.0 if int(digest[8:10], 16) % 2 else 1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 1e-12:
        return vec
    return [v / norm for v in vec]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors of equal length."""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return dot / (norm_a * norm_b)


def semantic_similarity(text_a: str, text_b: str) -> float:
    """Compute hash-based semantic similarity between two text strings.

    Returns a float in [-1.0, 1.0] where higher means more similar.
    Typical thresholds:
      > 0.8  -- strong match (block-worthy)
      > 0.6  -- moderate match (warn-worthy)
      < 0.6  -- no match
    """
    return cosine_similarity(_hash_embed(text_a), _hash_embed(text_b))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _numeric(val: Any) -> float:
    """Coerce a value to float for comparison, raising TypeError on failure."""
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (ValueError, TypeError):
        raise TypeError(f"Cannot compare non-numeric value: {val!r}")
