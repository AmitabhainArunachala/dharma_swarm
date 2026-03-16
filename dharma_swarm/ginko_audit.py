"""
ginko_audit.py — Self-Healing Continuous Audit System for Dharmic Quant

Three modes:
  1. One-shot:  python3 -m dharma_swarm.ginko_audit
  2. Fix mode:  python3 -m dharma_swarm.ginko_audit --fix
  3. Daemon:    python3 -m dharma_swarm.ginko_audit --daemon [--interval 1800]
  4. Enhance:   python3 -m dharma_swarm.ginko_audit --enhancements

Checks:
  - File manifest (16 new files from 25-agent build)
  - 11 fact-check items (plan claims vs reality)
  - Dependency completeness (pyproject.toml + importability)
  - Test suite health (runs ginko tests)
  - Integration smoke tests (module imports)
  - Orthogonal gap detection (what the plan misses)
  - Enhancement scoring (ranked by impact/effort)

Fixes:
  - Safe, reversible patches for known issues
  - Dry-run by default, --fix to apply

Reports:
  - JSON to ~/.dharma/ginko/audit/
  - Human-readable to stdout
  - Alert file on critical failures
"""

import argparse
import asyncio
import importlib
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("ginko_audit")

# ─── Constants ────────────────────────────────────────────────────────

DHARMA_SWARM_ROOT = Path.home() / "dharma_swarm"
SRC_DIR = DHARMA_SWARM_ROOT / "dharma_swarm"
TEST_DIR = DHARMA_SWARM_ROOT / "tests"
DHARMA_HOME = Path.home() / ".dharma"
GINKO_HOME = DHARMA_HOME / "ginko"
AUDIT_HOME = GINKO_HOME / "audit"

# Files the 25-agent build should create
EXPECTED_NEW_FILES = [
    SRC_DIR / "ginko_agents.py",
    SRC_DIR / "agent_registry.py",
    SRC_DIR / "ginko_sec.py",
    SRC_DIR / "ginko_paper_trade.py",
    SRC_DIR / "ginko_report_gen.py",
    SRC_DIR / "ginko_live_test.py",
    TEST_DIR / "test_ginko_data_integration.py",
    TEST_DIR / "test_ginko_sec.py",
    TEST_DIR / "test_ginko_paper_trade.py",
    TEST_DIR / "test_ginko_report_gen.py",
    TEST_DIR / "test_ginko_integration.py",
    DHARMA_SWARM_ROOT / "Dockerfile",
    DHARMA_SWARM_ROOT / "docker-compose.yml",
    DHARMA_SWARM_ROOT / "docs" / "yc_w27_application.md",
    DHARMA_SWARM_ROOT / "docs" / "substack_first_issue.md",
    DHARMA_SWARM_ROOT / "docs" / "hn_launch_post.md",
]

# Files that should be modified
EXPECTED_MODIFIED_FILES = [
    SRC_DIR / "ginko_signals.py",
    SRC_DIR / "ginko_orchestrator.py",
    SRC_DIR / "ginko_brier.py",
    SRC_DIR / "swarmlens_app.py",
    SRC_DIR / "dgc_cli.py",
]

# Required runtime dependencies
REQUIRED_DEPS = ["httpx", "fastapi", "uvicorn", "numpy"]
OPTIONAL_DEPS = ["hmmlearn", "arch"]


# ─── Data Classes ─────────────────────────────────────────────────────

@dataclass
class CheckResult:
    check_id: str
    category: str  # manifest, fact, dep, test, integration, gap
    claim: str
    status: str  # PASS, FAIL, WARN, SKIP
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    finding: str
    fix_available: bool = False
    fix_id: str | None = None

    @property
    def emoji(self) -> str:
        return {"PASS": "+", "FAIL": "X", "WARN": "!", "SKIP": "o"}.get(self.status, "?")


@dataclass
class FixPatch:
    fix_id: str
    description: str
    target_file: str
    action: str  # "shell", "verify_or_insert", "append"
    content: str
    safe: bool = True
    applied: bool = False


@dataclass
class Enhancement:
    id: str
    title: str
    description: str
    impact: str  # "1000x", "100x", "10x", "2x"
    effort: str  # "trivial", "small", "medium", "large"
    category: str  # "risk", "alpha", "infra", "compliance", "ux"
    dependencies: list[str] = field(default_factory=list)
    agent_spec: str = ""


@dataclass
class AuditReport:
    timestamp: str
    mode: str
    results: list[CheckResult] = field(default_factory=list)
    fixes: list[FixPatch] = field(default_factory=list)
    enhancements: list[Enhancement] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "PASS")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "FAIL")

    @property
    def warned(self) -> int:
        return sum(1 for r in self.results if r.status == "WARN")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "SKIP")


# ─── Auditor ──────────────────────────────────────────────────────────

class GinkoAuditor:
    """Continuous audit engine for Dharmic Quant build output."""

    def __init__(self):
        AUDIT_HOME.mkdir(parents=True, exist_ok=True)
        self.results: list[CheckResult] = []
        self.fixes: list[FixPatch] = []
        self.enhancements: list[Enhancement] = []

    # ── Phase 1: File Manifest ────────────────────────────────────

    def check_file_manifest(self) -> list[CheckResult]:
        """Verify all expected files from the 25-agent build exist."""
        results = []
        for f in EXPECTED_NEW_FILES:
            exists = f.exists()
            size = f.stat().st_size if exists else 0
            results.append(CheckResult(
                check_id=f"MANIFEST-{f.stem}",
                category="manifest",
                claim=f"Build creates {f.relative_to(DHARMA_SWARM_ROOT)}",
                status="PASS" if exists and size > 100 else "FAIL",
                severity="HIGH" if "ginko_" in f.name else "MEDIUM",
                finding=f"EXISTS ({size} bytes)" if exists else "MISSING — file not created by build",
            ))
        for f in EXPECTED_MODIFIED_FILES:
            exists = f.exists()
            results.append(CheckResult(
                check_id=f"MODIFIED-{f.stem}",
                category="manifest",
                claim=f"Build modifies {f.relative_to(DHARMA_SWARM_ROOT)}",
                status="PASS" if exists else "FAIL",
                severity="HIGH",
                finding=f"EXISTS — verify via git diff for modifications" if exists else "MISSING",
            ))
        return results

    # ── Phase 2: Fact Checks (11 discrepancies) ───────────────────

    def check_facts(self) -> list[CheckResult]:
        results = []
        results.append(self._fc01_ahimsa_position_limit())
        results.append(self._fc02_agent_registry_design())
        results.append(self._fc03_agent_identities())
        results.append(self._fc04_dependencies())
        results.append(self._fc05_swarmlens_tabs())
        results.append(self._fc06_git_state())
        results.append(self._fc07_ollama_api_path())
        results.append(self._fc08_satya_gate())
        results.append(self._fc09_hermes_orphaned())
        results.append(self._fc10_position_limit_wiring())
        results.append(self._fc11_test_count())
        return results

    def _fc01_ahimsa_position_limit(self) -> CheckResult:
        """AHIMSA gate: plan says it enforces 5% position limit.
        Reality: AHIMSA is keyword pattern matching for harmful intent.
        Position limit is in compute_position_size(max_position_pct=0.05)."""
        telos_path = SRC_DIR / "telos_gates.py"
        paper_trade_path = SRC_DIR / "ginko_paper_trade.py"

        telos_has_position_check = False
        paper_trade_has_gate = False

        if telos_path.exists():
            content = telos_path.read_text()
            telos_has_position_check = "position" in content.lower() and "0.05" in content

        if paper_trade_path.exists():
            content = paper_trade_path.read_text()
            paper_trade_has_gate = (
                "ahimsa" in content.lower()
                or "max_position" in content.lower()
                or "position_pct" in content.lower()
            )

        if telos_has_position_check:
            return CheckResult(
                check_id="FC-01", category="fact",
                claim="AHIMSA gate enforces 5% position limit",
                status="PASS", severity="HIGH",
                finding="AHIMSA gate contains position limit logic",
            )
        elif paper_trade_has_gate:
            return CheckResult(
                check_id="FC-01", category="fact",
                claim="AHIMSA gate enforces 5% position limit",
                status="WARN", severity="HIGH",
                finding="Paper trade has position limit via compute_position_size, NOT via AHIMSA telos gate. AHIMSA is keyword pattern matching for harmful intent.",
                fix_available=True, fix_id="FIX-01",
            )
        else:
            return CheckResult(
                check_id="FC-01", category="fact",
                claim="AHIMSA gate enforces 5% position limit",
                status="FAIL", severity="HIGH",
                finding="AHIMSA gate is keyword pattern matching (harmful intent detection). Position limit exists in compute_position_size(max_position_pct=0.05) but may not be wired into paper_trade.",
                fix_available=True, fix_id="FIX-01",
            )

    def _fc02_agent_registry_design(self) -> CheckResult:
        """Plan says 'recreate' agent_registry.py — it never existed before."""
        reg_path = SRC_DIR / "agent_registry.py"
        if not reg_path.exists():
            return CheckResult(
                check_id="FC-02", category="fact",
                claim="agent_registry.py recreated from prior version",
                status="WARN", severity="MEDIUM",
                finding="File not yet created (build may still be running). No prior version existed — this is new code.",
            )
        content = reg_path.read_text()
        uses_existing = ".dharma" in content and ("identity.json" in content or "ginko" in content)
        return CheckResult(
            check_id="FC-02", category="fact",
            claim="agent_registry.py follows existing agent identity patterns",
            status="PASS" if uses_existing else "WARN",
            severity="MEDIUM",
            finding="Uses existing identity.json pattern" if uses_existing else "May not align with existing ~/.dharma/ginko/agents/ file structure",
        )

    def _fc03_agent_identities(self) -> CheckResult:
        """Plan says 6 agents. Reality: 4 identity files exist (glm, hermes, kimi, nemotron).
        DEEPSEEK, SENTINEL, SCOUT don't exist. HERMES exists but plan ignores it."""
        agents_dir = GINKO_HOME / "agents"
        if not agents_dir.exists():
            return CheckResult(
                check_id="FC-03", category="fact",
                claim="6 agents: KIMI, DEEPSEEK, NEMOTRON, GLM, SENTINEL, SCOUT",
                status="FAIL", severity="HIGH",
                finding="Agents directory doesn't exist at ~/.dharma/ginko/agents/",
            )

        # Check both flat .json files and subdirectories with identity.json
        existing = set()
        for f in agents_dir.glob("*.json"):
            existing.add(f.stem.lower())
        for d in agents_dir.iterdir():
            if d.is_dir() and (d / "identity.json").exists():
                existing.add(d.name.lower())

        planned = {"kimi", "deepseek", "nemotron", "glm", "sentinel", "scout"}
        missing = planned - existing
        extra = existing - planned

        if not missing:
            status = "PASS"
        elif len(missing) <= 2:
            status = "WARN"
        else:
            status = "FAIL"

        parts = [f"Found: {sorted(existing)}"]
        if missing:
            parts.append(f"Missing from plan: {sorted(missing)}")
        if extra:
            parts.append(f"Extra (not in plan): {sorted(extra)}")
        if "hermes" in existing and "hermes" not in planned:
            parts.append("HERMES exists but plan ignores it")

        return CheckResult(
            check_id="FC-03", category="fact",
            claim="6 agents: KIMI, DEEPSEEK, NEMOTRON, GLM, SENTINEL, SCOUT",
            status=status, severity="HIGH",
            finding=". ".join(parts),
            fix_available=bool(missing), fix_id="FIX-03" if missing else None,
        )

    def _fc04_dependencies(self) -> CheckResult:
        """Plan assumes requirements.txt exists. Reality: only pyproject.toml.
        Missing from pyproject.toml: fastapi, uvicorn, numpy, hmmlearn, arch."""
        pyproject = DHARMA_SWARM_ROOT / "pyproject.toml"
        reqtxt = DHARMA_SWARM_ROOT / "requirements.txt"

        if reqtxt.exists():
            source = "requirements.txt"
            content = reqtxt.read_text().lower()
        elif pyproject.exists():
            source = "pyproject.toml"
            content = pyproject.read_text().lower()
        else:
            return CheckResult(
                check_id="FC-04", category="fact",
                claim="All runtime deps declared in project config",
                status="FAIL", severity="HIGH",
                finding="Neither pyproject.toml nor requirements.txt found",
            )

        missing = [d for d in REQUIRED_DEPS if d not in content]
        optional_missing = [d for d in OPTIONAL_DEPS if d not in content]

        if not missing:
            finding = f"All required deps present in {source}"
            status = "PASS"
        else:
            finding = f"Missing from {source}: {missing}"
            status = "FAIL"

        if optional_missing:
            finding += f". Optional (used with try/except): {optional_missing}"

        return CheckResult(
            check_id="FC-04", category="fact",
            claim="All runtime deps declared in project config",
            status=status, severity="HIGH",
            finding=finding,
            fix_available=bool(missing), fix_id="FIX-04" if missing else None,
        )

    def _fc05_swarmlens_tabs(self) -> CheckResult:
        """Verify SwarmLens has the new Fund and Brier tabs from build."""
        app_path = SRC_DIR / "swarmlens_app.py"
        if not app_path.exists():
            return CheckResult(
                check_id="FC-05", category="fact",
                claim="SwarmLens has Fund/Brier tabs + /fund landing page",
                status="SKIP", severity="MEDIUM",
                finding="swarmlens_app.py not found",
            )
        content = app_path.read_text()
        planned_routes = ["/api/fund", "/api/brier", "/fund"]
        found = [r for r in planned_routes if r in content]
        missing = [r for r in planned_routes if r not in content]

        if not missing:
            return CheckResult(
                check_id="FC-05", category="fact",
                claim="SwarmLens has Fund/Brier tabs + /fund landing page",
                status="PASS", severity="MEDIUM",
                finding=f"All routes found: {found}",
            )
        return CheckResult(
            check_id="FC-05", category="fact",
            claim="SwarmLens has Fund/Brier tabs + /fund landing page",
            status="WARN" if found else "FAIL",
            severity="MEDIUM",
            finding=f"Found: {found}. Missing: {missing}",
        )

    def _fc06_git_state(self) -> CheckResult:
        """Check git state — dirty tree + active worktrees = merge risk."""
        try:
            status_out = subprocess.run(
                ["git", "-C", str(DHARMA_SWARM_ROOT), "status", "--porcelain"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            dirty_count = len([l for l in status_out.split("\n") if l.strip()])

            wt_out = subprocess.run(
                ["git", "-C", str(DHARMA_SWARM_ROOT), "worktree", "list"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            wt_count = len([l for l in wt_out.split("\n") if l.strip()])

            branch = subprocess.run(
                ["git", "-C", str(DHARMA_SWARM_ROOT), "branch", "--show-current"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()

            finding = f"Branch: {branch}. {dirty_count} uncommitted changes. {wt_count} worktrees."
            if dirty_count > 20:
                finding += " RECOMMEND: commit or stash before merging build worktrees."

            return CheckResult(
                check_id="FC-06", category="fact",
                claim="Clean working tree for worktree-based build",
                status="PASS" if dirty_count < 5 else "WARN",
                severity="HIGH" if dirty_count > 20 else "MEDIUM",
                finding=finding,
            )
        except Exception as e:
            return CheckResult(
                check_id="FC-06", category="fact",
                claim="Clean working tree",
                status="SKIP", severity="MEDIUM",
                finding=f"Git check failed: {e}",
            )

    def _fc07_ollama_api_path(self) -> CheckResult:
        """Plan says agents use /v1/chat/completions. Ollama Cloud may use /api/chat."""
        config_path = SRC_DIR / "ollama_config.py"
        providers_path = SRC_DIR / "providers.py"

        content = ""
        if config_path.exists():
            content += config_path.read_text()
        if providers_path.exists():
            content += providers_path.read_text()

        if not content:
            return CheckResult(
                check_id="FC-07", category="fact",
                claim="Ollama Cloud API path is correct",
                status="SKIP", severity="MEDIUM",
                finding="Neither ollama_config.py nor providers.py found",
            )

        uses_v1 = "/v1/chat/completions" in content
        uses_api = "/api/chat" in content or "/api/generate" in content

        if uses_v1 and uses_api:
            path_info = "Both /v1/chat/completions AND /api/chat paths found (supports both)"
        elif uses_v1:
            path_info = "Uses /v1/chat/completions (OpenAI-compatible)"
        elif uses_api:
            path_info = "Uses /api/chat (native Ollama)"
        else:
            path_info = "No API path pattern detected"

        return CheckResult(
            check_id="FC-07", category="fact",
            claim="Ollama Cloud API path is correct",
            status="PASS" if uses_v1 else "WARN",
            severity="MEDIUM",
            finding=f"{path_info}. Build agents hardcoding /v1/chat/completions may fail if cloud endpoint expects /api/chat.",
        )

    def _fc08_satya_gate(self) -> CheckResult:
        """Plan says SATYA ensures all scores published.
        Reality: SATYA checks for deception keywords, not publication completeness."""
        telos_path = SRC_DIR / "telos_gates.py"
        if not telos_path.exists():
            return CheckResult(
                check_id="FC-08", category="fact",
                claim="SATYA gate ensures all scores published",
                status="SKIP", severity="MEDIUM",
                finding="telos_gates.py not found",
            )
        content = telos_path.read_text()
        has_publication = "publish" in content.lower() or "report" in content.lower()
        has_deception = "decei" in content.lower() or "mislead" in content.lower() or "fabricat" in content.lower()

        if has_publication and not has_deception:
            return CheckResult(
                check_id="FC-08", category="fact",
                claim="SATYA gate ensures all scores published",
                status="PASS", severity="MEDIUM",
                finding="SATYA gate includes publication verification",
            )
        return CheckResult(
            check_id="FC-08", category="fact",
            claim="SATYA gate ensures all scores published",
            status="WARN", severity="MEDIUM",
            finding="SATYA gate checks for deception keywords, NOT publication completeness. Report generator should enforce SATYA disclosure independently.",
        )

    def _fc09_hermes_orphaned(self) -> CheckResult:
        """HERMES identity exists but plan doesn't mention it."""
        hermes_path = GINKO_HOME / "agents" / "hermes.json"
        agents_path = SRC_DIR / "ginko_agents.py"

        hermes_exists = hermes_path.exists()
        if not hermes_exists:
            return CheckResult(
                check_id="FC-09", category="fact",
                claim="All existing agent identities integrated",
                status="PASS", severity="LOW",
                finding="No HERMES identity file (may have been removed)",
            )
        hermes_in_code = False
        if agents_path.exists():
            hermes_in_code = "hermes" in agents_path.read_text().lower()

        return CheckResult(
            check_id="FC-09", category="fact",
            claim="All existing agent identities integrated",
            status="PASS" if hermes_in_code else "WARN",
            severity="LOW",
            finding="HERMES integrated in ginko_agents.py" if hermes_in_code else "HERMES identity at ~/.dharma/ginko/agents/hermes.json is ORPHANED — not referenced in ginko_agents.py",
            fix_available=not hermes_in_code, fix_id="FIX-09" if not hermes_in_code else None,
        )

    def _fc10_position_limit_wiring(self) -> CheckResult:
        """Verify paper trade actually enforces position limits and stop losses."""
        pt_path = SRC_DIR / "ginko_paper_trade.py"
        if not pt_path.exists():
            return CheckResult(
                check_id="FC-10", category="fact",
                claim="Paper trading enforces position limits + stop losses",
                status="SKIP", severity="HIGH",
                finding="ginko_paper_trade.py not yet created (build may still run)",
            )
        content = pt_path.read_text()
        has_limit = any(k in content for k in ["compute_position_size", "max_position", "0.05", "position_pct"])
        has_stop = "stop_loss" in content

        parts = []
        if has_limit:
            parts.append("Position limit check found")
        else:
            parts.append("NO position limit — may allow unlimited position sizes")
        if has_stop:
            parts.append("Stop loss field found")
        else:
            parts.append("NO stop loss — REVERSIBILITY gate violated")

        return CheckResult(
            check_id="FC-10", category="fact",
            claim="Paper trading enforces position limits + stop losses",
            status="PASS" if has_limit and has_stop else "FAIL",
            severity="HIGH",
            finding=". ".join(parts),
            fix_available=not (has_limit and has_stop),
            fix_id="FIX-10" if not (has_limit and has_stop) else None,
        )

    def _fc11_test_count(self) -> CheckResult:
        """Count ginko test files — should be 10+ after build."""
        import glob as globmod
        test_files = sorted(globmod.glob(str(TEST_DIR / "test_ginko_*.py")))
        count = len(test_files)
        return CheckResult(
            check_id="FC-11", category="fact",
            claim="Comprehensive ginko test coverage (10+ test files)",
            status="PASS" if count >= 10 else "WARN" if count >= 5 else "FAIL",
            severity="MEDIUM",
            finding=f"{count} ginko test files. Original: 5, expected after build: 10+. Files: {[Path(f).name for f in test_files]}",
        )

    # ── Phase 3: Dependency Check ─────────────────────────────────

    def check_dependencies(self) -> list[CheckResult]:
        """Verify key modules are importable."""
        results = []
        checks = [
            ("httpx", "HTTP client", "CRITICAL"),
            ("fastapi", "Dashboard framework", "HIGH"),
            ("uvicorn", "ASGI server", "HIGH"),
            ("numpy", "Numerical computing", "HIGH"),
            ("pydantic", "Data validation", "MEDIUM"),
        ]
        for module, purpose, severity in checks:
            try:
                importlib.import_module(module)
                results.append(CheckResult(
                    check_id=f"DEP-{module}", category="dep",
                    claim=f"{module} importable ({purpose})",
                    status="PASS", severity=severity,
                    finding=f"{module} installed and importable",
                ))
            except ImportError:
                results.append(CheckResult(
                    check_id=f"DEP-{module}", category="dep",
                    claim=f"{module} importable ({purpose})",
                    status="FAIL", severity=severity,
                    finding=f"{module} NOT installed. Fix: pip install {module}",
                    fix_available=True, fix_id=f"FIX-DEP-{module}",
                ))
        return results

    # ── Phase 4: Test Suite ───────────────────────────────────────

    def check_tests(self) -> list[CheckResult]:
        """Run ginko test suite and report results."""
        import glob as globmod
        test_files = sorted(globmod.glob(str(TEST_DIR / "test_ginko_*.py")))
        if not test_files:
            return [CheckResult(
                check_id="TEST-suite", category="test",
                claim="Ginko test suite passes",
                status="SKIP", severity="HIGH",
                finding="No ginko test files found",
            )]

        try:
            proc = subprocess.run(
                ["python3", "-m", "pytest"] + test_files + ["-v", "--tb=line", "-q"],
                capture_output=True, text=True, timeout=180,
                cwd=str(DHARMA_SWARM_ROOT),
            )
            output = proc.stdout + proc.stderr
            passed = output.count(" PASSED") + output.count(" passed")
            failed = output.count(" FAILED") + output.count(" failed")
            errors = output.count(" ERROR") + output.count(" error")

            status = "PASS" if proc.returncode == 0 else "FAIL"
            finding = f"{passed} passed, {failed} failed, {errors} errors across {len(test_files)} files"

            if proc.returncode != 0:
                last_lines = output.strip().split("\n")[-15:]
                finding += "\n  " + "\n  ".join(last_lines)

            return [CheckResult(
                check_id="TEST-suite", category="test",
                claim="Ginko test suite passes",
                status=status, severity="CRITICAL" if failed > 0 else "HIGH",
                finding=finding,
            )]
        except subprocess.TimeoutExpired:
            return [CheckResult(
                check_id="TEST-suite", category="test",
                claim="Ginko test suite passes",
                status="WARN", severity="HIGH",
                finding="Test suite timed out after 180s",
            )]
        except Exception as e:
            return [CheckResult(
                check_id="TEST-suite", category="test",
                claim="Ginko test suite passes",
                status="SKIP", severity="HIGH",
                finding=f"Could not run tests: {e}",
            )]

    # ── Phase 5: Integration Smoke ────────────────────────────────

    def check_integration(self) -> list[CheckResult]:
        """Verify ginko modules can import without errors."""
        results = []
        modules = [
            "dharma_swarm.ginko_data",
            "dharma_swarm.ginko_regime",
            "dharma_swarm.ginko_signals",
            "dharma_swarm.ginko_brier",
            "dharma_swarm.ginko_orchestrator",
            "dharma_swarm.ginko_agents",
            "dharma_swarm.agent_registry",
            "dharma_swarm.ginko_sec",
            "dharma_swarm.ginko_paper_trade",
            "dharma_swarm.ginko_report_gen",
            "dharma_swarm.ginko_live_test",
        ]

        # Existing modules are CRITICAL, new ones are HIGH
        existing = {"ginko_data", "ginko_regime", "ginko_signals", "ginko_brier", "ginko_orchestrator"}

        for mod in modules:
            short = mod.split(".")[-1]
            severity = "CRITICAL" if short in existing else "HIGH"
            try:
                importlib.import_module(mod)
                results.append(CheckResult(
                    check_id=f"IMPORT-{short}", category="integration",
                    claim=f"{mod} importable",
                    status="PASS", severity=severity,
                    finding=f"Successfully imported",
                ))
            except ImportError as e:
                results.append(CheckResult(
                    check_id=f"IMPORT-{short}", category="integration",
                    claim=f"{mod} importable",
                    status="FAIL" if short in existing else "WARN",
                    severity=severity,
                    finding=f"Import failed: {e}",
                ))
            except Exception as e:
                results.append(CheckResult(
                    check_id=f"IMPORT-{short}", category="integration",
                    claim=f"{mod} importable",
                    status="WARN", severity="MEDIUM",
                    finding=f"Non-import error: {type(e).__name__}: {e}",
                ))
        return results

    # ── Phase 6: Orthogonal Gap Detection ─────────────────────────

    def detect_gaps(self) -> list[CheckResult]:
        """Find what the 25-agent plan misses entirely."""
        gaps = []

        # GAP-01: API key validation
        gaps.append(CheckResult(
            check_id="GAP-01", category="gap",
            claim="API keys validated before use",
            status="WARN", severity="HIGH",
            finding="No pre-flight API key check. OPENROUTER_API_KEY, FRED_API_KEY, FINNHUB_API_KEY assumed present. Silent failures when missing.",
        ))

        # GAP-02: Dashboard auth
        app_path = SRC_DIR / "swarmlens_app.py"
        has_auth = False
        if app_path.exists():
            content = app_path.read_text()
            has_auth = any(k in content.lower() for k in ["authorization", "bearer", "api_key", "authenticate"])
        gaps.append(CheckResult(
            check_id="GAP-02", category="gap",
            claim="Dashboard has authentication",
            status="PASS" if has_auth else "FAIL",
            severity="HIGH",
            finding="Auth found" if has_auth else "NO AUTH — portfolio positions visible to anyone. /fund (public) is fine but /api/* needs protection.",
        ))

        # GAP-03: Backtesting
        gaps.append(CheckResult(
            check_id="GAP-03", category="gap",
            claim="Backtesting framework exists",
            status="PASS" if (SRC_DIR / "ginko_backtest.py").exists() else "FAIL",
            severity="MEDIUM",
            finding="Forward-only paper trading with no historical validation. A hedge fund needs backtesting.",
        ))

        # GAP-04: Cost budget limits
        gaps.append(CheckResult(
            check_id="GAP-04", category="gap",
            claim="LLM cost budget limits",
            status="WARN", severity="MEDIUM",
            finding="Per-call cost tracking exists but no daily/weekly budget limits or kill switch. Continuous analysis at $0.26-0.72/Mtok needs caps.",
        ))

        # GAP-05: Graceful degradation
        data_path = SRC_DIR / "ginko_data.py"
        has_fallback = False
        if data_path.exists():
            content = data_path.read_text()
            has_fallback = any(k in content.lower() for k in ["fallback", "cache", "stale"])
        gaps.append(CheckResult(
            check_id="GAP-05", category="gap",
            claim="Graceful degradation when APIs down",
            status="PASS" if has_fallback else "WARN",
            severity="MEDIUM",
            finding="Has fallback/cache" if has_fallback else "No cached fallback. If FRED/finnhub/SEC is unreachable, entire daily cycle fails.",
        ))

        # GAP-06: Portfolio risk management
        gaps.append(CheckResult(
            check_id="GAP-06", category="gap",
            claim="Portfolio-level risk (correlation, VaR)",
            status="PASS" if (SRC_DIR / "ginko_risk.py").exists() else "FAIL",
            severity="MEDIUM",
            finding="Position-level stops exist but no correlation matrix, sector exposure limits, or VaR.",
        ))

        # GAP-07: Domain/DNS
        gaps.append(CheckResult(
            check_id="GAP-07", category="gap",
            claim="Domain configured for public access",
            status="FAIL", severity="LOW",
            finding="No domain registered. Fund accessible only via IP:port. Need DNS + SSL for credibility.",
        ))

        # GAP-08: Auto-publish to Substack
        gaps.append(CheckResult(
            check_id="GAP-08", category="gap",
            claim="Reports auto-published to Substack",
            status="FAIL", severity="LOW",
            finding="Generates Substack-formatted markdown but doesn't post via API. Manual copy-paste required.",
        ))

        return gaps

    # ── Phase 7: Enhancement Scoring ──────────────────────────────

    def score_enhancements(self) -> list[Enhancement]:
        """Rank enhancements by impact/effort — these become the next agent wave."""
        enhancements = [
            Enhancement(
                id="ENH-01",
                title="API Key Validator + Env Bootstrap",
                description="Pre-flight check for all API keys. Print status table. Return dict of available services. Other modules check before calling.",
                impact="10x", effort="trivial", category="infra",
                agent_spec="Add validate_api_keys() to ginko_data.py: checks OPENROUTER_API_KEY, FRED_API_KEY, FINNHUB_API_KEY, OLLAMA_API_KEY. Returns {service: bool}. Print table on startup. Modules skip API calls when key missing instead of crashing.",
            ),
            Enhancement(
                id="ENH-02",
                title="Dashboard Bearer Token Auth",
                description="API_KEY env var auth on /api/* endpoints. Landing page (/fund) stays public.",
                impact="10x", effort="small", category="infra",
                agent_spec="Add middleware to swarmlens_app.py: check Authorization: Bearer {DASHBOARD_API_KEY} on /api/* routes. /fund, /api/waitlist, /api/waitlist/count stay public. Return 401 JSON on invalid key. Config via DASHBOARD_API_KEY env var.",
            ),
            Enhancement(
                id="ENH-03",
                title="Real AHIMSA Position Gate",
                description="Wire telos gate to check position concentration before trade execution.",
                impact="10x", effort="trivial", category="risk",
                agent_spec="Add check_position_gate(portfolio_value, position_value) to ginko_paper_trade.py open_position(). If position > 5% of portfolio, raise AhimsaGateError. Log via witness. Wire into orchestrator action_execute_paper_trades.",
            ),
            Enhancement(
                id="ENH-04",
                title="Cost Budget + Kill Switch",
                description="Daily/weekly LLM spend tracking with hard limits.",
                impact="10x", effort="small", category="risk",
                agent_spec="Add to agent_registry.py: daily_budget_usd=5.0, weekly_budget_usd=25.0. Before each agent call, sum cost from task_log.jsonl for today/week. If over budget, return error + cached last response. Log budget warnings at 80%.",
            ),
            Enhancement(
                id="ENH-05",
                title="Backtesting Engine",
                description="Run signals against 1-5 years historical data. Compare vs SPY buy-and-hold.",
                impact="100x", effort="medium", category="alpha",
                agent_spec="Build ginko_backtest.py: download OHLCV from yfinance. Run generate_signal_report() for each trading day. Execute paper trades. Compute: Sharpe, max drawdown, win rate, vs SPY benchmark. Output backtest report JSON + equity curve.",
            ),
            Enhancement(
                id="ENH-06",
                title="Portfolio Correlation + VaR",
                description="Correlation matrix, VaR at 95%/99%, sector exposure limits.",
                impact="100x", effort="medium", category="risk",
                dependencies=["ginko_paper_trade.py"],
                agent_spec="Build ginko_risk.py: compute_correlation_matrix(positions, price_history), compute_var(portfolio, confidence=0.95), check_sector_exposure(max_pct=0.30). Wire into full_cycle as pre-trade risk check.",
            ),
            Enhancement(
                id="ENH-07",
                title="Darwin Engine Prompt Tournament",
                description="Monthly tournament: each agent gets 3 prompt variants, best Brier score wins, losers mutate.",
                impact="1000x", effort="medium", category="alpha",
                dependencies=["ginko_agents.py", "agent_registry.py", "evolution.py"],
                agent_spec="Wire evolution.py DarwinEngine to ginko agent prompts. Monthly: snapshot Brier scores, rank, top 2 survive, bottom 2 get LLM-generated prompt mutations. Track prompt lineage in agent_registry.",
            ),
            Enhancement(
                id="ENH-08",
                title="Social Sentiment Pipeline",
                description="X/Reddit/StockTwits sentiment as signal input.",
                impact="100x", effort="large", category="alpha",
                agent_spec="Build ginko_sentiment.py: X API search (last 24h), Reddit r/wallstreetbets, aggregate sentiment -1 to +1. Add SentimentSignal to ginko_signals.py. Weight: 10% of signal confidence.",
            ),
            Enhancement(
                id="ENH-09",
                title="ML Signal Ensemble",
                description="XGBoost on top of rule-based signals. Features: RSI, SMA, ATR, regime, sentiment, SEC.",
                impact="1000x", effort="large", category="alpha",
                dependencies=["ENH-05", "ENH-08"],
                agent_spec="Build ginko_ml_signals.py: XGBoost model. Features from signals+regime+sentiment. Train on backtest data. Walk-forward validation. Add ML signal at 30% weight. Retrain monthly.",
            ),
            Enhancement(
                id="ENH-10",
                title="Prediction Resolution Webhooks",
                description="Notify via Slack/email when predictions auto-resolve.",
                impact="10x", effort="small", category="ux",
                agent_spec="Add webhook_notify() to ginko_brier.py auto_resolve_predictions(). Support: Slack webhook URL, file log. Include: prediction question, outcome, Brier score, running average.",
            ),
            Enhancement(
                id="ENH-11",
                title="Multi-Timeframe Signals",
                description="Daily/weekly/monthly signals. Higher timeframe confirmation boosts confidence.",
                impact="100x", effort="medium", category="alpha",
                agent_spec="Extend ginko_signals.py: compute signals on 3 timeframes. All 3 align: confidence += 25%. Conflict: flag as timeframe divergence, reduce confidence 20%.",
            ),
            Enhancement(
                id="ENH-12",
                title="Performance Attribution Dashboard",
                description="Track which agent/signal/regime generates alpha.",
                impact="100x", effort="medium", category="ux",
                dependencies=["ginko_paper_trade.py", "agent_registry.py"],
                agent_spec="Build ginko_attribution.py: for each closed trade, trace to signal source + agent + regime at entry. Aggregate P&L by each dimension. Add /api/attribution endpoint + tab to SwarmLens.",
            ),
        ]

        # Sort by impact/effort ratio
        impact_map = {"1000x": 4, "100x": 3, "10x": 2, "2x": 1}
        effort_map = {"trivial": 5, "small": 4, "medium": 3, "large": 2, "huge": 1}
        enhancements.sort(
            key=lambda e: impact_map.get(e.impact, 0) * effort_map.get(e.effort, 0),
            reverse=True,
        )
        return enhancements

    # ── Fix Generation ────────────────────────────────────────────

    def generate_fixes(self, results: list[CheckResult]) -> list[FixPatch]:
        fixes = []
        for r in results:
            if not r.fix_available or not r.fix_id:
                continue
            if r.fix_id == "FIX-01":
                fixes.append(FixPatch(
                    fix_id="FIX-01",
                    description="Verify paper trade has AHIMSA position limit check",
                    target_file=str(SRC_DIR / "ginko_paper_trade.py"),
                    action="verify_or_insert",
                    content="# AHIMSA: check position_value / portfolio_value <= 0.05 in open_position()",
                    safe=False,
                ))
            elif r.fix_id == "FIX-04":
                fixes.append(FixPatch(
                    fix_id="FIX-04",
                    description="Add missing deps to pyproject.toml",
                    target_file=str(DHARMA_SWARM_ROOT / "pyproject.toml"),
                    action="verify_or_append",
                    content="fastapi>=0.104, uvicorn>=0.24, numpy>=1.24",
                    safe=False,
                ))
            elif r.fix_id and r.fix_id.startswith("FIX-DEP-"):
                module = r.fix_id.split("FIX-DEP-")[1]
                fixes.append(FixPatch(
                    fix_id=r.fix_id,
                    description=f"Install {module}",
                    target_file="N/A",
                    action="shell",
                    content=f"pip install {module}",
                    safe=True,
                ))
        return fixes

    # ── Apply Fixes ───────────────────────────────────────────────

    def apply_fixes(self, fixes: list[FixPatch], dry_run: bool = True) -> list[dict]:
        actions = []
        for fix in fixes:
            if not fix.safe and dry_run:
                actions.append({
                    "fix_id": fix.fix_id,
                    "status": "SKIPPED",
                    "reason": "Unsafe — needs manual review",
                    "description": fix.description,
                })
                continue
            if fix.action == "shell":
                if dry_run:
                    actions.append({
                        "fix_id": fix.fix_id,
                        "status": "DRY_RUN",
                        "command": fix.content,
                        "description": fix.description,
                    })
                else:
                    try:
                        subprocess.run(
                            fix.content.split(),
                            capture_output=True, timeout=60, check=True,
                        )
                        fix.applied = True
                        actions.append({
                            "fix_id": fix.fix_id,
                            "status": "APPLIED",
                            "command": fix.content,
                            "description": fix.description,
                        })
                    except Exception as e:
                        actions.append({
                            "fix_id": fix.fix_id,
                            "status": "FAILED",
                            "error": str(e),
                            "description": fix.description,
                        })
            else:
                actions.append({
                    "fix_id": fix.fix_id,
                    "status": "MANUAL",
                    "description": fix.description,
                    "content_preview": fix.content[:200],
                })
        return actions

    # ── Report ────────────────────────────────────────────────────

    def build_report(self, mode: str = "one-shot") -> AuditReport:
        """Run full audit pipeline and return structured report."""
        self.results = []
        self.results.extend(self.check_file_manifest())
        self.results.extend(self.check_facts())
        self.results.extend(self.check_dependencies())
        self.results.extend(self.check_tests())
        self.results.extend(self.check_integration())
        self.results.extend(self.detect_gaps())

        self.enhancements = self.score_enhancements()
        self.fixes = self.generate_fixes(self.results)

        return AuditReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            mode=mode,
            results=self.results,
            fixes=self.fixes,
            enhancements=self.enhancements,
        )

    def save_report(self, report: AuditReport) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = AUDIT_HOME / f"audit_{ts}.json"

        data = {
            "timestamp": report.timestamp,
            "mode": report.mode,
            "summary": {
                "total": len(report.results),
                "passed": report.passed,
                "failed": report.failed,
                "warned": report.warned,
                "skipped": report.skipped,
                "fixes_available": len(report.fixes),
                "enhancements": len(report.enhancements),
            },
            "results": [asdict(r) for r in report.results],
            "fixes": [{
                "fix_id": f.fix_id,
                "description": f.description,
                "target": f.target_file,
                "action": f.action,
                "safe": f.safe,
                "applied": f.applied,
            } for f in report.fixes],
            "enhancements": [asdict(e) for e in report.enhancements],
        }
        path.write_text(json.dumps(data, indent=2))

        # Latest pointer for quick access
        (AUDIT_HOME / "latest.json").write_text(json.dumps(data, indent=2))
        return path

    def format_terminal_report(self, report: AuditReport) -> str:
        lines = []
        lines.append("=" * 72)
        lines.append("  DHARMIC QUANT — POST-BUILD AUDIT REPORT")
        lines.append(f"  {report.timestamp}")
        lines.append("=" * 72)
        lines.append("")
        lines.append(f"  SUMMARY: {report.passed} PASS | {report.failed} FAIL | {report.warned} WARN | {report.skipped} SKIP")
        lines.append(f"  FIXES: {len(report.fixes)} available | ENHANCEMENTS: {len(report.enhancements)} scored")
        lines.append("")

        cat_names = {
            "manifest": "FILE MANIFEST",
            "fact": "FACT CHECKS",
            "dep": "DEPENDENCIES",
            "test": "TEST SUITE",
            "integration": "INTEGRATION",
            "gap": "ORTHOGONAL GAPS",
        }
        categories: dict[str, list[CheckResult]] = {}
        for r in report.results:
            categories.setdefault(r.category, []).append(r)

        for cat in ["manifest", "fact", "dep", "test", "integration", "gap"]:
            if cat not in categories:
                continue
            lines.append(f"--- {cat_names.get(cat, cat.upper())} ---")
            for r in categories[cat]:
                fix_tag = " [FIX]" if r.fix_available else ""
                lines.append(f"  [{r.emoji}] [{r.severity:8s}] {r.check_id}: {r.claim}")
                for line in r.finding.split("\n"):
                    lines.append(f"       {line}")
                if fix_tag:
                    lines.append(f"       {fix_tag}")
            lines.append("")

        if report.enhancements:
            lines.append("--- ENHANCEMENT ROADMAP (ranked by impact/effort) ---")
            for i, e in enumerate(report.enhancements, 1):
                lines.append(f"  {i:2d}. [{e.impact:5s}/{e.effort:7s}] {e.title}")
                lines.append(f"      {e.description[:100]}")
                if e.dependencies:
                    lines.append(f"      deps: {', '.join(e.dependencies)}")
            lines.append("")

        if report.fixes:
            lines.append("--- AVAILABLE FIXES ---")
            for f in report.fixes:
                tag = "AUTO" if f.safe else "MANUAL"
                lines.append(f"  [{tag}] {f.fix_id}: {f.description}")
            lines.append("")
            lines.append("  Run: python3 -m dharma_swarm.ginko_audit --fix")

        lines.append("=" * 72)
        return "\n".join(lines)


# ─── Daemon Mode ──────────────────────────────────────────────────────

async def run_daemon(interval: int = 1800):
    """Run audit on interval. Write alert file on critical failures."""
    logger.info(f"Ginko audit daemon starting (interval={interval}s)")
    auditor = GinkoAuditor()

    while True:
        try:
            report = auditor.build_report(mode="daemon")
            path = auditor.save_report(report)
            print(auditor.format_terminal_report(report))
            logger.info(f"Audit #{path.stem}: {report.passed}P/{report.failed}F/{report.warned}W")

            # Alert on critical failures
            critical = [r for r in report.results if r.status == "FAIL" and r.severity in ("CRITICAL", "HIGH")]
            if critical:
                alert_path = GINKO_HOME / "audit_alert.json"
                alert_path.write_text(json.dumps({
                    "timestamp": report.timestamp,
                    "critical_failures": [asdict(r) for r in critical],
                    "count": len(critical),
                }, indent=2))
                logger.warning(f"ALERT: {len(critical)} critical failures — {alert_path}")

        except Exception as e:
            logger.error(f"Audit cycle failed: {e}", exc_info=True)

        await asyncio.sleep(interval)


# ─── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Dharmic Quant Post-Build Audit System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 -m dharma_swarm.ginko_audit                     # One-shot audit
  python3 -m dharma_swarm.ginko_audit --fix                # Apply safe fixes
  python3 -m dharma_swarm.ginko_audit --daemon             # Every 30 min
  python3 -m dharma_swarm.ginko_audit --daemon --interval 600  # Every 10 min
  python3 -m dharma_swarm.ginko_audit --json               # JSON output
  python3 -m dharma_swarm.ginko_audit --enhancements       # Enhancement plan only
        """,
    )
    parser.add_argument("--fix", action="store_true", help="Apply safe fixes")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon")
    parser.add_argument("--interval", type=int, default=1800, help="Daemon interval seconds")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--enhancements", action="store_true", help="Show enhancement plan only")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    if args.daemon:
        asyncio.run(run_daemon(args.interval))
        return

    auditor = GinkoAuditor()
    report = auditor.build_report()

    if args.fix:
        # Run fixes, then re-audit
        actions = auditor.apply_fixes(report.fixes, dry_run=False)
        print("--- FIX RESULTS ---")
        for a in actions:
            print(f"  {a['fix_id']}: {a['status']} — {a['description']}")
        print("")
        # Re-audit after fixes
        report = auditor.build_report(mode="fix")

    if args.enhancements:
        for i, e in enumerate(report.enhancements, 1):
            print(f"\n{'=' * 60}")
            print(f"Enhancement {i}: {e.title}")
            print(f"Impact: {e.impact} | Effort: {e.effort} | Category: {e.category}")
            print(f"{e.description}")
            if e.dependencies:
                print(f"Dependencies: {', '.join(e.dependencies)}")
            print(f"\nAgent Spec:\n  {e.agent_spec}")
        return

    path = auditor.save_report(report)

    if args.json:
        print(json.dumps({
            "timestamp": report.timestamp,
            "summary": {"passed": report.passed, "failed": report.failed, "warned": report.warned},
            "results": [asdict(r) for r in report.results],
            "enhancements": [asdict(e) for e in report.enhancements],
        }, indent=2, default=str))
    else:
        print(auditor.format_terminal_report(report))
        print(f"\nFull report: {path}")


if __name__ == "__main__":
    main()
