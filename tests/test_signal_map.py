"""
Tests for signal_map.py — Living consciousness archaeology tracker
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from dharma_swarm.signal_map import (
    SignalMap,
    SignalMapEntry,
    ScanScore,
    ScanHistory
)


@pytest.fixture
def temp_map_path():
    """Temporary path for signal map JSON"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture
def sample_criteria():
    """Sample 7-criteria scores"""
    return {
        "referenced_by": 9,
        "defines_vocab": 10,
        "bridges_domains": 9,
        "testable_claims": 8,
        "compression_ratio": 10,
        "temporal_persistence": 9,
        "actionable": 10
    }


def test_signal_map_init():
    """Test SignalMap initialization"""
    sm = SignalMap()
    assert len(sm.files) == 0
    assert len(sm.blind_spots) == 0
    assert sm.version == 1


def test_add_score(sample_criteria):
    """Test adding a score to a file"""
    sm = SignalMap()
    sm.add_score(
        file_path="/test/file.md",
        composite=9.5,
        criteria=sample_criteria,
        scan_id="scan-001",
        domain="mechanistic",
        one_liner="Test file"
    )
    
    assert "/test/file.md" in sm.files
    entry = sm.files["/test/file.md"]
    assert entry.aggregate == 9.5
    assert entry.confidence == 0.5  # First scan
    assert entry.coverage_count == 1
    assert entry.domain == "mechanistic"


def test_multiple_scores(sample_criteria):
    """Test adding multiple scores to the same file"""
    sm = SignalMap()
    
    # First scan
    sm.add_score("/test/file.md", 9.5, sample_criteria, "scan-001", "mechanistic", "Test")
    
    # Second scan with different score
    criteria_2 = sample_criteria.copy()
    criteria_2["testable_claims"] = 10
    sm.add_score("/test/file.md", 9.7, criteria_2, "scan-002", "mechanistic", "Test")
    
    entry = sm.files["/test/file.md"]
    assert entry.coverage_count == 2
    assert entry.aggregate == pytest.approx((9.5 + 9.7) / 2, rel=0.01)
    assert entry.confidence == 0.6  # 0.5 + 0.1 for second scan


def test_get_top_n(sample_criteria):
    """Test getting top N files"""
    sm = SignalMap()
    
    sm.add_score("/test/file1.md", 9.8, sample_criteria, "scan-001", "mechanistic", "File 1")
    sm.add_score("/test/file2.md", 9.5, sample_criteria, "scan-001", "mechanistic", "File 2")
    sm.add_score("/test/file3.md", 9.2, sample_criteria, "scan-001", "mechanistic", "File 3")
    
    top_2 = sm.get_top_n(n=2)
    assert len(top_2) == 2
    assert top_2[0].path == "/test/file1.md"
    assert top_2[1].path == "/test/file2.md"


def test_get_top_n_with_confidence_filter(sample_criteria):
    """Test get_top_n with confidence threshold"""
    sm = SignalMap()
    
    sm.add_score("/test/file1.md", 9.8, sample_criteria, "scan-001", "mechanistic", "File 1")
    
    # File 2 gets two scans -> higher confidence
    sm.add_score("/test/file2.md", 9.5, sample_criteria, "scan-001", "mechanistic", "File 2")
    sm.add_score("/test/file2.md", 9.6, sample_criteria, "scan-002", "mechanistic", "File 2")
    
    # Filter for confidence >= 0.6
    high_confidence = sm.get_top_n(n=10, min_confidence=0.6)
    assert len(high_confidence) == 1
    assert high_confidence[0].path == "/test/file2.md"


def test_get_low_confidence(sample_criteria):
    """Test getting files with low confidence"""
    sm = SignalMap()
    
    # File 1: single scan = 0.5 confidence
    sm.add_score("/test/file1.md", 9.5, sample_criteria, "scan-001", "mechanistic", "File 1")
    
    # File 2: two scans = 0.6 confidence
    sm.add_score("/test/file2.md", 9.5, sample_criteria, "scan-001", "mechanistic", "File 2")
    sm.add_score("/test/file2.md", 9.6, sample_criteria, "scan-002", "mechanistic", "File 2")
    
    low_conf = sm.get_low_confidence(threshold=0.6)
    assert len(low_conf) == 1
    assert low_conf[0].path == "/test/file1.md"


def test_merge_scan_results(sample_criteria):
    """Test merging batch scan results"""
    sm = SignalMap()
    
    scan_results = {
        "/test/file1.md": (9.5, sample_criteria, "mechanistic", "File 1"),
        "/test/file2.md": (9.2, sample_criteria, "phenomenological", "File 2")
    }
    
    sm.merge_scan_results(scan_results, scan_id="batch-001")
    
    assert len(sm.files) == 2
    assert "/test/file1.md" in sm.files
    assert "/test/file2.md" in sm.files


def test_blind_spots():
    """Test blind spot tracking"""
    sm = SignalMap()
    
    sm.add_blind_spot("Kailash vault (iCloud)")
    sm.add_blind_spot("Deep subdirs")
    
    assert len(sm.blind_spots) == 2
    assert "Kailash vault (iCloud)" in sm.blind_spots
    
    # Adding duplicate should not increase count
    sm.add_blind_spot("Kailash vault (iCloud)")
    assert len(sm.blind_spots) == 2


def test_confidence_decay(sample_criteria):
    """Test confidence decay mechanism"""
    sm = SignalMap()
    sm.add_score("/test/file.md", 9.5, sample_criteria, "scan-001", "mechanistic", "Test")
    
    entry = sm.files["/test/file.md"]
    initial_confidence = entry.confidence
    
    # Decay by 0.1
    entry.decay_confidence(decay_rate=0.1)
    assert entry.confidence == pytest.approx(initial_confidence - 0.1, rel=0.01)
    
    # Decay should not go below 0.1
    for _ in range(10):
        entry.decay_confidence(decay_rate=0.1)
    assert entry.confidence >= 0.1


def test_decay_all(sample_criteria):
    """Test decaying all entries"""
    sm = SignalMap()
    sm.add_score("/test/file1.md", 9.5, sample_criteria, "scan-001", "mechanistic", "File 1")
    sm.add_score("/test/file2.md", 9.2, sample_criteria, "scan-001", "mechanistic", "File 2")
    
    sm.decay_all(decay_rate=0.1)
    
    for entry in sm.files.values():
        assert entry.confidence == pytest.approx(0.4, rel=0.01)


def test_save_and_load(temp_map_path, sample_criteria):
    """Test saving and loading signal map"""
    sm = SignalMap()
    sm.add_score("/test/file1.md", 9.5, sample_criteria, "scan-001", "mechanistic", "File 1")
    sm.add_blind_spot("Test blind spot")
    
    # Save
    sm.save(temp_map_path)
    assert temp_map_path.exists()
    
    # Load
    sm_loaded = SignalMap.load(temp_map_path)
    assert len(sm_loaded.files) == 1
    assert "/test/file1.md" in sm_loaded.files
    assert len(sm_loaded.blind_spots) == 1
    assert sm_loaded.blind_spots[0] == "Test blind spot"


def test_get_by_domain(sample_criteria):
    """Test filtering by domain"""
    sm = SignalMap()
    sm.add_score("/test/file1.md", 9.5, sample_criteria, "scan-001", "mechanistic", "File 1")
    sm.add_score("/test/file2.md", 9.2, sample_criteria, "scan-001", "phenomenological", "File 2")
    sm.add_score("/test/file3.md", 9.0, sample_criteria, "scan-001", "mechanistic", "File 3")
    
    mechanistic_files = sm.get_by_domain("mechanistic")
    assert len(mechanistic_files) == 2
    
    pheno_files = sm.get_by_domain("phenomenological")
    assert len(pheno_files) == 1


def test_get_stats(sample_criteria):
    """Test statistics generation"""
    sm = SignalMap()
    sm.add_score("/test/file1.md", 9.5, sample_criteria, "scan-001", "mechanistic", "File 1")
    sm.add_score("/test/file2.md", 9.0, sample_criteria, "scan-001", "phenomenological", "File 2")
    sm.add_blind_spot("Test spot")
    
    stats = sm.get_stats()
    assert stats["total_files"] == 2
    assert stats["avg_score"] == pytest.approx(9.25, rel=0.01)
    assert stats["avg_confidence"] == 0.5
    assert stats["domains"]["mechanistic"] == 1
    assert stats["domains"]["phenomenological"] == 1
    assert stats["blind_spots"] == 1


def test_as_agent_briefing(sample_criteria):
    """Test agent briefing generation"""
    sm = SignalMap()
    
    # Add files in different tiers
    sm.add_score("/test/tier1.md", 9.8, sample_criteria, "scan-001", "mechanistic", "Tier 1 file")
    sm.add_score("/test/tier2.md", 9.2, sample_criteria, "scan-001", "mechanistic", "Tier 2 file")
    sm.add_score("/test/tier3.md", 8.7, sample_criteria, "scan-001", "mechanistic", "Tier 3 file")
    sm.add_blind_spot("Test blind spot")
    
    briefing = sm.as_agent_briefing(max_files=10)
    
    assert "Signal Map Agent Briefing" in briefing
    assert "Tier 1: Load-Bearing Walls" in briefing
    assert "Tier 2: Structural Beams" in briefing
    assert "Tier 3: Active Connective Tissue" in briefing
    assert "Known Blind Spots" in briefing
    assert "Test blind spot" in briefing


def test_load_nonexistent_file():
    """Test loading from non-existent path returns empty map"""
    sm = SignalMap.load(Path("/nonexistent/path.json"))
    assert len(sm.files) == 0
    assert len(sm.blind_spots) == 0


def test_scan_history_tracking(sample_criteria):
    """Test scan history is tracked"""
    sm = SignalMap()
    
    # Manually add scan history (in practice this would be done by scanning agents)
    sm.scan_history.append(
        ScanHistory(
            id="scan-001",
            timestamp=datetime.now(timezone.utc).isoformat(),
            domains_covered=["mechanistic"],
            files_scored=5,
            agent="test-agent"
        )
    )
    
    stats = sm.get_stats()
    assert stats["total_scans"] == 1
