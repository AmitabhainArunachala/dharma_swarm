from __future__ import annotations

import json
from pathlib import Path

from dharma_swarm.runtime_artifacts import (
    dgc_health_snapshot_summary,
    write_dgc_health_snapshot,
)


def test_write_dgc_health_snapshot_persists_fresh_runtime_metadata(tmp_path: Path) -> None:
    state_dir = tmp_path / ".dharma"
    (state_dir / "daemon.pid").parent.mkdir(parents=True, exist_ok=True)
    (state_dir / "daemon.pid").write_text("4242\n", encoding="utf-8")

    path = write_dgc_health_snapshot(
        state_dir,
        daemon_pid=4242,
        agent_count=7,
        task_count=11,
        anomaly_count=2,
        source="orchestrate_live",
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["daemon_pid"] == 4242
    assert payload["agent_count"] == 7
    assert payload["task_count"] == 11
    assert payload["anomaly_count"] == 2
    assert payload["source"] == "orchestrate_live"

    summary = dgc_health_snapshot_summary(state_dir)
    assert summary["status"] == "fresh"
    assert summary["daemon_pid_mismatch"] is False

