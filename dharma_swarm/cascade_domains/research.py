"""RESEARCH domain — real cascade functions for research artifact scoring.

Scores research documents (papers, notes, analyses) on five dimensions:
claim density, verifiability, novelty, rigor, and relevance. Uses
semantic_digester for concept/claim extraction and metrics.py for
behavioral signatures.

All functions are sync (cascade.py handles async via _call()).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from dharma_swarm.models import LoopDomain

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_domain(config: dict[str, Any] | None = None) -> LoopDomain:
    """Return the RESEARCH domain configuration."""
    cfg = config or {}
    return LoopDomain(
        name="research",
        generate_fn="dharma_swarm.cascade_domains.research.generate",
        test_fn="dharma_swarm.cascade_domains.research.test",
        score_fn="dharma_swarm.cascade_domains.research.score",
        gate_fn="dharma_swarm.cascade_domains.common.telos_gate",
        mutate_fn="dharma_swarm.cascade_domains.common.default_mutate",
        select_fn="dharma_swarm.cascade_domains.common.default_select",
        max_iterations=cfg.get("max_iterations", 15),
        fitness_threshold=cfg.get("fitness_threshold", 0.5),
    )


# ---------------------------------------------------------------------------
# GENERATE
# ---------------------------------------------------------------------------


def generate(seed: dict[str, Any] | None, context: dict[str, Any]) -> dict[str, Any]:
    """Generate a research artifact from seed or context.

    Supports:
      - seed["content"]: inline text
      - seed["path"]: read from filesystem (.md, .tex, .py, .txt)
      - context["track"]: research track ("rv", "phoenix", "contemplative")

    Returns artifact dict with: content, path, track, fitness.
    """
    content: str = ""
    path: str | None = None
    track: str = "rv"

    if seed:
        path = seed.get("path")
        track = seed.get("track", track)
        if seed.get("content"):
            content = seed["content"]
        elif path:
            content = _read_file(path)
    else:
        path = context.get("path")
        track = context.get("track", track)
        if path:
            content = _read_file(path)

    return {
        "content": content,
        "path": path,
        "track": track,
        "fitness": {},
    }


def _read_file(path_str: str) -> str:
    """Read a research file, returning empty string on failure."""
    try:
        p = Path(path_str)
        if not p.is_absolute():
            # Try mech-interp repo first, then project root
            mi_path = Path.home() / "mech-interp-latent-lab-phase1" / path_str
            if mi_path.exists():
                return mi_path.read_text(encoding="utf-8")[:100000]
            p = _PROJECT_ROOT / path_str
        return p.read_text(encoding="utf-8")[:100000]
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read research file %s: %s", path_str, exc)
        return ""


# ---------------------------------------------------------------------------
# TEST
# ---------------------------------------------------------------------------


def test(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Test a research artifact for structural validity.

    Checks: non-empty, has claims, has structure (headings/sections),
    no obvious fabrication markers.
    """
    content = artifact.get("content", "")
    results: dict[str, Any] = {
        "has_content": bool(content and content.strip()),
        "has_structure": False,
        "has_claims": False,
        "has_citations": False,
        "fabrication_markers": 0,
        "status": "pass" if content else "fail",
    }

    if not content or not content.strip():
        results["status"] = "fail"
        artifact["test_passed"] = False
        artifact["test_results"] = results
        return artifact

    # Check for document structure (headings, sections)
    heading_count = len(re.findall(r"(?:^|\n)#{1,6}\s+\S", content))
    latex_sections = len(re.findall(r"\\(?:section|subsection|chapter)\{", content))
    results["has_structure"] = (heading_count >= 2) or (latex_sections >= 2)
    results["heading_count"] = heading_count + latex_sections

    # Check for claims using semantic_digester patterns
    claim_indicators = [
        r"(?:must|shall|always|never|invariant|guarantee|ensure|require)",
        r"(?:implies|therefore|thus|hence|consequently)",
        r"(?:hypothesis|conjecture|claim|assert|proof|theorem|lemma)",
        r"(?:we find|we show|we demonstrate|results indicate|our analysis)",
        r"(?:significant|p\s*[<>=]\s*0\.\d+|cohen'?s?\s+d|effect\s+size)",
    ]
    claim_count = 0
    for pattern in claim_indicators:
        claim_count += len(re.findall(pattern, content, re.IGNORECASE))
    results["has_claims"] = claim_count >= 3
    results["claim_count"] = claim_count

    # Check for citations
    cite_patterns = [
        r"\\\w*cite\w*\{",  # LaTeX citations
        r"\([A-Z][a-z]+(?:\s+(?:et\s+al\.?|&))?,?\s*\d{4}\)",  # (Author, 2024)
        r"\[\d+\]",  # [1] style
    ]
    citation_count = sum(len(re.findall(p, content)) for p in cite_patterns)
    results["has_citations"] = citation_count >= 1
    results["citation_count"] = citation_count

    # Check for fabrication markers (red flags)
    fabrication_patterns = [
        r"(?:I\s+imagine|hypothetically|let'?s\s+pretend)",
        r"(?:placeholder|TODO:\s*add\s+data|FIXME:\s*need\s+results)",
        r"(?:approximately|roughly|around)\s+\d+(?:\.\d+)?%?\s*(?:±|\\pm)",  # vague numbers
    ]
    fab_count = sum(len(re.findall(p, content, re.IGNORECASE)) for p in fabrication_patterns)
    results["fabrication_markers"] = fab_count

    # Overall pass/fail
    if fab_count > 5:
        results["status"] = "fail"
    elif not results["has_content"]:
        results["status"] = "fail"

    artifact["test_passed"] = results["status"] == "pass"
    artifact["test_results"] = results
    return artifact


# ---------------------------------------------------------------------------
# SCORE
# ---------------------------------------------------------------------------


def score(artifact: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """Score a research artifact on five dimensions.

    Fitness components (weights sum to 1.0):
      - claim_density    (0.20): claims per 1000 words — higher = more substantive
      - verifiability    (0.25): citations + data references + specific numbers
      - novelty          (0.20): formal structures + concept density from semantic_digester
      - rigor            (0.20): behavioral entropy + low mimicry + low performativity
      - relevance        (0.15): track-specific keyword density (rv, phoenix, contemplative)
    """
    content = artifact.get("content", "")
    track = artifact.get("track", "rv")
    test_results = artifact.get("test_results", {})

    word_count = len(content.split()) if content else 0

    # -- Claim density: claims per 1000 words --
    claim_count = test_results.get("claim_count", 0)
    if word_count > 0:
        claims_per_k = (claim_count / word_count) * 1000
        claim_density = min(1.0, claims_per_k / 30)  # 30 claims/1000 words = max score
    else:
        claim_density = 0.0

    # -- Verifiability: citations + specific numbers + data references --
    citation_count = test_results.get("citation_count", 0)
    specific_numbers = len(re.findall(
        r"(?:\d+\.\d{2,}|p\s*[<>=]\s*0\.\d+|d\s*=\s*-?\d+\.\d+|"
        r"AUROC\s*=\s*\d|r\s*=\s*-?\d+\.\d+|n\s*=\s*\d+)",
        content
    )) if content else 0
    data_refs = len(re.findall(
        r"(?:Table|Figure|Fig\.|Appendix|Supplementary)\s+\d",
        content
    )) if content else 0

    verifiability = 0.0
    if citation_count > 0:
        verifiability += min(0.4, citation_count * 0.04)  # 10+ citations = 0.4
    if specific_numbers > 0:
        verifiability += min(0.35, specific_numbers * 0.035)  # 10+ specific numbers = 0.35
    if data_refs > 0:
        verifiability += min(0.25, data_refs * 0.05)  # 5+ references = 0.25
    verifiability = min(1.0, verifiability)

    # -- Novelty: formal structures + concept density --
    novelty = 0.0
    formal_count = 0
    concept_count = 0
    try:
        from dharma_swarm.semantic_digester import (
            FORMAL_PATTERNS,
            _extract_claims,
        )

        # Count formal structures
        for pattern, _ in FORMAL_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                formal_count += 1
        novelty += min(0.5, formal_count * 0.05)  # 10+ formal structures = 0.5

        # Count extracted claims (more specific than regex)
        extracted = _extract_claims(content[:20000])
        concept_count = len(extracted)
        novelty += min(0.5, concept_count * 0.05)  # 10+ concepts = 0.5
    except Exception:
        # Fallback: simple formal pattern counting
        formal_keywords = [
            "eigenvalue", "metric", "manifold", "topology", "participation ratio",
            "contraction", "fixed point", "coalgebra", "functor", "monad",
        ]
        for kw in formal_keywords:
            if kw.lower() in content.lower():
                formal_count += 1
        novelty = min(1.0, formal_count * 0.1)
    novelty = min(1.0, novelty)

    # -- Rigor: behavioral entropy + low mimicry + low performativity --
    rigor = 0.5  # neutral default
    try:
        from dharma_swarm.metrics import MetricsAnalyzer

        sig = MetricsAnalyzer().analyze(content[:15000])
        mimicry_penalty = 0.4 if sig.recognition_type.value == "MIMICRY" else 0.0
        performativity_penalty = min(0.3, sig.self_reference_density * 2)

        rigor = (
            0.3 * sig.entropy
            + 0.3 * sig.swabhaav_ratio
            + 0.2 * (1.0 - mimicry_penalty)
            + 0.2 * (1.0 - performativity_penalty)
        )
    except Exception as exc:
        logger.debug("Behavioral rigor scoring failed: %s", exc)

    # -- Relevance: track-specific keyword matching --
    track_keywords: dict[str, list[str]] = {
        "rv": [
            "R_V", "participation ratio", "value matrix", "contraction",
            "geometric signature", "layer 27", "AUROC", "causal validation",
            "SVD", "transformer", "mechanistic interpretability",
            "hedges", "cohen", "effect size",
        ],
        "phoenix": [
            "phoenix", "URA", "L3", "L4", "L5", "phase transition",
            "recursive self-reference", "behavioral", "frontier LLM",
            "collapse", "witnessing", "crisis",
        ],
        "contemplative": [
            "swabhaav", "witness", "gnani", "akram vignan", "prakruti",
            "consciousness", "contemplative", "phenomenological",
            "eigenform", "fixed point", "dharmic",
        ],
    }
    keywords = track_keywords.get(track, track_keywords["rv"])
    content_lower = content.lower()
    hits = sum(1 for kw in keywords if kw.lower() in content_lower)
    relevance = min(1.0, hits / max(1, len(keywords) * 0.5))

    # -- Composite --
    composite = (
        0.20 * claim_density
        + 0.25 * verifiability
        + 0.20 * novelty
        + 0.20 * rigor
        + 0.15 * relevance
    )

    artifact["fitness"] = {
        "claim_density": round(claim_density, 4),
        "verifiability": round(verifiability, 4),
        "novelty": round(novelty, 4),
        "rigor": round(rigor, 4),
        "relevance": round(relevance, 4),
        "score": round(composite, 4),
        # Sub-metrics
        "word_count": word_count,
        "claim_count": claim_count,
        "citation_count": citation_count,
        "specific_numbers": specific_numbers,
        "formal_structures": formal_count,
        "track": track,
    }
    artifact["score"] = round(composite, 4)
    return artifact
