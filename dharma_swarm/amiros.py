"""AMIROS — Autonomous Multi-agent Intelligence Research Operating System.

The research control plane. Five JSON registries + a harvester that
closes the loop between experiments, claims, artifacts, and the ontology.

Designed from the AMIROS research spec (March 2026):
  - Experiment Registry: what was tried
  - Claim Registry: what was concluded  
  - Artifact Registry: what was produced
  - Config Registry: what parameters were used
  - Harvest Log: what was extracted from agent outputs

The registries are simple JSON files — lighter than W&B or MLflow,
but capturing the same provenance chain:
  experiment → config → artifact → claim → paper number

Ground: Ashby (recorded variety), Bateson (pattern requires recording),
        Dada Bhagwan (witness everything — Axiom P6).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Registry Models
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class Experiment(BaseModel):
    """A research experiment — the atomic unit of empirical work."""

    id: str = Field(default_factory=_new_id)
    name: str
    hypothesis: str
    lane: str = ""  # "rv_metric", "triton_kernels", "dharma_swarm", "agni"
    config_id: str = ""  # links to ConfigEntry
    status: str = "proposed"  # "proposed", "running", "completed", "failed", "abandoned"
    agent_id: str = ""  # which agent ran it
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_summary: str = ""
    artifact_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class Claim(BaseModel):
    """A research claim — a statement derived from experiment results.

    Claims have a lifecycle: proposed → supported → validated → challenged → retired.
    Each claim must cite its evidence (experiments + artifacts).
    """

    id: str = Field(default_factory=_new_id)
    statement: str
    confidence: float = 0.5  # 0.0 to 1.0
    status: str = "proposed"  # "proposed", "supported", "validated", "challenged", "retired"
    evidence_experiment_ids: list[str] = Field(default_factory=list)
    evidence_artifact_ids: list[str] = Field(default_factory=list)
    counterevidence: list[str] = Field(default_factory=list)
    domain: str = ""  # "rv_metric", "triton", "architecture"
    cited_in: list[str] = Field(default_factory=list)  # paper sections
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    def challenge(self, reason: str) -> None:
        self.counterevidence.append(reason)
        if len(self.counterevidence) >= 2:
            self.status = "challenged"
        self.updated_at = _utc_now()

    def validate(self) -> None:
        self.status = "validated"
        self.updated_at = _utc_now()


class Artifact(BaseModel):
    """A research artifact — a file, dataset, or output produced by an experiment."""

    id: str = Field(default_factory=_new_id)
    name: str
    artifact_type: str  # "data", "code", "figure", "document", "model", "log"
    path: str  # relative path in workspace
    experiment_id: str = ""
    description: str = ""
    size_bytes: int = 0
    checksum: str = ""  # SHA-256 for integrity
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)


class ConfigEntry(BaseModel):
    """An experiment configuration — frozen parameters for reproducibility."""

    id: str = Field(default_factory=_new_id)
    name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    model: str = ""  # which LLM/model was used
    provider: str = ""  # which provider
    gpu: str = ""  # which GPU, if applicable
    frozen: bool = False  # once experiment starts, config is frozen
    created_at: datetime = Field(default_factory=_utc_now)

    def freeze(self) -> None:
        self.frozen = True


class HarvestEntry(BaseModel):
    """A harvest — extracted signal from agent output or conversation.

    The harvester reads agent outputs and extracts:
    - Claims worth tracking
    - Artifacts worth indexing
    - Patterns worth investigating
    """

    id: str = Field(default_factory=_new_id)
    source: str  # "agent_output", "conversation", "stigmergy", "evolution"
    agent_id: str = ""
    raw_text: str = ""
    extracted_claims: list[str] = Field(default_factory=list)
    extracted_artifacts: list[str] = Field(default_factory=list)
    extracted_patterns: list[str] = Field(default_factory=list)
    processed: bool = False
    created_at: datetime = Field(default_factory=_utc_now)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Registry Store
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class AMIROSRegistry:
    """The five AMIROS registries — research provenance chain.

    All registries are backed by JSON files in ~/.dharma/amiros/.
    Simple, grep-able, git-versionable.

    Usage:
        amiros = AMIROSRegistry()

        # Register an experiment
        config = amiros.register_config("rv_sweep", {"models": [...], "layers": "all"})
        exp = amiros.register_experiment("R_V across 8 models", "V > O > K > Q hierarchy holds", lane="rv_metric", config_id=config.id)

        # Record results
        artifact = amiros.register_artifact("rv_results.json", "data", exp.id)
        claim = amiros.register_claim("Universal V > O > K > Q hierarchy", evidence_experiments=[exp.id])

        # Harvest agent output
        amiros.harvest("agent_output", agent_id="researcher_01", raw_text="...", claims=["..."])
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._base = (state_dir or Path.home() / ".dharma") / "amiros"
        self._base.mkdir(parents=True, exist_ok=True)

        # v0.6.1: explicit persist path (alias to _base for API compatibility)
        if state_dir is not None:
            self._persist_path: Path = state_dir / "amiros"
        else:
            self._persist_path = self._base

        self._experiments_path = self._base / "experiments.jsonl"
        self._claims_path = self._base / "claims.jsonl"
        self._artifacts_path = self._base / "artifacts.jsonl"
        self._configs_path = self._base / "configs.jsonl"
        self._harvests_path = self._base / "harvests.jsonl"

        # In-memory indexes for fast lookup
        self._experiments: dict[str, Experiment] = {}
        self._claims: dict[str, Claim] = {}
        self._artifacts: dict[str, Artifact] = {}
        self._configs: dict[str, ConfigEntry] = {}
        self._harvests: list[HarvestEntry] = []

        # Load existing
        self._load_all()

    # ── Registration ──────────────────────────────────────────────

    def register_experiment(
        self,
        name: str,
        hypothesis: str,
        lane: str = "",
        config_id: str = "",
        agent_id: str = "",
        tags: list[str] | None = None,
    ) -> Experiment:
        """Register a new experiment."""
        exp = Experiment(
            name=name,
            hypothesis=hypothesis,
            lane=lane,
            config_id=config_id,
            agent_id=agent_id,
            tags=tags or [],
        )
        self._experiments[exp.id] = exp
        self._append(self._experiments_path, exp)
        self._save()
        logger.info("AMIROS: Registered experiment %s: %s", exp.id[:8], name)
        return exp

    def register_claim(
        self,
        statement: str,
        confidence: float = 0.5,
        domain: str = "",
        evidence_experiments: list[str] | None = None,
        evidence_artifacts: list[str] | None = None,
    ) -> Claim:
        """Register a new claim."""
        claim = Claim(
            statement=statement,
            confidence=confidence,
            domain=domain,
            evidence_experiment_ids=evidence_experiments or [],
            evidence_artifact_ids=evidence_artifacts or [],
        )
        self._claims[claim.id] = claim
        self._append(self._claims_path, claim)

        # Link claim back to experiments
        for exp_id in claim.evidence_experiment_ids:
            if exp_id in self._experiments:
                self._experiments[exp_id].claim_ids.append(claim.id)

        self._save()
        logger.info("AMIROS: Registered claim %s: %s", claim.id[:8], statement[:60])
        return claim

    def register_artifact(
        self,
        name: str,
        artifact_type: str,
        experiment_id: str = "",
        path: str = "",
        description: str = "",
        tags: list[str] | None = None,
    ) -> Artifact:
        """Register a new artifact."""
        artifact = Artifact(
            name=name,
            artifact_type=artifact_type,
            experiment_id=experiment_id,
            path=path,
            description=description,
            tags=tags or [],
        )
        self._artifacts[artifact.id] = artifact
        self._append(self._artifacts_path, artifact)

        # Link artifact back to experiment
        if experiment_id and experiment_id in self._experiments:
            self._experiments[experiment_id].artifact_ids.append(artifact.id)

        return artifact

    def register_config(
        self,
        name: str,
        parameters: dict[str, Any],
        model: str = "",
        provider: str = "",
        gpu: str = "",
    ) -> ConfigEntry:
        """Register an experiment configuration."""
        config = ConfigEntry(
            name=name,
            parameters=parameters,
            model=model,
            provider=provider,
            gpu=gpu,
        )
        self._configs[config.id] = config
        self._append(self._configs_path, config)
        return config

    def harvest(
        self,
        source: str,
        agent_id: str = "",
        raw_text: str = "",
        claims: list[str] | None = None,
        artifacts: list[str] | None = None,
        patterns: list[str] | None = None,
    ) -> HarvestEntry:
        """Record a harvest from agent output."""
        entry = HarvestEntry(
            source=source,
            agent_id=agent_id,
            raw_text=raw_text[:2000],  # cap raw text
            extracted_claims=claims or [],
            extracted_artifacts=artifacts or [],
            extracted_patterns=patterns or [],
        )
        self._harvests.append(entry)
        self._append(self._harvests_path, entry)
        self._save()
        return entry

    # ── Lifecycle updates ─────────────────────────────────────────

    def start_experiment(self, exp_id: str) -> Experiment | None:
        exp = self._experiments.get(exp_id)
        if exp:
            exp.status = "running"
            exp.started_at = _utc_now()
            if exp.config_id and exp.config_id in self._configs:
                self._configs[exp.config_id].freeze()
        return exp

    def complete_experiment(
        self, exp_id: str, result_summary: str, success: bool = True,
    ) -> Experiment | None:
        exp = self._experiments.get(exp_id)
        if exp:
            exp.status = "completed" if success else "failed"
            exp.completed_at = _utc_now()
            exp.result_summary = result_summary
        return exp

    def challenge_claim(self, claim_id: str, reason: str) -> Claim | None:
        claim = self._claims.get(claim_id)
        if claim:
            claim.challenge(reason)
        return claim

    def validate_claim(self, claim_id: str) -> Claim | None:
        claim = self._claims.get(claim_id)
        if claim:
            claim.validate()
        return claim

    # ── Queries ───────────────────────────────────────────────────

    def get_experiment(self, exp_id: str) -> Experiment | None:
        return self._experiments.get(exp_id)

    def get_claim(self, claim_id: str) -> Claim | None:
        return self._claims.get(claim_id)

    def experiments_by_lane(self, lane: str) -> list[Experiment]:
        return [e for e in self._experiments.values() if e.lane == lane]

    def claims_by_domain(self, domain: str) -> list[Claim]:
        return [c for c in self._claims.values() if c.domain == domain]

    def active_claims(self) -> list[Claim]:
        return [c for c in self._claims.values()
                if c.status in ("proposed", "supported", "validated")]

    def unprocessed_harvests(self) -> list[HarvestEntry]:
        return [h for h in self._harvests if not h.processed]

    def provenance_chain(self, claim_id: str) -> dict[str, Any]:
        """Trace a claim back to its full provenance chain.

        Returns: claim → experiments → configs → artifacts
        """
        claim = self._claims.get(claim_id)
        if not claim:
            return {"error": f"Claim {claim_id} not found"}

        experiments = []
        for exp_id in claim.evidence_experiment_ids:
            exp = self._experiments.get(exp_id)
            if exp:
                config = self._configs.get(exp.config_id) if exp.config_id else None
                artifacts = [self._artifacts[a] for a in exp.artifact_ids
                           if a in self._artifacts]
                experiments.append({
                    "experiment": exp.model_dump(),
                    "config": config.model_dump() if config else None,
                    "artifacts": [a.model_dump() for a in artifacts],
                })

        return {
            "claim": claim.model_dump(),
            "provenance": experiments,
        }

    # ── Stats ─────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        return {
            "experiments": {
                "total": len(self._experiments),
                "by_status": self._count_by(self._experiments.values(), "status"),
                "by_lane": self._count_by(self._experiments.values(), "lane"),
            },
            "claims": {
                "total": len(self._claims),
                "by_status": self._count_by(self._claims.values(), "status"),
            },
            "artifacts": {
                "total": len(self._artifacts),
                "by_type": self._count_by(self._artifacts.values(), "artifact_type"),
            },
            "configs": len(self._configs),
            "harvests": {
                "total": len(self._harvests),
                "unprocessed": len(self.unprocessed_harvests()),
            },
        }

    @staticmethod
    def _count_by(items: Any, field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            val = getattr(item, field, "") or "unknown"
            counts[val] = counts.get(val, 0) + 1
        return counts

    # ── Persistence ───────────────────────────────────────────────

    def _append(self, path: Path, model: BaseModel) -> None:
        with open(path, "a") as fh:
            fh.write(model.model_dump_json() + "\n")

    def _load_all(self) -> None:
        """Load all registries from disk."""
        self._experiments = self._load_registry(self._experiments_path, Experiment)
        self._claims = self._load_registry(self._claims_path, Claim)
        self._artifacts = self._load_registry(self._artifacts_path, Artifact)
        self._configs = self._load_registry(self._configs_path, ConfigEntry)
        self._harvests = self._load_list(self._harvests_path, HarvestEntry)

    def _load_registry(self, path: Path, model_cls: type) -> dict[str, Any]:
        result = {}
        if not path.exists():
            return result
        try:
            for line in path.read_text().strip().split("\n"):
                if line.strip():
                    obj = model_cls.model_validate_json(line)
                    result[obj.id] = obj
        except Exception as exc:
            logger.warning("Failed to load %s: %s", path.name, exc)
        return result

    def _load_list(self, path: Path, model_cls: type) -> list[Any]:
        result = []
        if not path.exists():
            return result
        try:
            for line in path.read_text().strip().split("\n"):
                if line.strip():
                    result.append(model_cls.model_validate_json(line))
        except Exception as exc:
            logger.warning("Failed to load %s: %s", path.name, exc)
        return result

    def _save(self) -> None:
        """Write a JSON summary snapshot for quick persistence (v0.6.1)."""
        try:
            summary = {
                "total_experiments": len(self._experiments),
                "total_claims": len(self._claims),
                "total_artifacts": len(self._artifacts),
                "total_configs": len(self._configs),
                "total_harvested": len(self._harvests),
            }
            summary_path = self._base / "summary.json"
            summary_path.write_text(json.dumps(summary, indent=2))
        except Exception as exc:
            logger.debug("AMIROS _save failed (non-fatal): %s", exc)

    def _load(self) -> None:
        """Reload registries from JSONL files (v0.6.1)."""
        try:
            self._load_all()
        except Exception as exc:
            logger.debug("AMIROS _load failed (non-fatal): %s", exc)

    # ── Agent Feedback Loop ────────────────────────────────────

    def briefing_for_agent(
        self,
        agent_id: str = "",
        role: str = "",
        task_description: str = "",
        max_items: int = 5,
    ) -> str:
        """Generate a context briefing for an agent from AMIROS registries.

        Closes the feedback loop: agents read their own (and others')
        experiment results, claim statuses, and harvest patterns.
        This gets injected into agent prompts via the organism.

        Returns a formatted markdown string, or "" if nothing relevant.
        """
        lines: list[str] = []

        # 1. Recent experiments relevant to this agent or task
        relevant_exps: list[Experiment] = []
        for exp in sorted(
            self._experiments.values(),
            key=lambda e: e.created_at,
            reverse=True,
        )[:20]:
            # Agent's own experiments
            if agent_id and exp.agent_id == agent_id:
                relevant_exps.append(exp)
            # Task keyword match
            elif task_description:
                task_lower = task_description.lower()
                if (exp.name.lower() in task_lower
                        or any(t in task_lower for t in exp.tags)):
                    relevant_exps.append(exp)
            if len(relevant_exps) >= max_items:
                break

        if relevant_exps:
            lines.append("### Recent Experiments")
            for exp in relevant_exps[:max_items]:
                duration = f" ({exp.duration_seconds:.0f}s)" if exp.duration_seconds else ""
                lines.append(
                    f"- [{exp.status}] {exp.name}{duration}"
                    + (f" — {exp.result_summary[:100]}" if exp.result_summary else "")
                )

        # 2. Active claims in the system
        active = self.active_claims()
        if active:
            lines.append("### Active Claims")
            for claim in sorted(active, key=lambda c: c.confidence, reverse=True)[:max_items]:
                challenges = f" ({len(claim.challenges)} challenges)" if claim.challenges else ""
                lines.append(
                    f"- [{claim.status}] conf={claim.confidence:.2f}{challenges} "
                    f"{claim.statement[:100]}"
                )

        # 3. Unprocessed harvest patterns (what's been noticed but not acted on)
        unprocessed = self.unprocessed_harvests()
        if unprocessed:
            pattern_counts: dict[str, int] = {}
            for h in unprocessed:
                for p in h.extracted_patterns:
                    pattern_counts[p] = pattern_counts.get(p, 0) + 1
            if pattern_counts:
                lines.append("### Unprocessed Patterns")
                for pattern, count in sorted(
                    pattern_counts.items(), key=lambda x: x[1], reverse=True
                )[:max_items]:
                    lines.append(f"- ({count}x) {pattern}")

        if not lines:
            return ""

        return "## AMIROS Briefing\n" + "\n".join(lines)

    def save_snapshot(self) -> Path:
        """Write a full JSON snapshot for debugging/backup."""
        snapshot = {
            "timestamp": _utc_now().isoformat(),
            "experiments": {k: v.model_dump() for k, v in self._experiments.items()},
            "claims": {k: v.model_dump() for k, v in self._claims.items()},
            "artifacts": {k: v.model_dump() for k, v in self._artifacts.items()},
            "configs": {k: v.model_dump() for k, v in self._configs.items()},
            "stats": self.stats(),
        }
        snapshot_path = self._base / "snapshot.json"
        snapshot_path.write_text(json.dumps(snapshot, indent=2, default=str))
        return snapshot_path
