"""Tests for dharma_swarm.tui_helpers -- status text builders."""

import asyncio
from datetime import datetime, timezone
import json
import tempfile
from pathlib import Path

import pytest

from dharma_swarm.runtime_state import (
    ArtifactRecord,
    ContextBundleRecord,
    DelegationRun,
    MemoryFact,
    OperatorAction,
    RuntimeStateStore,
    SessionState,
    TaskClaim,
)
from dharma_swarm.tui_helpers import (
    _read_json,
    build_darwin_status_text,
    build_runtime_status_text,
    build_status_text,
)


# ---------------------------------------------------------------------------
# _read_json
# ---------------------------------------------------------------------------


def test_read_json_valid():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"key": "value"}, f)
        f.flush()
        result = _read_json(Path(f.name))
    assert result == {"key": "value"}


def test_read_json_invalid():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("not json at all")
        f.flush()
        result = _read_json(Path(f.name))
    assert result is None


def test_read_json_missing_file():
    result = _read_json(Path("/nonexistent/path/file.json"))
    assert result is None


def test_read_json_empty_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("")
        f.flush()
        result = _read_json(Path(f.name))
    assert result is None


def test_read_json_complex():
    data = {"nested": {"list": [1, 2, 3], "bool": True, "null": None}}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        f.flush()
        result = _read_json(Path(f.name))
    assert result == data


# ---------------------------------------------------------------------------
# build_status_text
# ---------------------------------------------------------------------------


def test_build_status_text_returns_string():
    result = build_status_text()
    assert isinstance(result, str)


def test_build_status_text_has_header():
    result = build_status_text()
    assert "DGC System Status" in result


def test_build_status_text_contains_source_modules():
    """Should report source module count since the dharma_swarm dir exists."""
    result = build_status_text()
    assert "Source modules:" in result


def test_build_status_text_thread_info(tmp_path, monkeypatch):
    """If thread state exists, it should be included in output."""
    import dharma_swarm.tui_helpers as helpers

    # Create a mock .dharma directory with thread state
    dharma_dir = tmp_path / ".dharma"
    dharma_dir.mkdir()
    thread_state = {"current_thread": "mechanistic"}
    (dharma_dir / "thread_state.json").write_text(json.dumps(thread_state))

    # Monkeypatch the state dir
    monkeypatch.setattr(helpers, "DHARMA_STATE", dharma_dir)
    result = build_status_text()
    assert "mechanistic" in result


def test_build_status_text_pulse_info(tmp_path, monkeypatch):
    """If pulse log exists, it should show last pulse timestamp."""
    import dharma_swarm.tui_helpers as helpers

    dharma_dir = tmp_path / ".dharma"
    dharma_dir.mkdir()
    pulse_entry = {"timestamp": "2026-03-07T12:00:00Z", "status": "ok"}
    (dharma_dir / "pulse_log.jsonl").write_text(json.dumps(pulse_entry) + "\n")

    monkeypatch.setattr(helpers, "DHARMA_STATE", dharma_dir)
    result = build_status_text()
    assert "Last pulse:" in result
    assert "2026-03-07" in result


def test_build_status_text_archive_info(tmp_path, monkeypatch):
    """If evolution archive exists, it should show entry count."""
    import dharma_swarm.tui_helpers as helpers

    dharma_dir = tmp_path / ".dharma"
    evo_dir = dharma_dir / "evolution"
    evo_dir.mkdir(parents=True)
    (evo_dir / "archive.jsonl").write_text('{"id":"a"}\n{"id":"b"}\n{"id":"c"}\n')

    monkeypatch.setattr(helpers, "DHARMA_STATE", dharma_dir)
    result = build_status_text()
    assert "Archive entries: 3" in result


def test_build_status_text_ecosystem_info(tmp_path, monkeypatch):
    """If manifest exists, should show ecosystem alive count."""
    import dharma_swarm.tui_helpers as helpers

    manifest = {
        "ecosystem": {
            "path1": {"exists": True},
            "path2": {"exists": True},
            "path3": {"exists": False},
        }
    }
    manifest_path = tmp_path / ".dharma_manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    monkeypatch.setattr(helpers, "HOME", tmp_path)
    result = build_status_text()
    assert "Ecosystem: 2/3 alive" in result


def test_build_status_text_no_state_dir(tmp_path, monkeypatch):
    """With empty state dir, should still produce header and source count."""
    import dharma_swarm.tui_helpers as helpers

    empty_dharma = tmp_path / ".dharma_nonexistent"
    monkeypatch.setattr(helpers, "DHARMA_STATE", empty_dharma)
    result = build_status_text()
    assert "DGC System Status" in result


def test_build_darwin_status_text_reports_recent_experiments(tmp_path, monkeypatch):
    import dharma_swarm.tui_helpers as helpers

    dharma_dir = tmp_path / ".dharma"
    evo_dir = dharma_dir / "evolution"
    evo_dir.mkdir(parents=True)
    (evo_dir / "experiments.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "component": "fragile.py",
                        "execution_profile": "llm_default",
                        "promotion_state": "candidate",
                        "evidence_tier": "local",
                        "pass_rate": 0.0,
                        "weighted_fitness": 0.1,
                        "failure_class": "rollback",
                        "failure_signature": "rollback:apply_or_test",
                    }
                ),
                json.dumps(
                    {
                        "component": "fragile.py",
                        "execution_profile": "llm_default",
                        "promotion_state": "candidate",
                        "evidence_tier": "local",
                        "pass_rate": 0.0,
                        "weighted_fitness": 0.1,
                        "failure_class": "rollback",
                        "failure_signature": "rollback:apply_or_test",
                    }
                ),
                json.dumps(
                    {
                        "component": "strong.py",
                        "execution_profile": "pkg_profile",
                        "promotion_state": "component_pass",
                        "evidence_tier": "component",
                        "pass_rate": 1.0,
                        "weighted_fitness": 0.9,
                    }
                ),
            ]
        )
        + "\n"
    )
    (evo_dir / "archive.jsonl").write_text(
        json.dumps(
            {
                "id": "entry-1",
                "component": "strong.py",
                "promotion_state": "component_pass",
                "execution_profile": "pkg_profile",
                "fitness": {"correctness": 1.0, "safety": 1.0},
            }
        )
        + "\n"
    )

    monkeypatch.setattr(helpers, "DHARMA_STATE", dharma_dir)
    result = build_darwin_status_text()

    assert "Darwin Control" in result
    assert "Recent experiments: 3" in result
    assert "Promotion ladder:" in result
    assert "Failure classes: rollback=2" in result
    assert "Avoidance hints" in result
    assert "Recent archived mutations" in result


def test_build_darwin_status_text_reports_dse_observation_stream(tmp_path, monkeypatch):
    import dharma_swarm.tui_helpers as helpers

    dharma_dir = tmp_path / ".dharma"
    observations_dir = dharma_dir / "evolution" / "observations"
    observations_dir.mkdir(parents=True)
    (observations_dir / "coalgebra_stream.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "cycle_id": "cycle-a",
                        "component": "child.py",
                        "rv": 0.9,
                        "best_fitness": 0.4,
                        "approaching_fixed_point": False,
                        "ouroboros": {
                            "recognition_type": "GENUINE",
                            "swabhaav_ratio": 0.72,
                            "is_mimicry": False,
                            "is_genuine": True,
                        },
                        "l4_correlation": {
                            "is_l4_like": True,
                            "bridge_group": "dse_l4_like",
                        },
                    }
                ),
                json.dumps(
                    {
                        "cycle_id": "cycle-b",
                        "component": "other.py",
                        "rv": 0.8,
                        "best_fitness": 0.6,
                        "approaching_fixed_point": True,
                        "ouroboros": {
                            "recognition_type": "NONE",
                            "swabhaav_ratio": 0.2,
                            "is_mimicry": True,
                            "is_genuine": False,
                        },
                        "l4_correlation": {
                            "is_l4_like": False,
                            "bridge_group": "dse_evolution",
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (observations_dir / "coordination_log.jsonl").write_text(
        json.dumps(
            {
                "global_truths": 2,
                "productive_disagreements": 1,
                "is_globally_coherent": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(helpers, "DHARMA_STATE", dharma_dir)
    result = build_darwin_status_text()

    assert "DSE observation stream" in result
    assert "observations=2" in result
    assert "components=2" in result
    assert "avg_rv=0.85" in result
    assert "avg_fitness=0.50" in result
    assert "mimicry=50.0%" in result
    assert "witness=0.46" in result
    assert "latest=NONE" in result
    assert "l4_like=1/2" in result
    assert "fixed_point=1/2" in result
    assert "latest_component=other.py" in result
    assert "coordination truths=2" in result
    assert "disagreements=1" in result
    assert "coherent=no" in result


def test_build_darwin_status_text_reports_reciprocity_summary(tmp_path, monkeypatch):
    import dharma_swarm.tui_helpers as helpers

    dharma_dir = tmp_path / ".dharma"
    observations_dir = dharma_dir / "evolution" / "observations"
    observations_dir.mkdir(parents=True)
    (observations_dir / "coalgebra_stream.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "cycle_id": "cycle-a",
                        "component": "child.py",
                        "reciprocity": {
                            "chain_valid": True,
                            "invariant_issues": 0,
                            "challenged_claims": 0,
                            "total_routed_usd": 1000.0,
                            "issue_codes": [],
                        },
                    }
                ),
                json.dumps(
                    {
                        "cycle_id": "cycle-b",
                        "component": "other.py",
                        "reciprocity": {
                            "chain_valid": False,
                            "invariant_issues": 2,
                            "challenged_claims": 1,
                            "total_routed_usd": 5000.0,
                            "issue_codes": [
                                "routing_missing_project",
                                "verified_ecology_missing_audit",
                            ],
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(helpers, "DHARMA_STATE", dharma_dir)
    result = build_darwin_status_text()

    assert "reciprocity invalid_chain=1/2" in result
    assert "latest_issues=2" in result
    assert "challenged=1" in result
    assert "routed_usd=5000.00" in result
    assert (
        "issue_codes=routing_missing_project,verified_ecology_missing_audit"
        in result
    )


def test_build_runtime_status_text_reports_runtime_db_state(tmp_path, monkeypatch):
    import dharma_swarm.tui_helpers as helpers

    dharma_dir = tmp_path / ".dharma"
    runtime_dir = dharma_dir / "state"
    runtime_dir.mkdir(parents=True)
    runtime_db = runtime_dir / "runtime.db"

    async def seed_runtime() -> None:
        store = RuntimeStateStore(runtime_db)
        await store.init_db()
        now = datetime(2026, 3, 11, 1, 2, 3, tzinfo=timezone.utc)
        await store.upsert_session(
            SessionState(
                session_id="sess-runtime-view",
                operator_id="operator",
                current_task_id="task-runtime-view",
                created_at=now,
                updated_at=now,
            )
        )
        await store.record_task_claim(
            TaskClaim(
                claim_id="claim-runtime-view",
                session_id="sess-runtime-view",
                task_id="task-runtime-view",
                agent_id="codex",
                status="acknowledged",
                claimed_at=now,
                acked_at=now,
            )
        )
        await store.record_delegation_run(
            DelegationRun(
                run_id="run-runtime-view",
                session_id="sess-runtime-view",
                task_id="task-runtime-view",
                claim_id="claim-runtime-view",
                assigned_by="operator",
                assigned_to="codex",
                status="in_progress",
                current_artifact_id="artifact-runtime-view",
                started_at=now,
            )
        )
        await store.record_artifact(
            ArtifactRecord(
                artifact_id="artifact-runtime-view",
                artifact_kind="report",
                session_id="sess-runtime-view",
                task_id="task-runtime-view",
                run_id="run-runtime-view",
                payload_path=str(tmp_path / "report.md"),
                manifest_path=str(tmp_path / "report.md.manifest.json"),
                checksum="abc123",
                promotion_state="published",
                created_at=now,
            )
        )
        await store.record_memory_fact(
            MemoryFact(
                fact_id="fact-runtime-view",
                fact_kind="finding",
                truth_state="promoted",
                text="Canonical runtime is healthy.",
                session_id="sess-runtime-view",
                task_id="task-runtime-view",
                created_at=now,
                updated_at=now,
            )
        )
        await store.record_context_bundle(
            ContextBundleRecord(
                bundle_id="ctx-runtime-view",
                session_id="sess-runtime-view",
                task_id="task-runtime-view",
                run_id="run-runtime-view",
                token_budget=2048,
                rendered_text="Context bundle",
                checksum="ctx123",
                created_at=now,
            )
        )
        await store.record_operator_action(
            OperatorAction(
                action_id="act-runtime-view",
                action_name="bridge_task_responded",
                actor="codex",
                session_id="sess-runtime-view",
                task_id="task-runtime-view",
                run_id="run-runtime-view",
                created_at=now,
            )
        )

    asyncio.run(seed_runtime())

    monkeypatch.setattr(helpers, "DHARMA_STATE", dharma_dir)
    monkeypatch.setattr(
        helpers.shutil,
        "which",
        lambda prog: f"/mock/bin/{prog}" if prog != "claude" else None,
    )
    result = build_runtime_status_text()

    assert "Runtime Control Plane" in result
    assert "Sessions=1" in result
    assert "Claims=1" in result
    assert "AckedClaims=1" in result
    assert "Artifacts=1" in result
    assert "PromotedFacts=1" in result
    assert "ContextBundles=1" in result
    assert "OperatorActions=1" in result
    assert "Active runs" in result
    assert "Recent artifacts" in result
    assert "Recent operator actions" in result
    assert "python3: /mock/bin/python3" in result
    assert "claude: not found" in result


def test_build_runtime_status_text_handles_missing_runtime_db(tmp_path, monkeypatch):
    import dharma_swarm.tui_helpers as helpers

    dharma_dir = tmp_path / ".dharma"
    monkeypatch.setattr(helpers, "DHARMA_STATE", dharma_dir)
    monkeypatch.setattr(helpers.shutil, "which", lambda prog: None)

    result = build_runtime_status_text()

    assert "Runtime Control Plane" in result
    assert "No canonical runtime database found" in result
    assert "Toolchain" in result
