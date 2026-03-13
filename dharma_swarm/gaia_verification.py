"""3-of-5 oracle verification for GAIA ecological claims.

Five oracle types: satellite imagery, IoT ground sensors, human auditor,
community attestation, statistical model. Threshold signature scheme
requires 3-of-5 to mark an offset as verified.

Integrates with sheaf.py for multi-perspective coherence:
- H0 = global truths all oracles agree on
- H1 = productive disagreements needing resolution (Anekanta)
"""

from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.cohomology_cechcohomology_to_sheaf_coord import (
    LocalClaimAssessment,
    to_sheaf_coordination as coordinate_claim_assessments,
)
from dharma_swarm.gaia_ledger import (
    GaiaLedger,
    UnitType,
    VerificationUnit,
    _new_id,
)
from dharma_swarm.sheaf import (
    CoordinationResult,
)


# ── Oracle Types ─────────────────────────────────────────────────────────


ORACLE_TYPES = [
    "satellite",
    "iot_sensor",
    "human_auditor",
    "community",
    "statistical_model",
]

VERIFICATION_THRESHOLD = 3  # 3-of-5 required


# ── Oracle Verdicts ──────────────────────────────────────────────────────


class OracleVerdict(BaseModel):
    """A single oracle's assessment of an offset claim."""

    oracle_type: str
    target_id: str
    confidence: float = 0.0
    evidence_summary: str = ""
    evidence_hash: str = ""
    agrees_with_claim: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationSession(BaseModel):
    """A complete verification session for one offset claim."""

    id: str = Field(default_factory=_new_id)
    offset_id: str
    verdicts: list[OracleVerdict] = Field(default_factory=list)
    threshold: int = VERIFICATION_THRESHOLD
    is_complete: bool = False
    final_confidence: float = 0.0
    agreeing_oracles: list[str] = Field(default_factory=list)
    dissenting_oracles: list[str] = Field(default_factory=list)

    @property
    def oracle_count(self) -> int:
        return len(self.verdicts)

    @property
    def agreement_count(self) -> int:
        return sum(1 for v in self.verdicts if v.agrees_with_claim)

    @property
    def meets_threshold(self) -> bool:
        return self.agreement_count >= self.threshold

    def finalize(self) -> None:
        """Compute final verdict from collected oracle assessments."""
        self.is_complete = True
        self.agreeing_oracles = [
            v.oracle_type for v in self.verdicts if v.agrees_with_claim
        ]
        self.dissenting_oracles = [
            v.oracle_type for v in self.verdicts if not v.agrees_with_claim
        ]
        if self.agreeing_oracles:
            agreeing_verdicts = [
                v for v in self.verdicts if v.agrees_with_claim
            ]
            self.final_confidence = sum(
                v.confidence for v in agreeing_verdicts
            ) / len(agreeing_verdicts)
        else:
            self.final_confidence = 0.0


# ── Verification Protocol ────────────────────────────────────────────────


class VerificationOracle:
    """Coordinates 3-of-5 oracle verification and records to ledger.

    Each oracle type is modeled as a separate agent in the sheaf topology.
    Their assessments are local sections; gluing produces global truth (H0)
    or productive disagreements (H1).
    """

    def __init__(self, ledger: GaiaLedger) -> None:
        self._ledger = ledger
        self._sessions: dict[str, VerificationSession] = {}

    def start_session(self, offset_id: str) -> VerificationSession:
        session = VerificationSession(offset_id=offset_id)
        self._sessions[session.id] = session
        return session

    def submit_verdict(
        self, session_id: str, verdict: OracleVerdict
    ) -> VerificationSession:
        session = self._sessions[session_id]
        if session.is_complete:
            raise ValueError(f"Session {session_id} already finalized")
        # Prevent duplicate oracle types
        existing_types = {v.oracle_type for v in session.verdicts}
        if verdict.oracle_type in existing_types:
            raise ValueError(
                f"Oracle type {verdict.oracle_type} already submitted"
            )
        session.verdicts.append(verdict)
        return session

    def finalize_session(self, session_id: str) -> VerificationSession:
        """Finalize session and record to ledger if threshold met."""
        session = self._sessions[session_id]
        session.finalize()

        if session.meets_threshold:
            # Record each agreeing oracle's verification to the ledger
            for verdict in session.verdicts:
                if verdict.agrees_with_claim:
                    unit = VerificationUnit(
                        oracle_type=verdict.oracle_type,
                        target_id=session.offset_id,
                        target_type=UnitType.OFFSET,
                        confidence=verdict.confidence,
                        method_details=verdict.evidence_summary,
                        evidence_hash=verdict.evidence_hash,
                    )
                    self._ledger.record_verification(unit)

        return session

    def get_session(self, session_id: str) -> VerificationSession | None:
        return self._sessions.get(session_id)

    # ── Sheaf Integration ─────────────────────────────────────────────

    def to_sheaf_coordination(
        self, session_id: str
    ) -> CoordinationResult | None:
        """Map a verification session onto sheaf cohomology.

        Each oracle is an agent. Their verdicts are local sections (discoveries).
        H0 = global truths (agreement). H1 = productive disagreements.
        """
        session = self._sessions.get(session_id)
        if not session or not session.verdicts:
            return None

        assessments = [
            LocalClaimAssessment(
                source_id=verdict.oracle_type,
                target_id=session.offset_id,
                claim_name="valid",
                agrees_with_claim=verdict.agrees_with_claim,
                confidence=verdict.confidence,
                evidence_refs=[verdict.evidence_hash] if verdict.evidence_hash else [],
                evidence_summary=verdict.evidence_summary,
                topic=f"offset:{session.offset_id}",
                metadata=dict(verdict.metadata),
            )
            for verdict in session.verdicts
        ]
        return coordinate_claim_assessments(assessments)


# ── Convenience: Full Verification Pipeline ──────────────────────────────


def verify_offset(
    ledger: GaiaLedger,
    offset_id: str,
    verdicts: Sequence[OracleVerdict],
) -> tuple[VerificationSession, CoordinationResult | None]:
    """Run full 3-of-5 verification: collect verdicts, finalize, sheaf-check.

    Args:
        ledger: The GAIA ledger to record verifications to.
        offset_id: ID of the offset being verified.
        verdicts: Oracle verdicts (up to 5).

    Returns:
        Tuple of (finalized session, sheaf coordination result).
    """
    oracle = VerificationOracle(ledger)
    session = oracle.start_session(offset_id)

    for verdict in verdicts:
        oracle.submit_verdict(session.id, verdict)

    oracle.finalize_session(session.id)
    coordination = oracle.to_sheaf_coordination(session.id)

    return session, coordination


__all__ = [
    "ORACLE_TYPES",
    "OracleVerdict",
    "VERIFICATION_THRESHOLD",
    "VerificationOracle",
    "VerificationSession",
    "verify_offset",
]
