from __future__ import annotations

from pathlib import Path

from dharma_swarm import cron_scheduler
from dharma_swarm.mission_garden import (
    PACK_ID,
    PACK_VERSION,
    install_planetary_reciprocity_garden_jobs,
)


def _redirect_cron_storage(tmp_path: Path, monkeypatch) -> None:
    cron_dir = tmp_path / "cron"
    monkeypatch.setattr(cron_scheduler, "DHARMA_DIR", tmp_path)
    monkeypatch.setattr(cron_scheduler, "CRON_DIR", cron_dir)
    monkeypatch.setattr(cron_scheduler, "JOBS_FILE", cron_dir / "jobs.json")
    monkeypatch.setattr(cron_scheduler, "OUTPUT_DIR", cron_dir / "output")
    monkeypatch.setattr(cron_scheduler, "LOCK_FILE", cron_dir / ".tick.lock")


def test_install_planetary_reciprocity_garden_jobs_creates_expected_pack(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _redirect_cron_storage(tmp_path, monkeypatch)

    jobs = install_planetary_reciprocity_garden_jobs(
        repo_root=tmp_path / "repo",
        snapshot_root=tmp_path / "snapshot",
    )

    assert len(jobs) == 3
    assert [job["name"] for job in jobs] == [
        "planetary-reciprocity-pulse",
        "planetary-reciprocity-cultivation",
        "telos-mission-scout",
    ]
    assert jobs[0]["handler"] == "headless_prompt"
    assert jobs[0]["model"] == "haiku"
    assert jobs[1]["timeout_sec"] == 900
    assert jobs[2]["metadata"]["pack_id"] == PACK_ID
    assert jobs[2]["metadata"]["pack_version"] == PACK_VERSION
    assert str(tmp_path / "repo") in jobs[0]["prompt"]


def test_install_planetary_reciprocity_garden_jobs_is_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _redirect_cron_storage(tmp_path, monkeypatch)

    first = install_planetary_reciprocity_garden_jobs(
        repo_root=tmp_path / "repo",
        snapshot_root=tmp_path / "snapshot",
    )
    second = install_planetary_reciprocity_garden_jobs(
        repo_root=tmp_path / "repo",
        snapshot_root=tmp_path / "snapshot",
    )

    assert [job["id"] for job in first] == [job["id"] for job in second]
    assert len(cron_scheduler.list_jobs(include_disabled=True)) == 3
