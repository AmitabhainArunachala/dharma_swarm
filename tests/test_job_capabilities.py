from __future__ import annotations

from dharma_swarm.job_capabilities import (
    JobExecutionSurface,
    resolve_job_capability_profile,
)
from dharma_swarm.models import ProviderType
from dharma_swarm.runtime_provider import PREFERRED_LOW_COST_RUNTIME_PROVIDERS


def test_resolve_job_capability_profile_defaults_to_claude_bare_and_canonical_order():
    profile = resolve_job_capability_profile({})

    assert profile.execution_surface is JobExecutionSurface.CLAUDE_BARE
    assert profile.provider_order == PREFERRED_LOW_COST_RUNTIME_PROVIDERS


def test_resolve_job_capability_profile_parses_portable_alias_and_allowlist():
    profile = resolve_job_capability_profile(
        {
            "execution_surface": "portable_text",
            "provider_allowlist": [
                ProviderType.OLLAMA.value,
                ProviderType.GROQ.value,
                "not-a-provider",
                ProviderType.OLLAMA.value,
            ],
        }
    )

    assert profile.execution_surface is JobExecutionSurface.HOSTED_API
    assert profile.provider_order == (ProviderType.OLLAMA, ProviderType.GROQ)
