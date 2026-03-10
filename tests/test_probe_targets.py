"""Tests for Darwin probe target registry."""

from dharma_swarm.probe_targets import ProbeTargetRegistry


def test_probe_target_registry_prefers_exact_match(tmp_path):
    registry = ProbeTargetRegistry.from_configs(
        [
            {
                "component_pattern": "pkg/*.py",
                "workspace": tmp_path / "glob",
                "test_command": "python3 -m pytest tests/test_pkg.py -q",
                "timeout": 7.0,
                "priority": 1,
            },
            {
                "component_pattern": "pkg/sample.py",
                "workspace": tmp_path / "exact",
                "test_command": "python3 -m pytest tests/test_sample.py -q",
                "timeout": 5.0,
                "priority": 0,
            },
        ]
    )

    resolved = registry.resolve("pkg/sample.py")

    assert resolved is not None
    assert resolved.matched_pattern == "pkg/sample.py"
    assert resolved.workspace == (tmp_path / "exact").resolve()
    assert resolved.test_command == "python3 -m pytest tests/test_sample.py -q"
    assert resolved.timeout == 5.0


def test_probe_target_registry_matches_basename_glob(tmp_path):
    registry = ProbeTargetRegistry()
    registry.register(
        "*.service.py",
        workspace=tmp_path / "services",
        test_command="python3 -m pytest tests/test_services.py -q",
        timeout=9.0,
    )

    resolved = registry.resolve("pkg/payment.service.py")

    assert resolved is not None
    assert resolved.matched_pattern == "*.service.py"
    assert resolved.workspace == (tmp_path / "services").resolve()
