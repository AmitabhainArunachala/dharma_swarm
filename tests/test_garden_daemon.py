from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

import garden_daemon as gd


def _configure_tmp_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    garden_dir = home / ".dharma" / "garden"
    shared_dir = home / ".dharma" / "shared"
    costs_dir = home / ".dharma" / "costs"

    for path in (garden_dir, shared_dir, costs_dir, home / "dharma_swarm"):
        path.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(gd, "HOME", home)
    monkeypatch.setattr(gd, "GARDEN_DIR", garden_dir)
    monkeypatch.setattr(gd, "SHARED_DIR", shared_dir)
    monkeypatch.setattr(gd, "COSTS_DIR", costs_dir)
    monkeypatch.setattr(gd, "COST_LEDGER_PATH", costs_dir / "daily_ledger.jsonl")
    monkeypatch.setattr(gd, "HEARTBEAT_DIR", garden_dir)


def test_check_triggers_skips_followups_when_sensor_fails(capsys: pytest.CaptureFixture[str]) -> None:
    triggered = gd.check_triggers({"status": "timeout", "skill": "ecosystem-pulse"})

    assert triggered == []
    assert "SENSOR FAILED (timeout)" in capsys.readouterr().out


def test_append_cost_entry_uses_recorded_at_day_for_daily_totals(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)

    started_at = datetime(2026, 3, 17, 23, 59, 50)
    gd._append_cost_entry(
        "hum",
        "sonnet",
        elapsed=30.0,
        status="success",
        recorded_at=started_at,
    )

    entries = [
        json.loads(line)
        for line in gd.COST_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert entries == [
        {
            "timestamp": started_at.isoformat(),
            "date": "2026-03-17",
            "session_id": "garden_daemon",
            "tool": "garden_skill",
            "category": "garden",
            "estimated_cost_usd": gd.MODEL_COST_USD["sonnet"],
            "agent_description": "hum (success, 30s)",
            "model": "sonnet",
        }
    ]
    assert gd._read_daily_total("2026-03-17") == gd.MODEL_COST_USD["sonnet"]
    assert gd._read_daily_total("2026-03-18") == 0.0


def test_append_cost_entry_uses_advisory_lock_and_fsync(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)
    lock_calls: list[int] = []
    fsync_calls: list[int] = []

    monkeypatch.setattr(gd.fcntl, "flock", lambda fd, op: lock_calls.append(op))
    monkeypatch.setattr(gd.os, "fsync", lambda fd: fsync_calls.append(fd))

    gd._append_cost_entry("ecosystem-pulse", "haiku", elapsed=12.0, status="success")

    entries = [
        json.loads(line)
        for line in gd.COST_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert lock_calls == [gd.fcntl.LOCK_EX, gd.fcntl.LOCK_UN]
    assert len(fsync_calls) == 1
    assert entries[0]["estimated_cost_usd"] == gd.MODEL_COST_USD["haiku"]


def test_read_daily_total_tolerates_malformed_cost_amounts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)

    gd.COST_LEDGER_PATH.write_text(
        "\n".join(
            [
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": "0.06"}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": "oops"}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": None}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": True}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": 0.01}),
                json.dumps({"date": "2026-03-17", "estimated_cost_usd": 9.99}),
            ])
        + "\n",
        encoding="utf-8",
    )

    assert gd._read_daily_total("2026-03-18") == pytest.approx(0.07)
    assert gd._read_daily_total("2026-03-17") == pytest.approx(9.99)


def test_read_daily_total_skips_non_finite_cost_amounts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)

    gd.COST_LEDGER_PATH.write_text(
        "\n".join(
            [
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": "nan"}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": "inf"}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": "-inf"}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": 0.06}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": "0.01"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert gd._read_daily_total("2026-03-18") == pytest.approx(0.07)


def test_cost_cap_logic_ignores_non_finite_daily_totals_from_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)

    gd.COST_LEDGER_PATH.write_text(
        "\n".join(
            [
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": "nan"}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": "inf"}),
                json.dumps({"date": "2026-03-18", "estimated_cost_usd": 5.25}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            value = datetime(2026, 3, 18, 0, 0, 0)
            if tz is not None:
                return value.astimezone(tz) if value.tzinfo else value.replace(tzinfo=tz)
            return value

    monkeypatch.setattr(gd, "datetime", FakeDateTime)

    assert gd._read_daily_total() == pytest.approx(5.25)
    assert gd._effective_model("hum", "sonnet") == "haiku"
    assert gd._should_skip_for_cost("hum") is False


def test_write_heartbeat_uses_atomic_json_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)
    captured: list[tuple[Path, str]] = []

    def _fake_atomic_write(path: Path, text: str, *, encoding: str = "utf-8") -> None:
        assert encoding == "utf-8"
        captured.append((path, text))

    monkeypatch.setattr(gd, "_atomic_write_text", _fake_atomic_write)

    started = datetime(2026, 3, 18, 1, 2, 3)
    gd._write_heartbeat("hum", "running", started, pid=4242)

    assert [path for path, _ in captured] == [gd._heartbeat_path("hum")]
    assert json.loads(captured[0][1]) == {
        "skill": "hum",
        "status": "running",
        "started": started.isoformat(),
        "pid": 4242,
    }


@pytest.mark.asyncio
async def test_run_cycle_hybrid_stops_after_failed_sensor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(gd, "_no_cycle_in_24h", lambda: False)
    monkeypatch.setattr(gd, "_read_daily_total", lambda date_str=None: 0.0)

    calls: list[str] = []

    async def _fake_run_skill(skill_key: str, model_override: str | None = None) -> dict:
        del model_override
        calls.append(skill_key)
        return {
            "skill": gd.SKILLS[skill_key]["name"],
            "key": skill_key,
            "status": "exception" if skill_key == "ecosystem-pulse" else "success",
            "timestamp": "2026-03-18T00:00:00",
        }

    monkeypatch.setattr(gd, "run_skill", _fake_run_skill)

    report = await gd.run_cycle()

    assert calls == ["ecosystem-pulse"]
    assert report["skills_run"] == 1
    assert report["results"][0]["status"] == "exception"


@pytest.mark.asyncio
async def test_run_cycle_hybrid_runs_triggered_followups_after_successful_sensor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(gd, "_no_cycle_in_24h", lambda: False)
    monkeypatch.setattr(gd, "_read_daily_total", lambda date_str=None: 0.0)
    monkeypatch.setattr(gd, "check_triggers", lambda pulse_result: ["hum", "research-status"])

    calls: list[str] = []

    async def _fake_run_skill(skill_key: str, model_override: str | None = None) -> dict:
        del model_override
        calls.append(skill_key)
        return {
            "skill": gd.SKILLS[skill_key]["name"],
            "key": skill_key,
            "status": "success",
            "timestamp": "2026-03-18T00:00:00",
        }

    monkeypatch.setattr(gd, "run_skill", _fake_run_skill)

    report = await gd.run_cycle()

    assert calls == ["ecosystem-pulse", "hum", "research-status"]
    assert report["skills_run"] == 3
    assert report["successes"] == 3


@pytest.mark.asyncio
async def test_run_skill_records_cost_against_start_time(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)

    start = datetime(2026, 3, 17, 23, 59, 50)
    end = datetime(2026, 3, 18, 0, 0, 5)

    class FakeDateTime(datetime):
        _values = [start, end, end, end]

        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            value = cls._values.pop(0) if cls._values else end
            if tz is not None:
                return value.astimezone(tz) if value.tzinfo else value.replace(tzinfo=tz)
            return value

    class FakeProc:
        pid = 4242
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"pulse ok", b""

    async def _fake_create_subprocess_exec(*args, **kwargs) -> FakeProc:
        del args, kwargs
        return FakeProc()

    monkeypatch.setattr(gd, "datetime", FakeDateTime)
    monkeypatch.setattr(gd.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)

    result = await gd.run_skill("ecosystem-pulse")

    entries = [
        json.loads(line)
        for line in gd.COST_LEDGER_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert result["status"] == "success"
    assert entries[0]["timestamp"] == start.isoformat()
    assert entries[0]["date"] == "2026-03-17"
    assert gd._read_daily_total("2026-03-17") == gd.MODEL_COST_USD["haiku"]
    assert gd._read_daily_total("2026-03-18") == 0.0


@pytest.mark.asyncio
async def test_run_cycle_writes_reports_and_shared_heartbeat_atomically(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _configure_tmp_paths(monkeypatch, tmp_path)

    cycle_mark = datetime(2026, 3, 18, 0, 0, 0)
    cycle_end = datetime(2026, 3, 18, 0, 0, 5)

    class FakeDateTime(datetime):
        _values = [cycle_mark, cycle_mark, cycle_end]

        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            value = cls._values.pop(0) if cls._values else cycle_end
            if tz is not None:
                return value.astimezone(tz) if value.tzinfo else value.replace(tzinfo=tz)
            return value

    writes: list[tuple[Path, dict[str, object]]] = []

    def _fake_atomic_write(path: Path, text: str, *, encoding: str = "utf-8") -> None:
        assert encoding == "utf-8"
        payload = json.loads(text)
        writes.append((path, payload))

    async def _fake_run_skill(skill_key: str, model_override: str | None = None) -> dict:
        del model_override
        return {
            "skill": gd.SKILLS[skill_key]["name"],
            "key": skill_key,
            "status": "success",
            "timestamp": cycle_mark.isoformat(),
        }

    monkeypatch.setattr(gd, "datetime", FakeDateTime)
    monkeypatch.setattr(gd, "_atomic_write_text", _fake_atomic_write)
    monkeypatch.setattr(gd, "_read_daily_total", lambda date_str=None: 0.0)
    monkeypatch.setattr(gd, "run_skill", _fake_run_skill)

    report = await gd.run_cycle(skill_keys=["ecosystem-pulse"])

    written_paths = [path for path, _ in writes]
    assert written_paths == [
        gd.GARDEN_DIR / "cycle_20260318_000000.json",
        gd.GARDEN_DIR / "latest_cycle.json",
        gd.SHARED_DIR / "garden_heartbeat.json",
    ]
    assert writes[0][1] == report
    assert writes[1][1] == report
    assert writes[2][1] == {
        "cycle_id": "20260318_000000",
        "timestamp": cycle_end.isoformat(),
        "status": "completed",
        "successes": 1,
        "total_skills": 1,
        "elapsed_seconds": 5.0,
    }
