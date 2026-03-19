"""Tests for algedonic.py -- emergency bypass channel (Pydantic + async)."""

import json
from pathlib import Path

import pytest

from dharma_swarm.algedonic import (
    AlgedonicChannel,
    AlgedonicSignal,
    detect_coherence_collapse,
    detect_error_spike,
    detect_resource_depletion,
    run_detectors,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dharma_dir(tmp_path: Path) -> Path:
    """Ephemeral .dharma root for test isolation."""
    d = tmp_path / ".dharma"
    d.mkdir()
    return d


@pytest.fixture
def channel(dharma_dir: Path) -> AlgedonicChannel:
    return AlgedonicChannel(state_dir=dharma_dir / "algedonic")


# ---------------------------------------------------------------------------
# AlgedonicSignal model
# ---------------------------------------------------------------------------


def test_signal_defaults():
    """Signal gets a UUID id, UTC timestamp, and critical severity by default."""
    sig = AlgedonicSignal(trigger="test", category="external", message="msg")
    assert len(sig.id) == 16
    assert sig.severity == "critical"
    assert sig.acknowledged is False
    assert sig.acknowledged_at is None
    assert sig.auto_safe_mode is False


def test_signal_roundtrip_json():
    """Signal serialises to JSON and back without data loss."""
    sig = AlgedonicSignal(
        trigger="x", category="error_spike", message="boom", severity="warning"
    )
    raw = sig.model_dump_json()
    restored = AlgedonicSignal.model_validate_json(raw)
    assert restored.id == sig.id
    assert restored.severity == "warning"
    assert restored.category == "error_spike"


# ---------------------------------------------------------------------------
# AlgedonicChannel -- emit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_persists_to_jsonl(channel: AlgedonicChannel):
    """Emitting a signal appends a line to signals.jsonl."""
    sig = await channel.emit("test_trigger", "external", "Something happened", severity="warning")
    lines = channel._signals_path.read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["id"] == sig.id
    assert data["severity"] == "warning"


@pytest.mark.asyncio
async def test_emit_critical_creates_alert_marker(
    channel: AlgedonicChannel, dharma_dir: Path
):
    """Critical emit writes .ALGEDONIC_ALERT marker."""
    await channel.emit("crit", "security_event", "breach", severity="critical")
    alert = dharma_dir / ".ALGEDONIC_ALERT"
    assert alert.exists()
    content = alert.read_text()
    assert "CRITICAL" in content
    assert "breach" in content


@pytest.mark.asyncio
async def test_emit_warning_no_alert_marker(
    channel: AlgedonicChannel, dharma_dir: Path
):
    """Warning-level emit does NOT write .ALGEDONIC_ALERT."""
    await channel.emit("warn", "external", "minor", severity="warning")
    alert = dharma_dir / ".ALGEDONIC_ALERT"
    assert not alert.exists()


# ---------------------------------------------------------------------------
# AlgedonicChannel -- recent / active_alerts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recent_returns_newest_first(channel: AlgedonicChannel):
    """recent() returns signals sorted newest-first."""
    await channel.emit("a", "external", "first", severity="info")
    await channel.emit("b", "external", "second", severity="info")
    await channel.emit("c", "external", "third", severity="info")

    recent = await channel.recent(limit=2)
    assert len(recent) == 2
    assert recent[0].trigger == "c"
    assert recent[1].trigger == "b"


@pytest.mark.asyncio
async def test_active_alerts_sync(channel: AlgedonicChannel):
    """active_alerts property works synchronously."""
    await channel.emit("x", "external", "one", severity="warning")
    await channel.emit("y", "external", "two", severity="info")
    assert len(channel.active_alerts) == 2


# ---------------------------------------------------------------------------
# AlgedonicChannel -- acknowledge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acknowledge_marks_signal(channel: AlgedonicChannel):
    """acknowledge() sets acknowledged=True and acknowledged_at."""
    sig = await channel.emit("ack_me", "external", "test")
    ok = await channel.acknowledge(sig.id)
    assert ok is True

    recent = await channel.recent()
    found = [s for s in recent if s.id == sig.id][0]
    assert found.acknowledged is True
    assert found.acknowledged_at is not None


@pytest.mark.asyncio
async def test_acknowledge_nonexistent_returns_false(channel: AlgedonicChannel):
    """acknowledge() returns False for unknown signal id."""
    ok = await channel.acknowledge("nonexistent_id_1234")
    assert ok is False


@pytest.mark.asyncio
async def test_acknowledge_removes_alert_when_no_critical(
    channel: AlgedonicChannel, dharma_dir: Path
):
    """Acking the last critical signal removes .ALGEDONIC_ALERT."""
    sig = await channel.emit("crit", "security_event", "breach", severity="critical")
    assert (dharma_dir / ".ALGEDONIC_ALERT").exists()

    await channel.acknowledge(sig.id)
    assert not (dharma_dir / ".ALGEDONIC_ALERT").exists()


@pytest.mark.asyncio
async def test_acknowledge_keeps_alert_when_other_critical(
    channel: AlgedonicChannel, dharma_dir: Path
):
    """Acking one critical keeps .ALGEDONIC_ALERT if another critical remains."""
    sig1 = await channel.emit("crit1", "security_event", "one", severity="critical")
    await channel.emit("crit2", "security_event", "two", severity="critical")

    await channel.acknowledge(sig1.id)
    assert (dharma_dir / ".ALGEDONIC_ALERT").exists()


# ---------------------------------------------------------------------------
# AlgedonicChannel -- check_unacknowledged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_unacknowledged_timeout_zero(channel: AlgedonicChannel):
    """With timeout=0, any unacked signal is timed out."""
    await channel.emit("old", "external", "stale", severity="warning")
    timed_out = await channel.check_unacknowledged(timeout_minutes=0)
    assert len(timed_out) == 1


@pytest.mark.asyncio
async def test_check_unacknowledged_safe_mode(
    channel: AlgedonicChannel, dharma_dir: Path
):
    """Critical timed-out signal writes .SAFE_MODE and sets auto_safe_mode."""
    await channel.emit("crit", "error_spike", "bad", severity="critical")
    timed_out = await channel.check_unacknowledged(timeout_minutes=0)

    assert len(timed_out) == 1
    safe_mode = dharma_dir / ".SAFE_MODE"
    assert safe_mode.exists()
    assert "SAFE MODE" in safe_mode.read_text()

    # Verify auto_safe_mode persisted
    recent = await channel.recent()
    critical = [s for s in recent if s.severity == "critical"][0]
    assert critical.auto_safe_mode is True


@pytest.mark.asyncio
async def test_check_unacknowledged_warning_no_safe_mode(
    channel: AlgedonicChannel, dharma_dir: Path
):
    """Warning-only timeout does NOT trigger .SAFE_MODE."""
    await channel.emit("warn", "external", "minor", severity="warning")
    await channel.check_unacknowledged(timeout_minutes=0)
    assert not (dharma_dir / ".SAFE_MODE").exists()


@pytest.mark.asyncio
async def test_check_unacknowledged_large_timeout_no_timeout(
    channel: AlgedonicChannel,
):
    """With a large timeout, freshly emitted signals are not timed out."""
    await channel.emit("fresh", "external", "new", severity="critical")
    timed_out = await channel.check_unacknowledged(timeout_minutes=9999)
    assert len(timed_out) == 0


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_error_spike_no_file(dharma_dir: Path):
    """No session_actions file => None."""
    result = await detect_error_spike(state_dir=dharma_dir)
    assert result is None


@pytest.mark.asyncio
async def test_detect_error_spike_triggers(dharma_dir: Path):
    """Error rate above threshold fires a signal."""
    loops = dharma_dir / "loops"
    loops.mkdir(parents=True)
    actions = loops / "session_actions.jsonl"
    with actions.open("w") as f:
        for i in range(10):
            status = "error" if i < 7 else "ok"
            f.write(json.dumps({"action": f"a{i}", "status": status}) + "\n")

    result = await detect_error_spike(threshold=0.5, state_dir=dharma_dir)
    assert result is not None
    assert result.category == "error_spike"
    assert "0.70" in result.trigger


@pytest.mark.asyncio
async def test_detect_error_spike_below_threshold(dharma_dir: Path):
    """Low error rate => None."""
    loops = dharma_dir / "loops"
    loops.mkdir(parents=True)
    actions = loops / "session_actions.jsonl"
    with actions.open("w") as f:
        for i in range(10):
            f.write(json.dumps({"action": f"a{i}", "status": "ok"}) + "\n")

    result = await detect_error_spike(threshold=0.5, state_dir=dharma_dir)
    assert result is None


@pytest.mark.asyncio
async def test_detect_coherence_collapse_triggers(dharma_dir: Path):
    """TCS below threshold fires a signal."""
    meta = dharma_dir / "meta"
    meta.mkdir(parents=True)
    (meta / "identity_history.jsonl").write_text(
        json.dumps({"tcs": 0.12, "regime": "critical"}) + "\n"
    )

    result = await detect_coherence_collapse(threshold=0.25, state_dir=dharma_dir)
    assert result is not None
    assert result.category == "coherence_collapse"
    assert result.severity == "critical"


@pytest.mark.asyncio
async def test_detect_coherence_collapse_healthy(dharma_dir: Path):
    """TCS above threshold => None."""
    meta = dharma_dir / "meta"
    meta.mkdir(parents=True)
    (meta / "identity_history.jsonl").write_text(
        json.dumps({"tcs": 0.85}) + "\n"
    )

    result = await detect_coherence_collapse(threshold=0.25, state_dir=dharma_dir)
    assert result is None


@pytest.mark.asyncio
async def test_detect_resource_depletion_triggers(dharma_dir: Path):
    """Daily spend above limit fires a signal."""
    from datetime import datetime, timezone

    costs = dharma_dir / "costs"
    costs.mkdir(parents=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ledger = costs / "daily_ledger.jsonl"
    with ledger.open("w") as f:
        f.write(json.dumps({"date": today, "cost": 7.0}) + "\n")
        f.write(json.dumps({"date": today, "cost": 6.5}) + "\n")

    result = await detect_resource_depletion(daily_limit=12.0, state_dir=dharma_dir)
    assert result is not None
    assert result.category == "resource_depletion"
    assert "$13.50" in result.trigger


@pytest.mark.asyncio
@pytest.mark.parametrize("cost_key", ["cost_usd", "estimated_cost_usd"])
async def test_detect_resource_depletion_accepts_current_cost_ledger_fields(
    dharma_dir: Path,
    cost_key: str,
):
    """Resource depletion should read the actual cost-ledger schemas in use."""
    from datetime import datetime, timezone

    costs = dharma_dir / "costs"
    costs.mkdir(parents=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (costs / "daily_ledger.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"date": today, cost_key: 7.25}),
                json.dumps({"timestamp": f"{today}T01:02:03+00:00", cost_key: "5.00"}),
            ]
        )
        + "\n"
    )

    result = await detect_resource_depletion(daily_limit=12.0, state_dir=dharma_dir)

    assert result is not None
    assert result.category == "resource_depletion"
    assert "$12.25" in result.trigger


@pytest.mark.asyncio
async def test_detect_resource_depletion_skips_non_finite_cost_rows(dharma_dir: Path):
    """Poisoned cost rows should not suppress or inflate depletion detection."""
    from datetime import datetime, timezone

    costs = dharma_dir / "costs"
    costs.mkdir(parents=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (costs / "daily_ledger.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"date": today, "estimated_cost_usd": "nan"}),
                json.dumps({"date": today, "estimated_cost_usd": "inf"}),
                json.dumps({"date": today, "cost_usd": 6.5}),
                json.dumps({"timestamp": f"{today}T04:05:06+00:00", "estimated_cost_usd": "6.0"}),
            ]
        )
        + "\n"
    )

    result = await detect_resource_depletion(daily_limit=12.0, state_dir=dharma_dir)

    assert result is not None
    assert "$12.50" in result.trigger


@pytest.mark.asyncio
async def test_detect_resource_depletion_under_limit(dharma_dir: Path):
    """Spend under limit => None."""
    from datetime import datetime, timezone

    costs = dharma_dir / "costs"
    costs.mkdir(parents=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (costs / "daily_ledger.jsonl").write_text(
        json.dumps({"date": today, "cost": 2.0}) + "\n"
    )

    result = await detect_resource_depletion(daily_limit=12.0, state_dir=dharma_dir)
    assert result is None


# ---------------------------------------------------------------------------
# run_detectors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_detectors_all_clear(dharma_dir: Path):
    """When no conditions are met, run_detectors returns empty list."""
    signals = await run_detectors(state_dir=dharma_dir)
    assert signals == []


@pytest.mark.asyncio
async def test_run_detectors_multiple_fires(dharma_dir: Path):
    """run_detectors aggregates signals from multiple detectors."""
    from datetime import datetime, timezone

    # Trigger error spike
    loops = dharma_dir / "loops"
    loops.mkdir(parents=True)
    with (loops / "session_actions.jsonl").open("w") as f:
        for _ in range(10):
            f.write(json.dumps({"status": "error"}) + "\n")

    # Trigger coherence collapse
    meta = dharma_dir / "meta"
    meta.mkdir(parents=True)
    (meta / "identity_history.jsonl").write_text(
        json.dumps({"tcs": 0.05}) + "\n"
    )

    # Trigger resource depletion
    costs = dharma_dir / "costs"
    costs.mkdir(parents=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    (costs / "daily_ledger.jsonl").write_text(
        json.dumps({"date": today, "cost": 15.0}) + "\n"
    )

    signals = await run_detectors(state_dir=dharma_dir)
    categories = sorted(s.category for s in signals)
    assert len(signals) == 3
    assert categories == ["coherence_collapse", "error_spike", "resource_depletion"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_channel_empty(tmp_path: Path):
    """Fresh channel with nonexistent dir returns empty lists."""
    ch = AlgedonicChannel(state_dir=tmp_path / "nonexistent")
    assert ch.active_alerts == []
    recent = await ch.recent()
    assert recent == []
