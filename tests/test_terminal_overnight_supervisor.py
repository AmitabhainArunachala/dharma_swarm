from __future__ import annotations

import json
from pathlib import Path

from dharma_swarm.terminal_overnight_supervisor import (
    SupervisorConfig,
    TerminalOvernightSupervisor,
    normalize_summary_fields,
    parse_csv_field,
    parse_summary_fields,
)


def test_parse_summary_fields_extracts_expected_keys() -> None:
    payload = parse_summary_fields(
        "\n".join(
            [
                "RESULT: upgraded repo pane",
                "FILES: terminal/src/app.tsx, terminal/src/protocol.ts",
                "TESTS: bunx tsc --noEmit",
                "BLOCKERS: none",
                "NEXT_TASK: improve control pane",
                "STATUS: in_progress",
                "ACCEPTANCE: fail",
            ]
        )
    )
    assert payload["result"] == "upgraded repo pane"
    assert payload["status"] == "in_progress"
    assert payload["acceptance"] == "fail"


def test_parse_csv_field_handles_none_and_values() -> None:
    assert parse_csv_field("none") == []
    assert parse_csv_field("a, b , c") == ["a", "b", "c"]


def test_supervisor_writes_initial_state(tmp_path: Path) -> None:
    supervisor = TerminalOvernightSupervisor(SupervisorConfig(run_id="test-run", once=True))
    supervisor.run_dir = tmp_path / "run"
    supervisor.state_dir = supervisor.run_dir / "state"
    supervisor.logs_dir = supervisor.run_dir / "logs"
    supervisor.prompts_dir = supervisor.run_dir / "prompts"
    supervisor.outputs_dir = supervisor.run_dir / "outputs"
    supervisor.run_path = supervisor.state_dir / "run.json"
    supervisor.backlog_path = supervisor.state_dir / "backlog.json"
    supervisor.verification_path = supervisor.state_dir / "verification.json"
    supervisor.handoff_path = supervisor.state_dir / "handoff.md"
    supervisor.cycles_path = supervisor.state_dir / "cycles.jsonl"
    supervisor.latest_summary_path = supervisor.state_dir / "latest_summary.txt"
    supervisor.run_dir.mkdir(parents=True, exist_ok=True)
    supervisor.state_dir.mkdir(parents=True, exist_ok=True)
    supervisor.logs_dir.mkdir(parents=True, exist_ok=True)
    supervisor.prompts_dir.mkdir(parents=True, exist_ok=True)
    supervisor.outputs_dir.mkdir(parents=True, exist_ok=True)

    supervisor._write_initial_state()

    run_payload = json.loads(supervisor.run_path.read_text())
    backlog_payload = json.loads(supervisor.backlog_path.read_text())
    assert run_payload["run_id"] == "test-run"
    assert backlog_payload["tasks"]


def test_normalize_summary_fields_detects_placeholder_or_transport_failure() -> None:
    normalized = normalize_summary_fields(
        {
            "result": "<one short paragraph>",
            "files": "",
            "tests": "",
            "blockers": "",
            "next_task": "",
            "status": "",
            "acceptance": "",
        },
        "failed to connect to websocket",
    )
    assert normalized["status"] == "blocked"
    assert normalized["acceptance"] == "fail"
    assert "transport" in normalized["blockers"]
