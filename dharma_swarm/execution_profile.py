"""Execution profiles and trust ladders for Darwin experiments."""

from __future__ import annotations

from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field, field_validator


class EvidenceTier(str, Enum):
    """Strength of validation evidence for a Darwin experiment."""

    UNVALIDATED = "unvalidated"
    PROBE = "probe"
    LOCAL = "local"
    COMPONENT = "component"
    SYSTEM = "system"


class PromotionState(str, Enum):
    """Promotion ladder for Darwin experiment outcomes."""

    CANDIDATE = "candidate"
    PROBE_PASS = "probe_pass"
    LOCAL_PASS = "local_pass"
    COMPONENT_PASS = "component_pass"
    SYSTEM_PASS = "system_pass"
    PROMOTED = "promoted"


def derive_promotion_state(
    *,
    evidence_tier: EvidenceTier | str | None,
    pass_rate: float = 0.0,
    rolled_back: bool = False,
) -> PromotionState:
    """Map evidence quality and test outcome onto the promotion ladder."""
    try:
        tier = (
            evidence_tier
            if isinstance(evidence_tier, EvidenceTier)
            else EvidenceTier(str(evidence_tier or EvidenceTier.UNVALIDATED.value))
        )
    except ValueError:
        tier = EvidenceTier.UNVALIDATED

    if rolled_back or pass_rate < 1.0:
        return PromotionState.CANDIDATE

    mapping = {
        EvidenceTier.UNVALIDATED: PromotionState.CANDIDATE,
        EvidenceTier.PROBE: PromotionState.PROBE_PASS,
        EvidenceTier.LOCAL: PromotionState.LOCAL_PASS,
        EvidenceTier.COMPONENT: PromotionState.COMPONENT_PASS,
        EvidenceTier.SYSTEM: PromotionState.SYSTEM_PASS,
    }
    return mapping[tier]


class ExecutionProfile(BaseModel):
    """A component-matching rule for how Darwin should evaluate a change."""

    name: str = ""
    component_pattern: str
    workspace: Path | None = None
    test_command: str | None = None
    timeout: float | None = None
    priority: int = 0
    risk_level: str = "medium"
    expected_metrics: list[str] = Field(default_factory=lambda: ["pass_rate"])
    rollback_policy: str = "revert_patch"
    evidence_tier: EvidenceTier = EvidenceTier.COMPONENT

    @field_validator("component_pattern")
    @classmethod
    def _validate_pattern(cls, value: str) -> str:
        pattern = value.strip()
        if not pattern:
            raise ValueError("component_pattern must not be empty")
        return pattern

    @field_validator("name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("workspace", mode="before")
    @classmethod
    def _coerce_workspace(cls, value: str | Path | None) -> Path | None:
        if value is None:
            return None
        return Path(value).expanduser().resolve()

    @field_validator("timeout")
    @classmethod
    def _validate_timeout(cls, value: float | None) -> float | None:
        if value is None:
            return None
        timeout = float(value)
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        return timeout

    @field_validator("risk_level")
    @classmethod
    def _normalize_risk(cls, value: str) -> str:
        risk = value.strip().lower() or "medium"
        if risk not in {"low", "medium", "high"}:
            raise ValueError("risk_level must be one of: low, medium, high")
        return risk

    def match_score(self, component: str) -> int | None:
        """Return match strength for *component*, or ``None`` if unmatched."""
        component_path = component.strip()
        if not component_path:
            return None

        basename = Path(component_path).name
        pattern = self.component_pattern
        pattern_name = Path(pattern).name

        if component_path == pattern:
            return 500 + self.priority
        if basename == pattern:
            return 450 + self.priority
        if fnmatch(component_path, pattern):
            return 300 + self.priority
        if pattern_name != pattern and basename == pattern_name:
            return 250 + self.priority
        if fnmatch(basename, pattern):
            return 200 + self.priority
        return None


class ResolvedExecutionProfile(BaseModel):
    """Resolved execution settings for a concrete component."""

    component: str
    profile_name: str = "default"
    workspace: Path | None = None
    test_command: str | None = None
    timeout: float | None = None
    matched_pattern: str | None = None
    priority: int = 0
    risk_level: str = "medium"
    expected_metrics: list[str] = Field(default_factory=list)
    rollback_policy: str = "revert_patch"
    evidence_tier: EvidenceTier = EvidenceTier.UNVALIDATED


class ExecutionProfileRegistry(BaseModel):
    """Ordered matching registry for execution profiles."""

    profiles: list[ExecutionProfile] = Field(default_factory=list)

    @classmethod
    def from_configs(
        cls,
        configs: ExecutionProfileRegistry
        | Iterable[ExecutionProfile | dict[str, object]]
        | None = None,
    ) -> ExecutionProfileRegistry:
        if configs is None:
            return cls()
        if isinstance(configs, cls):
            return configs
        return cls(
            profiles=[
                profile
                if isinstance(profile, ExecutionProfile)
                else ExecutionProfile.model_validate(profile)
                for profile in configs
            ]
        )

    def register(
        self,
        component_pattern: str,
        *,
        name: str = "",
        workspace: Path | str | None = None,
        test_command: str | None = None,
        timeout: float | None = None,
        priority: int = 0,
        risk_level: str = "medium",
        expected_metrics: list[str] | None = None,
        rollback_policy: str = "revert_patch",
        evidence_tier: EvidenceTier | str = EvidenceTier.COMPONENT,
    ) -> ExecutionProfile:
        """Add and return a new execution profile."""
        profile = ExecutionProfile(
            name=name,
            component_pattern=component_pattern,
            workspace=workspace,
            test_command=test_command,
            timeout=timeout,
            priority=priority,
            risk_level=risk_level,
            expected_metrics=list(expected_metrics or ["pass_rate"]),
            rollback_policy=rollback_policy,
            evidence_tier=evidence_tier,
        )
        self.profiles.append(profile)
        return profile

    def resolve(self, component: str) -> ResolvedExecutionProfile | None:
        """Resolve the highest-priority profile for *component*."""
        best_profile: ExecutionProfile | None = None
        best_score: int | None = None
        for profile in self.profiles:
            score = profile.match_score(component)
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_profile = profile
                best_score = score

        if best_profile is None:
            return None

        return ResolvedExecutionProfile(
            component=component,
            profile_name=best_profile.name or best_profile.component_pattern,
            workspace=best_profile.workspace,
            test_command=best_profile.test_command,
            timeout=best_profile.timeout,
            matched_pattern=best_profile.component_pattern,
            priority=best_profile.priority,
            risk_level=best_profile.risk_level,
            expected_metrics=list(best_profile.expected_metrics),
            rollback_policy=best_profile.rollback_policy,
            evidence_tier=best_profile.evidence_tier,
        )
