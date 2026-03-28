"""Capability contracts for portable vs locked cron/headless jobs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from dharma_swarm.models import ProviderType
from dharma_swarm.runtime_provider import PREFERRED_LOW_COST_RUNTIME_PROVIDERS


class JobExecutionSurface(str, Enum):
    """Execution surfaces a cron/headless job may require."""

    CLAUDE_BARE = "claude_bare"
    HOSTED_API = "hosted_api"
    CLAUDE_BARE_WITH_HOSTED_FALLBACK = "claude_bare_with_hosted_fallback"


_EXECUTION_SURFACE_ALIASES: dict[str, JobExecutionSurface] = {
    "": JobExecutionSurface.CLAUDE_BARE,
    "claude": JobExecutionSurface.CLAUDE_BARE,
    "claude_bare": JobExecutionSurface.CLAUDE_BARE,
    "claude-cli": JobExecutionSurface.CLAUDE_BARE,
    "hosted": JobExecutionSurface.HOSTED_API,
    "hosted_api": JobExecutionSurface.HOSTED_API,
    "portable": JobExecutionSurface.HOSTED_API,
    "portable_text": JobExecutionSurface.HOSTED_API,
    "claude_bare_with_hosted_fallback": JobExecutionSurface.CLAUDE_BARE_WITH_HOSTED_FALLBACK,
    "claude_hosted_fallback": JobExecutionSurface.CLAUDE_BARE_WITH_HOSTED_FALLBACK,
    "claude_bare_with_fallback": JobExecutionSurface.CLAUDE_BARE_WITH_HOSTED_FALLBACK,
}


@dataclass(frozen=True, slots=True)
class JobCapabilityProfile:
    """Resolved execution contract for a cron/headless job."""

    execution_surface: JobExecutionSurface = JobExecutionSurface.CLAUDE_BARE
    provider_order: tuple[ProviderType, ...] = ()

    @property
    def allows_claude_bare(self) -> bool:
        return self.execution_surface in {
            JobExecutionSurface.CLAUDE_BARE,
            JobExecutionSurface.CLAUDE_BARE_WITH_HOSTED_FALLBACK,
        }

    @property
    def prefers_hosted_api(self) -> bool:
        return self.execution_surface is JobExecutionSurface.HOSTED_API

    @property
    def allows_hosted_fallback(self) -> bool:
        return self.execution_surface is JobExecutionSurface.CLAUDE_BARE_WITH_HOSTED_FALLBACK


def _parse_execution_surface(value: Any) -> JobExecutionSurface:
    key = str(value or "").strip().lower().replace("-", "_")
    return _EXECUTION_SURFACE_ALIASES.get(key, JobExecutionSurface.CLAUDE_BARE)


def _parse_provider_types(raw: Any) -> tuple[ProviderType, ...]:
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
        return ()
    providers: list[ProviderType] = []
    for item in raw:
        try:
            provider = item if isinstance(item, ProviderType) else ProviderType(str(item).strip().lower())
        except ValueError:
            continue
        if provider not in providers:
            providers.append(provider)
    return tuple(providers)


def resolve_job_capability_profile(job: Mapping[str, Any]) -> JobCapabilityProfile:
    """Resolve capability constraints from cron/headless job metadata."""

    execution_surface = _parse_execution_surface(job.get("execution_surface"))
    provider_order = _parse_provider_types(
        job.get("available_provider_types") or job.get("provider_allowlist") or ()
    )
    if not provider_order:
        provider_order = PREFERRED_LOW_COST_RUNTIME_PROVIDERS
    return JobCapabilityProfile(
        execution_surface=execution_surface,
        provider_order=provider_order,
    )


__all__ = [
    "JobCapabilityProfile",
    "JobExecutionSurface",
    "resolve_job_capability_profile",
]
