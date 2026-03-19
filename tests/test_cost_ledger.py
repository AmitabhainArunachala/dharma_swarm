"""Tests for cost_ledger.py — metabolic budget enforcement."""

import json
from pathlib import Path

import pytest

import dharma_swarm.cost_ledger as cost_ledger_module
from dharma_swarm.cost_ledger import (
    BudgetConfig,
    CostLedger,
    InvocationCost,
)


@pytest.fixture
def tmp_ledger(tmp_path):
    """Create a ledger with a temporary directory."""
    return CostLedger(
        base_dir=tmp_path,
        budget=BudgetConfig(daily_limit_usd=5.0),
    )


def test_record_and_daily_total(tmp_ledger):
    """Recording invocations accumulates daily total."""
    tmp_ledger.record(InvocationCost(
        agent="test_agent",
        model="llama-3.3-70b-instruct",
        tokens_in=1000,
        tokens_out=500,
    ))
    assert tmp_ledger.daily_total() > 0
    assert tmp_ledger.daily_invocation_count() == 1


def test_budget_remaining(tmp_ledger):
    """Budget remaining decreases with spending."""
    assert tmp_ledger.budget_remaining() == 5.0
    tmp_ledger.record(InvocationCost(cost_usd=2.0))
    assert tmp_ledger.budget_remaining() == 3.0


def test_should_degrade(tmp_ledger):
    """Degradation triggers at 80% utilization."""
    assert not tmp_ledger.should_degrade()
    tmp_ledger.record(InvocationCost(cost_usd=4.1))  # 82%
    assert tmp_ledger.should_degrade()


@pytest.mark.real_budget
def test_should_stop(tmp_ledger):
    """Hard stop at 100% utilization."""
    assert not tmp_ledger.should_stop()
    tmp_ledger.record(InvocationCost(cost_usd=5.1))
    assert tmp_ledger.should_stop()


def test_suggest_model_healthy(tmp_ledger):
    """No degradation when budget is healthy."""
    assert tmp_ledger.suggest_model("claude-opus-4-20250514") == "claude-opus-4-20250514"


def test_suggest_model_degraded(tmp_ledger):
    """Model downgrade when budget is tight."""
    tmp_ledger.record(InvocationCost(cost_usd=4.5))  # 90%
    suggested = tmp_ledger.suggest_model("claude-opus-4-20250514")
    assert suggested == "claude-sonnet-4-20250514"


def test_pre_flight_check_allowed(tmp_ledger):
    """Pre-flight passes when budget is available."""
    result = tmp_ledger.pre_flight_check("llama-3.3-70b-instruct", 1000, 500)
    assert result["allowed"] is True


def test_pre_flight_check_exhausted(tmp_ledger):
    """Pre-flight blocks when budget is exhausted."""
    tmp_ledger.record(InvocationCost(cost_usd=5.5))
    result = tmp_ledger.pre_flight_check("llama-3.3-70b-instruct", 1000, 500)
    assert result["allowed"] is False


def test_estimate_cost():
    """Cost estimation uses pricing table."""
    ledger = CostLedger(base_dir=Path("/tmp/test_costs"))
    cost = ledger.estimate_cost("llama-3.3-70b-instruct", 1_000_000, 1_000_000)
    assert cost == pytest.approx(0.75, abs=0.01)  # 0.35 + 0.40


def test_summary(tmp_ledger):
    """Summary provides useful aggregate info."""
    tmp_ledger.record(InvocationCost(
        agent="agent_a", model="deepseek-chat", cost_usd=1.0
    ))
    tmp_ledger.record(InvocationCost(
        agent="agent_b", model="deepseek-chat", cost_usd=0.5
    ))
    summary = tmp_ledger.summary()
    assert summary["invocations"] == 2
    assert summary["total_usd"] == 1.5
    assert "deepseek-chat" in summary["by_model"]
    assert "agent_a" in summary["by_agent"]


def test_ledger_file_persistence(tmp_ledger, tmp_path):
    """Ledger writes to JSONL files that can be re-read."""
    tmp_ledger.record(InvocationCost(cost_usd=1.23, agent="test"))
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["cost_usd"] == 1.23


def test_record_uses_invocation_timestamp_day_for_ledger_file(tmp_ledger, tmp_path):
    """Backfilled invocations should land in the matching UTC-day ledger."""
    invocation = InvocationCost(
        agent="test_agent",
        model="deepseek-chat",
        cost_usd=0.25,
        timestamp="2026-03-17T23:59:59+00:00",
    )

    tmp_ledger.record(invocation)

    expected_path = tmp_path / "2026-03-17.jsonl"
    assert expected_path.exists()
    lines = expected_path.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["timestamp"] == invocation.timestamp


def test_backfilled_previous_day_record_does_not_change_today_total(tmp_ledger, tmp_path):
    """Historical records should not consume today's budget window."""
    tmp_ledger.record(
        InvocationCost(
            agent="historical",
            model="deepseek-chat",
            cost_usd=1.5,
            timestamp="2026-03-17T12:00:00+00:00",
        )
    )

    today_files = [path for path in tmp_path.glob("*.jsonl") if path.name != "2026-03-17.jsonl"]
    assert today_files == []
    assert tmp_ledger.daily_total() == 0.0
    assert tmp_ledger.daily_invocation_count() == 0


def test_record_locks_and_fsyncs_jsonl_append(tmp_ledger, monkeypatch, tmp_path):
    """Ledger appends should hold a lock and fsync before release."""
    events: list[tuple[str, int, int | None]] = []

    def fake_flock(fd: int, operation: int) -> None:
        events.append(("flock", fd, operation))

    def fake_fsync(fd: int) -> None:
        events.append(("fsync", fd, None))

    monkeypatch.setattr(cost_ledger_module.fcntl, "flock", fake_flock)
    monkeypatch.setattr(cost_ledger_module.os, "fsync", fake_fsync)

    tmp_ledger.record(
        InvocationCost(agent="durability", model="deepseek-chat", cost_usd=0.42)
    )

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["agent"] == "durability"
    assert [event[0] for event in events] == ["flock", "fsync", "flock"]
    assert events[0][2] == cost_ledger_module.fcntl.LOCK_EX
    assert events[-1][2] == cost_ledger_module.fcntl.LOCK_UN
    assert events[0][1] == events[1][1] == events[2][1]


def test_daily_total_skips_non_finite_cost_rows(tmp_path):
    """Persisted nan/inf rows should not poison today's budget totals."""
    ledger = CostLedger(
        base_dir=tmp_path,
        budget=BudgetConfig(daily_limit_usd=5.0),
    )
    ledger_path = ledger._ledger_path()
    ledger_path.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-03-18T00:00:00+00:00","agent":"ok","model":"deepseek-chat","cost_usd":1.25}',
                '{"timestamp":"2026-03-18T00:01:00+00:00","agent":"bad","model":"deepseek-chat","cost_usd":NaN}',
                '{"timestamp":"2026-03-18T00:02:00+00:00","agent":"worse","model":"deepseek-chat","cost_usd":Infinity}',
            ]
        )
        + "\n"
    )

    assert ledger.daily_total() == pytest.approx(1.25)
    assert ledger.daily_invocation_count() == 1
    summary = ledger.summary()
    assert summary["total_usd"] == pytest.approx(1.25)
    assert summary["invocations"] == 1
    assert summary["by_agent"] == {"ok": pytest.approx(1.25)}


def test_record_rejects_non_finite_cost_values(tmp_ledger, tmp_path):
    """Write-time non-finite costs should fail fast instead of corrupting the ledger."""
    invocation = InvocationCost(agent="bad-write", model="deepseek-chat", cost_usd=0.5)
    invocation.cost_usd = float("nan")

    with pytest.raises(ValueError, match="finite"):
        tmp_ledger.record(invocation)

    assert list(tmp_path.glob("*.jsonl")) == []
