"""AI Reciprocity Ledger: high-level trust object projected into GAIA.

This module sits one layer above ``gaia_ledger.py``.

It models the public-benefit reciprocity object described in the Jagat Kalyan
docs:

- AI actors and AI-intensive activity
- restorative obligations
- project routing
- livelihood transition
- evidence, outcomes, and audits

The ledger stays append-only and hash-chained, then projects the convertible
parts into the lower-level categorical GAIA substrate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from dharma_swarm.gaia_ledger import (
    ComputeUnit,
    FundingUnit,
    GaiaLedger,
    LaborUnit,
    LedgerEntry,
    OffsetUnit,
    UnitType,
    VerificationUnit,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid4().hex[:12]


def _blake2b(data: str) -> str:
    return hashlib.blake2b(data.encode(), digest_size=16).hexdigest()


class ActorType(str, Enum):
    LAB = "lab"
    ENTERPRISE = "enterprise"
    CLOUD = "cloud"
    RESEARCH_ORG = "research_org"
    OTHER = "other"


class DisclosureLevel(str, Enum):
    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


class ExposureClass(str, Enum):
    TRAINING = "training"
    INFERENCE = "inference"
    ENTERPRISE_AI = "enterprise_ai"
    AUTOMATION_PROGRAM = "automation_program"
    OTHER = "other"


class ConfidenceLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class LaborTransitionRiskClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class ObligationType(str, Enum):
    ECOLOGY = "ecology"
    LIVELIHOOD = "livelihood"
    MIXED = "mixed"


class ObligationBasis(str, Enum):
    FORMULA = "formula"
    PLEDGE = "pledge"
    POLICY = "policy"
    PILOT_RULE = "pilot_rule"


class ObligationStatus(str, Enum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    FULFILLED = "fulfilled"
    DISPUTED = "disputed"
    RETIRED = "retired"


class QuantityUnit(str, Enum):
    USD = "usd"
    TCO2E = "tco2e"
    POINTS = "points"
    MIXED = "mixed"


class ProjectType(str, Enum):
    CARBON_REMOVAL = "carbon_removal"
    BIODIVERSITY = "biodiversity"
    WATERSHED = "watershed"
    METHANE = "methane"
    RESILIENCE = "resilience"
    LIVELIHOOD_TRANSITION = "livelihood_transition"
    MIXED = "mixed"


class IntegrityClass(str, Enum):
    EXPERIMENTAL = "experimental"
    EMERGING = "emerging"
    HIGH_INTEGRITY = "high_integrity"


class ConsentStatus(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


class LivelihoodMode(str, Enum):
    TRAINING = "training"
    COOPERATIVE = "cooperative"
    CONTRACT_WORK = "contract_work"
    MICROENTERPRISE = "microenterprise"
    MUTUAL_AID = "mutual_aid"
    MIXED = "mixed"


class EvidenceSubjectType(str, Enum):
    ACTIVITY = "activity"
    PROJECT = "project"
    OUTCOME = "outcome"
    LIVELIHOOD = "livelihood"
    AUDIT = "audit"


class EvidenceType(str, Enum):
    METERING = "metering"
    SATELLITE = "satellite"
    SENSOR = "sensor"
    GROUND_AUDIT = "ground_audit"
    FINANCIAL = "financial"
    SURVEY = "survey"
    POLICY = "policy"


class OutcomeType(str, Enum):
    CARBON = "carbon"
    BIODIVERSITY = "biodiversity"
    WATERSHED = "watershed"
    METHANE = "methane"
    INCOME = "income"
    TRAINING = "training"
    OWNERSHIP = "ownership"
    OTHER = "other"


class OutcomeStatus(str, Enum):
    ESTIMATED = "estimated"
    MEASURED = "measured"
    VERIFIED = "verified"
    CHALLENGED = "challenged"
    REVERSED = "reversed"


class AuditScope(str, Enum):
    ACTIVITY = "activity"
    OBLIGATION = "obligation"
    PROJECT = "project"
    OUTCOME = "outcome"
    LEDGER_SLICE = "ledger_slice"


class AuditStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    QUALIFIED = "qualified"
    FAILED = "failed"
    CHALLENGED = "challenged"


class AIActor(BaseModel):
    actor_id: str = Field(default_factory=_new_id)
    actor_name: str
    actor_type: ActorType
    jurisdiction: str
    disclosure_level: DisclosureLevel = DisclosureLevel.PARTIAL
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActivityRecord(BaseModel):
    activity_id: str = Field(default_factory=_new_id)
    actor_id: str
    workload_label: str = ""
    period_start: date
    period_end: date
    exposure_class: ExposureClass
    energy_mwh: float | None = None
    emissions_tco2e: float | None = None
    labor_transition_risk_class: LaborTransitionRiskClass = (
        LaborTransitionRiskClass.UNKNOWN
    )
    methodology_ref: str = ""
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("energy_mwh", "emissions_tco2e")
    @classmethod
    def non_negative_optional(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("numeric values cannot be negative")
        return value


class ObligationRecord(BaseModel):
    obligation_id: str = Field(default_factory=_new_id)
    activity_id: str
    obligation_type: ObligationType
    obligation_basis: ObligationBasis
    obligation_quantity: float
    obligation_unit: QuantityUnit
    status: ObligationStatus = ObligationStatus.PROPOSED
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("obligation_quantity")
    @classmethod
    def quantity_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("obligation_quantity must be positive")
        return value


class ProjectRecord(BaseModel):
    project_id: str = Field(default_factory=_new_id)
    project_name: str
    project_type: ProjectType
    location: str
    operator_name: str = ""
    integrity_class: IntegrityClass = IntegrityClass.EMERGING
    indigenous_or_local_consent: ConsentStatus = ConsentStatus.UNKNOWN
    methodology_ref: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RoutingRecord(BaseModel):
    routing_id: str = Field(default_factory=_new_id)
    obligation_id: str
    project_id: str
    routed_value: float
    routed_unit: QuantityUnit
    routed_at: datetime = Field(default_factory=_utc_now)
    restrictions: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("routed_value")
    @classmethod
    def routed_positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("routed_value must be positive")
        return value


class LivelihoodRecord(BaseModel):
    livelihood_id: str = Field(default_factory=_new_id)
    project_id: str
    participant_count: int
    livelihood_mode: LivelihoodMode
    median_compensation_local: float | None = None
    local_ownership_share: float | None = None
    transition_target_group: str
    person_hours: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("participant_count")
    @classmethod
    def participants_positive(cls, value: int) -> int:
        if value < 0:
            raise ValueError("participant_count cannot be negative")
        return value

    @field_validator("median_compensation_local", "person_hours")
    @classmethod
    def non_negative_money_or_hours(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("numeric values cannot be negative")
        return value

    @field_validator("local_ownership_share")
    @classmethod
    def ownership_ratio_bounded(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("local_ownership_share must be between 0 and 1")
        return value


class EvidenceRecord(BaseModel):
    evidence_id: str = Field(default_factory=_new_id)
    subject_type: EvidenceSubjectType
    subject_id: str
    evidence_type: EvidenceType
    source_ref: str
    captured_at: datetime = Field(default_factory=_utc_now)
    verifier: str | None = None
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutcomeRecord(BaseModel):
    outcome_id: str = Field(default_factory=_new_id)
    project_id: str
    outcome_type: OutcomeType
    quantity: float
    unit: str
    measured_at: datetime = Field(default_factory=_utc_now)
    status: OutcomeStatus = OutcomeStatus.ESTIMATED
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("quantity")
    @classmethod
    def quantity_non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("quantity cannot be negative")
        return value


class AuditRecord(BaseModel):
    audit_id: str = Field(default_factory=_new_id)
    scope: AuditScope
    scope_id: str
    audit_status: AuditStatus
    auditor: str
    issued_at: datetime = Field(default_factory=_utc_now)
    notes_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReciprocityIssue(BaseModel):
    code: str
    message: str
    severity: str = "error"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AIReciprocityLedger:
    """Append-only reciprocity ledger with a GAIA projection path."""

    ECOLOGICAL_OUTCOMES = {
        OutcomeType.CARBON,
        OutcomeType.BIODIVERSITY,
        OutcomeType.WATERSHED,
        OutcomeType.METHANE,
    }

    VERIFIED_OUTCOME_STATUSES = {
        OutcomeStatus.VERIFIED,
        OutcomeStatus.CHALLENGED,
        OutcomeStatus.REVERSED,
    }

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or (Path.home() / ".dharma" / "ai_reciprocity_ledger")
        self._entries: list[LedgerEntry] = []
        self._actors: dict[str, AIActor] = {}
        self._activities: dict[str, ActivityRecord] = {}
        self._obligations: dict[str, ObligationRecord] = {}
        self._projects: dict[str, ProjectRecord] = {}
        self._routings: dict[str, RoutingRecord] = {}
        self._livelihoods: dict[str, LivelihoodRecord] = {}
        self._evidence: dict[str, EvidenceRecord] = {}
        self._outcomes: dict[str, OutcomeRecord] = {}
        self._audits: dict[str, AuditRecord] = {}

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
        for index, entry in enumerate(self._entries):
            if index == 0:
                if entry.prev_hash != "":
                    return False
                continue
            if entry.prev_hash != self._entries[index - 1].compute_hash():
                return False
        return True

    def record_actor(self, actor: AIActor) -> LedgerEntry:
        self._actors[actor.actor_id] = actor
        return self._append_entry("ai_actor", actor.model_dump(mode="json"))

    def record_activity(self, activity: ActivityRecord) -> LedgerEntry:
        self._activities[activity.activity_id] = activity
        return self._append_entry("activity", activity.model_dump(mode="json"))

    def record_obligation(self, obligation: ObligationRecord) -> LedgerEntry:
        self._obligations[obligation.obligation_id] = obligation
        return self._append_entry("obligation", obligation.model_dump(mode="json"))

    def record_project(self, project: ProjectRecord) -> LedgerEntry:
        self._projects[project.project_id] = project
        return self._append_entry("project", project.model_dump(mode="json"))

    def record_routing(self, routing: RoutingRecord) -> LedgerEntry:
        self._routings[routing.routing_id] = routing
        return self._append_entry("routing", routing.model_dump(mode="json"))

    def record_livelihood(self, livelihood: LivelihoodRecord) -> LedgerEntry:
        self._livelihoods[livelihood.livelihood_id] = livelihood
        return self._append_entry("livelihood", livelihood.model_dump(mode="json"))

    def record_evidence(self, evidence: EvidenceRecord) -> LedgerEntry:
        self._evidence[evidence.evidence_id] = evidence
        return self._append_entry("evidence", evidence.model_dump(mode="json"))

    def record_outcome(self, outcome: OutcomeRecord) -> LedgerEntry:
        self._outcomes[outcome.outcome_id] = outcome
        return self._append_entry("outcome", outcome.model_dump(mode="json"))

    def record_audit(self, audit: AuditRecord) -> LedgerEntry:
        self._audits[audit.audit_id] = audit
        return self._append_entry("audit", audit.model_dump(mode="json"))

    def evidence_for(
        self,
        subject_type: EvidenceSubjectType,
        subject_id: str,
    ) -> list[EvidenceRecord]:
        return [
            record
            for record in self._evidence.values()
            if record.subject_type == subject_type and record.subject_id == subject_id
        ]

    def audits_for(self, scope: AuditScope, scope_id: str) -> list[AuditRecord]:
        return [
            record
            for record in self._audits.values()
            if record.scope == scope and record.scope_id == scope_id
        ]

    def routings_for_obligation(self, obligation_id: str) -> list[RoutingRecord]:
        return [
            record
            for record in self._routings.values()
            if record.obligation_id == obligation_id
        ]

    def total_obligation(self, unit: QuantityUnit) -> float:
        return sum(
            record.obligation_quantity
            for record in self._obligations.values()
            if record.obligation_unit == unit
        )

    def total_routed(self, unit: QuantityUnit) -> float:
        return sum(
            record.routed_value
            for record in self._routings.values()
            if record.routed_unit == unit
        )

    def invariant_issues(self) -> list[ReciprocityIssue]:
        issues: list[ReciprocityIssue] = []

        for activity in self._activities.values():
            if activity.actor_id not in self._actors:
                issues.append(
                    ReciprocityIssue(
                        code="activity_missing_actor",
                        message="activity references unknown actor",
                        metadata={
                            "activity_id": activity.activity_id,
                            "actor_id": activity.actor_id,
                        },
                    )
                )

        for obligation in self._obligations.values():
            if obligation.activity_id not in self._activities:
                issues.append(
                    ReciprocityIssue(
                        code="obligation_missing_activity",
                        message="obligation references unknown activity",
                        metadata={
                            "obligation_id": obligation.obligation_id,
                            "activity_id": obligation.activity_id,
                        },
                    )
                )

            routed = self.routings_for_obligation(obligation.obligation_id)
            if obligation.status == ObligationStatus.FULFILLED and not routed:
                issues.append(
                    ReciprocityIssue(
                        code="fulfilled_without_routing",
                        message="fulfilled obligation has no routing records",
                        metadata={"obligation_id": obligation.obligation_id},
                    )
                )

            comparable_routed = [
                route.routed_value
                for route in routed
                if route.routed_unit == obligation.obligation_unit
            ]
            if comparable_routed and sum(comparable_routed) > obligation.obligation_quantity + 1e-9:
                issues.append(
                    ReciprocityIssue(
                        code="routing_exceeds_obligation",
                        message="routing total exceeds obligation quantity",
                        metadata={
                            "obligation_id": obligation.obligation_id,
                            "obligation_quantity": obligation.obligation_quantity,
                            "routed_total": sum(comparable_routed),
                        },
                    )
                )

        for routing in self._routings.values():
            if routing.obligation_id not in self._obligations:
                issues.append(
                    ReciprocityIssue(
                        code="routing_missing_obligation",
                        message="routing references unknown obligation",
                        metadata={
                            "routing_id": routing.routing_id,
                            "obligation_id": routing.obligation_id,
                        },
                    )
                )
            if routing.project_id not in self._projects:
                issues.append(
                    ReciprocityIssue(
                        code="routing_missing_project",
                        message="routing references unknown project",
                        metadata={
                            "routing_id": routing.routing_id,
                            "project_id": routing.project_id,
                        },
                    )
                )

        for livelihood in self._livelihoods.values():
            if livelihood.project_id not in self._projects:
                issues.append(
                    ReciprocityIssue(
                        code="livelihood_missing_project",
                        message="livelihood references unknown project",
                        metadata={
                            "livelihood_id": livelihood.livelihood_id,
                            "project_id": livelihood.project_id,
                        },
                    )
                )
            if not livelihood.transition_target_group.strip():
                issues.append(
                    ReciprocityIssue(
                        code="livelihood_missing_target_group",
                        message="livelihood record requires transition_target_group",
                        metadata={"livelihood_id": livelihood.livelihood_id},
                    )
                )

        for outcome in self._outcomes.values():
            project = self._projects.get(outcome.project_id)
            if project is None:
                issues.append(
                    ReciprocityIssue(
                        code="outcome_missing_project",
                        message="outcome references unknown project",
                        metadata={
                            "outcome_id": outcome.outcome_id,
                            "project_id": outcome.project_id,
                        },
                    )
                )
                continue

            if (
                outcome.outcome_type in self.ECOLOGICAL_OUTCOMES
                and outcome.status in self.VERIFIED_OUTCOME_STATUSES
            ):
                evidence = self.evidence_for(
                    EvidenceSubjectType.OUTCOME,
                    outcome.outcome_id,
                )
                audits = self.audits_for(AuditScope.OUTCOME, outcome.outcome_id)
                if not evidence:
                    issues.append(
                        ReciprocityIssue(
                            code="verified_ecology_missing_evidence",
                            message="verified ecological outcome has no evidence",
                            metadata={"outcome_id": outcome.outcome_id},
                        )
                    )
                if not audits:
                    issues.append(
                        ReciprocityIssue(
                            code="verified_ecology_missing_audit",
                            message="verified ecological outcome has no audit",
                            metadata={"outcome_id": outcome.outcome_id},
                        )
                    )
                if project.integrity_class == IntegrityClass.EXPERIMENTAL:
                    issues.append(
                        ReciprocityIssue(
                            code="experimental_project_verified_claim",
                            message="experimental project cannot sustain a high-confidence ecological claim",
                            metadata={
                                "project_id": project.project_id,
                                "outcome_id": outcome.outcome_id,
                            },
                        )
                    )

        return issues

    def summary(self) -> dict[str, Any]:
        issues = self.invariant_issues()
        integrity_mix = {
            integrity.value: sum(
                1
                for project in self._projects.values()
                if project.integrity_class == integrity
            )
            for integrity in IntegrityClass
        }
        return {
            "entries": self.entry_count,
            "chain_valid": self.verify_chain_integrity(),
            "actors": len(self._actors),
            "activities": len(self._activities),
            "obligations": len(self._obligations),
            "projects": len(self._projects),
            "routings": len(self._routings),
            "livelihoods": len(self._livelihoods),
            "evidence": len(self._evidence),
            "outcomes": len(self._outcomes),
            "audits": len(self._audits),
            "active_obligations": sum(
                1
                for record in self._obligations.values()
                if record.status == ObligationStatus.ACTIVE
            ),
            "fulfilled_obligations": sum(
                1
                for record in self._obligations.values()
                if record.status == ObligationStatus.FULFILLED
            ),
            "total_obligation_usd": self.total_obligation(QuantityUnit.USD),
            "total_routed_usd": self.total_routed(QuantityUnit.USD),
            "challenged_claims": sum(
                1
                for record in self._outcomes.values()
                if record.status == OutcomeStatus.CHALLENGED
            ),
            "integrity_mix": integrity_mix,
            "invariant_issues": len(issues),
            "issues": [issue.model_dump() for issue in issues],
        }

    def save(self) -> Path:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        path = self._data_dir / "reciprocity_ledger.jsonl"
        with open(path, "w", encoding="utf-8") as handle:
            for entry in self._entries:
                handle.write(
                    json.dumps(entry.model_dump(mode="json"), default=str) + "\n"
                )
        return path

    def load(self) -> int:
        path = self._data_dir / "reciprocity_ledger.jsonl"
        if not path.exists():
            return 0
        count = 0
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    entry = LedgerEntry.model_validate_json(stripped)
                except ValueError:
                    continue
                self._entries.append(entry)
                self._rebuild_from_entry(entry)
                count += 1
        return count

    def _rebuild_from_entry(self, entry: LedgerEntry) -> None:
        payload = entry.payload
        if entry.entry_type == "ai_actor":
            actor = AIActor.model_validate(payload)
            self._actors[actor.actor_id] = actor
        elif entry.entry_type == "activity":
            activity = ActivityRecord.model_validate(payload)
            self._activities[activity.activity_id] = activity
        elif entry.entry_type == "obligation":
            obligation = ObligationRecord.model_validate(payload)
            self._obligations[obligation.obligation_id] = obligation
        elif entry.entry_type == "project":
            project = ProjectRecord.model_validate(payload)
            self._projects[project.project_id] = project
        elif entry.entry_type == "routing":
            routing = RoutingRecord.model_validate(payload)
            self._routings[routing.routing_id] = routing
        elif entry.entry_type == "livelihood":
            livelihood = LivelihoodRecord.model_validate(payload)
            self._livelihoods[livelihood.livelihood_id] = livelihood
        elif entry.entry_type == "evidence":
            evidence = EvidenceRecord.model_validate(payload)
            self._evidence[evidence.evidence_id] = evidence
        elif entry.entry_type == "outcome":
            outcome = OutcomeRecord.model_validate(payload)
            self._outcomes[outcome.outcome_id] = outcome
        elif entry.entry_type == "audit":
            audit = AuditRecord.model_validate(payload)
            self._audits[audit.audit_id] = audit

    def to_gaia_ledger(
        self,
        data_dir: Path | None = None,
    ) -> tuple[GaiaLedger, list[str]]:
        """Project convertible records into the lower-level GAIA substrate."""

        gaia = GaiaLedger(data_dir=data_dir)
        warnings: list[str] = []

        actors = self._actors

        for activity in self._activities.values():
            if activity.energy_mwh is None:
                warnings.append(
                    f"activity {activity.activity_id} has no energy_mwh; skipped compute projection"
                )
                continue
            emissions = activity.emissions_tco2e or 0.0
            carbon_intensity = (
                emissions / activity.energy_mwh if activity.energy_mwh > 0 else 0.0
            )
            actor = actors.get(activity.actor_id)
            gaia.record_compute(
                ComputeUnit(
                    provider=actor.actor_name if actor else activity.actor_id,
                    energy_mwh=activity.energy_mwh,
                    carbon_intensity=carbon_intensity,
                    workload_type=activity.exposure_class.value,
                    timestamp=datetime.combine(
                        activity.period_end,
                        datetime.min.time(),
                        tzinfo=timezone.utc,
                    ),
                    metadata={
                        "activity_id": activity.activity_id,
                        "methodology_ref": activity.methodology_ref,
                        "confidence": activity.confidence.value,
                    },
                )
            )

        for routing in self._routings.values():
            obligation = self._obligations.get(routing.obligation_id)
            project = self._projects.get(routing.project_id)
            if obligation is None or project is None:
                continue
            if routing.routed_unit != QuantityUnit.USD:
                warnings.append(
                    f"routing {routing.routing_id} uses {routing.routed_unit.value}; skipped funding projection"
                )
                continue
            activity = self._activities.get(obligation.activity_id)
            actor = actors.get(activity.actor_id) if activity else None
            gaia.record_funding(
                FundingUnit(
                    amount_usd=routing.routed_value,
                    source=actor.actor_name if actor else obligation.activity_id,
                    destination=project.project_name,
                    purpose=obligation.obligation_type.value,
                    timestamp=routing.routed_at,
                    metadata={
                        "routing_id": routing.routing_id,
                        "project_id": routing.project_id,
                    },
                )
            )

        for livelihood in self._livelihoods.values():
            if livelihood.person_hours is None:
                warnings.append(
                    f"livelihood {livelihood.livelihood_id} has no person_hours; skipped labor projection"
                )
                continue
            gaia.record_labor(
                LaborUnit(
                    worker_id=f"cohort:{livelihood.livelihood_id}",
                    project_id=livelihood.project_id,
                    hours=livelihood.person_hours,
                    skill_type=livelihood.livelihood_mode.value,
                    location=self._projects.get(livelihood.project_id, ProjectRecord(
                        project_id="unknown",
                        project_name="unknown",
                        project_type=ProjectType.MIXED,
                        location="unknown",
                    )).location,
                    output_metric=float(livelihood.participant_count),
                    output_unit="participants",
                    wage_rate=livelihood.median_compensation_local or 0.0,
                    metadata={
                        "livelihood_id": livelihood.livelihood_id,
                        "transition_target_group": livelihood.transition_target_group,
                        "local_ownership_share": livelihood.local_ownership_share,
                    },
                )
            )

        for outcome in self._outcomes.values():
            project = self._projects.get(outcome.project_id)
            if project is None:
                continue
            unit_normalized = outcome.unit.lower()
            convertible = outcome.outcome_type in {OutcomeType.CARBON, OutcomeType.METHANE} and (
                "co2e" in unit_normalized or unit_normalized in {"tco2e", "co2e_tons", "tons_co2e"}
            )
            if not convertible:
                warnings.append(
                    f"outcome {outcome.outcome_id} is not convertible to a GAIA offset unit"
                )
                continue

            offset = OffsetUnit(
                project_id=project.project_id,
                co2e_tons=outcome.quantity,
                confidence=0.0,
                is_verified=False,
                metadata={
                    "outcome_id": outcome.outcome_id,
                    "project_name": project.project_name,
                    "integrity_class": project.integrity_class.value,
                    "status": outcome.status.value,
                },
            )
            gaia.record_offset(offset)

            oracle_seen: set[str] = set()
            for evidence in self.evidence_for(EvidenceSubjectType.OUTCOME, outcome.outcome_id):
                oracle_type = _evidence_to_oracle_type(evidence.evidence_type)
                if oracle_type in oracle_seen:
                    continue
                oracle_seen.add(oracle_type)
                gaia.record_verification(
                    VerificationUnit(
                        oracle_type=oracle_type,
                        target_id=offset.id,
                        target_type=UnitType.OFFSET,
                        confidence=_confidence_to_score(evidence.confidence),
                        method_details=evidence.source_ref,
                        metadata={
                            "evidence_id": evidence.evidence_id,
                            "verifier": evidence.verifier,
                        },
                    )
                )
            for audit in self.audits_for(AuditScope.OUTCOME, outcome.outcome_id):
                if audit.audit_status not in {AuditStatus.PASSED, AuditStatus.QUALIFIED}:
                    continue
                oracle_type = "human_auditor"
                if oracle_type in oracle_seen:
                    continue
                oracle_seen.add(oracle_type)
                gaia.record_verification(
                    VerificationUnit(
                        oracle_type=oracle_type,
                        target_id=offset.id,
                        target_type=UnitType.OFFSET,
                        confidence=0.9 if audit.audit_status == AuditStatus.PASSED else 0.75,
                        method_details=audit.notes_ref or audit.auditor,
                        metadata={"audit_id": audit.audit_id},
                    )
                )

        return gaia, warnings


def _confidence_to_score(confidence: ConfidenceLevel) -> float:
    return {
        ConfidenceLevel.LOW: 0.45,
        ConfidenceLevel.MEDIUM: 0.7,
        ConfidenceLevel.HIGH: 0.9,
    }[confidence]


def _evidence_to_oracle_type(evidence_type: EvidenceType) -> str:
    return {
        EvidenceType.SATELLITE: "satellite",
        EvidenceType.SENSOR: "iot_sensor",
        EvidenceType.METERING: "statistical_model",
        EvidenceType.GROUND_AUDIT: "human_auditor",
        EvidenceType.FINANCIAL: "community",
        EvidenceType.SURVEY: "community",
        EvidenceType.POLICY: "statistical_model",
    }[evidence_type]


__all__ = [
    "AIActor",
    "AIReciprocityLedger",
    "ActivityRecord",
    "ActorType",
    "AuditRecord",
    "AuditScope",
    "AuditStatus",
    "ConfidenceLevel",
    "ConsentStatus",
    "DisclosureLevel",
    "EvidenceRecord",
    "EvidenceSubjectType",
    "EvidenceType",
    "ExposureClass",
    "IntegrityClass",
    "LaborTransitionRiskClass",
    "LivelihoodMode",
    "LivelihoodRecord",
    "ObligationBasis",
    "ObligationRecord",
    "ObligationStatus",
    "ObligationType",
    "OutcomeRecord",
    "OutcomeStatus",
    "OutcomeType",
    "ProjectRecord",
    "ProjectType",
    "QuantityUnit",
    "ReciprocityIssue",
    "RoutingRecord",
]
