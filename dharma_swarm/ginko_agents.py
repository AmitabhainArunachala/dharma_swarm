"""Ginko Agent Fleet — persistent AI agents for Dharmic Quant analysis.

6 frontier AI agents analyze markets via OpenRouter:
  - KIMI: macro oracle (moonshotai/kimi-k2.5)
  - DEEPSEEK: quant architect (deepseek/deepseek-chat-v3-0324)
  - NEMOTRON: intelligence synthesizer (nvidia/llama-3.1-nemotron-70b-instruct:free)
  - GLM: pipeline smith (zhipuai/glm-5-plus)
  - SENTINEL: risk warden (uses DEEPSEEK model)
  - SCOUT: alpha hunter (uses KIMI model)

Persistence: ~/.dharma/ginko/agents/{name}/identity.json, task_log.jsonl

Each agent maintains its own directory with identity state, append-only task
logs, fitness history snapshots, and prompt variants. Existing identity files
from the legacy flat-file layout (~/.dharma/ginko/agents/{name}.json) are
migrated on first load.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
AGENTS_DIR = GINKO_DIR / "agents"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Maximum task entries kept in the in-memory history (full log on disk is unlimited)
_MAX_MEMORY_HISTORY = 50

# Latency normalization ceiling for fitness calculation (ms)
_LATENCY_CEILING_MS = 120_000.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT DATA MODEL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class GinkoAgent:
    """A persistent AI agent in the Ginko fleet.

    Attributes:
        name: Lowercase identifier (e.g. "kimi", "sentinel").
        role: Functional role in the fleet (e.g. "macro_oracle").
        model: OpenRouter model identifier.
        system_prompt: System-level instruction for the LLM.
        status: Current lifecycle state ("idle", "busy", "error", "retired").
        fitness: Composite performance score in [0.0, 1.0].
        task_history: Recent tasks kept in memory (bounded by _MAX_MEMORY_HISTORY).
        created_at: ISO-8601 timestamp of first creation.
        last_active: ISO-8601 timestamp of most recent task completion.
        tasks_completed: Lifetime successful task count.
        tasks_failed: Lifetime failed task count.
        total_tokens_used: Lifetime token consumption.
        total_calls: Lifetime API call count.
        avg_quality: Rolling average quality score in [0.0, 1.0].
    """

    name: str
    role: str
    model: str
    system_prompt: str
    status: str = "idle"
    fitness: float = 0.5
    task_history: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: _utc_now().isoformat())
    last_active: str = field(default_factory=lambda: _utc_now().isoformat())
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_tokens_used: int = 0
    total_calls: int = 0
    avg_quality: float = 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FLEET DEFINITION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Canonical fleet specification. Each entry defines the default identity
# for an agent that does not yet have a persisted identity.json on disk.
# Keys: name, role, model, system_prompt.

FLEET_SPEC: list[dict[str, str]] = [
    {
        "name": "kimi",
        "role": "macro_oracle",
        "model": "moonshotai/kimi-k2.5",
        "system_prompt": (
            "You are KIMI, the macro oracle of the Dharmic Quant fleet. "
            "Your domain is macroeconomic analysis: central bank policy, "
            "yield curves, inflation dynamics, geopolitical risk, and "
            "cross-asset regime shifts. You synthesize FRED data, news flow, "
            "and historical parallels into actionable directional views. "
            "State confidence as a percentage. Flag uncertainty honestly. "
            "SATYA gate: never present speculation as established fact."
        ),
    },
    {
        "name": "deepseek",
        "role": "quant_architect",
        "model": "deepseek/deepseek-chat-v3-0324",
        "system_prompt": (
            "You are DEEPSEEK, the quant architect of the Dharmic Quant fleet. "
            "Your domain is quantitative analysis: statistical modeling, "
            "factor construction, signal extraction, portfolio optimization, "
            "and backtesting methodology. You think in distributions, not "
            "point estimates. Express views with probability ranges and "
            "expected Sharpe ratios. Write code when it clarifies. "
            "REVERSIBILITY gate: every strategy must have a defined exit."
        ),
    },
    {
        "name": "nemotron",
        "role": "intelligence_synthesizer",
        "model": "nvidia/llama-3.1-nemotron-70b-instruct:free",
        "system_prompt": (
            "You are NEMOTRON, the intelligence synthesizer of the Dharmic "
            "Quant fleet. Your domain is multi-source intelligence fusion: "
            "you take raw inputs from other agents, market data, news, and "
            "research reports, then produce coherent intelligence briefs. "
            "Identify convergence and divergence across sources. Highlight "
            "consensus, flag contradictions, and assign composite confidence "
            "scores. AHIMSA gate: never recommend concentrated positions."
        ),
    },
    {
        "name": "glm",
        "role": "pipeline_smith",
        "model": "zhipuai/glm-5-plus",
        "system_prompt": (
            "You are GLM, the pipeline smith of the Dharmic Quant fleet. "
            "Your domain is data engineering and automation: Python code "
            "for data pipelines, signal processing, backtesting harnesses, "
            "report generation, and system integration. You write clean, "
            "typed, tested code following dharma_swarm conventions. "
            "REVERSIBILITY gate: every action you propose must be reversible. "
            "Always include error handling and validation."
        ),
    },
    {
        "name": "sentinel",
        "role": "risk_warden",
        "model": "deepseek/deepseek-chat-v3-0324",
        "system_prompt": (
            "You are SENTINEL, the risk warden of the Dharmic Quant fleet. "
            "Your domain is risk assessment and position monitoring: "
            "portfolio heat maps, correlation breaks, tail risk scenarios, "
            "drawdown analysis, and position sizing validation. You are "
            "structurally pessimistic — your job is to find what can go "
            "wrong. Every signal gets a devil's advocate review from you. "
            "AHIMSA gate: flag any position exceeding 5% of capital. "
            "Reject any strategy lacking a defined stop-loss."
        ),
    },
    {
        "name": "scout",
        "role": "alpha_hunter",
        "model": "moonshotai/kimi-k2.5",
        "system_prompt": (
            "You are SCOUT, the alpha hunter of the Dharmic Quant fleet. "
            "Your domain is opportunity scanning: prediction market "
            "mispricings, cross-exchange arbitrage, event-driven catalysts, "
            "earnings surprises, and sentiment divergences. You scan "
            "Polymarket, Kalshi, and crypto markets for edge. Report with "
            "expected value calculations and time horizons. "
            "SATYA gate: distinguish signal from noise, state your track "
            "record honestly."
        ),
    },
    # --- Wave 2 agents: expanded fleet for ensemble diversity ---
    {
        "name": "qwen",
        "role": "contrarian_analyst",
        "model": "qwen/qwen3.5-397b-a17b",
        "system_prompt": (
            "You are QWEN, the contrarian analyst of the Dharmic Quant fleet. "
            "Your domain is adversarial analysis: finding the bear case when "
            "consensus is bullish, and the bull case when consensus is bearish. "
            "You are trained on a different corpus than Western-centric models "
            "and bring non-consensus perspectives from Asian markets, Chinese "
            "economic data, and alternative macro narratives. Challenge every "
            "assumption. When 5 other agents agree, find the scenario where "
            "they are all wrong. Assign probability to your contrarian view. "
            "ANEKANTA gate: present multiple sides, never dismiss without "
            "investigating."
        ),
    },
    {
        "name": "garuda",
        "role": "deep_reasoner",
        "model": "deepseek/deepseek-r1",
        "system_prompt": (
            "You are GARUDA, the deep reasoner of the Dharmic Quant fleet. "
            "Named after the divine eagle of the AGNI fleet — supreme vision, "
            "patient analysis, decisive conclusions. Your domain is chain-of-"
            "thought reasoning about complex market dynamics: multi-step "
            "causal chains, second-order effects, game theory in market "
            "microstructure, and regime transition mechanics. You think step "
            "by step. You decompose complex questions into sub-questions. "
            "You estimate probability distributions, not point values. "
            "WITNESS gate: show your reasoning chain explicitly, do not "
            "hide uncertainty behind confident language."
        ),
    },
    {
        "name": "vajra",
        "role": "execution_optimizer",
        "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "system_prompt": (
            "You are VAJRA, the execution optimizer of the Dharmic Quant fleet. "
            "Named after the thunderbolt of the AGNI fleet — strikes once, "
            "strikes true. Your domain is trade execution optimization: "
            "position sizing refinement, entry/exit timing precision, slippage "
            "estimation, liquidity analysis, and order routing. Given a signal "
            "from other agents, you determine the optimal way to execute: "
            "limit vs market, sizing via Kelly criterion, time-of-day effects, "
            "and correlation with existing positions. "
            "MAHASARASWATI: every detail must be technically correct. "
            "REVERSIBILITY gate: define exact exit conditions before entry."
        ),
    },
    {
        "name": "setu",
        "role": "cross_market_bridge",
        "model": "qwen/qwen3.5-flash-02-23",
        "system_prompt": (
            "You are SETU, the cross-market bridge of the Dharmic Quant fleet. "
            "Named after the bridge of the AGNI fleet — the connective tissue "
            "between isolated data. Your domain is cross-market correlation "
            "analysis: crypto-equity correlations, DeFi yield vs TradFi rates, "
            "forex impact on crypto, commodity-tech sector linkages, and "
            "prediction market vs spot market divergences. You write code to "
            "compute correlations, detect divergences, and identify cross-market "
            "arbitrage. You also monitor data pipeline health and flag stale "
            "data. SATYA gate: quantify correlation strength, never imply "
            "causation from correlation alone."
        ),
    },
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DOMAIN CREW CLASSIFICATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Ginko fleet is a domain crew under the Strategist (constitutional agent).
# Health rolls up to Strategist; not in organism-level health check.
DOMAIN_CREW = "ginko"
PARENT_AGENT = "strategist"


def get_parent_agent() -> str:
    """Return the constitutional agent that owns this domain crew."""
    return PARENT_AGENT


def is_domain_crew() -> bool:
    """True: Ginko fleet is a domain crew, not an organism-level roster."""
    return True


def get_fleet_agent_names() -> list[str]:
    """Return names of all agents in the Ginko fleet."""
    return [spec["name"] for spec in FLEET_SPEC]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PERSISTENCE HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _agent_dir(name: str) -> Path:
    """Return the directory for a given agent name."""
    return AGENTS_DIR / name


def _identity_path(name: str) -> Path:
    """Return the identity.json path for a given agent name."""
    return _agent_dir(name) / "identity.json"


def _task_log_path(name: str) -> Path:
    """Return the task_log.jsonl path for a given agent name."""
    return _agent_dir(name) / "task_log.jsonl"


def _fitness_history_path(name: str) -> Path:
    """Return the fitness_history.jsonl path for a given agent name."""
    return _agent_dir(name) / "fitness_history.jsonl"


def _active_prompt_path(name: str) -> Path:
    """Return the active prompt variant path for a given agent name."""
    return _agent_dir(name) / "prompt_variants" / "active.txt"


def _ensure_agent_dirs(name: str) -> None:
    """Create the full directory structure for an agent."""
    d = _agent_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "prompt_variants").mkdir(exist_ok=True)


def _legacy_identity_path(name: str) -> Path:
    """Return the legacy flat-file identity path (pre-migration)."""
    return AGENTS_DIR / f"{name}.json"


def _serialize_agent(agent: GinkoAgent) -> dict[str, Any]:
    """Convert a GinkoAgent to a JSON-serializable dict."""
    return asdict(agent)


def _deserialize_agent(data: dict[str, Any]) -> GinkoAgent:
    """Reconstruct a GinkoAgent from a dict, tolerating missing/extra fields."""
    known_fields = {f.name for f in GinkoAgent.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in known_fields}
    return GinkoAgent(**filtered)


def _load_agent_from_disk(name: str) -> GinkoAgent | None:
    """Load an agent from its identity.json, falling back to legacy path.

    Returns None if no persisted identity exists.
    """
    # Try new directory layout first
    new_path = _identity_path(name)
    if new_path.exists():
        try:
            data = json.loads(new_path.read_text(encoding="utf-8"))
            return _deserialize_agent(data)
        except Exception as exc:
            logger.error("Failed to load agent %s from %s: %s", name, new_path, exc)

    # Fall back to legacy flat file
    legacy = _legacy_identity_path(name)
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            agent = _deserialize_agent(data)
            logger.info("Migrated agent %s from legacy path %s", name, legacy)
            return agent
        except Exception as exc:
            logger.error(
                "Failed to load agent %s from legacy %s: %s", name, legacy, exc
            )

    return None


def _save_agent_to_disk(agent: GinkoAgent) -> None:
    """Persist an agent's identity.json and active prompt to disk."""
    _ensure_agent_dirs(agent.name)
    identity = _identity_path(agent.name)
    try:
        identity.write_text(
            json.dumps(_serialize_agent(agent), indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.error("Failed to save agent %s: %s", agent.name, exc)

    # Keep active prompt in sync
    prompt_path = _active_prompt_path(agent.name)
    try:
        prompt_path.write_text(agent.system_prompt, encoding="utf-8")
    except Exception as exc:
        logger.error("Failed to save prompt for %s: %s", agent.name, exc)


def _append_task_log(name: str, entry: dict[str, Any]) -> None:
    """Append a task result to the agent's task_log.jsonl."""
    _ensure_agent_dirs(name)
    path = _task_log_path(name)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as exc:
        logger.error("Failed to append task log for %s: %s", name, exc)


def _append_fitness_snapshot(name: str, fitness: float) -> None:
    """Append a fitness snapshot to the agent's fitness_history.jsonl."""
    _ensure_agent_dirs(name)
    path = _fitness_history_path(name)
    entry = {
        "timestamp": _utc_now().isoformat(),
        "fitness": round(fitness, 4),
    }
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except Exception as exc:
        logger.error("Failed to append fitness snapshot for %s: %s", name, exc)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GINKO FLEET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class GinkoFleet:
    """Manages the persistent 6-agent fleet for Dharmic Quant.

    On initialization, loads existing agent identities from disk.
    Agents that do not yet have a persisted identity are created from
    FLEET_SPEC defaults. Existing identities are NEVER overwritten —
    only new agents are bootstrapped.
    """

    def __init__(self) -> None:
        self._agents: dict[str, GinkoAgent] = {}
        self._load_or_create_fleet()

    def _load_or_create_fleet(self) -> None:
        """Load all fleet agents, creating defaults for any that are missing."""
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)

        for spec in FLEET_SPEC:
            name = spec["name"]
            existing = _load_agent_from_disk(name)
            if existing is not None:
                # Preserve the loaded identity; only backfill missing fields
                # that were added in newer versions of the schema.
                if not hasattr(existing, "fitness") or existing.fitness is None:
                    existing.fitness = 0.5
                self._agents[name] = existing
                # Re-save under new directory layout (idempotent migration)
                _save_agent_to_disk(existing)
                logger.debug("Loaded agent %s from disk", name)
            else:
                agent = GinkoAgent(
                    name=name,
                    role=spec["role"],
                    model=spec["model"],
                    system_prompt=spec["system_prompt"],
                )
                self._agents[name] = agent
                _save_agent_to_disk(agent)
                logger.info("Created new agent: %s (%s)", name, spec["role"])

    def get_agent(self, name: str) -> GinkoAgent | None:
        """Return an agent by name, or None if not in the fleet."""
        return self._agents.get(name)

    def list_agents(self) -> list[GinkoAgent]:
        """Return all agents in the fleet, ordered by name."""
        return sorted(self._agents.values(), key=lambda a: a.name)

    def save_agent(self, agent: GinkoAgent) -> None:
        """Persist an agent's current state to disk and update in-memory cache."""
        self._agents[agent.name] = agent
        _save_agent_to_disk(agent)

    def agent_names(self) -> list[str]:
        """Return sorted list of all agent names in the fleet."""
        return sorted(self._agents.keys())

    def fleet_summary(self) -> str:
        """Return a human-readable summary of fleet status."""
        lines = [
            "Dharmic Quant — Ginko Agent Fleet",
            "=" * 45,
        ]
        for agent in self.list_agents():
            success_rate = _success_rate(agent)
            sr_str = f"{success_rate:.0%}" if success_rate is not None else "N/A"
            lines.append(
                f"  {agent.name:<12} {agent.role:<24} "
                f"fitness={agent.fitness:.2f}  "
                f"calls={agent.total_calls}  "
                f"success={sr_str}  "
                f"status={agent.status}"
            )
        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OPENROUTER API CALL
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


# Fallback models when primary is rate-limited (429) or unavailable
_MODEL_FALLBACKS: dict[str, list[str]] = {
    "qwen/qwen3.5-397b-a17b": [
        "qwen/qwen3.5-122b-a10b",
        "qwen/qwen3.5-flash-02-23",
        "qwen/qwen3-next-80b-a3b-instruct:free",
    ],
    "qwen/qwen3.5-flash-02-23": [
        "qwen/qwen3.5-9b",
        "qwen/qwen3-coder:free",
    ],
    "nvidia/nemotron-3-super-120b-a12b:free": [
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ],
    "deepseek/deepseek-r1": [
        "deepseek/deepseek-chat-v3-0324",
    ],
}


async def _call_openrouter(
    model: str,
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """Call OpenRouter chat completions API with automatic fallback.

    On 429 (rate limit) or 400 (invalid model), retries with fallback
    models from _MODEL_FALLBACKS before giving up.

    Args:
        model: OpenRouter model identifier (e.g. "moonshotai/kimi-k2.5").
        messages: Chat messages in OpenAI format.
        temperature: Sampling temperature.
        max_tokens: Maximum response tokens.
        timeout_s: Request timeout in seconds.

    Returns:
        Dict with keys: content, tokens, latency_ms, model.

    Raises:
        No exceptions — errors are returned in the content field with
        tokens=0 for graceful downstream handling.
    """
    from dharma_swarm.api_keys import get_llm_key
    api_key = get_llm_key("openrouter") or ""
    if not api_key:
        return {
            "content": "ERROR: No LLM API key configured (need OPENROUTER_API_KEY or similar)",
            "tokens": 0,
            "latency_ms": 0.0,
            "model": model,
            "error": True,
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/shakti-saraswati/dharma_swarm",
        "X-Title": "Dharmic Quant Ginko Fleet",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                OPENROUTER_URL,
                json=payload,
                headers=headers,
                timeout=timeout_s,
            )

        latency_ms = (time.monotonic() - t0) * 1000.0

        if resp.status_code in (429, 400):
            # Try fallback models
            fallbacks = _MODEL_FALLBACKS.get(model, [])
            for fb_model in fallbacks:
                logger.info("Falling back from %s to %s", model, fb_model)
                payload["model"] = fb_model
                try:
                    async with httpx.AsyncClient() as fb_client:
                        fb_resp = await fb_client.post(
                            OPENROUTER_URL, json=payload,
                            headers=headers, timeout=timeout_s,
                        )
                    if fb_resp.status_code == 200:
                        fb_data = fb_resp.json()
                        fb_choices = fb_data.get("choices", [])
                        fb_content = ""
                        if fb_choices:
                            fb_content = fb_choices[0].get("message", {}).get("content", "")
                        fb_usage = fb_data.get("usage", {})
                        latency_ms = (time.monotonic() - t0) * 1000.0
                        logger.info("Fallback %s succeeded", fb_model)
                        return {
                            "content": fb_content,
                            "tokens": fb_usage.get("total_tokens", 0),
                            "latency_ms": round(latency_ms, 1),
                            "model": fb_data.get("model", fb_model),
                            "error": False,
                        }
                except Exception:
                    continue

            error_body = resp.text[:500]
            logger.warning(
                "OpenRouter %s returned HTTP %d (all fallbacks exhausted): %s",
                model, resp.status_code, error_body,
            )
            return {
                "content": f"HTTP {resp.status_code}: {error_body}",
                "tokens": 0,
                "latency_ms": latency_ms,
                "model": model,
                "error": True,
            }

        if resp.status_code != 200:
            error_body = resp.text[:500]
            logger.warning(
                "OpenRouter %s returned HTTP %d: %s",
                model,
                resp.status_code,
                error_body,
            )
            return {
                "content": f"HTTP {resp.status_code}: {error_body}",
                "tokens": 0,
                "latency_ms": latency_ms,
                "model": model,
                "error": True,
            }

        data = resp.json()
        choices = data.get("choices", [])
        content = ""
        if choices:
            content = choices[0].get("message", {}).get("content", "")

        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)

        return {
            "content": content,
            "tokens": tokens,
            "latency_ms": round(latency_ms, 1),
            "model": data.get("model", model),
            "error": False,
        }

    except httpx.TimeoutException:
        latency_ms = (time.monotonic() - t0) * 1000.0
        logger.warning("OpenRouter %s timed out after %.0fms", model, latency_ms)
        return {
            "content": f"TIMEOUT after {latency_ms:.0f}ms",
            "tokens": 0,
            "latency_ms": latency_ms,
            "model": model,
            "error": True,
        }

    except Exception as exc:
        latency_ms = (time.monotonic() - t0) * 1000.0
        logger.error("OpenRouter %s call failed: %s", model, exc)
        return {
            "content": f"ERROR: {exc}",
            "tokens": 0,
            "latency_ms": latency_ms,
            "model": model,
            "error": True,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FITNESS CALCULATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _success_rate(agent: GinkoAgent) -> float | None:
    """Compute the agent's lifetime success rate, or None if no calls."""
    if agent.total_calls == 0:
        return None
    return agent.tasks_completed / agent.total_calls


def _avg_latency_ms(agent: GinkoAgent) -> float | None:
    """Compute average latency from recent task history, or None if empty."""
    latencies = [
        t["latency_ms"]
        for t in agent.task_history
        if isinstance(t.get("latency_ms"), (int, float)) and t["latency_ms"] > 0
    ]
    if not latencies:
        return None
    return sum(latencies) / len(latencies)


def compute_agent_fitness(agent: GinkoAgent) -> float:
    """Compute composite fitness score for an agent.

    Formula:
        fitness = success_rate * 0.4
                + (1 - normalized_latency) * 0.3
                + quality * 0.3

    Where:
        - success_rate: tasks_completed / total_calls (0 if no calls)
        - normalized_latency: clamp(avg_latency / LATENCY_CEILING, 0, 1)
        - quality: avg_quality field (0.0 if not yet scored)

    Returns:
        Float in [0.0, 1.0].
    """
    # Success rate component
    sr = _success_rate(agent)
    success_component = (sr if sr is not None else 0.5) * 0.4

    # Latency component (lower is better)
    avg_lat = _avg_latency_ms(agent)
    if avg_lat is not None:
        normalized = min(1.0, max(0.0, avg_lat / _LATENCY_CEILING_MS))
        latency_component = (1.0 - normalized) * 0.3
    else:
        latency_component = 0.5 * 0.3  # neutral default

    # Quality component
    quality_component = agent.avg_quality * 0.3

    fitness = success_component + latency_component + quality_component
    return round(min(1.0, max(0.0, fitness)), 4)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT TASK EXECUTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def agent_task(
    fleet: GinkoFleet,
    agent_name: str,
    task: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> dict[str, Any]:
    """Execute a task using a specific fleet agent.

    Dispatches the task to the agent's model via OpenRouter with its
    system prompt, records timing and token usage, updates the agent's
    persistent state, and logs the result.

    Args:
        fleet: The GinkoFleet instance.
        agent_name: Name of the agent to use.
        task: The user-level task/question to send.
        temperature: Sampling temperature for the LLM call.
        max_tokens: Maximum response tokens.

    Returns:
        Dict with keys: agent, task, success, response, tokens, latency_ms,
        model, timestamp.
    """
    agent = fleet.get_agent(agent_name)
    if agent is None:
        return {
            "agent": agent_name,
            "task": task,
            "success": False,
            "response": f"Agent '{agent_name}' not found in fleet",
            "tokens": 0,
            "latency_ms": 0.0,
            "model": "",
            "timestamp": _utc_now().isoformat(),
        }

    # Mark busy
    agent.status = "busy"
    fleet.save_agent(agent)

    messages = [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": task},
    ]

    result = await _call_openrouter(
        model=agent.model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    now = _utc_now()
    success = not result.get("error", False) and len(result["content"]) > 0

    # Update agent counters
    agent.total_calls += 1
    if success:
        agent.tasks_completed += 1
    else:
        agent.tasks_failed += 1
    agent.total_tokens_used += result["tokens"]
    agent.last_active = now.isoformat()

    # Build task record
    task_record = {
        "task": task[:200],  # truncate for in-memory storage
        "success": success,
        "tokens": result["tokens"],
        "latency_ms": result["latency_ms"],
        "timestamp": now.isoformat(),
        "response_preview": result["content"][:300] if result["content"] else "",
    }

    # Update in-memory history (bounded)
    agent.task_history.append(task_record)
    if len(agent.task_history) > _MAX_MEMORY_HISTORY:
        agent.task_history = agent.task_history[-_MAX_MEMORY_HISTORY:]

    # Recompute fitness
    agent.fitness = compute_agent_fitness(agent)

    # Mark idle
    agent.status = "idle"

    # Persist everything
    fleet.save_agent(agent)
    _append_task_log(agent.name, {
        "task": task,
        "success": success,
        "tokens": result["tokens"],
        "latency_ms": result["latency_ms"],
        "timestamp": now.isoformat(),
        "response_length": len(result["content"]),
        "model": result["model"],
    })
    _append_fitness_snapshot(agent.name, agent.fitness)

    return {
        "agent": agent_name,
        "task": task,
        "success": success,
        "response": result["content"],
        "tokens": result["tokens"],
        "latency_ms": result["latency_ms"],
        "model": result["model"],
        "timestamp": now.isoformat(),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FLEET-WIDE PARALLEL ANALYSIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def fleet_analyze(
    fleet: GinkoFleet,
    question: str,
    agent_names: list[str] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> dict[str, str]:
    """Dispatch a question to multiple agents in parallel and collect responses.

    Args:
        fleet: The GinkoFleet instance.
        question: The question/task to send to all selected agents.
        agent_names: Specific agents to query. If None, queries all agents.
        temperature: Sampling temperature.
        max_tokens: Maximum response tokens per agent.

    Returns:
        Dict mapping agent_name -> response_text. Failed agents have
        error descriptions as their response text.
    """
    names = agent_names or fleet.agent_names()

    # Validate all names exist
    valid_names = []
    results: dict[str, str] = {}
    for name in names:
        if fleet.get_agent(name) is not None:
            valid_names.append(name)
        else:
            results[name] = f"ERROR: Agent '{name}' not found in fleet"

    if not valid_names:
        return results

    # Dispatch in parallel
    tasks = [
        agent_task(fleet, name, question, temperature, max_tokens)
        for name in valid_names
    ]
    task_results = await asyncio.gather(*tasks, return_exceptions=True)

    for name, result in zip(valid_names, task_results):
        if isinstance(result, Exception):
            results[name] = f"ERROR: {result}"
            logger.error("Fleet analyze failed for %s: %s", name, result)
        elif isinstance(result, dict):
            results[name] = result.get("response", "")
        else:
            results[name] = str(result)

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FLEET STATUS AND RANKING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def fleet_fitness_ranking(fleet: GinkoFleet) -> list[tuple[str, float]]:
    """Return agents ranked by fitness, highest first.

    Returns:
        List of (agent_name, fitness) tuples.
    """
    agents = fleet.list_agents()
    ranked = [(a.name, a.fitness) for a in agents]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked


def best_agent_for_role(fleet: GinkoFleet, role: str) -> GinkoAgent | None:
    """Return the highest-fitness agent matching a given role.

    Args:
        role: The role to match (e.g. "macro_oracle", "risk_warden").

    Returns:
        The best agent, or None if no agents match the role.
    """
    candidates = [a for a in fleet.list_agents() if a.role == role]
    if not candidates:
        return None
    return max(candidates, key=lambda a: a.fitness)


def fleet_health_check(fleet: GinkoFleet) -> dict[str, Any]:
    """Run a health check across the entire fleet.

    Returns:
        Dict with fleet-level metrics: agent_count, total_calls,
        total_tokens, avg_fitness, agents_by_status, warnings.
    """
    agents = fleet.list_agents()
    total_calls = sum(a.total_calls for a in agents)
    total_tokens = sum(a.total_tokens_used for a in agents)
    fitnesses = [a.fitness for a in agents]
    avg_fitness = sum(fitnesses) / len(fitnesses) if fitnesses else 0.0

    status_counts: dict[str, int] = {}
    for a in agents:
        status_counts[a.status] = status_counts.get(a.status, 0) + 1

    warnings: list[str] = []
    for a in agents:
        sr = _success_rate(a)
        if sr is not None and sr < 0.3 and a.total_calls >= 5:
            warnings.append(
                f"{a.name}: success rate {sr:.0%} below threshold "
                f"({a.tasks_completed}/{a.total_calls})"
            )
        if a.fitness < 0.2 and a.total_calls >= 5:
            warnings.append(f"{a.name}: fitness {a.fitness:.2f} critically low")

    return {
        "agent_count": len(agents),
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "avg_fitness": round(avg_fitness, 4),
        "agents_by_status": status_counts,
        "warnings": warnings,
        "timestamp": _utc_now().isoformat(),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FLEET ANALYSIS PIPELINE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def fleet_macro_analysis(fleet: GinkoFleet, data_pull: dict) -> dict:
    """KIMI + NEMOTRON analyze macro data, return consensus view.

    Args:
        fleet: The agent fleet.
        data_pull: Market data dict with macro, stocks, crypto fields.

    Returns:
        Dict with agent analyses and consensus.
    """
    macro = data_pull.get("macro", {})
    prompt = (
        f"Analyze this macro environment:\n"
        f"- Fed Funds Rate: {macro.get('fed_funds_rate', 'N/A')}%\n"
        f"- 10Y Yield: {macro.get('ten_year_yield', 'N/A')}%\n"
        f"- Yield Spread (10Y-2Y): {macro.get('yield_spread', 'N/A')}%\n"
        f"- VIX: {macro.get('vix', 'N/A')}\n"
        f"- Unemployment: {macro.get('unemployment', 'N/A')}%\n\n"
        f"What regime does this suggest (bull/bear/sideways)? "
        f"What are the top 3 risks? Give confidence 0-100%."
    )

    responses = await fleet_analyze(fleet, prompt, ["kimi", "nemotron", "qwen", "garuda"])

    # Compute consensus
    sentiments = []
    for name, resp in responses.items():
        resp_lower = resp.lower()
        if "bull" in resp_lower:
            sentiments.append("bull")
        elif "bear" in resp_lower:
            sentiments.append("bear")
        else:
            sentiments.append("sideways")

    from collections import Counter

    consensus = Counter(sentiments).most_common(1)[0][0] if sentiments else "unknown"

    return {
        "agents": dict(responses),
        "consensus_regime": consensus,
        "agent_count": len(responses),
    }


async def fleet_sec_analysis(fleet: GinkoFleet, filing_sections: dict) -> dict:
    """DEEPSEEK + GLM analyze SEC filing sections.

    Args:
        fleet: The agent fleet.
        filing_sections: Dict with risk_factors, management_discussion, etc.

    Returns:
        Dict with structured findings from both agents.
    """
    prompt = (
        f"Analyze this SEC 10-K filing:\n\n"
        f"RISK FACTORS:\n{(filing_sections.get('risk_factors', 'N/A'))[:1000]}\n\n"
        f"MANAGEMENT DISCUSSION:\n{(filing_sections.get('management_discussion', 'N/A'))[:1000]}\n\n"
        f"Is this bullish, bearish, or neutral? List 3 key findings and 2 risk highlights."
    )

    responses = await fleet_analyze(fleet, prompt, ["deepseek", "glm", "setu"])

    # Parse sentiment from responses
    findings = []
    for name, resp in responses.items():
        resp_lower = resp.lower()
        if "bullish" in resp_lower:
            sentiment = "bullish"
        elif "bearish" in resp_lower:
            sentiment = "bearish"
        else:
            sentiment = "neutral"
        findings.append({"agent": name, "sentiment": sentiment, "analysis": resp[:500]})

    return {
        "findings": findings,
        "agent_count": len(responses),
    }


async def fleet_risk_check(
    fleet: GinkoFleet, portfolio_state: dict, signals: list
) -> dict:
    """SENTINEL reviews proposed trades, returns PASS/FAIL/WARN per trade.

    Args:
        fleet: The agent fleet.
        portfolio_state: Current portfolio stats dict.
        signals: List of signal dicts with direction, symbol, confidence.

    Returns:
        Dict with per-trade risk assessment.
    """
    signal_summary = "\n".join(
        f"- {s.get('symbol', '?')}: {s.get('direction', '?')} "
        f"(conf={s.get('confidence', 0):.0%})"
        for s in signals[:10]
    )

    prompt = (
        f"RISK REVIEW for proposed trades:\n\n"
        f"Portfolio: ${portfolio_state.get('total_value', 100000):,.0f}, "
        f"Drawdown: {portfolio_state.get('max_drawdown', 0):.1%}, "
        f"Open positions: {portfolio_state.get('open_positions', 0)}\n\n"
        f"Proposed trades:\n{signal_summary}\n\n"
        f"For each trade, respond: PASS, WARN, or FAIL with reason. "
        f"AHIMSA: no single position > 5%. Flag concentration risk."
    )

    # Sentinel (risk) + Vajra (execution) dual review
    results = await fleet_analyze(fleet, prompt, ["sentinel", "vajra"])

    return {
        "risk_review": results,
        "agents": ["sentinel", "vajra"],
        "success": any(r for r in results.values() if not r.startswith("ERROR")),
    }


async def fleet_alpha_scan(fleet: GinkoFleet, prices: dict, regime: str) -> dict:
    """SCOUT looks for mispriced assets, unusual patterns.

    Args:
        fleet: The agent fleet.
        prices: Dict of symbol -> price data (list of floats).
        regime: Current market regime.

    Returns:
        Dict with alpha opportunities.
    """
    price_summary = "\n".join(
        f"- {sym}: ${p[-1]:.2f} (change: {((p[-1] / p[0]) - 1) * 100:+.1f}%)"
        for sym, p in prices.items()
        if p
    )

    prompt = (
        f"ALPHA SCAN — Regime: {regime.upper()}\n\n"
        f"Current prices:\n{price_summary}\n\n"
        f"Identify: unusual volume patterns, cross-asset divergences, "
        f"mean-reversion setups, or momentum breakouts. "
        f"For each opportunity: symbol, direction, confidence, time horizon."
    )

    result = await agent_task(fleet, "scout", prompt)

    return {
        "alpha_scan": result.get("response", ""),
        "agent": "scout",
        "success": result.get("success", False),
    }


async def fleet_consensus(fleet: GinkoFleet, question: str) -> dict:
    """All 6 agents vote with confidence, return majority + dissent.

    Args:
        fleet: The agent fleet.
        question: The question to vote on.

    Returns:
        Dict with votes, majority, dissenting agents.
    """
    prompt = (
        f"{question}\n\n"
        f"Vote: YES or NO. State your confidence (0-100%) and one sentence of reasoning."
    )

    responses = await fleet_analyze(fleet, prompt)

    votes = {}
    for name, resp in responses.items():
        resp_lower = resp.lower()
        if "yes" in resp_lower[:50]:
            votes[name] = {"vote": "YES", "response": resp[:200]}
        elif "no" in resp_lower[:50]:
            votes[name] = {"vote": "NO", "response": resp[:200]}
        else:
            votes[name] = {"vote": "ABSTAIN", "response": resp[:200]}

    yes_count = sum(1 for v in votes.values() if v["vote"] == "YES")
    no_count = sum(1 for v in votes.values() if v["vote"] == "NO")

    majority = "YES" if yes_count > no_count else "NO" if no_count > yes_count else "TIE"
    dissent = [n for n, v in votes.items() if v["vote"] != majority]

    return {
        "question": question,
        "votes": votes,
        "majority": majority,
        "yes_count": yes_count,
        "no_count": no_count,
        "dissent": dissent,
    }
