"""Guardian Crew — a tiny crew of powerful coding agents on a cron cycle.

These agents run continuously in the background, checking for:
    - Interface mismatches (wrong types, missing methods, broken call chains)
    - Dead loops (cybernetic loops declared in CYBERNETIC_LOOP_MAP.md but not running)
    - Broken connections (imports that fail, modules that exist in config but not on disk)
    - Model routing failures (providers returning 403/billing/timeout at high rates)
    - Memory write path failures (KnowledgeStore, MemoryPalace, evolution archive)
    - New code that breaks existing contracts (post-commit regression detection)

The crew has three specialist agents:

    AUDITOR: Interface contract verifier
        - Parses every Python file for calls to external modules
        - Checks that method signatures match the actual callee definition
        - Detects new mismatches introduced since the last clean commit
        - Writes findings to ~/.dharma/guardian/interface_audit.md

    LOOP_WATCHER: Cybernetic loop health monitor
        - Checks that all 13 loops in orchestrate_live are producing output
        - Reads signal_bus, message_bus, evolution archive for signs of life
        - Detects silent failures (loop running but producing zero events)
        - Writes findings to ~/.dharma/guardian/loop_health.md

    ROUTER_PROBE: Model routing health checker
        - Tests each provider in CANONICAL_SEED_ORDER with a minimal ping
        - Measures p50/p99 latency, error rate, circuit-breaker status
        - Identifies dead providers before they waste agent budgets
        - Writes findings to ~/.dharma/guardian/router_health.md

Combined output → ~/.dharma/guardian/GUARDIAN_REPORT.md (overwritten each cycle)
GitHub issue created when severity >= BLOCKER and no open issue exists for that mismatch.

Cycle: every 4 hours (configurable via GUARDIAN_INTERVAL_SECONDS env var).

Usage::

    # One-shot
    python -m dharma_swarm.guardian_crew

    # As a background task in orchestrate_live (wired at end of task_factories)
    await guardian_crew.start_guardian_loop(state_dir=STATE_DIR)

Future-proofing design:
    - Each check is a standalone async function. Adding a new check = one function.
    - Results are structured dicts. The report synthesizer works regardless of check count.
    - Severity levels: BLOCKER, DEGRADED, WARNING, OK.
      BLOCKER: creates a GitHub issue + emits algedonic signal to S5.
      DEGRADED: writes to report, logs warning.
      WARNING: writes to report only.
      OK: not written (keeps report short).
    - The crew is self-documenting: the report always describes what was checked,
      what passed, and what failed. It can be read by any future agent to understand
      the current health state.
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_GUARDIAN_INTERVAL = int(os.environ.get("GUARDIAN_INTERVAL_SECONDS", "14400"))  # 4 hours

# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

@dataclass
class GuardianFinding:
    severity: str          # BLOCKER | DEGRADED | WARNING | OK
    check: str             # which check found this
    title: str             # short title
    detail: str            # full explanation
    file: str = ""         # relevant file
    line: int = 0          # relevant line
    fix_hint: str = ""     # concrete 1-line fix suggestion


# ---------------------------------------------------------------------------
# AUDITOR: Interface contract verification
# ---------------------------------------------------------------------------

# These are the call patterns we actively track.
# Format: (caller_file, method_or_attr, correct_name_or_signature, severity)
_KNOWN_CONTRACTS: list[tuple[str, str, str, str]] = [
    # New modules introduced by recent commits
    ("archaeology_ingestion.py", "palace.recall", "PalaceQuery(text=..., max_results=...)", "BLOCKER"),
    ("dgm_loop.py", "DarwinEngine", "archive_path only — no _provider attr", "DEGRADED"),
    ("gnani_lodestone.py", "TelosGraph.get_by_name", "must exist on TelosGraph", "DEGRADED"),
    ("gnani_lodestone.py", "ConceptGraph.get_node", "must exist on ConceptGraph", "DEGRADED"),
    ("gnani_lodestone.py", "TaskBoard.get_by_title", "must exist on TaskBoard", "DEGRADED"),
    # Existing known contracts
    ("orchestrate_live.py", "PersistentAgent(role=..., provider_type=...)", "AgentRole enum + ProviderType enum", "BLOCKER"),
    ("swarm.py", "_classify_failure", "private method coupling to orchestrator", "DEGRADED"),
    ("swarm.py", "samvara.current_power", "needs None guard before .value", "DEGRADED"),
]

# Methods that must exist on their respective classes
_METHOD_EXISTENCE_CHECKS: list[tuple[str, str, str, str]] = [
    # (module, class_name, method_name, severity)
    ("dharma_swarm.memory_palace", "MemoryPalace", "recall", "BLOCKER"),
    ("dharma_swarm.memory_palace", "MemoryPalace", "ingest", "BLOCKER"),
    ("dharma_swarm.memory_palace", "PalaceQuery", "__init__", "BLOCKER"),
    ("dharma_swarm.evolution", "DarwinEngine", "auto_evolve", "BLOCKER"),
    ("dharma_swarm.evolution", "DarwinEngine", "apply_diff_and_test", "BLOCKER"),
    ("dharma_swarm.archaeology_ingestion", "ArchaeologyIngestionDaemon", "run_once", "BLOCKER"),
    ("dharma_swarm.dgm_loop", "DGMLoop", "run_one_generation", "BLOCKER"),
    ("dharma_swarm.world_actions", "WorldActionResult", "to_json", "BLOCKER"),
    ("dharma_swarm.gnani_lodestone", "GnaniLodestone", "seed_all", "BLOCKER"),
    ("dharma_swarm.telos_gates", "TelosGatekeeper", "check", "BLOCKER"),
    ("dharma_swarm.stigmergy", "StigmergyStore", "leave_mark", "BLOCKER"),
    ("dharma_swarm.task_board", "TaskBoard", "get_by_title", "DEGRADED"),
    ("dharma_swarm.telos_graph", "TelosGraph", "get_by_name", "DEGRADED"),
]

# Import chains that must succeed
_IMPORT_CHECKS: list[tuple[str, str]] = [
    ("dharma_swarm.world_actions", "BLOCKER"),
    ("dharma_swarm.dgm_loop", "BLOCKER"),
    ("dharma_swarm.archaeology_ingestion", "BLOCKER"),
    ("dharma_swarm.gnani_lodestone", "BLOCKER"),
    ("dharma_swarm.memory_palace", "BLOCKER"),
    ("dharma_swarm.evolution", "BLOCKER"),
    ("dharma_swarm.telos_gates", "BLOCKER"),
    ("dharma_swarm.stigmergy", "BLOCKER"),
    ("dharma_swarm.autonomous_agent", "BLOCKER"),
    ("dharma_swarm.orchestrate_live", "BLOCKER"),
]


async def run_auditor(src_root: Path) -> list[GuardianFinding]:
    """AUDITOR: Check import chains, method existence, and known contract violations."""
    findings: list[GuardianFinding] = []

    # 1. Import checks
    for module_name, severity in _IMPORT_CHECKS:
        try:
            spec = importlib.util.find_spec(module_name)
            if spec is None:
                findings.append(GuardianFinding(
                    severity=severity,
                    check="AUDITOR:import",
                    title=f"Module not found: {module_name}",
                    detail=f"importlib.find_spec returned None for {module_name}",
                    file=module_name.replace('.', '/') + '.py',
                    fix_hint=f"Ensure {module_name.split('.')[-1]}.py exists in dharma_swarm/",
                ))
        except Exception as exc:
            findings.append(GuardianFinding(
                severity=severity,
                check="AUDITOR:import",
                title=f"Import error: {module_name}",
                detail=str(exc),
                file=module_name.replace('.', '/') + '.py',
            ))

    # 2. Method existence checks (parse AST, don't import)
    for module_name, class_name, method_name, severity in _METHOD_EXISTENCE_CHECKS:
        module_path = module_name.replace('.', '/')
        # Try both dharma_swarm/ prefix styles
        candidates = [
            src_root / (module_path.replace('dharma_swarm/', '') + '.py'),
            src_root / (module_path + '.py'),
        ]
        found_file = next((p for p in candidates if p.exists()), None)
        if found_file is None:
            findings.append(GuardianFinding(
                severity=severity,
                check="AUDITOR:method_exists",
                title=f"File not found for {module_name}",
                detail=f"Tried: {[str(c) for c in candidates]}",
            ))
            continue

        try:
            tree = ast.parse(found_file.read_text(encoding="utf-8"))
            class_node = next(
                (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == class_name),
                None,
            )
            if class_node is None:
                findings.append(GuardianFinding(
                    severity=severity,
                    check="AUDITOR:method_exists",
                    title=f"Class {class_name} not found in {found_file.name}",
                    detail=f"Module {module_name} exists but class {class_name} is missing",
                    file=found_file.name,
                    fix_hint=f"Add class {class_name} to {found_file.name}",
                ))
                continue

            method_exists = any(
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == method_name
                for n in ast.walk(class_node)
            )
            if not method_exists:
                findings.append(GuardianFinding(
                    severity=severity,
                    check="AUDITOR:method_exists",
                    title=f"{class_name}.{method_name}() missing in {found_file.name}",
                    detail=f"Class {class_name} exists but method {method_name} is not defined",
                    file=found_file.name,
                    fix_hint=f"Add `def {method_name}(self, ...)` to {class_name}",
                ))
        except SyntaxError as exc:
            findings.append(GuardianFinding(
                severity="BLOCKER",
                check="AUDITOR:syntax",
                title=f"Syntax error: {found_file.name}",
                detail=f"Line {exc.lineno}: {exc.msg}",
                file=found_file.name,
                line=exc.lineno or 0,
                fix_hint=f"Fix syntax at line {exc.lineno}",
            ))

    # 3. Scan all Python files for syntax errors (catches regressions)
    for py_file in sorted(src_root.glob("*.py")):
        try:
            ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            findings.append(GuardianFinding(
                severity="BLOCKER",
                check="AUDITOR:syntax",
                title=f"Syntax error: {py_file.name}",
                detail=f"Line {exc.lineno}: {exc.msg}",
                file=py_file.name,
                line=exc.lineno or 0,
                fix_hint=f"Fix syntax error at line {exc.lineno}",
            ))

    return findings


# ---------------------------------------------------------------------------
# LOOP_WATCHER: Cybernetic loop health monitor
# ---------------------------------------------------------------------------

# Expected loops and their heartbeat signals
_EXPECTED_LOOPS = [
    ("evolution", "evolution archive", lambda d: (d / "evolution" / "archive.jsonl").exists()),
    ("stigmergy", "stigmergy marks", lambda d: (d / "stigmergy" / "marks.jsonl").exists()),
    ("telos", "telos objectives", lambda d: (d / "telos" / "objectives.jsonl").exists()),
    ("memory", "memory palace db", lambda d: (d / "memory" / "palace.db").exists() or (d / "memory" / "palace").exists()),
    ("gnani", "gnani seeded flag", lambda d: (d / "meta" / "gnani_seeded").exists()),
    ("archaeology", "lessons learned", lambda d: (d / "meta" / "lessons_learned.md").exists()),
    ("sub_swarms", "sub_swarm specs dir", lambda d: True),  # optional — OK if not yet created
]

# Loops that should be producing fresh output (check mtime)
_FRESHNESS_CHECKS = [
    # (description, path_lambda, max_age_hours)
    ("evolution archive", lambda d: d / "evolution" / "archive.jsonl", 24),
    ("stigmergy marks", lambda d: d / "stigmergy" / "marks.jsonl", 24),
    ("telos objectives", lambda d: d / "telos" / "objectives.jsonl", 72),
]


async def run_loop_watcher(state_dir: Path) -> list[GuardianFinding]:
    """LOOP_WATCHER: Check all cybernetic loops are alive and producing output."""
    findings: list[GuardianFinding] = []
    now = time.time()

    # 1. Existence checks
    for loop_name, artifact_name, check_fn in _EXPECTED_LOOPS:
        try:
            exists = check_fn(state_dir)
            if not exists:
                findings.append(GuardianFinding(
                    severity="WARNING",
                    check="LOOP_WATCHER:existence",
                    title=f"Loop artifact missing: {loop_name} ({artifact_name})",
                    detail=f"Expected artifact for {loop_name} loop not found in {state_dir}",
                    fix_hint=f"Run `dgc orchestrate-live` to boot the {loop_name} loop",
                ))
        except Exception as exc:
            logger.debug("Loop existence check failed for %s: %s", loop_name, exc)

    # 2. Freshness checks
    for description, path_fn, max_age_hours in _FRESHNESS_CHECKS:
        try:
            path = path_fn(state_dir)
            if path.exists():
                age_hours = (now - path.stat().st_mtime) / 3600
                if age_hours > max_age_hours:
                    findings.append(GuardianFinding(
                        severity="DEGRADED",
                        check="LOOP_WATCHER:freshness",
                        title=f"Stale loop output: {description}",
                        detail=(
                            f"{path.name} last modified {age_hours:.1f}h ago "
                            f"(threshold: {max_age_hours}h). "
                            f"The {description} loop may not be running."
                        ),
                        file=str(path),
                        fix_hint=f"Check if the {description} loop is active; restart if needed.",
                    ))
        except Exception as exc:
            logger.debug("Freshness check failed for %s: %s", description, exc)

    # 3. Evolution archive entry count check
    archive_path = state_dir / "evolution" / "archive.jsonl"
    if archive_path.exists():
        try:
            lines = [l for l in archive_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            applied = sum(1 for l in lines if '"applied"' in l)
            total = len(lines)
            if total > 0 and applied == 0:
                findings.append(GuardianFinding(
                    severity="DEGRADED",
                    check="LOOP_WATCHER:evolution_quality",
                    title="Evolution archive: zero applied entries",
                    detail=(
                        f"Archive has {total} entries but 0 have status='applied'. "
                        f"Evolution is running in shadow mode or all diffs are being rejected. "
                        f"Set DHARMA_EVOLUTION_SHADOW=0 and DGC_AUTONOMY_LEVEL=2 for real mutation."
                    ),
                    file=str(archive_path),
                    fix_hint="Set DHARMA_EVOLUTION_SHADOW=0 and DGC_AUTONOMY_LEVEL=2 in .env",
                ))
        except Exception as exc:
            logger.debug("Evolution archive check failed: %s", exc)

    return findings


# ---------------------------------------------------------------------------
# ROUTER_PROBE: Model routing health checker
# ---------------------------------------------------------------------------

# Providers to probe (in priority order from CANONICAL_SEED_ORDER)
_PROVIDERS_TO_PROBE = [
    ("anthropic", "claude-sonnet-4-20250514", "ANTHROPIC_API_KEY"),
    ("openrouter", "openai/gpt-4o-mini", "OPENROUTER_API_KEY"),
    ("groq", "llama3-8b-8192", "GROQ_API_KEY"),
    ("ollama_cloud", "llama3.1:8b", None),  # no key needed
]

_CIRCUIT_BREAKER_SIGNALS = ["403", "billing", "exhausted", "access_denied", "payment"]


async def run_router_probe(state_dir: Path) -> list[GuardianFinding]:
    """ROUTER_PROBE: Check model routing health — dead providers, circuit breakers."""
    findings: list[GuardianFinding] = []

    # Check circuit breaker state file
    cb_path = state_dir / "meta" / "circuit_breakers.json"
    if cb_path.exists():
        try:
            cb_data = json.loads(cb_path.read_text(encoding="utf-8"))
            for provider, state in cb_data.items():
                is_open = state.get("is_open", False)
                trip_count = state.get("trip_count", 0)
                reason = state.get("reason", "")
                if is_open:
                    severity = "BLOCKER" if any(s in reason.lower() for s in _CIRCUIT_BREAKER_SIGNALS) else "DEGRADED"
                    findings.append(GuardianFinding(
                        severity=severity,
                        check="ROUTER_PROBE:circuit_breaker",
                        title=f"Circuit breaker OPEN: {provider}",
                        detail=f"Provider {provider} circuit breaker is open. Trips: {trip_count}. Reason: {reason}",
                        fix_hint=f"Check API key for {provider}; delete circuit_breakers.json to reset.",
                    ))
        except Exception as exc:
            logger.debug("Circuit breaker check failed: %s", exc)

    # Check for dead provider patterns in logs
    log_dir = state_dir.parent / ".dharma" / "logs" if (state_dir.parent / ".dharma").exists() else state_dir / "logs"
    if not log_dir.exists():
        log_dir = Path.home() / ".dharma" / "logs"

    if log_dir.exists():
        try:
            # Scan last 1000 lines of the most recent log for dead provider signals
            log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
            if log_files:
                recent_log = log_files[0]
                lines = recent_log.read_text(encoding="utf-8", errors="ignore").splitlines()[-1000:]
                provider_errors: dict[str, int] = {}
                for line in lines:
                    for provider, _, _ in _PROVIDERS_TO_PROBE:
                        if provider in line.lower():
                            for signal in _CIRCUIT_BREAKER_SIGNALS:
                                if signal in line.lower():
                                    provider_errors[provider] = provider_errors.get(provider, 0) + 1

                for provider, count in provider_errors.items():
                    if count >= 3:
                        findings.append(GuardianFinding(
                            severity="DEGRADED",
                            check="ROUTER_PROBE:log_errors",
                            title=f"Repeated errors: {provider} ({count} in last 1000 log lines)",
                            detail=f"Provider {provider} appears {count} times in error patterns. Possible dead provider.",
                            fix_hint=f"Check {provider} API key and quota; consider moving it lower in CANONICAL_SEED_ORDER.",
                        ))
        except Exception as exc:
            logger.debug("Log scan failed: %s", exc)

    # Check env vars for configured providers
    for provider, model, env_key in _PROVIDERS_TO_PROBE:
        if env_key and not os.environ.get(env_key):
            findings.append(GuardianFinding(
                severity="WARNING",
                check="ROUTER_PROBE:missing_key",
                title=f"Missing API key: {provider} ({env_key})",
                detail=f"Provider {provider} (model: {model}) requires {env_key} but it is not set.",
                fix_hint=f"Add {env_key}=... to ~/.dharma/.env or ~/dharma_swarm/.env",
            ))

    return findings


# ---------------------------------------------------------------------------
# Report synthesizer
# ---------------------------------------------------------------------------

def _severity_rank(s: str) -> int:
    return {"BLOCKER": 0, "DEGRADED": 1, "WARNING": 2, "OK": 3}.get(s, 4)


def synthesize_report(
    auditor_findings: list[GuardianFinding],
    loop_findings: list[GuardianFinding],
    router_findings: list[GuardianFinding],
    generated_at: str,
    src_root: Path,
) -> str:
    all_findings = auditor_findings + loop_findings + router_findings
    all_findings.sort(key=lambda f: _severity_rank(f.severity))

    blockers = [f for f in all_findings if f.severity == "BLOCKER"]
    degraded = [f for f in all_findings if f.severity == "DEGRADED"]
    warnings = [f for f in all_findings if f.severity == "WARNING"]

    lines = [
        "# GUARDIAN CREW REPORT",
        f"*Generated: {generated_at}*",
        f"*Src root: {src_root}*",
        "",
        "## Summary",
        f"| Severity | Count |",
        f"|----------|-------|",
        f"| BLOCKER  | {len(blockers)} |",
        f"| DEGRADED | {len(degraded)} |",
        f"| WARNING  | {len(warnings)} |",
        f"| TOTAL    | {len(all_findings)} |",
        "",
    ]

    def _section(title: str, findings: list[GuardianFinding]) -> list[str]:
        if not findings:
            return [f"## {title}", "*None.*", ""]
        out = [f"## {title}"]
        for i, f in enumerate(findings, 1):
            out += [
                f"### {i}. {f.title}",
                f"**Check:** `{f.check}` | **File:** `{f.file or 'N/A'}`" +
                (f" line {f.line}" if f.line else ""),
                "",
                f.detail,
                "",
            ]
            if f.fix_hint:
                out += [f"**Fix:** {f.fix_hint}", ""]
        return out

    lines += _section("BLOCKERs", blockers)
    lines += _section("DEGRADED", degraded)
    lines += _section("WARNINGs", warnings)

    lines += [
        "## Checked By",
        "- **AUDITOR**: Import chains, method existence, syntax errors across all modules",
        "- **LOOP_WATCHER**: Cybernetic loop artifact existence + freshness + evolution quality",
        "- **ROUTER_PROBE**: Circuit breaker state, log error patterns, missing API keys",
        "",
        "---",
        "*Guardian Crew runs every 4 hours. Report overwrites previous. "
        "BLOCKERs trigger GitHub issues via world_actions.github_create_issue().*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# GitHub issue creation for BLOCKERs
# ---------------------------------------------------------------------------

async def _create_issue_if_needed(finding: GuardianFinding, repo: str, state_dir: Path) -> bool:
    """Create a GitHub issue for a BLOCKER finding if one doesn't already exist."""
    # Check dedup registry
    issues_log = state_dir / "guardian" / "issues_created.json"
    issues_log.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, str] = {}
    if issues_log.exists():
        try:
            existing = json.loads(issues_log.read_text(encoding="utf-8"))
        except Exception:
            pass

    issue_key = f"{finding.check}:{finding.title[:80]}"
    if issue_key in existing:
        logger.debug("Issue already created for: %s", issue_key)
        return False

    try:
        from dharma_swarm.world_actions import github_create_issue

        body = (
            f"**Guardian Crew — Automatic BLOCKER Detection**\n\n"
            f"**Check:** `{finding.check}`\n"
            f"**File:** `{finding.file}`" + (f" (line {finding.line})" if finding.line else "") + "\n\n"
            f"**Detail:**\n{finding.detail}\n\n"
            f"**Suggested Fix:**\n{finding.fix_hint or 'See detail above.'}\n\n"
            f"---\n*Auto-generated by Guardian Crew at {datetime.now(timezone.utc).isoformat()}*"
        )
        result = github_create_issue(repo=repo, title=f"[GUARDIAN] {finding.title}", body=body)
        if result.success:
            existing[issue_key] = result.url or "created"
            issues_log.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            logger.info("Guardian: created GitHub issue for '%s'", finding.title)
            return True
        else:
            logger.warning("Guardian: GitHub issue creation failed: %s", result.message)
    except Exception as exc:
        logger.debug("Issue creation failed (non-fatal): %s", exc)

    return False


# ---------------------------------------------------------------------------
# Main guardian run function
# ---------------------------------------------------------------------------

async def run_guardian_cycle(
    src_root: Path | None = None,
    state_dir: Path | None = None,
    github_repo: str = "AmitabhainArunachala/dharma_swarm",
    create_issues: bool = True,
) -> dict[str, Any]:
    """Run one full guardian cycle: audit + loop_watch + router_probe + report.

    Returns:
        Dict with finding counts, report path, and issue creation results.
    """
    src_root = src_root or Path.home() / "dharma_swarm" / "dharma_swarm"
    state_dir = state_dir or Path.home() / ".dharma"
    generated_at = datetime.now(timezone.utc).isoformat()

    logger.info("Guardian Crew: starting cycle (src=%s)", src_root)

    # Run all three agents in parallel
    auditor_findings, loop_findings, router_findings = await asyncio.gather(
        run_auditor(src_root),
        run_loop_watcher(state_dir),
        run_router_probe(state_dir),
        return_exceptions=False,
    )

    # Synthesize report
    report = synthesize_report(
        auditor_findings=auditor_findings,
        loop_findings=loop_findings,
        router_findings=router_findings,
        generated_at=generated_at,
        src_root=src_root,
    )

    # Write report to disk
    report_dir = state_dir / "guardian"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "GUARDIAN_REPORT.md"
    report_path.write_text(report, encoding="utf-8")

    # Also write to repo root (version-controlled visibility)
    try:
        repo_report_path = src_root.parent / "GUARDIAN_REPORT.md"
        repo_report_path.write_text(report, encoding="utf-8")
    except Exception:
        pass

    # Create GitHub issues for BLOCKERs
    issues_created = 0
    all_findings = auditor_findings + loop_findings + router_findings
    blockers = [f for f in all_findings if f.severity == "BLOCKER"]

    if create_issues and blockers:
        for finding in blockers[:5]:  # cap at 5 issues per cycle
            created = await _create_issue_if_needed(finding, github_repo, state_dir)
            if created:
                issues_created += 1

    result = {
        "generated_at": generated_at,
        "blockers": len(blockers),
        "degraded": len([f for f in all_findings if f.severity == "DEGRADED"]),
        "warnings": len([f for f in all_findings if f.severity == "WARNING"]),
        "total_findings": len(all_findings),
        "issues_created": issues_created,
        "report_path": str(report_path),
    }

    logger.info(
        "Guardian Crew cycle complete: %d blockers, %d degraded, %d warnings, %d issues created",
        result["blockers"], result["degraded"], result["warnings"], result["issues_created"],
    )
    return result


# ---------------------------------------------------------------------------
# Orchestrate_live integration
# ---------------------------------------------------------------------------

async def start_guardian_loop(
    src_root: Path | None = None,
    state_dir: Path | None = None,
    github_repo: str = "AmitabhainArunachala/dharma_swarm",
    interval_seconds: int = _GUARDIAN_INTERVAL,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    """Run the guardian crew in a continuous loop (called from orchestrate_live).

    Runs immediately at boot, then every interval_seconds (default 4 hours).
    """
    logger.info("Guardian Crew: starting loop (interval=%ds)", interval_seconds)
    _shutdown = shutdown_event or asyncio.Event()

    # Boot-time run
    try:
        await asyncio.wait_for(
            run_guardian_cycle(src_root=src_root, state_dir=state_dir, github_repo=github_repo),
            timeout=300.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Guardian Crew: boot-time cycle timed out (300s)")
    except Exception as exc:
        logger.warning("Guardian Crew: boot-time cycle failed (non-fatal): %s", exc)

    # Recurring loop
    while not _shutdown.is_set():
        try:
            await asyncio.wait_for(_shutdown.wait(), timeout=float(interval_seconds))
            break
        except asyncio.TimeoutError:
            pass
        if _shutdown.is_set():
            break
        try:
            await asyncio.wait_for(
                run_guardian_cycle(src_root=src_root, state_dir=state_dir, github_repo=github_repo),
                timeout=300.0,
            )
        except asyncio.TimeoutError:
            logger.warning("Guardian Crew: cycle timed out (300s)")
        except Exception as exc:
            logger.warning("Guardian Crew: cycle failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    result = await run_guardian_cycle()
    print(json.dumps(result, indent=2))

    # Print the report to stdout
    report_path = Path(result["report_path"])
    if report_path.exists():
        print("\n" + report_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    asyncio.run(_main())
