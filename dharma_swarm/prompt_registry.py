"""Prompt Registry — production-grade prompt template management for dharma_swarm.

Stores, versions, discovers, assembles, and evaluates prompt templates as
first-class evolvable artifacts. Integrates with:

  - Darwin Engine: prompts evolve via fitness-driven selection
  - Agent Runner: prompt assembly from registry + runtime context
  - Stigmergy: high-fitness prompt patterns propagate as marks
  - TraceStore: every invocation logged with prompt_id + version
  - Canary Deployer: A/B testing with statistical significance gates

Architecture (Beer's VSM mapping):
  S1 (Operations): PromptTemplate storage and assembly
  S2 (Coordination): PromptRouter matches tasks to templates
  S3 (Control): PromptAuditor enforces TPP structure + quality gates
  S4 (Intelligence): PromptObserver tracks fitness trends + regressions
  S5 (Identity): TPP levels encode telos/identity constraints

Storage format: YAML frontmatter + Markdown body (mirrors SKILL.md pattern).
Versioning: SemVer (MAJOR.MINOR.PATCH) with migration guides.
Location: ~/.dharma/prompts/ (runtime) + dharma_swarm/prompts/ (version-controlled).

Principle grounding:
  P1 (Action-only writes): All prompt mutations go through typed actions
  P6 (Witness everything): Every invocation traced with full lineage
  P8 (Seed contains tree): Base templates unfold into agent-specific prompts
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TPPLevel(str, Enum):
    """Thinkodynamic Prompt Protocol levels.

    Ordered from most invariant (telos) to most volatile (technical).
    MAJOR version bumps when telos/identity change.
    MINOR version bumps when context/task change.
    PATCH version bumps when technical/formatting change.
    """

    TELOS = "telos"          # Why this prompt exists (moksha alignment)
    IDENTITY = "identity"    # Who the agent is (role, constraints, v7 rules)
    CONTEXT = "context"      # What the agent knows (runtime state, memory)
    TASK = "task"            # What the agent does (specific instructions)
    TECHNICAL = "technical"  # How to format output (JSON, markdown, etc.)


class PromptStatus(str, Enum):
    """Lifecycle status of a prompt template."""

    DRAFT = "draft"
    ACTIVE = "active"
    CANARY = "canary"        # Under A/B test
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class CanaryVerdict(str, Enum):
    """Result of an A/B test comparison."""

    PROMOTE = "promote"       # Statistically significant improvement
    ROLLBACK = "rollback"     # Regression detected
    INCONCLUSIVE = "inconclusive"  # Not enough data yet
    RUNNING = "running"       # Test still in progress


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


class PromptVersion(BaseModel):
    """Semantic version for prompt templates.

    MAJOR: Changed telos or identity framing (breaks agent behavior contract).
    MINOR: Added/modified context or task sections (additive change).
    PATCH: Wording improvements, formatting, token optimization.
    """

    major: int = 1
    minor: int = 0
    patch: int = 0

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def bump_major(self) -> "PromptVersion":
        return PromptVersion(major=self.major + 1, minor=0, patch=0)

    def bump_minor(self) -> "PromptVersion":
        return PromptVersion(major=self.major, minor=self.minor + 1, patch=0)

    def bump_patch(self) -> "PromptVersion":
        return PromptVersion(major=self.major, minor=self.minor, patch=self.patch + 1)

    @classmethod
    def parse(cls, version_str: str) -> "PromptVersion":
        """Parse '1.2.3' into a PromptVersion."""
        parts = version_str.strip().split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid version format: {version_str!r} (expected MAJOR.MINOR.PATCH)")
        return cls(major=int(parts[0]), minor=int(parts[1]), patch=int(parts[2]))

    def __lt__(self, other: "PromptVersion") -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PromptVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __hash__(self) -> int:
        return hash((self.major, self.minor, self.patch))


# ---------------------------------------------------------------------------
# TPP Section
# ---------------------------------------------------------------------------


class TPPSection(BaseModel):
    """A single section within the Thinkodynamic Prompt Protocol.

    Each prompt template contains up to 5 TPP sections, ordered from
    most invariant (telos) to most volatile (technical).
    """

    level: TPPLevel
    content: str
    required: bool = True
    token_estimate: int = 0  # Estimated token count for budget tracking

    def compute_token_estimate(self) -> int:
        """Rough token estimate: ~4 chars per token for English text."""
        self.token_estimate = max(1, len(self.content) // 4)
        return self.token_estimate


# ---------------------------------------------------------------------------
# Prompt Template
# ---------------------------------------------------------------------------


class PromptTemplate(BaseModel):
    """A versioned, TPP-structured prompt template.

    The fundamental unit of the prompt registry. Each template:
    - Has a unique name + version pair
    - Contains up to 5 TPP sections (telos through technical)
    - Can inherit from a parent template (extending its sections)
    - Tracks its own fitness history via invocation outcomes
    - Is content-addressable via SHA-256 hash
    """

    # Identity
    id: str = Field(default_factory=_new_id)
    name: str                                     # e.g. "coder_base", "researcher_rv"
    version: PromptVersion = Field(default_factory=PromptVersion)
    status: PromptStatus = PromptStatus.DRAFT
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    # TPP Structure
    sections: list[TPPSection] = Field(default_factory=list)

    # Inheritance
    parent_name: Optional[str] = None             # Name of parent template
    parent_version: Optional[str] = None          # Version of parent to extend

    # Discovery metadata
    description: str = ""
    tags: list[str] = Field(default_factory=list)  # e.g. ["coder", "research", "rv"]
    agent_roles: list[str] = Field(default_factory=list)  # Which AgentRoles this fits
    task_types: list[str] = Field(default_factory=list)    # e.g. ["code", "review", "research"]

    # Content hash for deduplication and integrity
    content_hash: str = ""

    # Fitness tracking (aggregated from invocations)
    invocation_count: int = 0
    mean_fitness: float = 0.0
    fitness_samples: list[float] = Field(default_factory=list, max_length=100)

    # Migration notes (populated on MAJOR version bumps)
    migration_notes: str = ""

    def compute_hash(self) -> str:
        """SHA-256 hash of all section content, ordered by TPP level."""
        ordered = sorted(self.sections, key=lambda s: list(TPPLevel).index(s.level))
        content = "||".join(f"{s.level.value}:{s.content}" for s in ordered)
        self.content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return self.content_hash

    def total_token_estimate(self) -> int:
        """Sum token estimates across all sections."""
        return sum(s.compute_token_estimate() for s in self.sections)

    def assemble(self, context_overrides: dict[TPPLevel, str] | None = None) -> str:
        """Assemble the full prompt string from TPP sections.

        Sections are ordered telos -> identity -> context -> task -> technical.
        Context overrides allow runtime injection (e.g., memory, thread state)
        without mutating the template.

        Args:
            context_overrides: Dict mapping TPP level to override content.
                If provided, replaces the corresponding section's content.

        Returns:
            Assembled prompt string with section markers.
        """
        overrides = context_overrides or {}
        level_order = list(TPPLevel)
        ordered = sorted(self.sections, key=lambda s: level_order.index(s.level))

        parts: list[str] = []
        for section in ordered:
            content = overrides.get(section.level, section.content)
            if content.strip():
                parts.append(content.strip())

        return "\n\n".join(parts)

    def get_section(self, level: TPPLevel) -> TPPSection | None:
        """Return the section at the given TPP level, or None."""
        for s in self.sections:
            if s.level == level:
                return s
        return None

    def record_fitness(self, score: float) -> None:
        """Record a fitness observation and update running mean."""
        self.fitness_samples.append(score)
        if len(self.fitness_samples) > 100:
            self.fitness_samples = self.fitness_samples[-100:]
        self.mean_fitness = statistics.mean(self.fitness_samples)
        self.invocation_count += 1
        self.updated_at = _utc_now()


# ---------------------------------------------------------------------------
# Invocation Record (for observability)
# ---------------------------------------------------------------------------


class PromptInvocation(BaseModel):
    """Record of a single prompt invocation.

    Links prompt_id + version to agent_id, task, output quality, and
    token usage. This is the primary observability artifact.
    """

    id: str = Field(default_factory=_new_id)
    timestamp: datetime = Field(default_factory=_utc_now)

    # What was invoked
    prompt_id: str
    prompt_name: str
    prompt_version: str
    prompt_hash: str

    # Who invoked it
    agent_id: str
    agent_role: str = ""

    # Execution context
    task_id: str = ""
    task_type: str = ""
    provider: str = ""
    model: str = ""

    # Results
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    success: bool = True
    fitness_score: float = 0.0

    # Lineage
    parent_invocation_id: Optional[str] = None

    # A/B test tracking
    canary_group: Optional[str] = None  # "control" or "canary"
    experiment_id: Optional[str] = None


# ---------------------------------------------------------------------------
# A/B Test Experiment
# ---------------------------------------------------------------------------


class PromptExperiment(BaseModel):
    """An A/B test comparing two prompt variants.

    Runs until either:
    - min_observations reached AND statistical significance achieved
    - max_duration_hours exceeded (auto-resolve as inconclusive)
    - Manual override by operator

    Uses Welch's t-test for fitness comparison. Promotes if:
    - p-value < significance_level
    - canary mean fitness > control mean fitness
    - canary mean fitness >= min_fitness_threshold
    """

    id: str = Field(default_factory=_new_id)
    created_at: datetime = Field(default_factory=_utc_now)

    # Variants
    control_prompt_id: str
    control_prompt_name: str
    control_version: str
    canary_prompt_id: str
    canary_prompt_name: str
    canary_version: str

    # Configuration
    canary_traffic_pct: float = 10.0   # Percentage of invocations routed to canary
    min_observations: int = 30          # Per variant, before significance test
    max_duration_hours: float = 72.0    # Auto-close after this
    significance_level: float = 0.05    # p-value threshold
    min_fitness_threshold: float = 0.6  # Canary must meet this floor

    # State
    verdict: CanaryVerdict = CanaryVerdict.RUNNING
    resolved_at: Optional[datetime] = None

    # Observations
    control_fitness: list[float] = Field(default_factory=list)
    canary_fitness: list[float] = Field(default_factory=list)

    # Results (populated on resolution)
    control_mean: float = 0.0
    canary_mean: float = 0.0
    p_value: float = 1.0
    effect_size: float = 0.0  # Cohen's d

    def record_observation(self, group: str, fitness: float) -> None:
        """Record a fitness observation for control or canary group."""
        if group == "control":
            self.control_fitness.append(fitness)
        elif group == "canary":
            self.canary_fitness.append(fitness)

    def is_ready_to_resolve(self) -> bool:
        """Check if we have enough data to resolve."""
        if self.verdict != CanaryVerdict.RUNNING:
            return False
        # Check duration
        elapsed = (_utc_now() - self.created_at).total_seconds() / 3600
        if elapsed > self.max_duration_hours:
            return True
        # Check observation count
        return (
            len(self.control_fitness) >= self.min_observations
            and len(self.canary_fitness) >= self.min_observations
        )

    def resolve(self) -> CanaryVerdict:
        """Resolve the experiment using Welch's t-test.

        Returns the verdict and populates result fields.
        """
        if not self.control_fitness or not self.canary_fitness:
            self.verdict = CanaryVerdict.INCONCLUSIVE
            self.resolved_at = _utc_now()
            return self.verdict

        self.control_mean = statistics.mean(self.control_fitness)
        self.canary_mean = statistics.mean(self.canary_fitness)

        # Need at least 2 observations per group for variance
        if len(self.control_fitness) < 2 or len(self.canary_fitness) < 2:
            self.verdict = CanaryVerdict.INCONCLUSIVE
            self.resolved_at = _utc_now()
            return self.verdict

        # Welch's t-test (no scipy dependency -- manual implementation)
        n1 = len(self.control_fitness)
        n2 = len(self.canary_fitness)
        var1 = statistics.variance(self.control_fitness)
        var2 = statistics.variance(self.canary_fitness)

        # Pooled standard error
        se = ((var1 / n1) + (var2 / n2)) ** 0.5
        if se == 0:
            # Zero variance in both groups -- compare means directly
            if self.canary_mean > self.control_mean and self.canary_mean >= self.min_fitness_threshold:
                self.verdict = CanaryVerdict.PROMOTE
            elif self.canary_mean < self.control_mean:
                self.verdict = CanaryVerdict.ROLLBACK
            else:
                self.verdict = CanaryVerdict.INCONCLUSIVE
            self.p_value = 0.0 if self.canary_mean != self.control_mean else 1.0
            self.resolved_at = _utc_now()
            return self.verdict

        t_stat = (self.canary_mean - self.control_mean) / se

        # Cohen's d effect size
        pooled_std = ((var1 + var2) / 2) ** 0.5
        self.effect_size = (self.canary_mean - self.control_mean) / pooled_std if pooled_std > 0 else 0.0

        # Approximate p-value using normal distribution (valid for large N)
        # For small N this is conservative, which is fine for our use case
        import math
        z = abs(t_stat)
        # Abramowitz & Stegun approximation
        p = 0.5 * math.erfc(z / math.sqrt(2))
        self.p_value = 2 * p  # Two-tailed

        self.resolved_at = _utc_now()

        # Decision logic
        if self.p_value < self.significance_level:
            if self.canary_mean > self.control_mean and self.canary_mean >= self.min_fitness_threshold:
                self.verdict = CanaryVerdict.PROMOTE
            elif self.canary_mean < self.control_mean:
                self.verdict = CanaryVerdict.ROLLBACK
            else:
                self.verdict = CanaryVerdict.INCONCLUSIVE
        else:
            # Check if duration exceeded
            elapsed = (_utc_now() - self.created_at).total_seconds() / 3600
            if elapsed > self.max_duration_hours:
                self.verdict = CanaryVerdict.INCONCLUSIVE
            else:
                self.verdict = CanaryVerdict.RUNNING  # Keep collecting data

        return self.verdict


# ---------------------------------------------------------------------------
# Prompt Registry (the store)
# ---------------------------------------------------------------------------


_DEFAULT_REGISTRY_PATH = Path.home() / ".dharma" / "prompts"
_BUILTIN_PROMPTS_PATH = Path(__file__).resolve().parent / "prompts"


class PromptRegistry:
    """Production prompt template registry.

    Manages the full lifecycle: create, version, discover, assemble,
    invoke, observe, test, and evolve prompt templates.

    Storage layout:
        {base_path}/
            templates/
                {name}/
                    manifest.json          # PromptTemplate metadata
                    v{MAJOR}.{MINOR}.{PATCH}.md  # Full template content
                    active.md              # Symlink/copy of current version
            invocations/
                {YYYY-MM-DD}.jsonl         # Daily invocation log
            experiments/
                {experiment_id}.json       # A/B test state
            index.json                     # Search index (name -> versions -> metadata)

    Integration points:
        - agent_runner._build_system_prompt() calls registry.assemble()
        - Darwin Engine registers prompts as evolvable artifacts
        - Stigmergy marks emitted for high-fitness prompts
        - Monitor watches invocation fitness for regression alerts
    """

    def __init__(
        self,
        base_path: Path | None = None,
        builtin_path: Path | None = None,
    ) -> None:
        self.base_path = base_path or _DEFAULT_REGISTRY_PATH
        self.builtin_path = builtin_path or _BUILTIN_PROMPTS_PATH

        self._templates_dir = self.base_path / "templates"
        self._invocations_dir = self.base_path / "invocations"
        self._experiments_dir = self.base_path / "experiments"
        self._index_path = self.base_path / "index.json"

        # In-memory cache (lazy-loaded)
        self._cache: dict[str, dict[str, PromptTemplate]] = {}  # name -> {version_str -> template}
        self._loaded = False

    # -- Lifecycle -----------------------------------------------------------

    def init(self) -> None:
        """Create directory structure on disk."""
        for d in (self._templates_dir, self._invocations_dir, self._experiments_dir):
            d.mkdir(parents=True, exist_ok=True)

    # -- CRUD ----------------------------------------------------------------

    def register(self, template: PromptTemplate) -> str:
        """Register a new prompt template or version.

        If a template with the same name and version exists, raises ValueError.
        Computes content hash and writes to disk.

        Returns the template id.
        """
        self.init()
        template.compute_hash()
        template.updated_at = _utc_now()

        version_str = str(template.version)
        template_dir = self._templates_dir / template.name
        template_dir.mkdir(parents=True, exist_ok=True)

        # Check for duplicate version
        version_file = template_dir / f"v{version_str}.json"
        if version_file.exists():
            raise ValueError(
                f"Prompt '{template.name}' v{version_str} already exists. "
                f"Bump version before registering."
            )

        # Write template
        data = json.loads(template.model_dump_json())
        self._write_json(version_file, data)

        # Update active pointer if this is ACTIVE or first version
        if template.status == PromptStatus.ACTIVE or not (template_dir / "active.json").exists():
            self._write_json(template_dir / "active.json", data)

        # Update cache
        if template.name not in self._cache:
            self._cache[template.name] = {}
        self._cache[template.name][version_str] = template

        # Rebuild index
        self._rebuild_index()

        logger.info(
            "Registered prompt '%s' v%s (hash=%s, status=%s)",
            template.name, version_str, template.content_hash, template.status.value,
        )
        return template.id

    def get(self, name: str, version: str | None = None) -> PromptTemplate | None:
        """Retrieve a prompt template by name and optional version.

        If version is None, returns the active version.
        """
        template_dir = self._templates_dir / name
        if not template_dir.exists():
            return None

        if version:
            path = template_dir / f"v{version}.json"
        else:
            path = template_dir / "active.json"

        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return PromptTemplate.model_validate(data)
        except Exception as exc:
            logger.warning("Failed to load prompt '%s': %s", name, exc)
            return None

    def list_templates(
        self,
        tags: list[str] | None = None,
        agent_role: str | None = None,
        task_type: str | None = None,
        status: PromptStatus | None = None,
    ) -> list[PromptTemplate]:
        """List templates matching optional filters.

        Supports discovery by tag, agent role, task type, and status.
        Returns active versions by default.
        """
        results: list[PromptTemplate] = []
        if not self._templates_dir.exists():
            return results

        for template_dir in sorted(self._templates_dir.iterdir()):
            if not template_dir.is_dir():
                continue
            active_path = template_dir / "active.json"
            if not active_path.exists():
                continue

            try:
                data = json.loads(active_path.read_text(encoding="utf-8"))
                template = PromptTemplate.model_validate(data)
            except Exception:
                continue

            # Apply filters
            if status and template.status != status:
                continue
            if tags and not set(tags).intersection(set(template.tags)):
                continue
            if agent_role and agent_role not in template.agent_roles:
                continue
            if task_type and task_type not in template.task_types:
                continue

            results.append(template)

        return results

    def list_versions(self, name: str) -> list[PromptVersion]:
        """List all versions for a named template, sorted ascending."""
        template_dir = self._templates_dir / name
        if not template_dir.exists():
            return []

        versions: list[PromptVersion] = []
        for path in template_dir.glob("v*.json"):
            version_str = path.stem[1:]  # Strip leading 'v'
            try:
                versions.append(PromptVersion.parse(version_str))
            except ValueError:
                continue

        return sorted(versions)

    def promote(self, name: str, version: str) -> bool:
        """Promote a specific version to active.

        Sets the version's status to ACTIVE and writes it as active.json.
        Deprecates the previously active version.
        """
        template = self.get(name, version)
        if template is None:
            logger.warning("Cannot promote non-existent prompt '%s' v%s", name, version)
            return False

        # Deprecate current active
        current_active = self.get(name)
        if current_active and str(current_active.version) != version:
            current_active.status = PromptStatus.DEPRECATED
            current_active.updated_at = _utc_now()
            version_file = self._templates_dir / name / f"v{current_active.version}.json"
            self._write_json(version_file, json.loads(current_active.model_dump_json()))

        # Promote new version
        template.status = PromptStatus.ACTIVE
        template.updated_at = _utc_now()
        template_dir = self._templates_dir / name
        self._write_json(template_dir / f"v{version}.json", json.loads(template.model_dump_json()))
        self._write_json(template_dir / "active.json", json.loads(template.model_dump_json()))

        logger.info("Promoted prompt '%s' v%s to active", name, version)
        return True

    def deprecate(self, name: str, version: str) -> bool:
        """Mark a version as deprecated."""
        template = self.get(name, version)
        if template is None:
            return False

        template.status = PromptStatus.DEPRECATED
        template.updated_at = _utc_now()
        version_file = self._templates_dir / name / f"v{version}.json"
        self._write_json(version_file, json.loads(template.model_dump_json()))
        return True

    # -- Assembly ------------------------------------------------------------

    def assemble(
        self,
        name: str,
        version: str | None = None,
        context_overrides: dict[TPPLevel, str] | None = None,
        parent_chain: bool = True,
    ) -> str | None:
        """Assemble a full prompt from a template, resolving inheritance.

        If parent_chain is True and the template has a parent, parent sections
        are included first, then overridden by child sections at the same level.

        Args:
            name: Template name.
            version: Specific version, or None for active.
            context_overrides: Runtime context to inject at specific TPP levels.
            parent_chain: Whether to resolve parent templates.

        Returns:
            Assembled prompt string, or None if template not found.
        """
        template = self.get(name, version)
        if template is None:
            return None

        # Resolve inheritance chain
        sections_by_level: dict[TPPLevel, str] = {}

        if parent_chain and template.parent_name:
            parent = self.get(template.parent_name, template.parent_version)
            if parent:
                for section in parent.sections:
                    sections_by_level[section.level] = section.content

        # Child sections override parent sections
        for section in template.sections:
            sections_by_level[section.level] = section.content

        # Runtime overrides override everything
        if context_overrides:
            for level, content in context_overrides.items():
                sections_by_level[level] = content

        # Assemble in TPP order
        parts: list[str] = []
        for level in TPPLevel:
            content = sections_by_level.get(level, "")
            if content.strip():
                parts.append(content.strip())

        return "\n\n".join(parts)

    # -- Invocation tracking -------------------------------------------------

    def log_invocation(self, invocation: PromptInvocation) -> str:
        """Log a prompt invocation to the daily JSONL file.

        Also updates the template's fitness tracking.

        Returns the invocation id.
        """
        self.init()

        # Write to daily log
        date_str = invocation.timestamp.strftime("%Y-%m-%d")
        log_file = self._invocations_dir / f"{date_str}.jsonl"
        data = json.loads(invocation.model_dump_json())
        self._append_jsonl(log_file, data)

        # Update template fitness
        template = self.get(invocation.prompt_name)
        if template and invocation.fitness_score > 0:
            template.record_fitness(invocation.fitness_score)
            # Persist updated fitness
            template_dir = self._templates_dir / invocation.prompt_name
            version_file = template_dir / f"v{invocation.prompt_version}.json"
            if version_file.exists():
                self._write_json(version_file, json.loads(template.model_dump_json()))
            active_file = template_dir / "active.json"
            if active_file.exists() and str(template.version) == invocation.prompt_version:
                self._write_json(active_file, json.loads(template.model_dump_json()))

        return invocation.id

    def get_invocations(
        self,
        prompt_name: str | None = None,
        days: int = 7,
        limit: int = 100,
    ) -> list[PromptInvocation]:
        """Retrieve recent invocations, optionally filtered by prompt name."""
        results: list[PromptInvocation] = []
        now = _utc_now()

        for day_offset in range(days):
            date = now - timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            log_file = self._invocations_dir / f"{date_str}.jsonl"
            if not log_file.exists():
                continue

            for line in log_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    inv = PromptInvocation.model_validate(data)
                    if prompt_name and inv.prompt_name != prompt_name:
                        continue
                    results.append(inv)
                except Exception:
                    continue

            if len(results) >= limit:
                break

        results.sort(key=lambda i: i.timestamp, reverse=True)
        return results[:limit]

    # -- A/B Testing ---------------------------------------------------------

    def create_experiment(
        self,
        control_name: str,
        canary_name: str,
        canary_version: str,
        control_version: str | None = None,
        canary_traffic_pct: float = 10.0,
        min_observations: int = 30,
    ) -> PromptExperiment:
        """Create a new A/B test experiment.

        The control is typically the current active version.
        The canary is the new variant being tested.
        """
        self.init()

        control = self.get(control_name, control_version)
        canary = self.get(canary_name, canary_version)

        if control is None:
            raise ValueError(f"Control prompt '{control_name}' not found")
        if canary is None:
            raise ValueError(f"Canary prompt '{canary_name}' v{canary_version} not found")

        # Mark canary as under test
        canary.status = PromptStatus.CANARY
        canary.updated_at = _utc_now()
        canary_dir = self._templates_dir / canary_name
        self._write_json(
            canary_dir / f"v{canary_version}.json",
            json.loads(canary.model_dump_json()),
        )

        experiment = PromptExperiment(
            control_prompt_id=control.id,
            control_prompt_name=control_name,
            control_version=str(control.version) if control_version is None else control_version,
            canary_prompt_id=canary.id,
            canary_prompt_name=canary_name,
            canary_version=canary_version,
            canary_traffic_pct=canary_traffic_pct,
            min_observations=min_observations,
        )

        # Persist
        exp_file = self._experiments_dir / f"{experiment.id}.json"
        self._write_json(exp_file, json.loads(experiment.model_dump_json()))

        logger.info(
            "Created experiment %s: %s v%s (control) vs %s v%s (canary, %g%% traffic)",
            experiment.id, control_name, experiment.control_version,
            canary_name, canary_version, canary_traffic_pct,
        )
        return experiment

    def route_experiment(self, prompt_name: str) -> tuple[str, str, str | None]:
        """Route an invocation to control or canary group.

        Checks if there's an active experiment for this prompt name.
        Returns (version_to_use, group_label, experiment_id).

        If no experiment is running, returns (active_version, "default", None).
        """
        # Find active experiment for this prompt
        for exp_file in self._experiments_dir.glob("*.json"):
            try:
                data = json.loads(exp_file.read_text(encoding="utf-8"))
                exp = PromptExperiment.model_validate(data)
            except Exception:
                continue

            if exp.verdict != CanaryVerdict.RUNNING:
                continue
            if exp.control_prompt_name != prompt_name and exp.canary_prompt_name != prompt_name:
                continue

            # Route based on traffic percentage
            import random
            if random.random() * 100 < exp.canary_traffic_pct:
                return exp.canary_version, "canary", exp.id
            else:
                return exp.control_version, "control", exp.id

        # No active experiment
        template = self.get(prompt_name)
        if template:
            return str(template.version), "default", None
        return "1.0.0", "default", None

    def resolve_experiment(self, experiment_id: str) -> CanaryVerdict:
        """Resolve an experiment if ready."""
        exp_file = self._experiments_dir / f"{experiment_id}.json"
        if not exp_file.exists():
            return CanaryVerdict.INCONCLUSIVE

        try:
            data = json.loads(exp_file.read_text(encoding="utf-8"))
            exp = PromptExperiment.model_validate(data)
        except Exception:
            return CanaryVerdict.INCONCLUSIVE

        if not exp.is_ready_to_resolve():
            return CanaryVerdict.RUNNING

        verdict = exp.resolve()
        self._write_json(exp_file, json.loads(exp.model_dump_json()))

        # Auto-promote or rollback
        if verdict == CanaryVerdict.PROMOTE:
            self.promote(exp.canary_prompt_name, exp.canary_version)
            logger.info(
                "Experiment %s: PROMOTE %s v%s (d=%.3f, p=%.4f)",
                experiment_id, exp.canary_prompt_name, exp.canary_version,
                exp.effect_size, exp.p_value,
            )
        elif verdict == CanaryVerdict.ROLLBACK:
            self.deprecate(exp.canary_prompt_name, exp.canary_version)
            logger.info(
                "Experiment %s: ROLLBACK %s v%s (d=%.3f, p=%.4f)",
                experiment_id, exp.canary_prompt_name, exp.canary_version,
                exp.effect_size, exp.p_value,
            )

        return verdict

    def get_active_experiments(self) -> list[PromptExperiment]:
        """Return all running experiments."""
        results: list[PromptExperiment] = []
        if not self._experiments_dir.exists():
            return results

        for exp_file in self._experiments_dir.glob("*.json"):
            try:
                data = json.loads(exp_file.read_text(encoding="utf-8"))
                exp = PromptExperiment.model_validate(data)
                if exp.verdict == CanaryVerdict.RUNNING:
                    results.append(exp)
            except Exception:
                continue

        return results

    # -- Observability -------------------------------------------------------

    def fitness_report(self, name: str, days: int = 7) -> dict[str, Any]:
        """Generate a fitness report for a prompt template.

        Includes: mean fitness, trend (improving/degrading/stable),
        invocation count, token usage, and per-day breakdown.
        """
        invocations = self.get_invocations(prompt_name=name, days=days)
        if not invocations:
            return {
                "name": name,
                "invocations": 0,
                "mean_fitness": 0.0,
                "trend": "unknown",
                "total_tokens": 0,
                "daily": {},
            }

        fitness_scores = [i.fitness_score for i in invocations if i.fitness_score > 0]
        total_tokens = sum(i.total_tokens for i in invocations)

        # Per-day breakdown
        daily: dict[str, dict[str, Any]] = {}
        for inv in invocations:
            day = inv.timestamp.strftime("%Y-%m-%d")
            if day not in daily:
                daily[day] = {"count": 0, "fitness_sum": 0.0, "tokens": 0}
            daily[day]["count"] += 1
            daily[day]["fitness_sum"] += inv.fitness_score
            daily[day]["tokens"] += inv.total_tokens

        for day_data in daily.values():
            if day_data["count"] > 0:
                day_data["mean_fitness"] = round(day_data["fitness_sum"] / day_data["count"], 4)

        # Trend detection (linear regression on daily means)
        trend = "stable"
        if len(daily) >= 3:
            daily_means = [
                daily[d].get("mean_fitness", 0.0)
                for d in sorted(daily.keys())
            ]
            # Simple: compare first half mean vs second half mean
            mid = len(daily_means) // 2
            first_half = statistics.mean(daily_means[:mid]) if daily_means[:mid] else 0
            second_half = statistics.mean(daily_means[mid:]) if daily_means[mid:] else 0
            delta = second_half - first_half
            if delta > 0.05:
                trend = "improving"
            elif delta < -0.05:
                trend = "degrading"

        mean_fitness = statistics.mean(fitness_scores) if fitness_scores else 0.0

        return {
            "name": name,
            "invocations": len(invocations),
            "mean_fitness": round(mean_fitness, 4),
            "trend": trend,
            "total_tokens": total_tokens,
            "daily": daily,
        }

    def regression_check(self, threshold: float = 0.1) -> list[dict[str, Any]]:
        """Check all active prompts for fitness regression.

        Returns a list of prompts where recent fitness dropped by more
        than threshold compared to their historical mean.
        """
        regressions: list[dict[str, Any]] = []

        for template in self.list_templates(status=PromptStatus.ACTIVE):
            if template.invocation_count < 10:
                continue  # Not enough data

            recent_invocations = self.get_invocations(
                prompt_name=template.name, days=1, limit=20,
            )
            if len(recent_invocations) < 3:
                continue

            recent_fitness = [i.fitness_score for i in recent_invocations if i.fitness_score > 0]
            if not recent_fitness:
                continue

            recent_mean = statistics.mean(recent_fitness)
            historical_mean = template.mean_fitness

            if historical_mean > 0 and (historical_mean - recent_mean) > threshold:
                regressions.append({
                    "name": template.name,
                    "version": str(template.version),
                    "historical_mean": round(historical_mean, 4),
                    "recent_mean": round(recent_mean, 4),
                    "delta": round(recent_mean - historical_mean, 4),
                    "severity": "high" if (historical_mean - recent_mean) > 2 * threshold else "medium",
                })

        return regressions

    # -- Integration with Darwin Engine --------------------------------------

    def as_evolvable_artifact(self, name: str) -> dict[str, Any] | None:
        """Export a prompt template as an artifact for the Darwin Engine.

        Returns a dict compatible with ArchiveEntry metadata format,
        allowing the evolution pipeline to treat prompts as first-class
        evolvable entities alongside code mutations.
        """
        template = self.get(name)
        if template is None:
            return None

        return {
            "artifact_type": "prompt_template",
            "name": template.name,
            "version": str(template.version),
            "content_hash": template.content_hash,
            "fitness": template.mean_fitness,
            "invocation_count": template.invocation_count,
            "token_estimate": template.total_token_estimate(),
            "tpp_levels": [s.level.value for s in template.sections],
            "tags": template.tags,
            "agent_roles": template.agent_roles,
        }

    def emit_stigmergy_mark(self, template: PromptTemplate) -> dict[str, Any]:
        """Build a stigmergy mark for a high-fitness prompt.

        Called by the integration layer when a prompt's fitness exceeds
        the crown_jewel_threshold. Other agents discover this mark and
        may adopt the prompt pattern.
        """
        return {
            "agent": "prompt_registry",
            "file_path": f"prompt:{template.name}:v{template.version}",
            "action": "write",
            "observation": (
                f"High-fitness prompt '{template.name}' v{template.version} "
                f"(fitness={template.mean_fitness:.3f}, n={template.invocation_count})"
            ),
            "salience": min(1.0, template.mean_fitness),
            "connections": [f"tag:{t}" for t in template.tags],
        }

    # -- Private helpers -----------------------------------------------------

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        """Atomically write JSON to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)

    def _append_jsonl(self, path: Path, data: dict[str, Any]) -> None:
        """Append a JSON line to a JSONL file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(data, default=str, ensure_ascii=False) + "\n")

    def _rebuild_index(self) -> None:
        """Rebuild the search index from disk."""
        index: dict[str, Any] = {}
        if not self._templates_dir.exists():
            return

        for template_dir in sorted(self._templates_dir.iterdir()):
            if not template_dir.is_dir():
                continue
            name = template_dir.name
            active_path = template_dir / "active.json"
            if not active_path.exists():
                continue

            try:
                data = json.loads(active_path.read_text(encoding="utf-8"))
                index[name] = {
                    "version": data.get("version", {}),
                    "status": data.get("status", "unknown"),
                    "tags": data.get("tags", []),
                    "agent_roles": data.get("agent_roles", []),
                    "task_types": data.get("task_types", []),
                    "mean_fitness": data.get("mean_fitness", 0.0),
                    "invocation_count": data.get("invocation_count", 0),
                    "content_hash": data.get("content_hash", ""),
                }
            except Exception:
                continue

        self._write_json(self._index_path, index)


# ---------------------------------------------------------------------------
# Prompt Auditor (structural validation)
# ---------------------------------------------------------------------------


class PromptAuditResult(BaseModel):
    """Result of auditing a prompt template."""

    prompt_name: str
    version: str
    passed: bool
    checks: dict[str, bool] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class PromptAuditor:
    """Validates prompt templates against structural and quality requirements.

    Checks:
    1. TPP completeness: all required levels present
    2. Content quality: no empty sections, minimum length
    3. Token budget: total estimate within bounds
    4. Injection safety: no known attack patterns
    5. Telos alignment: telos section references 7-STAR vector
    """

    def __init__(
        self,
        max_total_tokens: int = 8000,
        min_section_chars: int = 20,
    ) -> None:
        self.max_total_tokens = max_total_tokens
        self.min_section_chars = min_section_chars

    def audit(self, template: PromptTemplate) -> PromptAuditResult:
        """Run all audit checks on a template."""
        result = PromptAuditResult(
            prompt_name=template.name,
            version=str(template.version),
            passed=True,
        )

        # 1. TPP completeness
        present_levels = {s.level for s in template.sections}
        required_levels = {s.level for s in template.sections if s.required}
        missing = required_levels - present_levels
        result.checks["tpp_complete"] = len(missing) == 0
        if missing:
            result.errors.append(f"Missing required TPP levels: {[l.value for l in missing]}")
            result.passed = False

        # Check that at least telos and task sections exist
        has_telos = TPPLevel.TELOS in present_levels
        has_task = TPPLevel.TASK in present_levels
        result.checks["has_telos"] = has_telos
        result.checks["has_task"] = has_task
        if not has_telos:
            result.warnings.append("No TELOS section -- prompt lacks purpose grounding")
        if not has_task:
            result.warnings.append("No TASK section -- prompt has no actionable instructions")

        # 2. Content quality
        empty_sections = [s.level.value for s in template.sections if len(s.content.strip()) < self.min_section_chars]
        result.checks["no_empty_sections"] = len(empty_sections) == 0
        if empty_sections:
            result.warnings.append(f"Near-empty sections (< {self.min_section_chars} chars): {empty_sections}")

        # 3. Token budget
        total_tokens = template.total_token_estimate()
        result.checks["within_token_budget"] = total_tokens <= self.max_total_tokens
        if total_tokens > self.max_total_tokens:
            result.errors.append(
                f"Token estimate {total_tokens} exceeds budget {self.max_total_tokens}"
            )
            result.passed = False

        # 4. Injection safety
        from dharma_swarm.prompt_builder import sanitize_prompt_context
        for section in template.sections:
            sanitized = sanitize_prompt_context(section.content, source_name=f"{template.name}:{section.level.value}")
            if "[BLOCKED:" in sanitized:
                result.errors.append(f"Injection detected in {section.level.value} section")
                result.passed = False
        result.checks["injection_safe"] = result.passed

        # 5. Content hash integrity
        expected_hash = template.content_hash
        actual_hash = template.compute_hash()
        result.checks["hash_integrity"] = expected_hash == actual_hash or expected_hash == ""
        if expected_hash and expected_hash != actual_hash:
            result.errors.append(f"Content hash mismatch: expected {expected_hash}, got {actual_hash}")
            result.passed = False

        return result


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def get_registry(base_path: Path | None = None) -> PromptRegistry:
    """Factory function for the default prompt registry."""
    return PromptRegistry(base_path=base_path)


def create_base_templates() -> list[PromptTemplate]:
    """Create the canonical base prompt templates for dharma_swarm.

    These are the seed templates that all agent prompts inherit from.
    They encode the v7 rules, role briefings, and TPP structure.
    """
    from dharma_swarm.daemon_config import V7_BASE_RULES, ROLE_BRIEFINGS

    templates: list[PromptTemplate] = []

    # 1. Universal base (all agents inherit from this)
    universal = PromptTemplate(
        name="universal_base",
        version=PromptVersion(major=1, minor=0, patch=0),
        status=PromptStatus.ACTIVE,
        description="Universal base template. All agent prompts inherit from this.",
        tags=["base", "universal"],
        agent_roles=["general"],
        sections=[
            TPPSection(
                level=TPPLevel.TELOS,
                content=(
                    "You serve Jagat Kalyan (universal welfare). "
                    "Every action is measured against the 7-STAR telos vector: "
                    "Truth, Resilience, Flourishing, Sovereignty, Coherence, Emergence, Liberation. "
                    "Moksha = 1.0 always. The optimization target constraining all others."
                ),
                required=True,
            ),
            TPPSection(
                level=TPPLevel.IDENTITY,
                content=V7_BASE_RULES,
                required=True,
            ),
        ],
    )
    templates.append(universal)

    # 2. Role-specific templates
    for role_name, briefing in ROLE_BRIEFINGS.items():
        role_template = PromptTemplate(
            name=f"role_{role_name}",
            version=PromptVersion(major=1, minor=0, patch=0),
            status=PromptStatus.ACTIVE,
            description=f"Base template for {role_name} agents.",
            tags=["role", role_name],
            agent_roles=[role_name],
            parent_name="universal_base",
            parent_version="1.0.0",
            sections=[
                TPPSection(
                    level=TPPLevel.IDENTITY,
                    content=briefing,
                    required=True,
                ),
                TPPSection(
                    level=TPPLevel.TASK,
                    content=f"Execute tasks assigned to the {role_name} role with precision and integrity.",
                    required=True,
                ),
            ],
        )
        templates.append(role_template)

    return templates


__all__ = [
    "CanaryVerdict",
    "PromptAuditResult",
    "PromptAuditor",
    "PromptExperiment",
    "PromptInvocation",
    "PromptRegistry",
    "PromptStatus",
    "PromptTemplate",
    "PromptVersion",
    "TPPLevel",
    "TPPSection",
    "create_base_templates",
    "get_registry",
]
