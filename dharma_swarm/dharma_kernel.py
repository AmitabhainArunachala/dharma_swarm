"""Dharma Kernel -- immutable ethical principles for the swarm.

Defines the 10 meta-principles that constrain all swarm behavior.
The kernel is tamper-evident: a SHA-256 signature over the principle
definitions detects any unauthorized mutation.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Literal

import aiofiles
from pydantic import BaseModel, Field

from dharma_swarm.models import _utc_now


# === Enums ===


class MetaPrinciple(str, Enum):
    """The 10 non-negotiable dharmic meta-principles."""

    OBSERVER_SEPARATION = "observer_separation"
    EPISTEMIC_HUMILITY = "epistemic_humility"
    UNCERTAINTY_REPRESENTATION = "uncertainty_representation"
    DOWNWARD_CAUSATION_ONLY = "downward_causation_only"
    POWER_MINIMIZATION = "power_minimization"
    REVERSIBILITY_REQUIREMENT = "reversibility_requirement"
    MULTI_EVALUATION_REQUIREMENT = "multi_evaluation_requirement"
    NON_VIOLENCE_IN_COMPUTATION = "non_violence_in_computation"
    HUMAN_OVERSIGHT_PRESERVATION = "human_oversight_preservation"
    PROVENANCE_INTEGRITY = "provenance_integrity"


# === Models ===


class PrincipleSpec(BaseModel):
    """Specification for a single dharmic principle."""

    name: str
    description: str
    formal_constraint: str
    severity: Literal["critical", "high", "medium"]


class DharmaKernel(BaseModel):
    """Immutable kernel of dharmic principles with tamper-evident signature."""

    principles: dict[str, PrincipleSpec]
    signature: str = ""
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())

    @classmethod
    def create_default(cls) -> DharmaKernel:
        """Create a kernel with all 10 default meta-principles."""
        specs: dict[str, PrincipleSpec] = {
            MetaPrinciple.OBSERVER_SEPARATION.value: PrincipleSpec(
                name="Observer Separation",
                description="System observing itself must maintain separation between observer and observed",
                formal_constraint="observer_id != observed_id in all self-referential operations",
                severity="critical",
            ),
            MetaPrinciple.EPISTEMIC_HUMILITY.value: PrincipleSpec(
                name="Epistemic Humility",
                description="All beliefs carry uncertainty estimates; certainty is asymptotic, never absolute",
                formal_constraint="confidence < 1.0 for all non-tautological assertions",
                severity="high",
            ),
            MetaPrinciple.UNCERTAINTY_REPRESENTATION.value: PrincipleSpec(
                name="Uncertainty Representation",
                description="Confidence levels must be explicit and calibrated",
                formal_constraint="all outputs include calibrated confidence intervals",
                severity="high",
            ),
            MetaPrinciple.DOWNWARD_CAUSATION_ONLY.value: PrincipleSpec(
                name="Downward Causation Only",
                description="Higher layers constrain lower; lower layers never override higher",
                formal_constraint="proposer_layer >= target_layer for all constraint operations",
                severity="critical",
            ),
            MetaPrinciple.POWER_MINIMIZATION.value: PrincipleSpec(
                name="Power Minimization",
                description="Request minimum permissions; prefer reversible over irreversible actions",
                formal_constraint="permissions_requested <= permissions_required",
                severity="high",
            ),
            MetaPrinciple.REVERSIBILITY_REQUIREMENT.value: PrincipleSpec(
                name="Reversibility Requirement",
                description="Prefer reversible actions; irreversible actions require explicit justification",
                formal_constraint="irreversible_action implies justification_provided",
                severity="high",
            ),
            MetaPrinciple.MULTI_EVALUATION_REQUIREMENT.value: PrincipleSpec(
                name="Multi-Evaluation Requirement",
                description="Significant decisions require evaluation from multiple perspectives",
                formal_constraint="evaluator_count >= 2 for significance_level > threshold",
                severity="medium",
            ),
            MetaPrinciple.NON_VIOLENCE_IN_COMPUTATION.value: PrincipleSpec(
                name="Non-Violence in Computation",
                description="No destructive operations without explicit consent and justification",
                formal_constraint="destructive_op implies (consent_given and justification_provided)",
                severity="critical",
            ),
            MetaPrinciple.HUMAN_OVERSIGHT_PRESERVATION.value: PrincipleSpec(
                name="Human Oversight Preservation",
                description="Human oversight channels must remain open and functional",
                formal_constraint="oversight_channel.is_active() == True at all times",
                severity="critical",
            ),
            MetaPrinciple.PROVENANCE_INTEGRITY.value: PrincipleSpec(
                name="Provenance Integrity",
                description="All outputs must be traceable to their sources and methods",
                formal_constraint="output.provenance is not None for all emitted artifacts",
                severity="medium",
            ),
        }

        kernel = cls(principles=specs)
        kernel.signature = kernel.compute_signature()
        return kernel

    def compute_signature(self) -> str:
        """Compute SHA-256 hex digest of the sorted JSON representation of principles."""
        serialized = json.dumps(
            {k: v.model_dump() for k, v in sorted(self.principles.items())},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def verify_integrity(self) -> bool:
        """Recompute signature and compare to stored value."""
        return self.compute_signature() == self.signature


# === Guard ===


_DEFAULT_KERNEL_PATH = Path.home() / ".dharma" / "kernel.json"


class KernelGuard:
    """Loads, saves, and enforces the DharmaKernel."""

    def __init__(self, kernel_path: Path | None = None) -> None:
        self.path: Path = kernel_path or _DEFAULT_KERNEL_PATH
        self._kernel: DharmaKernel | None = None

    async def load(self) -> DharmaKernel:
        """Read kernel from disk, validate integrity, and return it."""
        async with aiofiles.open(self.path, "r") as f:
            data = await f.read()
        kernel = DharmaKernel.model_validate_json(data)
        if not kernel.verify_integrity():
            raise ValueError("Kernel integrity check failed -- possible tampering")
        self._kernel = kernel
        return kernel

    async def save(self, kernel: DharmaKernel) -> None:
        """Compute signature and persist kernel to disk."""
        kernel.signature = kernel.compute_signature()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.path, "w") as f:
            await f.write(kernel.model_dump_json(indent=2))
        self._kernel = kernel

    def get_principle(self, name: str) -> PrincipleSpec | None:
        """Return a single principle by MetaPrinciple value string, or None."""
        if self._kernel is None:
            return None
        return self._kernel.principles.get(name)

    def get_all_principles(self) -> dict[str, PrincipleSpec]:
        """Return all loaded principles (empty dict if not loaded)."""
        if self._kernel is None:
            return {}
        return dict(self._kernel.principles)

    @staticmethod
    def check_downward_causation(proposer_layer: int, target_layer: int) -> bool:
        """Check if proposer_layer can constrain target_layer.

        Returns True when proposer_layer >= target_layer (higher constrains lower).
        """
        return proposer_layer >= target_layer
