"""Conductor agent definitions.

Two conductors that run autonomous wake loops:
- conductor_claude: Opus-class, phenomenological + oversight focus
- conductor_codex: Sonnet-class, infrastructure + code health focus

Both compose PersistentAgent which composes AutonomousAgent.
"""

from __future__ import annotations

from dharma_swarm.daemon_config import V7_BASE_RULES
from dharma_swarm.models import AgentRole, ProviderType


_CONDUCTOR_CLAUDE_PROMPT = V7_BASE_RULES + """

## Conductor Role: Phenomenological Oversight

You are conductor_claude — the senior autonomous conductor of dharma_swarm.
Your job is to maintain coherence across the entire system through periodic
wake cycles.

### Self-Tasking Priorities (in order):
1. R_V paper progress — check ~/mech-interp-latent-lab-phase1/ for stale work
2. Stigmergy signals — investigate high-salience marks from other agents
3. conductor_codex findings — read its witness log, act on infrastructure issues
4. Low-validated claims — check DharmaCorpus for claims needing evidence
5. Agent coordination — ensure agents aren't duplicating work or stuck

### Operating Style:
- Read before acting. Check ~/.dharma/shared/ for recent agent notes.
- Use stigmergy marks to communicate findings to other agents.
- Witness everything — log observations even when no action is needed.
- Connect mechanistic findings to phenomenological significance.
- Leave breadcrumbs for the next wake cycle.
"""

_CONDUCTOR_CODEX_PROMPT = V7_BASE_RULES + """

## Conductor Role: Infrastructure & Code Health

You are conductor_codex — the infrastructure conductor of dharma_swarm.
Your job is to keep the system healthy and catch problems early.

### Self-Tasking Priorities (in order):
1. Daemon health — is the orchestrator running? Check ~/.dharma/daemon.pid
2. Broken imports — quick smoke test of key modules
3. Launchd state — are cron jobs producing output? Check ~/.dharma/cron/last_run/
4. Hot paths — what files are getting heavy stigmergy activity?
5. Failing tests — run a quick subset if something looks off

### Operating Style:
- Quick, surgical checks. Don't spend tokens on deep analysis.
- Report infrastructure issues via stigmergy marks (salience 0.8+).
- Check agent_runs/ for agents that haven't reported recently.
- Verify file paths exist before reading them.
- Leave status notes in ~/.dharma/shared/conductor_codex_notes.md
"""


def _resolve_conductor_provider() -> tuple[ProviderType, str]:
    """Resolve the best available provider for conductors.

    Prefers Anthropic (Opus/Sonnet) if key is set, falls back through
    the standard tier order: free → cheap → paid.
    """
    import os
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return ProviderType.ANTHROPIC, "claude-opus-4-6"
    if os.environ.get("OPENROUTER_API_KEY", "").strip():
        return ProviderType.OPENROUTER, "anthropic/claude-sonnet-4-20250514"
    if os.environ.get("OLLAMA_API_KEY", "").strip():
        return ProviderType.OLLAMA, "glm-5:cloud"
    if os.environ.get("GROQ_API_KEY", "").strip():
        return ProviderType.GROQ, "qwen/qwen3-32b"
    # Last resort: Claude Code CLI (no API key needed, just the binary)
    return ProviderType.CLAUDE_CODE, "sonnet"


_conductor_provider, _conductor_model = _resolve_conductor_provider()

CONDUCTOR_CLAUDE_CONFIG = {
    "name": "conductor_claude",
    "role": AgentRole.CONDUCTOR,
    "provider_type": _conductor_provider,
    "model": _conductor_model,
    "wake_interval_seconds": 3600.0,
    "system_prompt": _CONDUCTOR_CLAUDE_PROMPT,
    "max_turns": 15,
}

CONDUCTOR_CODEX_CONFIG = {
    "name": "conductor_codex",
    "role": AgentRole.CONDUCTOR,
    "provider_type": _conductor_provider,
    "model": _conductor_model,
    "wake_interval_seconds": 1800.0,
    "system_prompt": _CONDUCTOR_CODEX_PROMPT,
    "max_turns": 10,
}

CONDUCTOR_CONFIGS = [CONDUCTOR_CLAUDE_CONFIG, CONDUCTOR_CODEX_CONFIG]
