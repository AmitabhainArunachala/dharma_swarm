"""Tests for the Context Agent — autonomous nervous system."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from dharma_swarm.context_agent import (
    ContextAgent,
    Intelligence,
    NervousSystem,
    assemble_package,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dharma(tmp_path: Path) -> Path:
    """Create a minimal ~/.dharma-like structure for testing."""
    dharma = tmp_path / ".dharma"
    (dharma / "shared").mkdir(parents=True)
    (dharma / "meta" / "history").mkdir(parents=True)
    (dharma / "stigmergy").mkdir(parents=True)
    (dharma / "state").mkdir(parents=True)
    (dharma / "context" / "packages").mkdir(parents=True)
    (dharma / "context" / "distilled").mkdir(parents=True)
    (dharma / "context" / "dreams").mkdir(parents=True)
    (dharma / "context" / "bridge_notes").mkdir(parents=True)
    (dharma / "seeds").mkdir(parents=True)
    (dharma / "subconscious").mkdir(parents=True)

    # Write minimal state files
    (dharma / ".FOCUS").write_text("moment by moment smart evolution")
    (dharma / "thread_state.json").write_text(json.dumps({
        "current_thread": "mechanistic",
        "contributions": {"mechanistic": 49, "phenomenological": 0,
                          "architectural": 0, "alignment": 0, "scaling": 0},
    }))
    (dharma / "meta" / "recognition_seed.md").write_text(
        "# Recognition Seed\nTCS=0.942\n"
    )
    (dharma / "state" / "NOW.json").write_text(json.dumps({"health": {"status": "GREEN"}}))
    (dharma / "stigmergy" / "dgc_health.json").write_text(json.dumps({
        "daemon_pid": 12345, "agent_count": 10,
    }))
    (dharma / "stigmergy" / "mycelium_identity_tcs.json").write_text(json.dumps({
        "tcs": 0.942, "regime": "stable",
    }))
    (dharma / "stigmergy" / "mycelium_scoring_report.json").write_text(json.dumps({
        "scored_count": 38, "mean_stars": 6.3,
    }))
    (dharma / "stigmergy" / "marks.jsonl").write_text(
        '{"agent":"test","salience":0.5}\n'
    )
    (dharma / "meta" / "cascade_history.jsonl").write_text(
        '{"domain":"code","converged":true,"best_fitness":0.5}\n'
    )
    (dharma / "shared" / "jk_pulse.md").write_text("JK PULSE GREEN")
    (dharma / "shared" / "jk_alert.md").write_text("No alerts")

    return dharma


# ---------------------------------------------------------------------------
# NervousSystem tests
# ---------------------------------------------------------------------------

class TestNervousSystem:
    def test_scan_freshness_with_files(self, tmp_dharma: Path) -> None:
        """Freshness scan should detect existing files and score them."""
        ns = NervousSystem(base_path=tmp_dharma)
        result = ns.scan_freshness()

        assert ".FOCUS" in result
        assert result[".FOCUS"]["exists"] is True
        assert result[".FOCUS"]["freshness"] > 0.5  # just created

    def test_scan_freshness_missing_files(self, tmp_dharma: Path) -> None:
        """Should handle missing files gracefully."""
        ns = NervousSystem(base_path=tmp_dharma)
        result = ns.scan_freshness()

        # daemon.pid doesn't exist
        assert result["daemon.pid"]["exists"] is False
        assert result["daemon.pid"]["freshness"] == 0.0

    def test_assess_health_computes_score(self, tmp_dharma: Path) -> None:
        """Health assessment should produce a score between 0 and 1."""
        ns = NervousSystem(base_path=tmp_dharma)
        freshness = ns.scan_freshness()
        health = ns.assess_health(freshness)

        assert 0.0 <= health["score"] <= 1.0
        assert "alerts" in health
        assert "timestamp" in health

    def test_thread_balance_all_one_thread(self, tmp_dharma: Path) -> None:
        """Thread balance should be low when all contributions are in one thread."""
        ns = NervousSystem(base_path=tmp_dharma)
        balance = ns._compute_thread_balance()

        # mechanistic=49, all others=0 → very unbalanced
        assert balance < 0.2

    def test_thread_balance_even_distribution(self, tmp_dharma: Path) -> None:
        """Thread balance should be high when contributions are even."""
        (tmp_dharma / "thread_state.json").write_text(json.dumps({
            "current_thread": "mechanistic",
            "contributions": {"mechanistic": 10, "phenomenological": 10,
                              "architectural": 10, "alignment": 10, "scaling": 10},
        }))

        ns = NervousSystem(base_path=tmp_dharma)
        balance = ns._compute_thread_balance()

        assert balance > 0.9  # nearly perfect balance

    def test_find_bloated_notes(self, tmp_dharma: Path) -> None:
        """Should identify agent notes exceeding 50KB."""
        notes_path = tmp_dharma / "shared" / "researcher_notes.md"
        notes_path.write_text("x" * 60_000)  # 60KB

        ns = NervousSystem(base_path=tmp_dharma)
        bloated = ns.find_bloated_notes()

        assert len(bloated) == 1
        assert bloated[0][0] == "researcher"
        assert bloated[0][2] >= 58  # ~58KB

    def test_no_bloated_notes_when_small(self, tmp_dharma: Path) -> None:
        """Should return empty when all notes are small."""
        notes_path = tmp_dharma / "shared" / "researcher_notes.md"
        notes_path.write_text("small note")

        ns = NervousSystem(base_path=tmp_dharma)
        bloated = ns.find_bloated_notes()

        assert len(bloated) == 0


# ---------------------------------------------------------------------------
# Intelligence tests
# ---------------------------------------------------------------------------

class TestIntelligence:
    @pytest.mark.asyncio
    async def test_distill_notes_splits_and_calls_llm(self, tmp_dharma: Path) -> None:
        """Distillation should split notes and call LLM for summary."""
        notes_path = tmp_dharma / "shared" / "test_notes.md"
        entries = ["## Entry %d\nSome findings about item %d\n---" % (i, i) for i in range(10)]
        notes_path.write_text("\n---\n".join(entries))

        intel = Intelligence(base_path=tmp_dharma)
        intel._complete = AsyncMock(return_value="Key finding: X=42")

        result = await intel.distill_notes("test", notes_path)

        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "Key finding: X=42" in content
        assert "Recent Entries" in content

    @pytest.mark.asyncio
    async def test_distill_notes_skips_small_files(self, tmp_dharma: Path) -> None:
        """Should not distill files with fewer than 4 entries."""
        notes_path = tmp_dharma / "shared" / "small_notes.md"
        notes_path.write_text("## Entry 1\nSmall file\n")

        intel = Intelligence(base_path=tmp_dharma)
        result = await intel.distill_notes("test", notes_path)
        assert result is None

    @pytest.mark.asyncio
    async def test_cross_pollinate_calls_llm(self, tmp_dharma: Path) -> None:
        """Cross-pollination should read multiple agent notes and call LLM."""
        (tmp_dharma / "shared" / "researcher_notes.md").write_text("Finding about L27 activation")
        (tmp_dharma / "shared" / "archeologist_notes.md").write_text("PSMV seed about witnessing")

        intel = Intelligence(base_path=tmp_dharma)
        intel._complete = AsyncMock(return_value="Connection: L27 relates to witnessing")
        # Need to set agent notes to our test paths
        intel._agent_notes = {
            "researcher": tmp_dharma / "shared" / "researcher_notes.md",
            "archeologist": tmp_dharma / "shared" / "archeologist_notes.md",
        }

        result = await intel.cross_pollinate()

        assert result is not None
        assert "bridge_" in result.name

    @pytest.mark.asyncio
    async def test_generate_questions_returns_list(self, tmp_dharma: Path) -> None:
        """Question generation should return a list of question strings."""
        intel = Intelligence(base_path=tmp_dharma)
        intel._complete = AsyncMock(
            return_value="1. Why is mechanistic thread at 49 but others at 0?\n"
                         "2. What would phenomenological R_V look like?\n"
        )

        questions = await intel.generate_questions({
            ".FOCUS": {"exists": True, "freshness": 0.9, "tier": 3},
        })

        assert len(questions) >= 1
        assert any("?" in q for q in questions)


# ---------------------------------------------------------------------------
# ContextAgent integration tests
# ---------------------------------------------------------------------------

class TestContextAgent:
    @pytest.mark.asyncio
    async def test_run_cycle_produces_report(self, tmp_dharma: Path) -> None:
        """A full cycle should produce a health report and write files."""
        from dharma_swarm.signal_bus import SignalBus

        bus = SignalBus()
        agent = ContextAgent(signal_bus=bus, base_path=tmp_dharma)

        report = await agent.run_cycle()

        assert "health" in report
        assert report["health"]["score"] > 0.0
        assert report["cycle"] == 1

        # Should have emitted CONTEXT_HEALTH signal
        signals = bus.drain(["CONTEXT_HEALTH"])
        assert len(signals) >= 1
        assert signals[0]["score"] > 0.0

    @pytest.mark.asyncio
    async def test_run_cycle_writes_freshness_file(self, tmp_dharma: Path) -> None:
        """Cycle should write freshness.json to context dir."""
        from dharma_swarm.signal_bus import SignalBus

        agent = ContextAgent(signal_bus=SignalBus(), base_path=tmp_dharma)
        await agent.run_cycle()

        freshness_path = tmp_dharma / "context" / "freshness.json"
        assert freshness_path.exists()
        data = json.loads(freshness_path.read_text())
        assert "health" in data
        assert "freshness" in data

    @pytest.mark.asyncio
    async def test_run_cycle_writes_packages(self, tmp_dharma: Path) -> None:
        """Cycle should write pre-assembled context packages."""
        from dharma_swarm.signal_bus import SignalBus

        agent = ContextAgent(signal_bus=SignalBus(), base_path=tmp_dharma)
        await agent.run_cycle()

        packages_dir = tmp_dharma / "context" / "packages"
        assert (packages_dir / "session_start.md").exists()
        assert (packages_dir / "system_health.md").exists()

    @pytest.mark.asyncio
    async def test_health_alerts_on_stale_context(self, tmp_dharma: Path) -> None:
        """Should emit CONTEXT_STALE when health drops below threshold."""
        from dharma_swarm.signal_bus import SignalBus
        import os

        # Make all files look old by touching them with old timestamps
        old_time = 1700000000  # ~2023
        for f in tmp_dharma.rglob("*"):
            if f.is_file():
                os.utime(f, (old_time, old_time))

        bus = SignalBus()
        agent = ContextAgent(signal_bus=bus, base_path=tmp_dharma)
        report = await agent.run_cycle()

        # Health should be low
        assert report["health"]["score"] < HEALTH_ALERT

        # Should have stale signals
        stale_signals = bus.drain(["CONTEXT_STALE"])
        assert len(stale_signals) >= 1


# Import threshold for the last test
from dharma_swarm.context_agent import HEALTH_ALERT
