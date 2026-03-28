"""Ginko Evolution -- Darwin Engine prompt evolution for the Dharmic Quant fleet.

Bridges the DarwinEngine's evolutionary selection logic to the Ginko agent
fleet's prompt system.  Every 30 days (configurable), a tournament ranks all
agents by composite fitness derived from their task_log.jsonl histories, keeps
the winners' prompts unchanged, and mutates the losers' prompts via the
preferred runtime provider stack.

Full prompt lineage is preserved:
    ~/.dharma/ginko/agents/{name}/prompt_variants/
        active.txt          <- current prompt
        gen_0.txt           <- original prompt
        gen_1.txt           <- first mutation
        ...
        evolution_log.jsonl <- per-mutation audit trail

Tournament results are appended to:
    ~/.dharma/ginko/tournament_history.jsonl

Standalone module -- integrates with
ginko_agents.py and agent_registry.py without modifying them.

Usage:
    python3 -m dharma_swarm.ginko_evolution
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.runtime_provider import complete_via_preferred_runtime_providers

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
AGENTS_DIR = GINKO_DIR / "agents"
TOURNAMENT_HISTORY_PATH = GINKO_DIR / "tournament_history.jsonl"

MUTATION_MODEL = "deepseek/deepseek-chat-v3-0324"

# Fleet agent names (canonical order)
FLEET_AGENTS = ["kimi", "deepseek", "nemotron", "glm", "sentinel", "scout"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _jikoku() -> str:
    """JIKOKU timestamp -- UTC ISO-8601."""
    return _utc_now().isoformat()


def _sha256(text: str) -> str:
    """Return first 12 hex chars of SHA-256 digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read all entries from a JSONL file. Returns empty list on failure."""
    entries: list[dict[str, Any]] = []
    if not path.exists():
        return entries
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except Exception as exc:
        logger.warning("Failed to read %s: %s", path, exc)
    return entries


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    """Append a single JSON line to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")


def _read_json(path: Path) -> dict[str, Any] | None:
    """Read a JSON file, returning None on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# PromptVariant dataclass
# ---------------------------------------------------------------------------


@dataclass
class PromptVariant:
    """A single prompt variant in an agent's evolution lineage.

    Attributes:
        text: The full system prompt text.
        generation: Zero-indexed generation number.
        parent_hash: SHA-256 prefix of the parent prompt (None for gen 0).
        fitness_score: Composite fitness at the time this variant was active.
        created_at: ISO-8601 UTC timestamp of creation.
        active: Whether this variant is currently the active prompt.
    """

    text: str
    generation: int
    parent_hash: str | None
    fitness_score: float
    created_at: str = field(default_factory=_jikoku)
    active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptVariant:
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


# ---------------------------------------------------------------------------
# Fitness computation from task_log.jsonl
# ---------------------------------------------------------------------------


def _compute_fitness_from_log(agent_name: str) -> dict[str, Any]:
    """Compute composite fitness from an agent's task_log.jsonl.

    Returns a dict with success_rate, avg_latency, avg_quality,
    total_calls, composite_fitness.  Mirrors the logic in
    agent_registry.AgentRegistry.get_agent_fitness() but standalone.
    """
    task_log_path = AGENTS_DIR / agent_name / "task_log.jsonl"
    entries = _read_jsonl(task_log_path)

    if not entries:
        # Fall back to identity.json counters
        identity_path = AGENTS_DIR / agent_name / "identity.json"
        identity = _read_json(identity_path)
        if identity and identity.get("total_calls", 0) > 0:
            total = identity["total_calls"]
            completed = identity.get("tasks_completed", 0)
            sr = completed / total
            quality = identity.get("avg_quality", 0.0)
            fitness = identity.get("fitness", 0.5)
            return {
                "name": agent_name,
                "success_rate": round(sr, 4),
                "avg_latency": 0.0,
                "avg_quality": round(quality, 4),
                "total_calls": total,
                "composite_fitness": round(fitness, 4),
            }
        return {
            "name": agent_name,
            "success_rate": 0.0,
            "avg_latency": 0.0,
            "avg_quality": 0.0,
            "total_calls": 0,
            "composite_fitness": 0.0,
        }

    total = len(entries)
    successes = sum(1 for e in entries if e.get("success"))
    success_rate = successes / total

    latencies = [e.get("latency_ms", 0.0) for e in entries]
    avg_latency = sum(latencies) / total

    qualities = [e.get("quality", 0.5) for e in entries]
    avg_quality = sum(qualities) / len(qualities)

    # Speed score: linear decay from 5s (1.0) to 120s (0.0)
    speed_ceiling = 5_000.0
    speed_floor = 120_000.0
    if avg_latency <= speed_ceiling:
        speed_score = 1.0
    elif avg_latency >= speed_floor:
        speed_score = 0.0
    else:
        speed_score = 1.0 - (avg_latency - speed_ceiling) / (speed_floor - speed_ceiling)

    composite = success_rate * 0.4 + speed_score * 0.3 + avg_quality * 0.3

    return {
        "name": agent_name,
        "success_rate": round(success_rate, 4),
        "avg_latency": round(avg_latency, 1),
        "avg_quality": round(avg_quality, 4),
        "total_calls": total,
        "composite_fitness": round(composite, 4),
    }


# ---------------------------------------------------------------------------
# PromptTournament
# ---------------------------------------------------------------------------


class PromptTournament:
    """Tournament-based prompt evolution for the Ginko agent fleet.

    Every ``tournament_interval_days``, ranks agents by composite fitness,
    preserves winners' prompts, and mutates losers' prompts via an LLM call.

    Args:
        agents_dir: Path to the agents directory.
            Defaults to ``~/.dharma/ginko/agents/``.
        tournament_interval_days: Days between tournaments.
            Defaults to 30.
    """

    def __init__(
        self,
        agents_dir: Path | None = None,
        tournament_interval_days: int = 30,
    ) -> None:
        self.agents_dir = agents_dir or AGENTS_DIR
        self.tournament_interval_days = tournament_interval_days

    # -- paths ---------------------------------------------------------------

    def _agent_dir(self, name: str) -> Path:
        return self.agents_dir / name

    def _identity_path(self, name: str) -> Path:
        return self._agent_dir(name) / "identity.json"

    def _task_log_path(self, name: str) -> Path:
        return self._agent_dir(name) / "task_log.jsonl"

    def _prompt_dir(self, name: str) -> Path:
        return self._agent_dir(name) / "prompt_variants"

    def _active_prompt_path(self, name: str) -> Path:
        return self._prompt_dir(name) / "active.txt"

    def _evolution_log_path(self, name: str) -> Path:
        return self._prompt_dir(name) / "evolution_log.jsonl"

    # -- discovery -----------------------------------------------------------

    def _discover_agents(self) -> list[str]:
        """Return list of agent names that have identity.json on disk."""
        agents: list[str] = []
        if not self.agents_dir.exists():
            return agents
        for child in sorted(self.agents_dir.iterdir()):
            if child.is_dir() and (child / "identity.json").exists():
                agents.append(child.name)
        return agents

    def _load_current_prompt(self, name: str) -> str:
        """Load the active prompt for an agent."""
        active = self._active_prompt_path(name)
        if active.exists():
            try:
                return active.read_text(encoding="utf-8")
            except Exception:
                logger.debug("Active prompt read failed for %s", name, exc_info=True)
        # Fallback to identity.json
        identity = _read_json(self._identity_path(name))
        if identity:
            return identity.get("system_prompt", "")
        return ""

    def _get_current_generation(self, name: str) -> int:
        """Get the current prompt generation number for an agent."""
        identity = _read_json(self._identity_path(name))
        if identity:
            return identity.get("prompt_generation", 0)
        return 0

    # -- mutation via LLM ----------------------------------------------------

    async def mutate_prompt(
        self,
        current_prompt: str,
        fitness_scores: dict[str, Any],
    ) -> str:
        """Generate an improved prompt variant via the preferred runtime stack.

        Uses DeepSeek Chat v3 ($0.26/Mtok) for cost efficiency.

        Args:
            current_prompt: The current system prompt text.
            fitness_scores: Dict with success_rate, avg_quality,
                composite_fitness, etc. for context.

        Returns:
            The mutated prompt text.  On error, returns the original
            prompt unchanged (safe fallback).
        """
        fitness_summary = (
            f"success_rate={fitness_scores.get('success_rate', 'N/A')}, "
            f"avg_quality={fitness_scores.get('avg_quality', 'N/A')}, "
            f"composite_fitness={fitness_scores.get('composite_fitness', 'N/A')}, "
            f"total_calls={fitness_scores.get('total_calls', 'N/A')}"
        )

        mutation_prompt = (
            "You are a prompt evolution engine for a financial analysis AI agent fleet. "
            "The following trading analysis prompt scored poorly and needs improvement. "
            "Improve it to produce better predictions, sharper analysis, and higher accuracy. "
            "Keep the agent's core role and identity but refine the analytical approach, "
            "reasoning structure, and output format.\n\n"
            "CONSTRAINTS:\n"
            "- Preserve all SATYA/AHIMSA/REVERSIBILITY gate references\n"
            "- Keep the agent name and role identity\n"
            "- Add concrete analytical frameworks (e.g., base rates, Bayesian updating)\n"
            "- Improve calibration instructions (confidence should match accuracy)\n"
            "- Add structured output instructions for downstream parsing\n\n"
            f"CURRENT PROMPT:\n{current_prompt}\n\n"
            f"PERFORMANCE SCORES:\n{fitness_summary}\n\n"
            "Output ONLY the improved prompt text, nothing else. "
            "No preamble, no explanation, no markdown wrapping."
        )

        t0 = time.monotonic()
        try:
            response, config = await complete_via_preferred_runtime_providers(
                messages=[{"role": "user", "content": mutation_prompt}],
                openrouter_model=MUTATION_MODEL,
                max_tokens=1024,
                temperature=0.8,
                timeout_seconds=60.0,
            )
            latency_ms = (time.monotonic() - t0) * 1000.0
            content = response.content
            if content and len(content) > 12:
                usage = response.usage or {}
                total_tokens = int(
                    usage.get(
                        "total_tokens",
                        (usage.get("prompt_tokens", 0) or 0)
                        + (usage.get("completion_tokens", 0) or 0),
                    )
                    or 0
                )
                logger.info(
                    "Mutation succeeded via %s/%s (%.0fms, %d tokens): %d -> %d chars",
                    config.provider.value,
                    response.model,
                    latency_ms,
                    total_tokens,
                    len(current_prompt),
                    len(content),
                )
                return content.strip()

            logger.warning("Mutation LLM returned empty/short content")
            return current_prompt

        except Exception as exc:
            logger.error("Mutation LLM call failed: %s", exc)
            return current_prompt

    # -- prompt persistence --------------------------------------------------

    def _save_variant(
        self,
        agent_name: str,
        new_prompt: str,
        generation: int,
        parent_hash: str | None,
        fitness: float,
        reason: str,
    ) -> PromptVariant:
        """Save a new prompt variant to disk with full lineage.

        1. Archive current active.txt as gen_{N-1}.txt (if not already archived)
        2. Write new prompt to active.txt and gen_{N}.txt
        3. Update identity.json (system_prompt, prompt_generation)
        4. Append to evolution_log.jsonl
        """
        prompt_dir = self._prompt_dir(agent_name)
        prompt_dir.mkdir(parents=True, exist_ok=True)

        # Archive current active prompt before overwriting
        active_path = self._active_prompt_path(agent_name)
        prev_gen = generation - 1
        if active_path.exists() and prev_gen >= 0:
            archive_path = prompt_dir / f"gen_{prev_gen}.txt"
            if not archive_path.exists():
                try:
                    old_text = active_path.read_text(encoding="utf-8")
                    archive_path.write_text(old_text, encoding="utf-8")
                except Exception as exc:
                    logger.warning("Failed to archive gen_%d for %s: %s",
                                   prev_gen, agent_name, exc)

        # Write new prompt
        active_path.write_text(new_prompt, encoding="utf-8")
        gen_path = prompt_dir / f"gen_{generation}.txt"
        gen_path.write_text(new_prompt, encoding="utf-8")

        # Update identity.json
        identity = _read_json(self._identity_path(agent_name))
        if identity:
            identity["system_prompt"] = new_prompt
            identity["prompt_generation"] = generation
            identity["last_active"] = _jikoku()
            try:
                self._identity_path(agent_name).write_text(
                    json.dumps(identity, indent=2, default=str, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.error("Failed to update identity for %s: %s", agent_name, exc)

        # Append to evolution log
        now = _jikoku()
        _append_jsonl(self._evolution_log_path(agent_name), {
            "generation": generation,
            "reason": reason,
            "timestamp": now,
            "prompt_preview": new_prompt[:200],
            "previous_generation": prev_gen,
            "parent_hash": parent_hash,
            "fitness_at_evolution": fitness,
        })

        variant = PromptVariant(
            text=new_prompt,
            generation=generation,
            parent_hash=parent_hash,
            fitness_score=fitness,
            created_at=now,
            active=True,
        )

        logger.info(
            "Saved prompt variant for %s: gen %d -> %d (reason: %s)",
            agent_name, prev_gen, generation, reason,
        )
        return variant

    # -- lineage -------------------------------------------------------------

    def get_prompt_lineage(self, agent_name: str) -> list[PromptVariant]:
        """Load all prompt variants for an agent sorted by generation.

        Reads gen_*.txt files and correlates with evolution_log.jsonl
        for metadata.

        Args:
            agent_name: The agent identifier.

        Returns:
            List of PromptVariant sorted by generation ascending.
        """
        prompt_dir = self._prompt_dir(agent_name)
        if not prompt_dir.exists():
            return []

        # Read evolution log for metadata
        evo_log = _read_jsonl(self._evolution_log_path(agent_name))
        evo_by_gen: dict[int, dict[str, Any]] = {}
        for entry in evo_log:
            gen = entry.get("generation", -1)
            if gen >= 0:
                evo_by_gen[gen] = entry

        # Read all gen_*.txt files
        variants: list[PromptVariant] = []
        for gen_file in sorted(prompt_dir.glob("gen_*.txt")):
            stem = gen_file.stem  # "gen_0", "gen_1", ...
            try:
                gen_num = int(stem.split("_", 1)[1])
            except (ValueError, IndexError):
                continue

            try:
                text = gen_file.read_text(encoding="utf-8")
            except Exception:
                continue

            meta = evo_by_gen.get(gen_num, {})
            active_path = self._active_prompt_path(agent_name)
            is_active = False
            if active_path.exists():
                try:
                    is_active = active_path.read_text(encoding="utf-8") == text
                except Exception:
                    logger.debug("Active prompt comparison failed for %s", agent_name, exc_info=True)

            variant = PromptVariant(
                text=text,
                generation=gen_num,
                parent_hash=meta.get("parent_hash"),
                fitness_score=meta.get("fitness_at_evolution", 0.0),
                created_at=meta.get("timestamp", ""),
                active=is_active,
            )
            variants.append(variant)

        variants.sort(key=lambda v: v.generation)
        return variants

    # -- tournament history --------------------------------------------------

    def get_tournament_history(self) -> list[dict[str, Any]]:
        """Load all past tournament results from tournament_history.jsonl."""
        return _read_jsonl(TOURNAMENT_HISTORY_PATH)

    def save_tournament_result(self, result: dict[str, Any]) -> None:
        """Append a tournament result to tournament_history.jsonl."""
        _append_jsonl(TOURNAMENT_HISTORY_PATH, result)
        logger.info("Saved tournament result: %s", result.get("tournament_id", "unknown"))

    # -- the tournament ------------------------------------------------------

    async def run_tournament(self) -> dict[str, Any]:
        """Execute a full prompt evolution tournament.

        Steps:
            1. Discover all agents with identity.json on disk
            2. Compute fitness for each from task_log.jsonl
            3. Rank by composite_fitness (descending)
            4. Top 2: keep current prompts (winners)
            5. Bottom 2: mutate prompts via LLM call
            6. Middle agents: unchanged
            7. Save variants and tournament result

        Returns:
            Tournament result dict with rankings, winners, mutated agents,
            and prompt lineage counts.
        """
        tournament_id = f"tournament_{_utc_now().strftime('%Y%m%d_%H%M%S')}"
        logger.info("Starting tournament %s", tournament_id)

        # 1. Discover agents
        agent_names = self._discover_agents()
        if not agent_names:
            result = {
                "tournament_id": tournament_id,
                "timestamp": _jikoku(),
                "status": "no_agents",
                "rankings": [],
                "winners": [],
                "mutated": [],
                "unchanged": [],
            }
            self.save_tournament_result(result)
            return result

        # 2. Compute fitness for each agent
        fitness_map: dict[str, dict[str, Any]] = {}
        for name in agent_names:
            fitness_map[name] = _compute_fitness_from_log(name)

        # 3. Rank by composite fitness (descending)
        rankings = sorted(
            fitness_map.items(),
            key=lambda x: x[1].get("composite_fitness", 0.0),
            reverse=True,
        )

        ranked_names = [name for name, _ in rankings]
        ranked_fitness = [
            {"name": name, **scores}
            for name, scores in rankings
        ]

        # 4-6. Determine winners (top 2), losers (bottom 2), middle
        n = len(ranked_names)
        if n <= 2:
            # Too few agents to split meaningfully
            winners = ranked_names[:]
            losers = []
            middle = []
        elif n <= 4:
            winners = ranked_names[:1]
            losers = ranked_names[-1:]
            middle = ranked_names[1:-1]
        else:
            winners = ranked_names[:2]
            losers = ranked_names[-2:]
            middle = ranked_names[2:-2]

        # 5. Mutate losers' prompts
        mutated_agents: list[dict[str, Any]] = []
        for loser_name in losers:
            current_prompt = self._load_current_prompt(loser_name)
            current_gen = self._get_current_generation(loser_name)
            loser_fitness = fitness_map[loser_name]

            if not current_prompt:
                logger.warning("No prompt found for %s -- skipping mutation", loser_name)
                continue

            parent_hash = _sha256(current_prompt)

            # Generate mutated prompt
            new_prompt = await self.mutate_prompt(current_prompt, loser_fitness)

            # Check if mutation actually changed the prompt
            if new_prompt == current_prompt:
                logger.info("Mutation returned identical prompt for %s -- skipping", loser_name)
                mutated_agents.append({
                    "name": loser_name,
                    "status": "mutation_unchanged",
                    "generation": current_gen,
                    "fitness": loser_fitness.get("composite_fitness", 0.0),
                })
                continue

            # Save the new variant
            new_gen = current_gen + 1
            variant = self._save_variant(
                agent_name=loser_name,
                new_prompt=new_prompt,
                generation=new_gen,
                parent_hash=parent_hash,
                fitness=loser_fitness.get("composite_fitness", 0.0),
                reason=f"tournament_{tournament_id}_loser_mutation",
            )

            mutated_agents.append({
                "name": loser_name,
                "status": "mutated",
                "old_generation": current_gen,
                "new_generation": new_gen,
                "parent_hash": parent_hash,
                "new_hash": _sha256(new_prompt),
                "fitness_before": loser_fitness.get("composite_fitness", 0.0),
                "prompt_length_before": len(current_prompt),
                "prompt_length_after": len(new_prompt),
            })

        # Build tournament result
        result: dict[str, Any] = {
            "tournament_id": tournament_id,
            "timestamp": _jikoku(),
            "status": "completed",
            "agent_count": n,
            "rankings": ranked_fitness,
            "winners": [
                {
                    "name": w,
                    "fitness": fitness_map[w].get("composite_fitness", 0.0),
                    "action": "prompt_preserved",
                }
                for w in winners
            ],
            "mutated": mutated_agents,
            "unchanged": [
                {
                    "name": m,
                    "fitness": fitness_map[m].get("composite_fitness", 0.0),
                    "action": "no_change",
                }
                for m in middle
            ],
            "tournament_interval_days": self.tournament_interval_days,
        }

        self.save_tournament_result(result)
        logger.info(
            "Tournament %s completed: %d agents, %d winners, %d mutated",
            tournament_id, n, len(winners), len(mutated_agents),
        )

        return result


# ---------------------------------------------------------------------------
# Convenience wrappers
# ---------------------------------------------------------------------------


async def run_evolution_cycle() -> dict[str, Any]:
    """Convenience wrapper: create a PromptTournament and run it.

    Returns the tournament result dict.
    """
    tournament = PromptTournament()
    return await tournament.run_tournament()


def format_tournament_report(result: dict[str, Any]) -> str:
    """Format a tournament result dict as a human-readable report.

    Args:
        result: Dict returned by PromptTournament.run_tournament().

    Returns:
        Multi-line string suitable for logging or display.
    """
    lines: list[str] = [
        "=" * 60,
        "GINKO PROMPT EVOLUTION TOURNAMENT",
        f"ID: {result.get('tournament_id', 'unknown')}",
        f"Time: {result.get('timestamp', 'unknown')}",
        f"Status: {result.get('status', 'unknown')}",
        f"Agents: {result.get('agent_count', 0)}",
        "=" * 60,
        "",
        "RANKINGS (by composite fitness):",
        "-" * 45,
    ]

    rankings = result.get("rankings", [])
    for i, r in enumerate(rankings, 1):
        name = r.get("name", "?")
        fitness = r.get("composite_fitness", 0.0)
        sr = r.get("success_rate", 0.0)
        calls = r.get("total_calls", 0)
        lines.append(
            f"  {i}. {name:<12}  fitness={fitness:.4f}  "
            f"success={sr:.0%}  calls={calls}"
        )

    lines.append("")
    lines.append("WINNERS (prompts preserved):")
    lines.append("-" * 45)
    for w in result.get("winners", []):
        lines.append(
            f"  {w.get('name', '?'):<12}  "
            f"fitness={w.get('fitness', 0.0):.4f}  "
            f"action={w.get('action', '?')}"
        )

    lines.append("")
    lines.append("MUTATED (prompts evolved):")
    lines.append("-" * 45)
    mutated = result.get("mutated", [])
    if not mutated:
        lines.append("  (none)")
    for m in mutated:
        name = m.get("name", "?")
        status = m.get("status", "?")
        if status == "mutated":
            old_gen = m.get("old_generation", "?")
            new_gen = m.get("new_generation", "?")
            fitness = m.get("fitness_before", 0.0)
            len_before = m.get("prompt_length_before", 0)
            len_after = m.get("prompt_length_after", 0)
            lines.append(
                f"  {name:<12}  gen {old_gen} -> {new_gen}  "
                f"fitness={fitness:.4f}  "
                f"len {len_before} -> {len_after} chars"
            )
        else:
            lines.append(f"  {name:<12}  {status}")

    lines.append("")
    lines.append("UNCHANGED (middle of pack):")
    lines.append("-" * 45)
    unchanged = result.get("unchanged", [])
    if not unchanged:
        lines.append("  (none)")
    for u in unchanged:
        lines.append(
            f"  {u.get('name', '?'):<12}  "
            f"fitness={u.get('fitness', 0.0):.4f}"
        )

    lines.append("")
    lines.append(f"Next tournament in {result.get('tournament_interval_days', 30)} days")
    lines.append("=" * 60)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    result = asyncio.run(run_evolution_cycle())
    print(format_tournament_report(result))
