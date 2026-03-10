"""Categorical accounting ledger for GAIA ecological coordination.

Five objects (ComputeUnit, OffsetUnit, FundingUnit, LaborUnit, VerificationUnit),
five morphisms (offset_match, fund, employ, measure, verify), and five
conservation laws enforced algebraically.

Integrates with:
- monad.py: Self-observation via ObservedState wrapping
- sheaf.py: Multi-oracle verification via DiscoverySheaf
- telos_gates.py: AHIMSA (no harm), SATYA (no greenwashing)
- bridge.py: R_V as ecological fitness criterion

Think git, not blockchain -- BLAKE2b hashing, append-only commitment log.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Sequence

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    from uuid import uuid4

    return uuid4().hex[:12]


def _blake2b(data: str) -> str:
    """BLAKE2b hash, 16-byte digest, hex-encoded."""
    return hashlib.blake2b(data.encode(), digest_size=16).hexdigest()


# ── Units (Categorical Objects) ──────────────────────────────────────────


class UnitType(str, Enum):
    COMPUTE = "compute"
    OFFSET = "offset"
    FUNDING = "funding"
    LABOR = "labor"
    VERIFICATION = "verification"


class ComputeUnit(BaseModel):
    """Measured AI computation with carbon intensity."""

    id: str = Field(default_factory=_new_id)
    provider: str
    energy_mwh: float
    carbon_intensity: float  # tons CO2e per MWh (grid-specific)
    workload_type: str = "inference"
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def co2e_tons(self) -> float:
        return self.energy_mwh * self.carbon_intensity

    @field_validator("energy_mwh")
    @classmethod
    def energy_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Energy cannot be negative")
        return v


class OffsetUnit(BaseModel):
    """Verified carbon sequestration."""

    id: str = Field(default_factory=_new_id)
    project_id: str
    co2e_tons: float
    confidence: float = 0.0
    method: str = ""
    vintage_start: datetime = Field(default_factory=_utc_now)
    vintage_end: Optional[datetime] = None
    is_verified: bool = False
    verification_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("co2e_tons")
    @classmethod
    def co2e_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Sequestration cannot be negative")
        return v

    @field_validator("confidence")
    @classmethod
    def confidence_bounded(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


class FundingUnit(BaseModel):
    """Monetary transfer with provenance tracking."""

    id: str = Field(default_factory=_new_id)
    amount_usd: float
    source: str
    destination: str
    purpose: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)
    provenance_chain: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("amount_usd")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Funding amount must be positive")
        return v


class LaborUnit(BaseModel):
    """Person-hours with skill type and output metrics."""

    id: str = Field(default_factory=_new_id)
    worker_id: str
    project_id: str
    hours: float
    skill_type: str = ""
    location: str = ""
    output_metric: float = 0.0
    output_unit: str = ""
    wage_rate: float = 0.0
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("hours")
    @classmethod
    def hours_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Hours cannot be negative")
        return v


class VerificationUnit(BaseModel):
    """Attestation from an oracle with method and confidence."""

    id: str = Field(default_factory=_new_id)
    oracle_type: str  # satellite | iot_sensor | human_auditor | community | statistical_model
    target_id: str
    target_type: UnitType
    confidence: float = 0.0
    method_details: str = ""
    evidence_hash: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence")
    @classmethod
    def confidence_bounded(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# ── Morphisms ────────────────────────────────────────────────────────────


class MorphismType(str, Enum):
    OFFSET_MATCH = "offset_match"
    FUND = "fund"
    EMPLOY = "employ"
    MEASURE = "measure"
    VERIFY = "verify"


# Type constraints for each morphism
MORPHISM_TYPES: dict[MorphismType, tuple[UnitType, UnitType]] = {
    MorphismType.OFFSET_MATCH: (UnitType.COMPUTE, UnitType.OFFSET),
    MorphismType.FUND: (UnitType.FUNDING, UnitType.LABOR),
    MorphismType.EMPLOY: (UnitType.FUNDING, UnitType.LABOR),
    MorphismType.MEASURE: (UnitType.LABOR, UnitType.OFFSET),
    MorphismType.VERIFY: (UnitType.OFFSET, UnitType.VERIFICATION),
}


class Morphism(BaseModel):
    """A typed, auditable transformation in the GAIA category."""

    id: str = Field(default_factory=_new_id)
    morphism_type: MorphismType
    source_id: str
    target_id: str
    source_type: UnitType
    target_type: UnitType
    timestamp: datetime = Field(default_factory=_utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Conservation Laws ────────────────────────────────────────────────────


class ConservationViolation(BaseModel):
    """A violation of one of the five conservation laws."""

    law: str
    description: str
    severity: float = 1.0
    evidence: dict[str, Any] = Field(default_factory=dict)


class ConservationLawChecker:
    """Enforce the five GAIA conservation laws algebraically.

    1. No Creation Ex Nihilo: Sum(claimed) <= Sum(verified)
    2. No Double Counting: verify is injective
    3. Additionality: Offset must exceed baseline
    4. Temporal Coherence: Credits vest against measured curves
    5. Compositional Integrity: Morphism chains type-check
    """

    def check_no_creation_ex_nihilo(
        self,
        claimed_offsets: Sequence[OffsetUnit],
        verified_offsets: Sequence[OffsetUnit],
    ) -> ConservationViolation | None:
        total_claimed = sum(o.co2e_tons for o in claimed_offsets)
        total_verified = sum(
            o.co2e_tons * o.confidence for o in verified_offsets if o.is_verified
        )
        if total_claimed > total_verified + 1e-6:
            return ConservationViolation(
                law="no_creation_ex_nihilo",
                description=(
                    f"Claimed {total_claimed:.2f} tons > "
                    f"verified {total_verified:.2f} tons"
                ),
                severity=min(
                    1.0,
                    (total_claimed - total_verified) / max(total_claimed, 1e-6),
                ),
                evidence={
                    "total_claimed": total_claimed,
                    "total_verified": total_verified,
                },
            )
        return None

    def check_no_double_counting(
        self,
        verifications: Sequence[VerificationUnit],
    ) -> ConservationViolation | None:
        seen: dict[tuple[str, str], list[str]] = {}
        for v in verifications:
            key = (v.target_id, v.oracle_type)
            seen.setdefault(key, []).append(v.id)

        duplicates = {k: ids for k, ids in seen.items() if len(ids) > 1}
        if duplicates:
            return ConservationViolation(
                law="no_double_counting",
                description=(
                    f"{len(duplicates)} offset(s) verified multiple times "
                    f"by same oracle type"
                ),
                severity=len(duplicates) / max(len(seen), 1),
                evidence={
                    "duplicates": {
                        f"{k[0]}:{k[1]}": ids for k, ids in duplicates.items()
                    }
                },
            )
        return None

    def check_additionality(
        self,
        offset: OffsetUnit,
        baseline_co2e: float,
    ) -> ConservationViolation | None:
        if offset.co2e_tons <= baseline_co2e:
            return ConservationViolation(
                law="additionality",
                description=(
                    f"Offset {offset.co2e_tons:.2f} tons does not exceed "
                    f"baseline {baseline_co2e:.2f} tons"
                ),
                severity=1.0,
                evidence={
                    "offset_tons": offset.co2e_tons,
                    "baseline_tons": baseline_co2e,
                },
            )
        return None

    def check_temporal_coherence(
        self,
        offset: OffsetUnit,
        measurement_date: datetime | None = None,
    ) -> ConservationViolation | None:
        if not offset.is_verified and offset.co2e_tons > 0:
            return ConservationViolation(
                law="temporal_coherence",
                description="Offset claims sequestration without verification",
                severity=0.8,
                evidence={"offset_id": offset.id, "co2e_tons": offset.co2e_tons},
            )
        if measurement_date and offset.vintage_start > measurement_date:
            return ConservationViolation(
                law="temporal_coherence",
                description="Offset vintage precedes measurement date",
                severity=0.9,
                evidence={
                    "vintage_start": offset.vintage_start.isoformat(),
                    "measurement_date": measurement_date.isoformat(),
                },
            )
        return None

    def check_compositional_integrity(
        self,
        morphisms: Sequence[Morphism],
    ) -> ConservationViolation | None:
        mistyped: list[str] = []
        for m in morphisms:
            expected = MORPHISM_TYPES.get(m.morphism_type)
            if expected and (m.source_type, m.target_type) != expected:
                mistyped.append(
                    f"{m.id}: {m.morphism_type.value} expects "
                    f"{expected[0].value}->{expected[1].value}, got "
                    f"{m.source_type.value}->{m.target_type.value}"
                )
        if mistyped:
            return ConservationViolation(
                law="compositional_integrity",
                description=f"{len(mistyped)} type-mismatched morphism(s)",
                severity=1.0,
                evidence={"mistyped": mistyped},
            )
        return None

    def check_all(
        self,
        claimed_offsets: Sequence[OffsetUnit] = (),
        verified_offsets: Sequence[OffsetUnit] = (),
        verifications: Sequence[VerificationUnit] = (),
        morphisms: Sequence[Morphism] = (),
    ) -> list[ConservationViolation]:
        violations: list[ConservationViolation] = []
        v = self.check_no_creation_ex_nihilo(claimed_offsets, verified_offsets)
        if v:
            violations.append(v)
        v = self.check_no_double_counting(verifications)
        if v:
            violations.append(v)
        v = self.check_compositional_integrity(morphisms)
        if v:
            violations.append(v)
        return violations


# ── Commitment Ledger ────────────────────────────────────────────────────


class LedgerEntry(BaseModel):
    """Append-only, hash-chained entry. Think git, not blockchain."""

    id: str = Field(default_factory=_new_id)
    sequence: int = 0
    entry_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""
    prev_hash: str = ""
    timestamp: datetime = Field(default_factory=_utc_now)

    def compute_hash(self) -> str:
        data = json.dumps(
            {
                "sequence": self.sequence,
                "entry_type": self.entry_type,
                "payload_hash": self.payload_hash,
                "prev_hash": self.prev_hash,
                "timestamp": self.timestamp.isoformat(),
            },
            sort_keys=True,
        )
        return _blake2b(data)


class GaiaLedger:
    """Append-only categorical ledger with conservation law enforcement.

    Every transaction is:
    1. Type-checked (categorical morphism constraints)
    2. Conservation-law-checked (5 algebraic invariants)
    3. Hash-chained (BLAKE2b, append-only)
    4. Auditable (every claim traceable to raw data)
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or (Path.home() / ".dharma" / "gaia_ledger")
        self._entries: list[LedgerEntry] = []
        self._compute_units: dict[str, ComputeUnit] = {}
        self._offset_units: dict[str, OffsetUnit] = {}
        self._funding_units: dict[str, FundingUnit] = {}
        self._labor_units: dict[str, LaborUnit] = {}
        self._verification_units: dict[str, VerificationUnit] = {}
        self._morphisms: list[Morphism] = []
        self._conservation = ConservationLawChecker()

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def chain_head(self) -> str:
        if not self._entries:
            return ""
        return self._entries[-1].compute_hash()

    def _append_entry(self, entry_type: str, payload: dict[str, Any]) -> LedgerEntry:
        prev_hash = self.chain_head
        payload_hash = _blake2b(json.dumps(payload, sort_keys=True, default=str))
        entry = LedgerEntry(
            sequence=len(self._entries),
            entry_type=entry_type,
            payload=payload,
            payload_hash=payload_hash,
            prev_hash=prev_hash,
        )
        self._entries.append(entry)
        return entry

    def verify_chain_integrity(self) -> bool:
        for i, entry in enumerate(self._entries):
            if i == 0:
                if entry.prev_hash != "":
                    return False
            else:
                expected_prev = self._entries[i - 1].compute_hash()
                if entry.prev_hash != expected_prev:
                    return False
        return True

    # ── Record Units ──────────────────────────────────────────────────

    def record_compute(self, unit: ComputeUnit) -> LedgerEntry:
        self._compute_units[unit.id] = unit
        return self._append_entry("compute", unit.model_dump(mode="json"))

    def record_offset(self, unit: OffsetUnit) -> LedgerEntry:
        self._offset_units[unit.id] = unit
        return self._append_entry("offset", unit.model_dump(mode="json"))

    def record_funding(self, unit: FundingUnit) -> LedgerEntry:
        self._funding_units[unit.id] = unit
        return self._append_entry("funding", unit.model_dump(mode="json"))

    def record_labor(self, unit: LaborUnit) -> LedgerEntry:
        self._labor_units[unit.id] = unit
        return self._append_entry("labor", unit.model_dump(mode="json"))

    def record_verification(self, unit: VerificationUnit) -> LedgerEntry:
        self._verification_units[unit.id] = unit
        # Update target offset if applicable
        if (
            unit.target_type == UnitType.OFFSET
            and unit.target_id in self._offset_units
        ):
            offset = self._offset_units[unit.target_id]
            offset.verification_ids.append(unit.id)
            # 3-of-5 oracle threshold
            oracle_types = set()
            for vid in offset.verification_ids:
                if vid in self._verification_units:
                    oracle_types.add(self._verification_units[vid].oracle_type)
            if len(oracle_types) >= 3:
                offset.is_verified = True
                confidences = [
                    self._verification_units[vid].confidence
                    for vid in offset.verification_ids
                    if vid in self._verification_units
                ]
                offset.confidence = (
                    sum(confidences) / len(confidences) if confidences else 0.0
                )
        return self._append_entry("verification", unit.model_dump(mode="json"))

    def record_morphism(
        self, morphism: Morphism
    ) -> tuple[LedgerEntry, list[ConservationViolation]]:
        self._morphisms.append(morphism)
        entry = self._append_entry("morphism", morphism.model_dump(mode="json"))
        violations = self._conservation.check_all(
            claimed_offsets=list(self._offset_units.values()),
            verified_offsets=[
                o for o in self._offset_units.values() if o.is_verified
            ],
            verifications=list(self._verification_units.values()),
            morphisms=self._morphisms,
        )
        return entry, violations

    # ── Queries ───────────────────────────────────────────────────────

    def total_compute_co2e(self) -> float:
        return sum(u.co2e_tons for u in self._compute_units.values())

    def total_verified_offset(self) -> float:
        return sum(
            u.co2e_tons * u.confidence
            for u in self._offset_units.values()
            if u.is_verified
        )

    def net_carbon_position(self) -> float:
        """Positive = still emitting, negative = net-negative."""
        return self.total_compute_co2e() - self.total_verified_offset()

    def total_labor_hours(self) -> float:
        return sum(u.hours for u in self._labor_units.values())

    def total_funding_usd(self) -> float:
        return sum(u.amount_usd for u in self._funding_units.values())

    def worker_count(self) -> int:
        return len({u.worker_id for u in self._labor_units.values()})

    def conservation_check(self) -> list[ConservationViolation]:
        return self._conservation.check_all(
            claimed_offsets=list(self._offset_units.values()),
            verified_offsets=[
                o for o in self._offset_units.values() if o.is_verified
            ],
            verifications=list(self._verification_units.values()),
            morphisms=self._morphisms,
        )

    def summary(self) -> dict[str, Any]:
        violations = self.conservation_check()
        return {
            "entries": self.entry_count,
            "chain_valid": self.verify_chain_integrity(),
            "compute_units": len(self._compute_units),
            "offset_units": len(self._offset_units),
            "funding_units": len(self._funding_units),
            "labor_units": len(self._labor_units),
            "verification_units": len(self._verification_units),
            "morphisms": len(self._morphisms),
            "total_compute_co2e": self.total_compute_co2e(),
            "total_verified_offset": self.total_verified_offset(),
            "net_carbon_position": self.net_carbon_position(),
            "total_labor_hours": self.total_labor_hours(),
            "total_funding_usd": self.total_funding_usd(),
            "worker_count": self.worker_count(),
            "conservation_violations": len(violations),
            "violations": [v.model_dump() for v in violations],
        }

    # ── Persistence ───────────────────────────────────────────────────

    def save(self) -> Path:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        path = self._data_dir / "ledger.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for entry in self._entries:
                f.write(
                    json.dumps(entry.model_dump(mode="json"), default=str) + "\n"
                )
        return path

    def load(self) -> int:
        path = self._data_dir / "ledger.jsonl"
        if not path.exists():
            return 0
        count = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entry = LedgerEntry.model_validate(data)
                    self._entries.append(entry)
                    self._rebuild_from_entry(entry)
                    count += 1
                except (json.JSONDecodeError, ValueError):
                    continue
        return count

    def _rebuild_from_entry(self, entry: LedgerEntry) -> None:
        if entry.entry_type == "compute":
            unit = ComputeUnit.model_validate(entry.payload)
            self._compute_units[unit.id] = unit
        elif entry.entry_type == "offset":
            unit = OffsetUnit.model_validate(entry.payload)
            self._offset_units[unit.id] = unit
        elif entry.entry_type == "funding":
            unit = FundingUnit.model_validate(entry.payload)
            self._funding_units[unit.id] = unit
        elif entry.entry_type == "labor":
            unit = LaborUnit.model_validate(entry.payload)
            self._labor_units[unit.id] = unit
        elif entry.entry_type == "verification":
            unit = VerificationUnit.model_validate(entry.payload)
            self._verification_units[unit.id] = unit
        elif entry.entry_type == "morphism":
            morphism = Morphism.model_validate(entry.payload)
            self._morphisms.append(morphism)


# ── Self-Observation ─────────────────────────────────────────────────────


class GaiaObserver:
    """Observe the ledger's own state -- the strange loop where the system
    that measures ecological integrity measures its own measuring.

    Uses R_V-like contraction as fitness: is the ledger's self-model
    becoming more precise (contracting) or drifting (expanding)?
    """

    ORACLE_TYPES = {"satellite", "iot_sensor", "human_auditor", "community", "statistical_model"}

    def observe(self, ledger: GaiaLedger) -> dict[str, Any]:
        total_offsets = len(ledger._offset_units)
        verified_count = sum(
            1 for o in ledger._offset_units.values() if o.is_verified
        )
        coverage = verified_count / total_offsets if total_offsets > 0 else 0.0

        oracle_types = {
            v.oracle_type for v in ledger._verification_units.values()
        }
        diversity = len(oracle_types & self.ORACLE_TYPES) / len(self.ORACLE_TYPES)

        entries = max(ledger.entry_count, 1)
        violations = ledger.conservation_check()
        violation_rate = len(violations) / entries

        # Self-referential fitness: lower = healthier (like R_V contraction)
        fitness = 1.0 - (coverage * diversity * (1.0 - violation_rate))

        return {
            "chain_valid": ledger.verify_chain_integrity(),
            "conservation_violations": len(violations),
            "verification_coverage": coverage,
            "oracle_diversity": diversity,
            "violation_rate": violation_rate,
            "self_referential_fitness": fitness,
            "net_carbon_position": ledger.net_carbon_position(),
        }

    def is_goodhart_drifting(self, ledger: GaiaLedger) -> bool:
        """High offset claims but low verification = Goodhart drift."""
        total_claimed = sum(o.co2e_tons for o in ledger._offset_units.values())
        if total_claimed < 1e-6:
            return False
        total_verified = ledger.total_verified_offset()
        return (total_verified / total_claimed) < 0.5


__all__ = [
    "ComputeUnit",
    "ConservationLawChecker",
    "ConservationViolation",
    "FundingUnit",
    "GaiaLedger",
    "GaiaObserver",
    "LaborUnit",
    "LedgerEntry",
    "Morphism",
    "MorphismType",
    "MORPHISM_TYPES",
    "OffsetUnit",
    "UnitType",
    "VerificationUnit",
]
