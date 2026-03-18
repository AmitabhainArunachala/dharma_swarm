"""Research Scout — discover information that challenges or extends knowledge.

Scans for findings that validate, challenge, extend, or obsolete existing
knowledge in the dharma_corpus and foundations/ pillar documents.
Cross-references against existing claims to reject redundancy.
Stores validated findings with provenance and pillar grounding.

Ground: Friston (active inference — reduce prediction error by seeking
surprising information), Kauffman (adjacent possible — expand what the
system can know), Ashby (requisite variety — governance needs accurate models).
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_FINDINGS_DIR = Path.home() / ".dharma" / "memory"
_FINDINGS_FILE = "research_scout_findings.md"
_FINDINGS_JSONL = "research_scout_findings.jsonl"

# Pillar vocabulary for tagging
PILLAR_KEYWORDS: dict[str, list[str]] = {
    "PILLAR_01_LEVIN": ["multi-scale cognition", "cognitive light cone", "basal cognition", "bioelectricity", "morphogenesis"],
    "PILLAR_02_KAUFFMAN": ["adjacent possible", "autocatalytic", "self-organization", "complexity", "emergence"],
    "PILLAR_03_JANTSCH": ["self-organizing universe", "dissipative", "autoevolution"],
    "PILLAR_04_HOFSTADTER": ["strange loop", "self-reference", "analogy", "gödel", "tangled hierarchy"],
    "PILLAR_05_AUROBINDO": ["supramental", "overmind", "involution", "descent", "psychic being"],
    "PILLAR_06_DADA_BHAGWAN": ["shuddhatma", "pratishthit atma", "samvara", "nirjara", "pratikraman", "witness"],
    "PILLAR_07_VARELA": ["autopoiesis", "enactive", "structural coupling", "sense-making"],
    "PILLAR_08_BEER": ["viable system", "vsm", "requisite variety", "s1", "s2", "s3", "s4", "s5", "algedonic"],
    "PILLAR_09_DEACON": ["absential", "ententional", "autogen", "constraint", "absence"],
    "PILLAR_10_FRISTON": ["free energy", "active inference", "self-evidencing", "markov blanket", "prediction error"],
}

# Telos star mapping
TELOS_STARS = {
    "T1": "Truth (Satya)",
    "T2": "Resilience (Tapas)",
    "T3": "Flourishing (Ahimsa)",
    "T4": "Sovereignty (Swaraj)",
    "T5": "Coherence (Dharma)",
    "T6": "Emergence (Shakti)",
    "T7": "Liberation (Moksha)",
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class FindingCategory(str):
    VALIDATES = "validates"
    CHALLENGES = "challenges"
    EXTENDS = "extends"
    OBSOLETES = "obsoletes"


class Finding(BaseModel):
    """A single research scout finding."""

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)
    title: str
    summary: str
    source_url: str = ""
    source_type: str = ""  # web, reddit, hackernews, paper, blog
    category: str = "extends"  # validates, challenges, extends, obsoletes
    impact: str = "medium"  # high, medium, low
    pillars: list[str] = Field(default_factory=list)
    telos_impact: str = ""  # e.g. "Strengthens T1 (Satya)"
    action: str = ""  # What to do about it
    cross_ref_result: str = ""  # Result of cross-referencing against existing docs
    is_novel: bool = True  # False if redundant with existing knowledge
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Cross-referencing
# ---------------------------------------------------------------------------


def detect_pillars(text: str) -> list[str]:
    """Detect which pillars a text is related to based on keyword matching."""
    text_lower = text.lower()
    matched: list[str] = []
    for pillar, keywords in PILLAR_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                matched.append(pillar)
                break
    return matched


def detect_telos_impact(text: str) -> str:
    """Detect which telos star a finding most impacts."""
    text_lower = text.lower()
    scores: dict[str, int] = {}
    star_keywords = {
        "T1": ["truth", "verifiable", "accurate", "honest", "satya"],
        "T2": ["resilience", "stress", "robust", "antifragile", "tapas"],
        "T3": ["flourishing", "wellbeing", "life", "ahimsa", "non-violence"],
        "T4": ["sovereignty", "autonomy", "self-determination", "swaraj"],
        "T5": ["coherence", "consistent", "pattern", "dharma", "aligned"],
        "T6": ["emergence", "novel", "creative", "shakti", "new"],
        "T7": ["liberation", "moksha", "karma", "binding", "dissolution"],
    }
    for star, kws in star_keywords.items():
        scores[star] = sum(1 for kw in kws if kw in text_lower)
    if not any(scores.values()):
        return ""
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return ""
    return f"Impacts {best} ({TELOS_STARS[best]})"


def cross_reference_corpus(
    finding_text: str,
    existing_claims: list[str],
    existing_foundations: list[str],
) -> tuple[bool, str]:
    """Check if a finding is novel vs redundant with existing knowledge.

    Returns (is_novel, explanation).
    """
    finding_lower = finding_text.lower()
    # Simple word overlap check — in production this would use embeddings
    finding_words = set(re.findall(r"\w{4,}", finding_lower))

    best_overlap = 0.0
    best_match = ""

    for claim in existing_claims:
        claim_words = set(re.findall(r"\w{4,}", claim.lower()))
        if not claim_words:
            continue
        overlap = len(finding_words & claim_words) / max(len(finding_words), 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = claim[:100]

    for doc in existing_foundations:
        doc_words = set(re.findall(r"\w{4,}", doc.lower()))
        if not doc_words:
            continue
        overlap = len(finding_words & doc_words) / max(len(finding_words), 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = f"[foundation] {doc[:100]}"

    if best_overlap > 0.6:
        return False, f"Redundant (~{best_overlap:.0%} overlap with: {best_match})"
    if best_overlap > 0.3:
        return True, f"Partially overlaps ({best_overlap:.0%}) with: {best_match} — may extend"
    return True, "Novel finding — no significant overlap with existing knowledge"


# ---------------------------------------------------------------------------
# Markdown formatting
# ---------------------------------------------------------------------------


def _finding_to_md(finding: Finding) -> str:
    """Format a Finding as a markdown section."""
    ts = finding.timestamp.strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"## [{ts}] {finding.title}"]
    lines.append(f"- **Category**: {finding.category.upper()}")
    lines.append(f"- **Impact**: {finding.impact.upper()}")
    if finding.pillars:
        lines.append(f"- **Pillars**: {', '.join(finding.pillars)}")
    if finding.telos_impact:
        lines.append(f"- **Telos Impact**: {finding.telos_impact}")
    if finding.source_url:
        lines.append(f"- **Source**: {finding.source_url}")
    if finding.source_type:
        lines.append(f"- **Source Type**: {finding.source_type}")
    lines.append(f"- **Summary**: {finding.summary}")
    if finding.action:
        lines.append(f"- **Action**: {finding.action}")
    if finding.cross_ref_result:
        lines.append(f"- **Cross-ref**: {finding.cross_ref_result}")
    lines.append(f"- **Witness**: [{ts}, actor: research-scout, id: {finding.id}]")
    lines.append("")
    return "\n".join(lines)


_FINDINGS_HEADER = """# Research Scout Findings

> Validated findings that challenge, extend, or confirm existing knowledge.
> Each finding is cross-referenced against dharma_corpus claims and
> foundation documents. Redundant findings are rejected.
> Only findings traceable to at least one Pillar are stored.

"""


# ---------------------------------------------------------------------------
# ResearchScout
# ---------------------------------------------------------------------------


class ResearchScout:
    """Research scout that discovers and validates new knowledge.

    Findings are stored in both markdown (human-readable) and JSONL
    (machine-readable) formats. Cross-references against existing
    corpus claims and foundation documents to reject redundancy.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or _DEFAULT_FINDINGS_DIR
        self.findings_md = self.base_dir / _FINDINGS_FILE
        self.findings_jsonl = self.base_dir / _FINDINGS_JSONL

    # -- lifecycle -----------------------------------------------------------

    async def init(self) -> None:
        """Create directory and files if needed."""
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.findings_md.exists():
            self.findings_md.write_text(_FINDINGS_HEADER)
        if not self.findings_jsonl.exists():
            self.findings_jsonl.write_text("")

    # -- evaluate & store ----------------------------------------------------

    async def evaluate_finding(
        self,
        title: str,
        summary: str,
        source_url: str = "",
        source_type: str = "",
        existing_claims: Optional[list[str]] = None,
        existing_foundations: Optional[list[str]] = None,
    ) -> Finding:
        """Evaluate a potential finding: detect pillars, check novelty, store if valid.

        Returns the Finding with is_novel=False if rejected as redundant,
        or is_novel=True and stored if accepted.
        """
        return await asyncio.to_thread(
            self._evaluate_sync,
            title, summary, source_url, source_type,
            existing_claims or [], existing_foundations or [],
        )

    def _evaluate_sync(
        self,
        title: str,
        summary: str,
        source_url: str,
        source_type: str,
        existing_claims: list[str],
        existing_foundations: list[str],
    ) -> Finding:
        combined_text = f"{title} {summary}"

        # Detect pillars
        pillars = detect_pillars(combined_text)

        # Reject if no pillar grounding
        if not pillars:
            return Finding(
                title=title,
                summary=summary,
                source_url=source_url,
                source_type=source_type,
                pillars=[],
                is_novel=False,
                cross_ref_result="REJECTED: No pillar grounding — orphan knowledge",
            )

        # Cross-reference
        is_novel, cross_ref = cross_reference_corpus(
            combined_text, existing_claims, existing_foundations,
        )

        # Detect telos impact and category
        telos = detect_telos_impact(combined_text)

        finding = Finding(
            title=title,
            summary=summary,
            source_url=source_url,
            source_type=source_type,
            pillars=pillars,
            telos_impact=telos,
            cross_ref_result=cross_ref,
            is_novel=is_novel,
        )

        if is_novel:
            self._store_sync(finding)

        return finding

    def _store_sync(self, finding: Finding) -> None:
        """Store finding in both markdown and JSONL."""
        # Append to markdown
        content = self.findings_md.read_text() if self.findings_md.exists() else _FINDINGS_HEADER
        content += _finding_to_md(finding)
        self.findings_md.write_text(content)

        # Append to JSONL
        with open(self.findings_jsonl, "a") as f:
            f.write(json.dumps(json.loads(finding.model_dump_json()), default=str) + "\n")

    # -- read ----------------------------------------------------------------

    async def get_findings(
        self,
        category: Optional[str] = None,
        pillar: Optional[str] = None,
        limit: int = 50,
    ) -> list[Finding]:
        """Read findings, optionally filtered."""
        return await asyncio.to_thread(self._get_findings_sync, category, pillar, limit)

    def _get_findings_sync(
        self, category: Optional[str], pillar: Optional[str], limit: int,
    ) -> list[Finding]:
        if not self.findings_jsonl.exists():
            return []
        findings: list[Finding] = []
        for line in self.findings_jsonl.read_text().strip().split("\n"):
            if not line:
                continue
            try:
                f = Finding.model_validate(json.loads(line))
                if category and f.category != category:
                    continue
                if pillar and pillar not in f.pillars:
                    continue
                findings.append(f)
            except (json.JSONDecodeError, ValueError):
                continue
        findings.sort(key=lambda f: f.timestamp, reverse=True)
        return findings[:limit]

    async def get_stats(self) -> dict[str, Any]:
        """Get summary statistics of findings."""
        return await asyncio.to_thread(self._get_stats_sync)

    def _get_stats_sync(self) -> dict[str, Any]:
        findings = self._get_findings_sync(None, None, 10000)
        pillar_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        for f in findings:
            for p in f.pillars:
                pillar_counts[p] = pillar_counts.get(p, 0) + 1
            category_counts[f.category] = category_counts.get(f.category, 0) + 1
        return {
            "total": len(findings),
            "by_pillar": pillar_counts,
            "by_category": category_counts,
        }
