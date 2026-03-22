"""
JK Credibility Gates — Named critics that every welfare-tons artifact must pass.

Each gate is a checkpoint in the credibility stack. An artifact that fails
any gate is flagged and cannot be called "submission ready" or "proof."

These are NOT telos gates (those govern agent behavior). These are EVIDENCE
gates (they govern what the system is allowed to claim about the world).

Design: 2026-03-21, from the Ruthless Critique session.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class Verdict(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNVERIFIED = "unverified"


class GateID(Enum):
    # Layer 0: Internal coherence
    CONTRADICTION_CHECK = "contradiction_check"
    PROVENANCE_HASH = "provenance_hash"

    # Layer 1: Truth ledger
    SOURCE_INSPECTABLE = "source_inspectable"
    CITATION_VERIFIABLE = "citation_verifiable"
    NO_PRIVATE_EVIDENCE = "no_private_evidence"

    # Layer 2: Public readiness
    REPRODUCIBLE = "reproducible"
    LIMITATIONS_STATED = "limitations_stated"
    UNCERTAINTY_BOUNDED = "uncertainty_bounded"

    # Layer 3: External validation
    EXPERT_REVIEWED = "expert_reviewed"
    ADVERSARIAL_TESTED = "adversarial_tested"
    BUYER_VALIDATED = "buyer_validated"

    # Layer 4: Standards alignment
    STANDARDS_CROSSWALK = "standards_crosswalk"
    COMMUNITY_VOICE = "community_voice"


@dataclass(frozen=True)
class GateResult:
    gate: GateID
    verdict: Verdict
    detail: str
    evidence_path: Optional[str] = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ArtifactAudit:
    """Full audit of a JK artifact against all applicable gates."""

    artifact_path: str
    artifact_hash: str
    audited_at: str
    results: list[GateResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.verdict == Verdict.PASS for r in self.results)

    @property
    def failures(self) -> list[GateResult]:
        return [r for r in self.results if r.verdict == Verdict.FAIL]

    @property
    def warnings(self) -> list[GateResult]:
        return [
            r
            for r in self.results
            if r.verdict in (Verdict.WARN, Verdict.UNVERIFIED)
        ]

    @property
    def submission_ready(self) -> bool:
        """An artifact is submission-ready only if zero failures and
        zero unverified citations."""
        return (
            len(self.failures) == 0
            and all(
                r.verdict != Verdict.UNVERIFIED
                for r in self.results
                if r.gate == GateID.CITATION_VERIFIABLE
            )
        )

    def summary(self) -> dict:
        return {
            "artifact": self.artifact_path,
            "hash": self.artifact_hash,
            "audited_at": self.audited_at,
            "total_gates": len(self.results),
            "passed": sum(1 for r in self.results if r.verdict == Verdict.PASS),
            "failed": sum(1 for r in self.results if r.verdict == Verdict.FAIL),
            "warned": len(self.warnings),
            "submission_ready": self.submission_ready,
        }

    def to_dict(self) -> dict:
        return {
            "artifact_path": self.artifact_path,
            "artifact_hash": self.artifact_hash,
            "audited_at": self.audited_at,
            "results": [
                {
                    "gate": r.gate.value,
                    "verdict": r.verdict.value,
                    "detail": r.detail,
                    "evidence_path": r.evidence_path,
                    "timestamp": r.timestamp,
                }
                for r in self.results
            ],
            "summary": self.summary(),
        }


# ---------------------------------------------------------------------------
# Gate implementations
# ---------------------------------------------------------------------------

_PRIVATE_EVIDENCE_PATTERNS = [
    r"(?i)payment records",
    r"(?i)payroll audit",
    r"(?i)salesforce\s+CRM",
    r"(?i)whatsapp\s+group",
    r"(?i)internal\s+report",
    r"(?i)private\s+communication",
    r"(?i)FPIC\s+documentation\s+package",  # unless publicly available
]

_UNVERIFIABLE_MARKERS = [
    "UNVERIFIED",
    "unverifiable",
    "could not confirm",
    "not publicly available",
]


def _hash_file(path: Path) -> str:
    if not path.exists():
        return "FILE_NOT_FOUND"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def check_no_private_evidence(text: str) -> GateResult:
    """Flag citations that rely on non-public sources."""
    hits = []
    for pattern in _PRIVATE_EVIDENCE_PATTERNS:
        matches = re.findall(pattern, text)
        if matches:
            hits.extend(matches)

    if hits:
        return GateResult(
            gate=GateID.NO_PRIVATE_EVIDENCE,
            verdict=Verdict.WARN,
            detail=f"Found {len(hits)} private-evidence references: {hits[:5]}",
        )
    return GateResult(
        gate=GateID.NO_PRIVATE_EVIDENCE,
        verdict=Verdict.PASS,
        detail="No private-evidence references found",
    )


def check_citations_verifiable(text: str) -> GateResult:
    """Check that cited sources are publicly inspectable."""
    unverified = []
    for marker in _UNVERIFIABLE_MARKERS:
        if marker.lower() in text.lower():
            unverified.append(marker)

    # Check for citations without URLs
    citation_lines = [
        line
        for line in text.split("\n")
        if "source" in line.lower() or "cited" in line.lower()
    ]
    no_url_count = sum(
        1 for line in citation_lines if "http" not in line and "doi" not in line.lower()
    )

    if unverified:
        return GateResult(
            gate=GateID.CITATION_VERIFIABLE,
            verdict=Verdict.UNVERIFIED,
            detail=f"Unverified markers found: {unverified}",
        )
    if no_url_count > 3:
        return GateResult(
            gate=GateID.CITATION_VERIFIABLE,
            verdict=Verdict.WARN,
            detail=f"{no_url_count} citation lines lack URLs or DOIs",
        )
    return GateResult(
        gate=GateID.CITATION_VERIFIABLE,
        verdict=Verdict.PASS,
        detail="Citations appear verifiable",
    )


def check_limitations_stated(text: str) -> GateResult:
    """An honest artifact states its own limitations."""
    has_limitations = any(
        marker in text.lower()
        for marker in ["limitation", "assumption", "caveat", "not included", "does not"]
    )
    if not has_limitations:
        return GateResult(
            gate=GateID.LIMITATIONS_STATED,
            verdict=Verdict.FAIL,
            detail="No limitations or assumptions section found",
        )
    return GateResult(
        gate=GateID.LIMITATIONS_STATED,
        verdict=Verdict.PASS,
        detail="Limitations/assumptions section present",
    )


def check_uncertainty_bounded(text: str) -> GateResult:
    """Single-point estimates without uncertainty bounds are naive."""
    has_uncertainty = any(
        marker in text.lower()
        for marker in [
            "uncertainty",
            "confidence interval",
            "error bar",
            "±",
            "range:",
            "sensitivity",
            "monte carlo",
        ]
    )
    if not has_uncertainty:
        return GateResult(
            gate=GateID.UNCERTAINTY_BOUNDED,
            verdict=Verdict.WARN,
            detail="No uncertainty quantification found — single-point estimates only",
        )
    return GateResult(
        gate=GateID.UNCERTAINTY_BOUNDED,
        verdict=Verdict.PASS,
        detail="Uncertainty bounds present",
    )


def check_submission_claim(text: str, audit: ArtifactAudit) -> GateResult:
    """An artifact that says 'SUBMISSION READY' must actually pass all gates."""
    claims_ready = "submission ready" in text.lower() or "submission-ready" in text.lower()
    if claims_ready and not audit.submission_ready:
        return GateResult(
            gate=GateID.CONTRADICTION_CHECK,
            verdict=Verdict.FAIL,
            detail="Artifact claims 'SUBMISSION READY' but has gate failures or unverified citations",
        )
    return GateResult(
        gate=GateID.CONTRADICTION_CHECK,
        verdict=Verdict.PASS,
        detail="No false readiness claims",
    )


def audit_proof_artifact(path: Path) -> ArtifactAudit:
    """Run all applicable gates on a welfare-ton proof file."""
    text = path.read_text() if path.exists() else ""
    audit = ArtifactAudit(
        artifact_path=str(path),
        artifact_hash=_hash_file(path),
        audited_at=datetime.now(timezone.utc).isoformat(),
    )

    audit.results.append(check_no_private_evidence(text))
    audit.results.append(check_citations_verifiable(text))
    audit.results.append(check_limitations_stated(text))
    audit.results.append(check_uncertainty_bounded(text))
    # Submission claim check depends on prior results
    audit.results.append(check_submission_claim(text, audit))

    return audit


def audit_grant_artifact(path: Path) -> ArtifactAudit:
    """Run gates on a grant application."""
    text = path.read_text() if path.exists() else ""
    audit = ArtifactAudit(
        artifact_path=str(path),
        artifact_hash=_hash_file(path),
        audited_at=datetime.now(timezone.utc).isoformat(),
    )

    audit.results.append(check_no_private_evidence(text))
    audit.results.append(check_citations_verifiable(text))
    audit.results.append(check_limitations_stated(text))
    audit.results.append(check_uncertainty_bounded(text))
    audit.results.append(check_submission_claim(text, audit))

    return audit


def save_audit(audit: ArtifactAudit, output_dir: Path) -> Path:
    """Persist audit result to JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    name = Path(audit.artifact_path).stem
    out = output_dir / f"audit_{name}_{audit.artifact_hash}.json"
    out.write_text(json.dumps(audit.to_dict(), indent=2))
    return out


# ---------------------------------------------------------------------------
# Evidence Room
# ---------------------------------------------------------------------------

@dataclass
class EvidenceEntry:
    """One cited source in the evidence room."""

    citation_key: str  # e.g. "KFS_Annual_Report_2023"
    claimed_fact: str  # e.g. "deforestation rate 3.8%/yr"
    source_url: Optional[str] = None  # public URL if available
    source_type: str = "unknown"  # "public_url", "public_report", "private", "unverifiable"
    verified: bool = False
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "citation_key": self.citation_key,
            "claimed_fact": self.claimed_fact,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "verified": self.verified,
            "verified_by": self.verified_by,
            "verified_at": self.verified_at,
            "notes": self.notes,
        }


class EvidenceRoom:
    """Central registry of all cited sources across JK artifacts.

    Every citation in every proof/grant/paper must have an entry here.
    Entries without public URLs are flagged as unverifiable.
    """

    def __init__(self, room_dir: Path):
        self.room_dir = room_dir
        self.room_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.room_dir / "evidence_index.json"
        self._entries: dict[str, EvidenceEntry] = {}
        self._load()

    def _load(self) -> None:
        if self._index_path.exists():
            data = json.loads(self._index_path.read_text())
            for key, val in data.items():
                self._entries[key] = EvidenceEntry(**val)

    def _save(self) -> None:
        data = {k: v.to_dict() for k, v in self._entries.items()}
        self._index_path.write_text(json.dumps(data, indent=2))

    def add(self, entry: EvidenceEntry) -> None:
        self._entries[entry.citation_key] = entry
        self._save()

    def get(self, key: str) -> Optional[EvidenceEntry]:
        return self._entries.get(key)

    def unverified(self) -> list[EvidenceEntry]:
        return [e for e in self._entries.values() if not e.verified]

    def private_sources(self) -> list[EvidenceEntry]:
        return [
            e for e in self._entries.values() if e.source_type == "private"
        ]

    def stats(self) -> dict:
        total = len(self._entries)
        verified = sum(1 for e in self._entries.values() if e.verified)
        public = sum(
            1
            for e in self._entries.values()
            if e.source_type in ("public_url", "public_report")
        )
        return {
            "total_citations": total,
            "verified": verified,
            "unverified": total - verified,
            "public_sources": public,
            "private_sources": total - public,
            "verification_rate": verified / total if total > 0 else 0,
        }

    def all_entries(self) -> list[EvidenceEntry]:
        return list(self._entries.values())
