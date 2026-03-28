"""Source and report coverage metrics for AutoGrade."""

from __future__ import annotations

from dharma_swarm.auto_research.models import ResearchReport, SourceDocument


def source_quality(sources: list[SourceDocument]) -> float:
    if not sources:
        return 0.0
    return sum(max(0.0, min(source.authority_score, 1.0)) for source in sources) / len(sources)


def source_diversity(sources: list[SourceDocument]) -> float:
    if not sources:
        return 0.0
    unique_domains = {source.domain for source in sources if source.domain}
    unique_types = {source.source_type for source in sources if source.source_type}
    domain_score = len(unique_domains) / len(sources)
    type_score = len(unique_types) / len(sources)
    return min((0.7 * domain_score) + (0.3 * type_score), 1.0)


def topical_coverage(report: ResearchReport) -> float:
    if "topical_coverage" in report.metadata:
        return max(0.0, min(float(report.metadata["topical_coverage"]), 1.0))
    claim_score = min(len(report.claims) / 3.0, 1.0)
    source_score = min(len(report.source_ids) / 3.0, 1.0)
    return min((0.7 * claim_score) + (0.3 * source_score), 1.0)


def freshness(report: ResearchReport, sources: list[SourceDocument]) -> float:
    if not sources:
        return 0.0
    avg = sum(max(0.0, min(source.freshness_score, 1.0)) for source in sources) / len(sources)
    return avg if report.brief.requires_recency else max(avg, 0.9)


def structure(report: ResearchReport) -> float:
    score = 0.0
    if report.summary.strip():
        score += 0.35
    if report.body.strip():
        score += 0.35
    if "\n-" in report.body or report.body.startswith("- "):
        score += 0.20
    if len(report.body.split()) >= 20:
        score += 0.10
    return min(score, 1.0)


def actionability(report: ResearchReport) -> float:
    lowered = report.body.lower()
    score = 0.15 if report.body.strip() else 0.0
    if "recommended next step" in lowered or "next step" in lowered:
        score += 0.55
    if any(marker in lowered for marker in ("promote", "revise", "verify", "run")):
        score += 0.20
    if "\n-" in report.body or report.body.startswith("- "):
        score += 0.10
    return min(score, 1.0)


def novelty(report: ResearchReport, sources: list[SourceDocument]) -> float:
    if "novelty" in report.metadata:
        return max(0.0, min(float(report.metadata["novelty"]), 1.0))
    return min((len({source.domain for source in sources}) / 3.0) * 0.6 + (len(report.claims) / 3.0) * 0.4, 1.0)
