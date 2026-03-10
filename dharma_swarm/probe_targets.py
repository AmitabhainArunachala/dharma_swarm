"""Component-aware probe target registry for Darwin Engine."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, Field, field_validator


class ProbeTarget(BaseModel):
    """A matching rule for workspace-backed landscape probes."""

    component_pattern: str
    workspace: Path | None = None
    test_command: str | None = None
    timeout: float | None = None
    priority: int = 0

    @field_validator("component_pattern")
    @classmethod
    def _validate_pattern(cls, value: str) -> str:
        pattern = value.strip()
        if not pattern:
            raise ValueError("component_pattern must not be empty")
        return pattern

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
        if pattern_name != pattern and fnmatch(basename, pattern_name):
            return 150 + self.priority
        return None


class ResolvedProbeTarget(BaseModel):
    """Resolved probe settings for a component."""

    component: str
    workspace: Path | None = None
    test_command: str | None = None
    timeout: float | None = None
    matched_pattern: str | None = None
    priority: int = 0


class ProbeTargetRegistry(BaseModel):
    """Ordered matching registry for workspace-backed probe targets."""

    targets: list[ProbeTarget] = Field(default_factory=list)

    @classmethod
    def from_configs(
        cls,
        configs: ProbeTargetRegistry
        | Iterable[ProbeTarget | dict[str, object]]
        | None = None,
    ) -> ProbeTargetRegistry:
        if configs is None:
            return cls()
        if isinstance(configs, cls):
            return configs
        return cls(
            targets=[
                target
                if isinstance(target, ProbeTarget)
                else ProbeTarget.model_validate(target)
                for target in configs
            ]
        )

    def register(
        self,
        component_pattern: str,
        *,
        workspace: Path | str | None = None,
        test_command: str | None = None,
        timeout: float | None = None,
        priority: int = 0,
    ) -> ProbeTarget:
        """Add and return a new target rule."""
        target = ProbeTarget(
            component_pattern=component_pattern,
            workspace=workspace,
            test_command=test_command,
            timeout=timeout,
            priority=priority,
        )
        self.targets.append(target)
        return target

    def resolve(self, component: str) -> ResolvedProbeTarget | None:
        """Resolve the highest-priority rule for *component*."""
        best_target: ProbeTarget | None = None
        best_score: int | None = None
        for target in self.targets:
            score = target.match_score(component)
            if score is None:
                continue
            if best_score is None or score > best_score:
                best_target = target
                best_score = score

        if best_target is None:
            return None

        return ResolvedProbeTarget(
            component=component,
            workspace=best_target.workspace,
            test_command=best_target.test_command,
            timeout=best_target.timeout,
            matched_pattern=best_target.component_pattern,
            priority=best_target.priority,
        )
