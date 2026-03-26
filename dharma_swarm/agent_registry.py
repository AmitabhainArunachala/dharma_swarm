"""Agent Registry — JIKOKU paper trail, fitness computation, and prompt evolution.

Every agent action is timestamped (JIKOKU = UTC ISO-8601).
Fitness is computed from task_log.jsonl metrics.
Prompt evolution tracks system prompt versions with generation numbers.

Standalone module — only stdlib imports.

Model pricing ($/Mtok):
  moonshotai/kimi-k2.5: $0.45
  deepseek/deepseek-chat-v3-0324: $0.26
  nvidia/llama-3.1-nemotron-70b-instruct:free: $0.00
  zhipuai/glm-5-plus: $0.72
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"

# $/token pricing for cost computation.
# Keys are full OpenRouter model identifiers.
MODEL_PRICING: dict[str, float] = {
    "moonshotai/kimi-k2.5": 0.45e-6,
    "deepseek/deepseek-chat-v3-0324": 0.26e-6,
    "nvidia/llama-3.1-nemotron-70b-instruct:free": 0.0,
    "nvidia/nemotron-nano-9b-v2:free": 0.0,
    "nvidia/nemotron-3-super-120b-a12b:free": 0.0,
    "zhipuai/glm-5-plus": 0.72e-6,
    "z-ai/glm-4.5-air:free": 0.0,
    "google/gemma-3-27b-it:free": 0.0,
    "nousresearch/hermes-3-llama-3.1-405b:free": 0.0,
    "meta-llama/llama-3.3-70b-instruct:free": 0.0,
    "qwen/qwen3-coder:free": 0.0,
}

# Latency threshold (ms) used to normalize speed score.
# Anything at or below this gets a 1.0 speed score; above decays linearly.
_SPEED_CEILING_MS: float = 5_000.0
_SPEED_FLOOR_MS: float = 120_000.0

# ── Budget defaults (overridable via env vars) ────────────────────────
DAILY_BUDGET_USD: float = float(os.getenv("GINKO_DAILY_BUDGET", "5.0"))
WEEKLY_BUDGET_USD: float = float(os.getenv("GINKO_WEEKLY_BUDGET", "25.0"))
BUDGET_WARNING_THRESHOLD: float = 0.8  # warn at 80% of budget


def _utc_now() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def _jikoku() -> str:
    """Return JIKOKU timestamp — UTC ISO-8601 with timezone info."""
    return _utc_now().isoformat()


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, returning None on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write a JSON file (write to tmp then rename)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        shutil.move(str(tmp), str(path))
    except Exception as exc:
        logger.error("Failed to write %s: %s", path, exc)
        raise


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    """Append a single JSON line to a JSONL file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to append to %s: %s", path, exc)
        raise


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all entries from a JSONL file. Returns empty list on failure."""
    entries: list[dict[str, Any]] = []
    if not path.exists():
        return entries
    try:
        with path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning("Bad JSON at %s:%d: %s", path, lineno, exc)
    except Exception as exc:
        logger.error("Failed to read %s: %s", path, exc)
    return entries


def _lookup_price_per_token(model: str) -> float:
    """Look up per-token price for a model.

    Tries exact match first, then substring match against known keys.
    Returns 0.0 for unknown models (conservative — don't fabricate cost).
    """
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    model_lower = model.lower()
    for key, price in MODEL_PRICING.items():
        if key.lower() in model_lower or model_lower in key.lower():
            return price
    return 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IDENTITY SCHEMA
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class AgentIdentity:
    """On-disk agent identity.  Mirrors the existing identity.json schema."""

    name: str
    role: str
    model: str
    system_prompt: str
    status: str = "idle"
    created_at: str = ""
    last_active: str = ""
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_tokens_used: int = 0
    total_calls: int = 0
    avg_quality: float = 0.0
    prompt_generation: int = 0
    task_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON persistence."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentIdentity:
        """Deserialize from dict, ignoring unknown keys."""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AGENT REGISTRY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class AgentRegistry:
    """Registry for agent state, fitness, and prompt evolution.

    Each agent occupies a directory under ``agents_dir``:

    .. code-block:: text

        {agents_dir}/{name}/
            identity.json
            task_log.jsonl
            fitness_history.jsonl
            prompt_variants/
                active.txt
                gen_0.txt
                gen_1.txt
                ...
                evolution_log.jsonl
    """

    def __init__(self, agents_dir: Path | None = None) -> None:
        self.agents_dir = agents_dir or GINKO_DIR / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)

    # ── paths ──────────────────────────────────────────────────────────

    def _agent_dir(self, name: str) -> Path:
        return self.agents_dir / name

    def _identity_path(self, name: str) -> Path:
        return self._agent_dir(name) / "identity.json"

    def _task_log_path(self, name: str) -> Path:
        return self._agent_dir(name) / "task_log.jsonl"

    def _fitness_history_path(self, name: str) -> Path:
        return self._agent_dir(name) / "fitness_history.jsonl"

    def _prompt_dir(self, name: str) -> Path:
        return self._agent_dir(name) / "prompt_variants"

    def _active_prompt_path(self, name: str) -> Path:
        return self._prompt_dir(name) / "active.txt"

    def _evolution_log_path(self, name: str) -> Path:
        return self._prompt_dir(name) / "evolution_log.jsonl"

    def _runtime_fields_path(self, name: str) -> Path:
        return self._agent_dir(name) / "runtime_fields.json"

    def _frontier_tasks_path(self, name: str) -> Path:
        return self._agent_dir(name) / "frontier_tasks.jsonl"

    # ── registration ───────────────────────────────────────────────────

    def register_agent(
        self,
        name: str,
        role: str,
        model: str,
        system_prompt: str,
        runtime_fields: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create identity.json + prompt_variants/active.txt.

        Returns the identity dict.  If identity already exists on disk,
        returns the existing identity without overwriting.

        JIKOKU timestamp on ``created_at``.
        """
        identity_path = self._identity_path(name)
        if identity_path.exists():
            existing = _read_json(identity_path)
            if existing is not None:
                if runtime_fields is not None:
                    self.set_runtime_fields(name, runtime_fields)
                logger.info("Agent '%s' already registered — returning existing.", name)
                return existing

        now = _jikoku()
        identity = AgentIdentity(
            name=name,
            role=role,
            model=model,
            system_prompt=system_prompt,
            created_at=now,
            last_active=now,
            prompt_generation=0,
        )

        agent_dir = self._agent_dir(name)
        agent_dir.mkdir(parents=True, exist_ok=True)

        data = identity.to_dict()
        _write_json(identity_path, data)

        # Seed the prompt variants directory with gen_0 and active.
        prompt_dir = self._prompt_dir(name)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        active_path = self._active_prompt_path(name)
        active_path.write_text(system_prompt, encoding="utf-8")

        gen_0_path = prompt_dir / "gen_0.txt"
        gen_0_path.write_text(system_prompt, encoding="utf-8")

        # Seed evolution log with creation entry.
        _append_jsonl(self._evolution_log_path(name), {
            "generation": 0,
            "reason": "initial registration",
            "timestamp": now,
            "prompt_preview": system_prompt[:200],
        })

        if runtime_fields is not None:
            self.set_runtime_fields(name, runtime_fields)

        logger.info("Registered agent '%s' (role=%s, model=%s).", name, role, model)
        return data

    def set_runtime_fields(self, name: str, fields: list[dict[str, Any]]) -> None:
        """Persist the runtime field manifest for an agent."""
        payload = {
            "agent": name,
            "updated_at": _jikoku(),
            "fields": fields,
        }
        _write_json(self._runtime_fields_path(name), payload)

    def get_runtime_fields(self, name: str) -> list[dict[str, Any]]:
        """Load the runtime field manifest for an agent, if present."""
        data = _read_json(self._runtime_fields_path(name))
        if not data:
            return []
        fields = data.get("fields", [])
        return fields if isinstance(fields, list) else []

    def append_frontier_tasks(self, name: str, tasks: list[Any]) -> None:
        """Persist frontier task proposals for an agent without a second task store."""
        for task in tasks:
            payload = task.model_dump() if hasattr(task, "model_dump") else dict(task)
            _append_jsonl(self._frontier_tasks_path(name), payload)

    def get_frontier_tasks(self, name: str) -> list[dict[str, Any]]:
        """Load frontier task proposals persisted for an agent."""
        return _read_jsonl(self._frontier_tasks_path(name))

    # ── loading ────────────────────────────────────────────────────────

    def load_agent(self, name: str) -> dict[str, Any] | None:
        """Load agent identity from disk.

        Also handles legacy flat-file format (``{name}.json`` directly in
        agents_dir) by migrating it into the directory structure on first access.

        Returns:
            Identity dict, or ``None`` if the agent does not exist.
        """
        identity_path = self._identity_path(name)
        if identity_path.exists():
            return _read_json(identity_path)

        # Legacy migration: flat file → directory structure.
        legacy_path = self.agents_dir / f"{name}.json"
        if legacy_path.exists():
            data = _read_json(legacy_path)
            if data is not None:
                logger.info("Migrating legacy agent '%s' to directory format.", name)
                self._migrate_legacy(name, data, legacy_path)
                return data
        return None

    def _migrate_legacy(
        self,
        name: str,
        data: dict[str, Any],
        legacy_path: Path,
    ) -> None:
        """Migrate a flat-file agent JSON into the directory structure.

        Preserves the legacy file as ``{name}.json.bak`` for safety.
        """
        agent_dir = self._agent_dir(name)
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Write identity.json
        _write_json(self._identity_path(name), data)

        # Populate task_log.jsonl from embedded task_history
        task_history = data.get("task_history", [])
        if task_history:
            task_log_path = self._task_log_path(name)
            for entry in task_history:
                _append_jsonl(task_log_path, entry)

        # Seed prompt_variants from system_prompt
        system_prompt = data.get("system_prompt", "")
        if system_prompt:
            prompt_dir = self._prompt_dir(name)
            prompt_dir.mkdir(parents=True, exist_ok=True)
            self._active_prompt_path(name).write_text(system_prompt, encoding="utf-8")
            (prompt_dir / "gen_0.txt").write_text(system_prompt, encoding="utf-8")

        # Backup legacy file
        backup_path = legacy_path.with_suffix(".json.bak")
        try:
            shutil.move(str(legacy_path), str(backup_path))
            logger.info("Backed up legacy file to %s", backup_path)
        except Exception as exc:
            logger.warning("Could not backup legacy file %s: %s", legacy_path, exc)

    def list_agents(self) -> list[dict[str, Any]]:
        """List all registered agents.

        Scans both directory-based agents and legacy flat files.
        Returns a list of identity dicts sorted by name.
        """
        agents: dict[str, dict[str, Any]] = {}

        # Directory-based agents
        if self.agents_dir.exists():
            for child in sorted(self.agents_dir.iterdir()):
                if child.is_dir():
                    identity_path = child / "identity.json"
                    if identity_path.exists():
                        data = _read_json(identity_path)
                        if data is not None:
                            agents[child.name] = data

            # Legacy flat files
            for child in sorted(self.agents_dir.glob("*.json")):
                name = child.stem
                if name not in agents:
                    data = _read_json(child)
                    if data is not None:
                        agents[name] = data

        return sorted(agents.values(), key=lambda a: a.get("name", ""))

    # ── task logging ───────────────────────────────────────────────────

    def log_task(
        self,
        name: str,
        task: str,
        success: bool,
        tokens: int,
        latency_ms: float,
        response_preview: str = "",
    ) -> None:
        """Append task entry to task_log.jsonl with JIKOKU timestamp.

        Also updates identity.json counters (tasks_completed, tasks_failed,
        total_tokens_used, total_calls, last_active).

        Computes and stores ``cost_usd`` per entry for efficient budget
        tracking.  If the daily or weekly budget would be exceeded, logs a
        WARNING and sets ``budget_exceeded: true`` on the entry — but does
        NOT block the write (kill-switch evaluation happens upstream).
        """
        now = _jikoku()

        # Compute cost for this entry using model pricing.
        identity = self.load_agent(name)
        model = identity.get("model", "") if identity else ""
        price_per_token = _lookup_price_per_token(model)
        cost_usd = round(tokens * price_per_token, 8)

        entry: dict[str, Any] = {
            "task": task,
            "success": success,
            "tokens": tokens,
            "latency_ms": latency_ms,
            "cost_usd": cost_usd,
            "timestamp": now,
            "response_preview": response_preview[:500] if response_preview else "",
        }

        # Budget pre-check: flag but don't block.
        if self.is_budget_exceeded(name):
            entry["budget_exceeded"] = True
            logger.warning(
                "BUDGET EXCEEDED for agent '%s' — task logged with flag. "
                "Daily: $%.4f / $%.2f, Weekly: $%.4f / $%.2f",
                name,
                self.get_daily_spend(name),
                DAILY_BUDGET_USD,
                self.get_weekly_spend(name),
                WEEKLY_BUDGET_USD,
            )

        # Ensure agent directory exists (handles pre-existing agents).
        agent_dir = self._agent_dir(name)
        agent_dir.mkdir(parents=True, exist_ok=True)

        _append_jsonl(self._task_log_path(name), entry)

        # Update identity counters.
        if identity is not None:
            if success:
                identity["tasks_completed"] = identity.get("tasks_completed", 0) + 1
            else:
                identity["tasks_failed"] = identity.get("tasks_failed", 0) + 1
            identity["total_tokens_used"] = identity.get("total_tokens_used", 0) + tokens
            identity["total_calls"] = identity.get("total_calls", 0) + 1
            identity["last_active"] = now

            # Append to embedded task_history (capped at last 50 for identity.json).
            history = identity.get("task_history", [])
            history.append(entry)
            if len(history) > 50:
                history = history[-50:]
            identity["task_history"] = history

            _write_json(self._identity_path(name), identity)

        logger.debug(
            "Logged task for '%s': success=%s tokens=%d cost=$%.6f latency=%.0fms",
            name, success, tokens, cost_usd, latency_ms,
        )

    # ── fitness ────────────────────────────────────────────────────────

    def get_agent_fitness(self, name: str) -> dict[str, Any]:
        """Compute fitness from task_log.jsonl.

        Returns a dict with:
            - success_rate: tasks_ok / total_tasks (0.0 if no tasks)
            - avg_latency: mean latency_ms across all tasks
            - avg_quality: mean quality scores (defaults to 0.5 per task
              if no ``quality`` field is present in the log entry)
            - total_calls: count of task log entries
            - total_tokens: sum of all token counts
            - total_cost_usd: sum(tokens * model_price_per_token)
            - speed_score: normalized 0-1 (fast = high)
            - composite_fitness: success_rate * 0.4 + speed_score * 0.3 + quality * 0.3
        """
        entries = _read_jsonl(self._task_log_path(name))

        if not entries:
            return {
                "name": name,
                "success_rate": 0.0,
                "avg_latency": 0.0,
                "avg_quality": 0.0,
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "speed_score": 0.0,
                "composite_fitness": 0.0,
                "computed_at": _jikoku(),
            }

        total = len(entries)
        successes = sum(1 for e in entries if e.get("success"))
        success_rate = successes / total

        latencies = [e.get("latency_ms", 0.0) for e in entries]
        avg_latency = sum(latencies) / total if total else 0.0

        # Quality: use per-entry quality field if present, else default 0.5.
        qualities = [e.get("quality", 0.5) for e in entries]
        avg_quality = sum(qualities) / len(qualities)

        total_tokens = sum(e.get("tokens", 0) for e in entries)

        # Cost: look up model from identity, then multiply.
        identity = self.load_agent(name)
        model = identity.get("model", "") if identity else ""
        price_per_token = _lookup_price_per_token(model)
        total_cost_usd = round(total_tokens * price_per_token, 8)

        # Speed score: linear decay from ceiling to floor, clamped [0, 1].
        if avg_latency <= _SPEED_CEILING_MS:
            speed_score = 1.0
        elif avg_latency >= _SPEED_FLOOR_MS:
            speed_score = 0.0
        else:
            speed_score = 1.0 - (
                (avg_latency - _SPEED_CEILING_MS)
                / (_SPEED_FLOOR_MS - _SPEED_CEILING_MS)
            )

        composite_fitness = (
            success_rate * 0.4
            + speed_score * 0.3
            + avg_quality * 0.3
        )

        return {
            "name": name,
            "success_rate": round(success_rate, 4),
            "avg_latency": round(avg_latency, 1),
            "avg_quality": round(avg_quality, 4),
            "total_calls": total,
            "total_tokens": total_tokens,
            "total_cost_usd": total_cost_usd,
            "speed_score": round(speed_score, 4),
            "composite_fitness": round(composite_fitness, 4),
            "computed_at": _jikoku(),
        }

    def update_fitness_history(self, name: str) -> None:
        """Append current fitness snapshot to fitness_history.jsonl with JIKOKU.

        Call this periodically (e.g. after each task batch, daily reconciliation)
        to build a fitness time series for trend analysis.
        """
        fitness = self.get_agent_fitness(name)
        _append_jsonl(self._fitness_history_path(name), fitness)
        logger.debug("Updated fitness history for '%s': composite=%.4f",
                      name, fitness["composite_fitness"])

    def get_fitness_history(self, name: str) -> list[dict[str, Any]]:
        """Return all fitness history entries for an agent."""
        return _read_jsonl(self._fitness_history_path(name))

    # ── prompt evolution ───────────────────────────────────────────────

    def get_prompt_variant(self, name: str) -> str:
        """Read active prompt from prompt_variants/active.txt.

        Falls back to system_prompt in identity.json if active.txt
        does not exist.  Returns empty string if neither is available.
        """
        active_path = self._active_prompt_path(name)
        if active_path.exists():
            try:
                return active_path.read_text(encoding="utf-8")
            except Exception as exc:
                logger.warning("Failed to read active prompt for '%s': %s", name, exc)

        # Fallback: identity.json
        identity = self.load_agent(name)
        if identity:
            return identity.get("system_prompt", "")
        return ""

    def evolve_prompt(self, name: str, new_prompt: str, reason: str) -> None:
        """Save a new prompt variant with full history preservation.

        Steps:
            1. Archive current active prompt to ``prompt_variants/gen_{N}.txt``
            2. Write new prompt to ``active.txt``
            3. Increment ``prompt_generation`` in identity.json
            4. Update ``system_prompt`` in identity.json
            5. Log evolution in ``prompt_variants/evolution_log.jsonl``
               with reason + JIKOKU

        Never deletes old prompts — full lineage is always preserved.
        """
        identity = self.load_agent(name)
        if identity is None:
            raise ValueError(
                f"Cannot evolve prompt for unregistered agent '{name}'."
            )

        prompt_dir = self._prompt_dir(name)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        current_gen = identity.get("prompt_generation", 0)
        next_gen = current_gen + 1

        # 1. Archive current active prompt.
        active_path = self._active_prompt_path(name)
        if active_path.exists():
            archive_path = prompt_dir / f"gen_{current_gen}.txt"
            if not archive_path.exists():
                try:
                    old_prompt = active_path.read_text(encoding="utf-8")
                    archive_path.write_text(old_prompt, encoding="utf-8")
                except Exception as exc:
                    logger.warning(
                        "Failed to archive gen_%d for '%s': %s",
                        current_gen, name, exc,
                    )

        # 2. Write new prompt to active.txt.
        active_path.write_text(new_prompt, encoding="utf-8")

        # Also save as gen_{next_gen}.txt for completeness.
        next_gen_path = prompt_dir / f"gen_{next_gen}.txt"
        next_gen_path.write_text(new_prompt, encoding="utf-8")

        # 3 + 4. Update identity.json.
        now = _jikoku()
        identity["prompt_generation"] = next_gen
        identity["system_prompt"] = new_prompt
        identity["last_active"] = now
        _write_json(self._identity_path(name), identity)

        # 5. Log evolution.
        _append_jsonl(self._evolution_log_path(name), {
            "generation": next_gen,
            "reason": reason,
            "timestamp": now,
            "prompt_preview": new_prompt[:200],
            "previous_generation": current_gen,
        })

        logger.info(
            "Evolved prompt for '%s': gen %d -> %d (reason: %s)",
            name, current_gen, next_gen, reason,
        )

    def get_prompt_history(self, name: str) -> list[dict[str, Any]]:
        """Return evolution log entries for an agent.

        Each entry contains: generation, reason, timestamp, prompt_preview,
        previous_generation.
        """
        return _read_jsonl(self._evolution_log_path(name))

    # ── bulk operations ────────────────────────────────────────────────

    def migrate_all_legacy(self) -> list[str]:
        """Migrate all legacy flat-file agents to directory format.

        Returns list of agent names that were migrated.
        """
        migrated: list[str] = []
        if not self.agents_dir.exists():
            return migrated

        for child in sorted(self.agents_dir.glob("*.json")):
            name = child.stem
            # Skip if already has a directory
            if self._agent_dir(name).is_dir():
                continue
            data = _read_json(child)
            if data is not None:
                self._migrate_legacy(name, data, child)
                migrated.append(name)
                logger.info("Migrated legacy agent: %s", name)

        return migrated

    def get_fleet_fitness(self) -> list[dict[str, Any]]:
        """Compute fitness for all registered agents.

        Returns a list of fitness dicts sorted by composite_fitness descending.
        Useful for fleet-wide performance dashboards and Darwin Engine selection.
        """
        agents = self.list_agents()
        fitness_list = []
        for agent in agents:
            name = agent.get("name")
            if name:
                fitness = self.get_agent_fitness(name)
                fitness_list.append(fitness)

        fitness_list.sort(
            key=lambda f: f.get("composite_fitness", 0.0),
            reverse=True,
        )
        return fitness_list

    def get_fleet_summary(self) -> dict[str, Any]:
        """Return a high-level summary of the agent fleet.

        Includes: total agents, total tasks, total tokens, total cost,
        average composite fitness, and per-agent summaries.
        """
        fleet = self.get_fleet_fitness()
        total_calls = sum(f.get("total_calls", 0) for f in fleet)
        total_tokens = sum(f.get("total_tokens", 0) for f in fleet)
        total_cost = sum(f.get("total_cost_usd", 0.0) for f in fleet)
        composites = [f.get("composite_fitness", 0.0) for f in fleet]
        avg_fitness = (
            sum(composites) / len(composites) if composites else 0.0
        )

        return {
            "total_agents": len(fleet),
            "total_calls": total_calls,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6),
            "avg_composite_fitness": round(avg_fitness, 4),
            "agents": fleet,
            "computed_at": _jikoku(),
        }


    # ── budget tracking ──────────────────────────────────────────────

    def _cost_for_entry(
        self,
        entry: dict[str, Any],
        agent_name: str | None = None,
    ) -> float:
        """Extract or compute cost_usd for a single task log entry.

        New entries have ``cost_usd`` pre-computed.  Legacy entries (before
        budget tracking) only have ``tokens`` — fall back to model pricing
        if ``agent_name`` is provided, otherwise return 0.0.
        """
        if "cost_usd" in entry:
            return float(entry["cost_usd"])
        if agent_name is None:
            return 0.0
        identity = self.load_agent(agent_name)
        model = identity.get("model", "") if identity else ""
        price = _lookup_price_per_token(model)
        return round(int(entry.get("tokens", 0)) * price, 8)

    def _aggregate_spend(
        self,
        cutoff: datetime,
        agent_name: str | None = None,
    ) -> float:
        """Sum cost_usd across all task log entries since *cutoff*.

        Args:
            cutoff: Only include entries with timestamp >= this value.
            agent_name: If provided, only sum for this agent.
                If ``None``, sum across ALL registered agents.

        Returns:
            Total spend in USD.
        """
        cutoff_iso = cutoff.isoformat()
        total = 0.0

        if agent_name is not None:
            names = [agent_name]
        else:
            names = [
                a.get("name", "")
                for a in self.list_agents()
                if a.get("name")
            ]

        for name in names:
            entries = _read_jsonl(self._task_log_path(name))
            for entry in entries:
                ts = entry.get("timestamp", "")
                if ts >= cutoff_iso:
                    total += self._cost_for_entry(entry, agent_name=name)
        return round(total, 8)

    def get_daily_spend(self, agent_name: str | None = None) -> float:
        """Return total USD spent today (UTC midnight to now).

        Args:
            agent_name: Specific agent, or ``None`` for fleet-wide total.
        """
        now = _utc_now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return self._aggregate_spend(midnight, agent_name)

    def get_weekly_spend(self, agent_name: str | None = None) -> float:
        """Return total USD spent in the last 7 days.

        Args:
            agent_name: Specific agent, or ``None`` for fleet-wide total.
        """
        now = _utc_now()
        week_ago = now - timedelta(days=7)
        return self._aggregate_spend(week_ago, agent_name)

    def check_budget(
        self,
        agent_name: str | None = None,
    ) -> dict[str, Any]:
        """Return current budget status.

        Returns a dict with daily/weekly spend, budgets, remaining amounts,
        and an overall status string:

        - ``"OK"`` — spend is under the warning threshold.
        - ``"WARNING"`` — spend exceeds 80% of daily or weekly budget.
        - ``"EXCEEDED"`` — daily or weekly budget is fully exceeded.

        Budget limits are read from module-level ``DAILY_BUDGET_USD`` and
        ``WEEKLY_BUDGET_USD`` (overridable via ``GINKO_DAILY_BUDGET`` and
        ``GINKO_WEEKLY_BUDGET`` env vars).
        """
        daily_spent = self.get_daily_spend(agent_name)
        weekly_spent = self.get_weekly_spend(agent_name)
        daily_remaining = max(0.0, DAILY_BUDGET_USD - daily_spent)
        weekly_remaining = max(0.0, WEEKLY_BUDGET_USD - weekly_spent)

        if (
            daily_spent >= DAILY_BUDGET_USD
            or weekly_spent >= WEEKLY_BUDGET_USD
        ):
            status = "EXCEEDED"
        elif (
            daily_spent >= DAILY_BUDGET_USD * BUDGET_WARNING_THRESHOLD
            or weekly_spent >= WEEKLY_BUDGET_USD * BUDGET_WARNING_THRESHOLD
        ):
            status = "WARNING"
        else:
            status = "OK"

        return {
            "agent": agent_name,
            "daily_spent": round(daily_spent, 6),
            "daily_budget": DAILY_BUDGET_USD,
            "daily_remaining": round(daily_remaining, 6),
            "weekly_spent": round(weekly_spent, 6),
            "weekly_budget": WEEKLY_BUDGET_USD,
            "weekly_remaining": round(weekly_remaining, 6),
            "warning_threshold": BUDGET_WARNING_THRESHOLD,
            "status": status,
            "checked_at": _jikoku(),
        }

    def is_budget_exceeded(
        self,
        agent_name: str | None = None,
    ) -> bool:
        """Return ``True`` if daily OR weekly budget is exceeded.

        This is the kill-switch predicate.  Callers should check this
        before dispatching new LLM calls and refuse to dispatch if it
        returns ``True``.
        """
        daily = self.get_daily_spend(agent_name)
        if daily >= DAILY_BUDGET_USD:
            return True
        weekly = self.get_weekly_spend(agent_name)
        return weekly >= WEEKLY_BUDGET_USD

    def format_budget_report(self) -> str:
        """Return a human-readable budget report for the entire fleet.

        Shows per-agent daily/weekly spend, fleet totals, and overall
        budget status.  Suitable for CLI output or logging.
        """
        agents = self.list_agents()
        lines: list[str] = [
            "=== GINKO BUDGET REPORT ===",
            f"Daily budget:  ${DAILY_BUDGET_USD:.2f}",
            f"Weekly budget: ${WEEKLY_BUDGET_USD:.2f}",
            f"Warning at:    {BUDGET_WARNING_THRESHOLD:.0%}",
            "",
        ]

        if not agents:
            lines.append("No registered agents.")
            fleet_status = self.check_budget()
            lines.append(f"\nFleet status: {fleet_status['status']}")
            return "\n".join(lines)

        lines.append(
            f"{'Agent':<20} {'Today ($)':>10} {'Week ($)':>10} {'Status':>10}"
        )
        lines.append("-" * 54)

        for agent in agents:
            name = agent.get("name", "?")
            budget = self.check_budget(name)
            lines.append(
                f"{name:<20} {budget['daily_spent']:>10.4f} "
                f"{budget['weekly_spent']:>10.4f} {budget['status']:>10}"
            )

        # Fleet totals
        fleet = self.check_budget()
        lines.append("-" * 54)
        lines.append(
            f"{'FLEET TOTAL':<20} {fleet['daily_spent']:>10.4f} "
            f"{fleet['weekly_spent']:>10.4f} {fleet['status']:>10}"
        )
        lines.append("")
        lines.append(
            f"Daily remaining:  ${fleet['daily_remaining']:.4f}"
        )
        lines.append(
            f"Weekly remaining: ${fleet['weekly_remaining']:.4f}"
        )

        if fleet["status"] == "EXCEEDED":
            lines.append(
                "\n*** KILL SWITCH ACTIVE — budget exceeded, "
                "new LLM calls should be blocked ***"
            )
        elif fleet["status"] == "WARNING":
            lines.append(
                "\n* WARNING — approaching budget limit *"
            )

        return "\n".join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODULE-LEVEL CONVENIENCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def get_registry(agents_dir: Path | None = None) -> AgentRegistry:
    """Factory function for the default registry.

    Usage::

        from dharma_swarm.agent_registry import get_registry
        reg = get_registry()
        reg.list_agents()
    """
    return AgentRegistry(agents_dir=agents_dir)
