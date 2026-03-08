"""Tests for Merkle log tamper-evident audit trail."""

import pytest
from pathlib import Path
import tempfile

from dharma_swarm.merkle_log import MerkleLog


def test_merkle_log_append():
    """Test basic append and hash chaining."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test_merkle.json"
        log = MerkleLog(log_file)

        # Append first entry
        root1 = log.append({"mutation": "add docstring", "id": "001"})
        assert len(root1) == 64  # SHA-256 hex = 64 chars
        assert log.get_chain_length() == 1

        # Append second entry
        root2 = log.append({"mutation": "optimize loop", "id": "002"})
        assert len(root2) == 64
        assert log.get_chain_length() == 2

        # Roots should be different
        assert root1 != root2


def test_merkle_log_persistence():
    """Test that log persists to disk and reloads correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test_merkle.json"

        # Create log and add entries
        log1 = MerkleLog(log_file)
        root1 = log1.append({"data": "first"})
        root2 = log1.append({"data": "second"})

        # Reload from disk
        log2 = MerkleLog(log_file)
        assert log2.get_chain_length() == 2
        assert log2.get_root() == root2


def test_merkle_log_verify_with_data():
    """Test full verification with original data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test_merkle.json"
        log = MerkleLog(log_file)

        # Store original data
        data_store = [
            {"mutation": "add docstring"},
            {"mutation": "optimize loop"},
            {"mutation": "add type hints"}
        ]

        # Append all entries
        for data in data_store:
            log.append(data)

        # Verify with original data
        valid, last_index = log.verify_with_data(data_store)
        assert valid
        assert last_index == 3


def test_merkle_log_detects_tampering():
    """Test that tampering with data breaks verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test_merkle.json"
        log = MerkleLog(log_file)

        # Original data
        data_store = [
            {"mutation": "add docstring"},
            {"mutation": "optimize loop"},
        ]

        for data in data_store:
            log.append(data)

        # Tamper with data
        tampered_data = [
            {"mutation": "add docstring"},
            {"mutation": "TAMPERED DATA"},  # Modified!
        ]

        # Verification should fail
        valid, broken_index = log.verify_with_data(tampered_data)
        assert not valid
        assert broken_index == 1  # Second entry is where tampering detected


def test_merkle_log_empty_chain():
    """Test empty chain behavior."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "test_merkle.json"
        log = MerkleLog(log_file)

        assert log.get_chain_length() == 0
        assert log.get_root() is None

        # Empty chain is valid
        valid, _ = log.verify_chain()
        assert valid


def test_merkle_log_deterministic_hashing():
    """Test that same data produces same hash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file1 = Path(tmpdir) / "log1.json"
        log_file2 = Path(tmpdir) / "log2.json"

        log1 = MerkleLog(log_file1)
        log2 = MerkleLog(log_file2)

        # Same data
        data = {"mutation": "test", "value": 123}

        root1 = log1.append(data)
        root2 = log2.append(data)

        # Should produce identical hashes
        assert root1 == root2
