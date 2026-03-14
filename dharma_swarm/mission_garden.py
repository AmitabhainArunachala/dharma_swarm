"""Predefined mission-garden cron packs for long-running cultivation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

PACK_ID = "planetary_reciprocity_garden"
PACK_VERSION = "2026-03-15"
DEFAULT_REPO_ROOT = Path.home() / "dharma_swarm"
DEFAULT_SNAPSHOT_ROOT = (
    DEFAULT_REPO_ROOT / "reports" / "dual_engine_swarm_20260313_run" / "state"
)


@dataclass(frozen=True, slots=True)
class MissionGardenJobSpec:
    key: str
    name: str
    schedule: str
    prompt: str
    model: str
    timeout_sec: int
    urgent: bool = False


def _prompt_paths(repo_root: Path, snapshot_root: Path) -> dict[str, str]:
    return {
        "repo_root": str(repo_root),
        "mission_json": "~/.dharma/mission.json",
        "campaign_json": "~/.dharma/campaign.json",
        "fallback_mission_json": str(snapshot_root / "mission.json"),
        "director_latest": str(snapshot_root / "shared" / "thinkodynamic_director_latest.md"),
        "director_handoff": str(snapshot_root / "shared" / "thinkodynamic_director_handoff.md"),
        "public_brief": str(
            repo_root / "docs" / "reports" / "PLANETARY_RECIPROCITY_COMMONS_PUBLIC_BRIEF_2026-03-11.md"
        ),
        "concept_note": str(
            repo_root / "docs" / "reports" / "ANTHROPIC_RECIPROCITY_COMMONS_CONCEPT_NOTE_2026-03-11.md"
        ),
        "governance": str(
            repo_root / "docs" / "reports" / "PLANETARY_RECIPROCITY_COMMONS_GOVERNANCE_CHARTER_2026-03-11.md"
        ),
        "spinout_readme": str(
            repo_root / "spinouts" / "planetary_reciprocity_commons_seed" / "README.md"
        ),
        "spinout_cli": str(
            repo_root
            / "spinouts"
            / "planetary_reciprocity_commons_seed"
            / "src"
            / "planetary_reciprocity_commons"
            / "cli.py"
        ),
        "ledger": str(repo_root / "dharma_swarm" / "ai_reciprocity_ledger.py"),
        "gaia": str(repo_root / "dharma_swarm" / "gaia_verification.py"),
        "integration": str(repo_root / "dharma_swarm" / "integrations" / "reciprocity_commons.py"),
        "missions_dir": str(repo_root / "docs" / "missions"),
    }


def _build_specs(repo_root: Path, snapshot_root: Path) -> list[MissionGardenJobSpec]:
    paths = _prompt_paths(repo_root, snapshot_root)

    pulse_prompt = """You are the Planetary Reciprocity Pulse.

Mission: keep the ecological reciprocity mission warm without pretending it is already pilot-ready.

Read these local anchors first:
- {public_brief}
- {concept_note}
- {governance}
- {spinout_readme}
- {ledger}
- {gaia}
- {integration}
- {mission_json} if it exists, otherwise {fallback_mission_json}

Write a terse heartbeat to ~/.dharma/shared/planetary_reciprocity_pulse.md with:
- current phase
- strongest real asset
- weakest missing proof
- next pressure point
- one concrete next action

Constraints:
- max 140 words
- factual, no marketing language
- if the mission drifted, say exactly how
""".format(**paths)

    cultivation_prompt = """You are the Planetary Reciprocity Gardener.

Your job is to water and feed the mission in the background.

Read these local anchors first:
- {public_brief}
- {concept_note}
- {governance}
- {spinout_readme}
- {spinout_cli}
- {ledger}
- {gaia}
- {integration}
- {director_latest}
- {director_handoff}

Pick exactly one cultivation lane for this run:
- pilot design
- measurement and MRV
- governance
- partner thesis
- capital flow
- code and infra gap between current repo and a shippable service

Then:
1. Append a dated note to ~/.dharma/shared/planetary_reciprocity_garden.md with:
   lane, observation, proposed artifact or experiment, first next step, anti-greenwashing check
2. Write or refresh ~/.dharma/shared/planetary_reciprocity_backlog.md with the top 5 next tasks ordered by leverage

Constraints:
- do not make broad code changes
- prefer briefs, specs, checklists, and sharply bounded TODOs
- max 400 words
""".format(**paths)

    scout_prompt = """You are the Telos Mission Scout.

Realign to highest telos before proposing anything:
- truthfulness over theater
- non-harm over speed
- compounding world-benefit over local novelty
- operational reality over aspiration

Read:
- {mission_json} if it exists, otherwise {fallback_mission_json}
- {campaign_json} if it exists
- {director_latest}
- {director_handoff}
- ~/.dharma/shared/planetary_reciprocity_garden.md if it exists
- {missions_dir}
- {public_brief}
- {concept_note}

First decide whether the ecological reciprocity mission is still the highest-leverage mission.
Then write ~/.dharma/shared/telos_mission_scout.md with the top 3 mission candidates.

For each candidate include:
- title
- why now
- proof already present
- blocking gap
- next concrete action

If planetary reciprocity remains number one, say what has to become true before it graduates from cultivation to active execution.

Max 500 words. No theater.
""".format(**paths)

    return [
        MissionGardenJobSpec(
            key="pulse",
            name="planetary-reciprocity-pulse",
            schedule="every 6h",
            prompt=pulse_prompt,
            model="haiku",
            timeout_sec=600,
        ),
        MissionGardenJobSpec(
            key="cultivation",
            name="planetary-reciprocity-cultivation",
            schedule="every 24h",
            prompt=cultivation_prompt,
            model="sonnet",
            timeout_sec=900,
        ),
        MissionGardenJobSpec(
            key="telos-scout",
            name="telos-mission-scout",
            schedule="every 12h",
            prompt=scout_prompt,
            model="sonnet",
            timeout_sec=900,
        ),
    ]


def install_planetary_reciprocity_garden_jobs(
    *,
    repo_root: str | Path | None = None,
    snapshot_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Install the ecological mission-garden cron pack if missing."""

    from dharma_swarm.cron_scheduler import create_job, list_jobs

    resolved_repo = Path(repo_root).expanduser() if repo_root else DEFAULT_REPO_ROOT
    resolved_snapshot = (
        Path(snapshot_root).expanduser() if snapshot_root else DEFAULT_SNAPSHOT_ROOT
    )
    specs = _build_specs(resolved_repo, resolved_snapshot)
    existing = list_jobs(include_disabled=True)
    installed: list[dict[str, Any]] = []

    for spec in specs:
        found = None
        for job in existing:
            metadata = job.get("metadata", {})
            if (
                isinstance(metadata, dict)
                and metadata.get("pack_id") == PACK_ID
                and metadata.get("job_key") == spec.key
            ):
                found = job
                break
            if job.get("name") == spec.name:
                found = job
                break
        if found is not None:
            installed.append(found)
            continue

        job = create_job(
            prompt=spec.prompt,
            schedule=spec.schedule,
            name=spec.name,
            deliver="local",
            urgent=spec.urgent,
            handler="headless_prompt",
            model=spec.model,
            timeout_sec=spec.timeout_sec,
            metadata={
                "pack_id": PACK_ID,
                "pack_version": PACK_VERSION,
                "job_key": spec.key,
                "repo_root": str(resolved_repo),
                "snapshot_root": str(resolved_snapshot),
            },
        )
        installed.append(job)
        existing.append(job)

    return installed
