"""Tests for bridge_coordinator.py — cross-graph bridge discovery."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm.bridge_coordinator import (
    BridgeCoordinator,
    BridgeDiscoveryResult,
)

# Pre-import modules so we can patch their attributes
import dharma_swarm.semantic_gravity as _sg_mod
import dharma_swarm.telos_graph as _tg_mod


# ---------------------------------------------------------------------------
# BridgeDiscoveryResult model
# ---------------------------------------------------------------------------


class TestBridgeDiscoveryResult:
    def test_defaults(self):
        r = BridgeDiscoveryResult()
        assert r.discovered == 0
        assert r.updated == 0
        assert r.errors == []
        assert r.duration_seconds == 0.0
        assert r.phase_counts == {}

    def test_populated(self):
        r = BridgeDiscoveryResult(
            discovered=10,
            updated=3,
            errors=["fail"],
            duration_seconds=1.5,
            phase_counts={"a": 7, "b": 3},
        )
        assert r.discovered == 10
        assert r.updated == 3
        assert len(r.errors) == 1
        assert r.phase_counts["a"] == 7

    def test_serialization(self):
        r = BridgeDiscoveryResult(discovered=5, phase_counts={"x": 5})
        d = r.model_dump()
        assert d["discovered"] == 5
        assert d["phase_counts"]["x"] == 5


# ---------------------------------------------------------------------------
# BridgeCoordinator construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_default_state_dir(self):
        bc = BridgeCoordinator()
        assert bc._state_dir.name == ".dharma"

    def test_custom_state_dir(self, tmp_path):
        bc = BridgeCoordinator(state_dir=tmp_path)
        assert bc._state_dir == tmp_path


# ---------------------------------------------------------------------------
# discover_all — fault isolation
# ---------------------------------------------------------------------------


def _bc_with_db(tmp_path):
    """Create a BridgeCoordinator whose db dir exists."""
    db_dir = tmp_path / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return BridgeCoordinator(state_dir=tmp_path)


class TestDiscoverAll:
    @pytest.mark.asyncio
    async def test_all_discoverers_called(self, tmp_path):
        """All three discoverers run even when graphs are empty."""
        bc = _bc_with_db(tmp_path)

        with (
            patch.object(bc, "_discover_semantic_temporal", new_callable=AsyncMock, return_value=2) as m_st,
            patch.object(bc, "_discover_catalytic_telos", new_callable=AsyncMock, return_value=3) as m_ct,
            patch.object(bc, "_discover_concept_files", new_callable=AsyncMock, return_value=1) as m_cf,
        ):
            result = await bc.discover_all()

        m_st.assert_awaited_once()
        m_ct.assert_awaited_once()
        m_cf.assert_awaited_once()
        assert result.discovered == 6
        assert result.errors == []
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_fault_isolation(self, tmp_path):
        """One failing discoverer doesn't prevent others from running."""
        bc = _bc_with_db(tmp_path)

        with (
            patch.object(bc, "_discover_semantic_temporal", new_callable=AsyncMock, side_effect=RuntimeError("boom")),
            patch.object(bc, "_discover_catalytic_telos", new_callable=AsyncMock, return_value=5),
            patch.object(bc, "_discover_concept_files", new_callable=AsyncMock, return_value=2),
        ):
            result = await bc.discover_all()

        assert result.discovered == 7
        assert len(result.errors) == 1
        assert "boom" in result.errors[0]

    @pytest.mark.asyncio
    async def test_all_discoverers_fail(self, tmp_path):
        """If all fail, result has zero discovered and three errors."""
        bc = _bc_with_db(tmp_path)

        with (
            patch.object(bc, "_discover_semantic_temporal", new_callable=AsyncMock, side_effect=Exception("e1")),
            patch.object(bc, "_discover_catalytic_telos", new_callable=AsyncMock, side_effect=Exception("e2")),
            patch.object(bc, "_discover_concept_files", new_callable=AsyncMock, side_effect=Exception("e3")),
        ):
            result = await bc.discover_all()

        assert result.discovered == 0
        assert len(result.errors) == 3

    @pytest.mark.asyncio
    async def test_duration_measured(self, tmp_path):
        bc = _bc_with_db(tmp_path)

        with (
            patch.object(bc, "_discover_semantic_temporal", new_callable=AsyncMock, return_value=0),
            patch.object(bc, "_discover_catalytic_telos", new_callable=AsyncMock, return_value=0),
            patch.object(bc, "_discover_concept_files", new_callable=AsyncMock, return_value=0),
        ):
            result = await bc.discover_all()

        assert result.duration_seconds >= 0


# ---------------------------------------------------------------------------
# discover_single
# ---------------------------------------------------------------------------


class TestDiscoverSingle:
    @pytest.mark.asyncio
    async def test_valid_algorithm(self, tmp_path):
        bc = _bc_with_db(tmp_path)

        with patch.object(bc, "_discover_semantic_temporal", new_callable=AsyncMock, return_value=4):
            result = await bc.discover_single("semantic_temporal")

        assert result.discovered == 4
        assert result.phase_counts["semantic_temporal"] == 4

    @pytest.mark.asyncio
    async def test_invalid_algorithm(self, tmp_path):
        bc = BridgeCoordinator(state_dir=tmp_path)
        with pytest.raises(ValueError, match="Unknown algorithm"):
            await bc.discover_single("nonexistent")

    @pytest.mark.asyncio
    async def test_single_algorithm_failure(self, tmp_path):
        bc = _bc_with_db(tmp_path)

        with patch.object(bc, "_discover_concept_files", new_callable=AsyncMock, side_effect=RuntimeError("fail")):
            result = await bc.discover_single("concept_files")

        assert result.discovered == 0
        assert len(result.errors) == 1
        assert "fail" in result.errors[0]

    @pytest.mark.asyncio
    async def test_all_three_algorithms_accepted(self, tmp_path):
        """Each algorithm name dispatches correctly."""
        bc = _bc_with_db(tmp_path)

        for algo in ["semantic_temporal", "catalytic_telos", "concept_files"]:
            with patch.object(bc, f"_discover_{algo}", new_callable=AsyncMock, return_value=1):
                result = await bc.discover_single(algo)
                assert result.discovered == 1


# ---------------------------------------------------------------------------
# _discover_semantic_temporal (with mocked graphs)
# ---------------------------------------------------------------------------


def _mock_concept_node(node_id="c1", name="autopoiesis", source_file=""):
    return SimpleNamespace(id=node_id, name=name, source_file=source_file)


class _DictRow(dict):
    """sqlite3.Row-like object that supports both dict and index access."""

    def __init__(self, keys, values):
        super().__init__(zip(keys, values))
        self._values = list(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


def _make_tkg_conn(rows_by_call=None):
    """Build a mock temporal graph connection context manager.

    rows_by_call: list of (term, frequency) tuples or None values.
    """
    rows_by_call = rows_by_call or []
    call_idx = [0]

    class MockConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, *a):
            cursor = MagicMock()
            idx = call_idx[0]
            call_idx[0] += 1
            raw = rows_by_call[idx] if idx < len(rows_by_call) else None
            if raw is not None:
                cursor.fetchone.return_value = _DictRow(["term", "frequency"], raw)
            else:
                cursor.fetchone.return_value = None
            return cursor

    return MockConn()


class TestDiscoverSemanticTemporal:
    @pytest.mark.asyncio
    async def test_no_concepts(self, tmp_path):
        """Empty concept graph → 0 bridges."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        mock_cg = MagicMock()
        mock_cg.all_nodes.return_value = []
        mock_cg.node_count = 0

        mock_registry = AsyncMock()

        with (
            patch.object(_sg_mod.ConceptGraph, "load", new_callable=AsyncMock, return_value=mock_cg),
            patch("dharma_swarm.temporal_graph.TemporalKnowledgeGraph") as MockTKG,
        ):
            count = await bc._discover_semantic_temporal(mock_registry)

        assert count == 0

    @pytest.mark.asyncio
    async def test_concept_matches_temporal(self, tmp_path):
        """When a concept name matches a temporal term, bridge is created."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        node = _mock_concept_node("c1", "autopoiesis")
        mock_cg = MagicMock()
        mock_cg.all_nodes.return_value = [node]
        mock_cg.node_count = 1

        mock_registry = AsyncMock()
        conn = _make_tkg_conn(rows_by_call=[("autopoiesis", 5)])

        with (
            patch.object(_sg_mod.ConceptGraph, "load", new_callable=AsyncMock, return_value=mock_cg),
            patch("dharma_swarm.temporal_graph.TemporalKnowledgeGraph") as MockTKG,
        ):
            mock_tkg = MagicMock()
            mock_tkg._connect.return_value = conn
            MockTKG.return_value = mock_tkg

            count = await bc._discover_semantic_temporal(mock_registry)

        assert count == 1
        mock_registry.upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_concept_no_temporal_match(self, tmp_path):
        """When a concept has no temporal match, no bridge is created."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        node = _mock_concept_node("c1", "unknown_concept")
        mock_cg = MagicMock()
        mock_cg.all_nodes.return_value = [node]
        mock_cg.node_count = 1

        mock_registry = AsyncMock()
        conn = _make_tkg_conn(rows_by_call=[None])

        with (
            patch.object(_sg_mod.ConceptGraph, "load", new_callable=AsyncMock, return_value=mock_cg),
            patch("dharma_swarm.temporal_graph.TemporalKnowledgeGraph") as MockTKG,
        ):
            mock_tkg = MagicMock()
            mock_tkg._connect.return_value = conn
            MockTKG.return_value = mock_tkg

            count = await bc._discover_semantic_temporal(mock_registry)

        assert count == 0
        mock_registry.upsert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_temporal_db_exception_skips_node(self, tmp_path):
        """If temporal DB query fails for one node, it's skipped gracefully."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        nodes = [
            _mock_concept_node("c1", "good"),
            _mock_concept_node("c2", "bad"),
        ]
        mock_cg = MagicMock()
        mock_cg.all_nodes.return_value = nodes
        mock_cg.node_count = 2

        mock_registry = AsyncMock()

        call_count = [0]

        class FlakyConn:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, *a):
                call_count[0] += 1
                if call_count[0] <= 1:
                    cursor = MagicMock()
                    cursor.fetchone.return_value = _DictRow(["term", "frequency"], ("good", 1))
                    return cursor
                raise RuntimeError("db locked")

        with (
            patch.object(_sg_mod.ConceptGraph, "load", new_callable=AsyncMock, return_value=mock_cg),
            patch("dharma_swarm.temporal_graph.TemporalKnowledgeGraph") as MockTKG,
        ):
            mock_tkg = MagicMock()
            mock_tkg._connect.return_value = FlakyConn()
            MockTKG.return_value = mock_tkg

            count = await bc._discover_semantic_temporal(mock_registry)

        assert count == 1  # only the first node succeeded


# ---------------------------------------------------------------------------
# _discover_concept_files (with mocked graphs)
# ---------------------------------------------------------------------------


class TestDiscoverConceptFiles:
    @pytest.mark.asyncio
    async def test_no_concepts(self, tmp_path):
        bc = BridgeCoordinator(state_dir=tmp_path)

        mock_cg = MagicMock()
        mock_cg.all_nodes.return_value = []
        mock_cg.node_count = 0

        mock_registry = AsyncMock()

        with patch.object(_sg_mod.ConceptGraph, "load", new_callable=AsyncMock, return_value=mock_cg):
            count = await bc._discover_concept_files(mock_registry)

        assert count == 0

    @pytest.mark.asyncio
    async def test_concepts_with_source_files(self, tmp_path):
        bc = BridgeCoordinator(state_dir=tmp_path)

        nodes = [
            _mock_concept_node("c1", "autopoiesis", "varela.py"),
            _mock_concept_node("c2", "enaction", ""),  # no file
            _mock_concept_node("c3", "emergence", "kauffman.py"),
        ]
        mock_cg = MagicMock()
        mock_cg.all_nodes.return_value = nodes
        mock_cg.node_count = 3

        mock_registry = AsyncMock()

        with patch.object(_sg_mod.ConceptGraph, "load", new_callable=AsyncMock, return_value=mock_cg):
            count = await bc._discover_concept_files(mock_registry)

        assert count == 2  # only c1 and c3 have source_file
        assert mock_registry.upsert.await_count == 2

    @pytest.mark.asyncio
    async def test_bridge_edge_target_format(self, tmp_path):
        """Bridge edges use file:: prefix for target_id."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        node = _mock_concept_node("c1", "dharma", "dharma.py")
        mock_cg = MagicMock()
        mock_cg.all_nodes.return_value = [node]
        mock_cg.node_count = 1

        mock_registry = AsyncMock()

        with patch.object(_sg_mod.ConceptGraph, "load", new_callable=AsyncMock, return_value=mock_cg):
            count = await bc._discover_concept_files(mock_registry)

        assert count == 1
        edge_arg = mock_registry.upsert.call_args[0][0]
        assert edge_arg.target_id == "file::dharma.py"
        assert edge_arg.confidence == 0.95
        assert edge_arg.discovered_by == "bridge_coordinator.concept_files"


# ---------------------------------------------------------------------------
# _discover_catalytic_telos (with mocked graphs)
# ---------------------------------------------------------------------------


def _mock_telos_graph(objectives=None, load_error=None):
    """Create a mock TelosGraph with sync list_objectives + async load."""
    mock = MagicMock()
    if load_error:
        mock.load = AsyncMock(side_effect=load_error)
    else:
        mock.load = AsyncMock()
    mock.list_objectives.return_value = objectives or []
    return mock


class TestDiscoverCatalyticTelos:
    @pytest.mark.asyncio
    async def test_no_catalytic_nodes(self, tmp_path):
        bc = BridgeCoordinator(state_dir=tmp_path)

        mock_registry = AsyncMock()

        mock_cat = MagicMock()
        mock_cat._nodes = {}

        mock_telos = _mock_telos_graph([
            SimpleNamespace(id="o1", name="improve coherence"),
        ])

        with (
            patch("dharma_swarm.catalytic_graph.CatalyticGraph", return_value=mock_cat),
            patch.object(_tg_mod, "TelosGraph", return_value=mock_telos),
        ):
            count = await bc._discover_catalytic_telos(mock_registry)

        assert count == 0

    @pytest.mark.asyncio
    async def test_no_objectives(self, tmp_path):
        bc = BridgeCoordinator(state_dir=tmp_path)

        mock_registry = AsyncMock()

        mock_cat = MagicMock()
        mock_cat._nodes = {"semantic_gravity": True}

        mock_telos = _mock_telos_graph([])

        with (
            patch("dharma_swarm.catalytic_graph.CatalyticGraph", return_value=mock_cat),
            patch.object(_tg_mod, "TelosGraph", return_value=mock_telos),
        ):
            count = await bc._discover_catalytic_telos(mock_registry)

        assert count == 0

    @pytest.mark.asyncio
    async def test_word_overlap_match(self, tmp_path):
        """Catalytic node with word overlap to telos objective creates bridge."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        mock_registry = AsyncMock()

        mock_cat = MagicMock()
        mock_cat._nodes = {"semantic_gravity_engine": True}
        mock_cat.load.return_value = True

        mock_telos = _mock_telos_graph([
            SimpleNamespace(id="o1", name="enhance semantic gravity processing"),
        ])

        with (
            patch("dharma_swarm.catalytic_graph.CatalyticGraph", return_value=mock_cat),
            patch.object(_tg_mod, "TelosGraph", return_value=mock_telos),
        ):
            count = await bc._discover_catalytic_telos(mock_registry)

        assert count >= 1

    @pytest.mark.asyncio
    async def test_no_word_overlap_no_match(self, tmp_path):
        """When no significant words overlap, no bridge is created."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        mock_registry = AsyncMock()

        mock_cat = MagicMock()
        mock_cat._nodes = {"abc_xyz_pqr": True}
        mock_cat.load.return_value = True

        mock_telos = _mock_telos_graph([
            SimpleNamespace(id="o1", name="completely different topic here now"),
        ])

        with (
            patch("dharma_swarm.catalytic_graph.CatalyticGraph", return_value=mock_cat),
            patch.object(_tg_mod, "TelosGraph", return_value=mock_telos),
        ):
            count = await bc._discover_catalytic_telos(mock_registry)

        assert count == 0

    @pytest.mark.asyncio
    async def test_telos_load_failure(self, tmp_path):
        """If TelosGraph fails to load, returns 0 gracefully."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        mock_registry = AsyncMock()

        mock_cat = MagicMock()
        mock_cat._nodes = {"node1": True}
        mock_cat.load.return_value = True

        mock_telos = _mock_telos_graph(load_error=RuntimeError("db locked"))

        with (
            patch("dharma_swarm.catalytic_graph.CatalyticGraph", return_value=mock_cat),
            patch.object(_tg_mod, "TelosGraph", return_value=mock_telos),
        ):
            count = await bc._discover_catalytic_telos(mock_registry)

        assert count == 0

    @pytest.mark.asyncio
    async def test_confidence_calculation(self, tmp_path):
        """Confidence scales with word overlap ratio, capped at 0.9."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        mock_registry = AsyncMock()

        mock_cat = MagicMock()
        mock_cat._nodes = {"semantic_gravity_autopoiesis_engine": True}
        mock_cat.load.return_value = True

        mock_telos = _mock_telos_graph([
            SimpleNamespace(id="o1", name="semantic gravity autopoiesis analysis engine"),
        ])

        with (
            patch("dharma_swarm.catalytic_graph.CatalyticGraph", return_value=mock_cat),
            patch.object(_tg_mod, "TelosGraph", return_value=mock_telos),
        ):
            count = await bc._discover_catalytic_telos(mock_registry)

        assert count == 1
        edge = mock_registry.upsert.call_args[0][0]
        assert 0.5 <= edge.confidence <= 0.9

    @pytest.mark.asyncio
    async def test_short_words_ignored(self, tmp_path):
        """Words <= 3 chars are not considered for overlap matching."""
        bc = BridgeCoordinator(state_dir=tmp_path)

        mock_registry = AsyncMock()

        mock_cat = MagicMock()
        mock_cat._nodes = {"to_be_or_not": True}
        mock_cat.load.return_value = True

        mock_telos = _mock_telos_graph([
            SimpleNamespace(id="o1", name="for and the but"),
        ])

        with (
            patch("dharma_swarm.catalytic_graph.CatalyticGraph", return_value=mock_cat),
            patch.object(_tg_mod, "TelosGraph", return_value=mock_telos),
        ):
            count = await bc._discover_catalytic_telos(mock_registry)

        # All words are <=3 chars, so node_words is empty → skip
        assert count == 0


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


class TestSummary:
    @pytest.mark.asyncio
    async def test_summary_empty_db(self, tmp_path):
        """Summary with empty bridge registry."""
        bc = _bc_with_db(tmp_path)

        from dharma_swarm.bridge_registry import BridgeRegistry

        reg = BridgeRegistry(db_path=tmp_path / "db" / "bridges.db")
        await reg.init()
        await reg.close()

        info = await bc.summary()
        assert info["total_bridges"] == 0
        assert info["by_source_graph"] == {}
        assert info["by_edge_type"] == {}

    @pytest.mark.asyncio
    async def test_summary_with_edges(self, tmp_path):
        """Summary reflects actual edge counts in the registry."""
        bc = _bc_with_db(tmp_path)

        from dharma_swarm.bridge_registry import (
            BridgeEdge,
            BridgeEdgeKind,
            BridgeRegistry,
            GraphOrigin,
        )

        reg = BridgeRegistry(db_path=tmp_path / "db" / "bridges.db")
        await reg.init()
        await reg.upsert(BridgeEdge(
            source_graph=GraphOrigin.SEMANTIC,
            source_id="s1",
            target_graph=GraphOrigin.TELOS,
            target_id="t1",
            edge_type=BridgeEdgeKind.IMPLEMENTS_CONCEPT,
            confidence=0.8,
        ))
        await reg.upsert(BridgeEdge(
            source_graph=GraphOrigin.SEMANTIC,
            source_id="s2",
            target_graph=GraphOrigin.TEMPORAL,
            target_id="t2",
            edge_type=BridgeEdgeKind.RELATES_TO,
            confidence=0.7,
        ))
        await reg.close()

        info = await bc.summary()
        assert info["total_bridges"] == 2
        assert "semantic" in info["by_source_graph"]
