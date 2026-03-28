"""Scout Framework — reusable domain scout runner.

Generalizes the MiMo Explorer pattern into a configurable scout that:
1. Reads files from a domain-specific file list
2. Runs domain-specific commands
3. Sends context to an LLM with domain-specific instructions
4. Parses the response into a structured ScoutReport
5. Writes the report + deposits stigmergy marks for high-severity findings

Usage:
    # Run a single domain scout
    python3 -m dharma_swarm.scout_framework --domain architecture --once

    # Run all configured scouts
    python3 -m dharma_swarm.scout_framework --all --once

    # Daemon mode (cron replacement)
    python3 -m dharma_swarm.scout_framework --domain architecture --interval 3600
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is importable
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from dharma_swarm.scout_report import (
    Finding,
    ScoutReport,
    report_summary,
    write_report,
)

logger = logging.getLogger(__name__)

ROOT = Path.home() / "dharma_swarm"

# ---------------------------------------------------------------------------
# Domain Definitions
# ---------------------------------------------------------------------------

DOMAINS: dict[str, dict[str, Any]] = {
    "architecture": {
        "description": "Core module structure, abstractions, coupling, god objects",
        "model": "xiaomi/mimo-v2-pro",
        "files": [
            "dharma_swarm/swarm.py",
            "dharma_swarm/models.py",
            "dharma_swarm/model_hierarchy.py",
            "dharma_swarm/organism.py",
            "CLAUDE.md",
        ],
        "commands": [
            ("module count", "find dharma_swarm/dharma_swarm -name '*.py' | wc -l"),
            ("LOC", "wc -l dharma_swarm/dharma_swarm/*.py 2>/dev/null | tail -1"),
        ],
        "instruction": (
            "You are an architecture scout for dharma_swarm. Analyze the core modules. "
            "Look for: god objects, circular dependencies, dead code, abstraction leaks, "
            "type safety gaps (Any annotations), files over 500 lines, coupling between "
            "subsystems that should be independent. "
            "For each finding, classify severity and whether it's actionable."
        ),
        "stigmergy_channel": "systems",
    },
    "tests": {
        "description": "Test coverage, fragility, missing tests, test philosophy",
        "model": "xiaomi/mimo-v2-pro",
        "files": [
            "tests/conftest.py",
        ],
        "commands": [
            ("test count", "find tests -name 'test_*.py' | wc -l"),
            ("pytest dry run", "python3 -m pytest tests/ --collect-only -q 2>&1 | tail -5"),
            ("recent failures", "python3 -m pytest tests/ -q --tb=line -x --timeout=15 2>&1 | tail -20"),
        ],
        "instruction": (
            "You are a test quality scout. Analyze the test suite. "
            "Look for: untested modules (compare dharma_swarm/*.py vs tests/test_*.py), "
            "fragile tests (random failures, timing deps, network deps), "
            "test isolation issues (shared state, import-time side effects), "
            "coverage gaps in critical paths (routing, evolution, telos gates). "
            "For each finding, classify severity and suggest the specific test to write."
        ),
        "stigmergy_channel": "systems",
    },
    "routing": {
        "description": "Provider performance, cost optimization, EWMA accuracy, failure rates",
        "model": "xiaomi/mimo-v2-pro",
        "files": [
            "dharma_swarm/model_hierarchy.py",
            "dharma_swarm/smart_router.py",
            "dharma_swarm/routing_memory.py",
            "dharma_swarm/free_fleet.py",
        ],
        "commands": [
            ("EWMA data", "ls -la ~/.dharma/routing/ 2>/dev/null | head -10"),
            ("router decisions", "wc -l ~/.dharma/router/decisions.jsonl 2>/dev/null || echo 'no decisions log'"),
            ("free fleet discovery", "python3 -c 'from dharma_swarm.free_fleet import refresh_fleet; t=refresh_fleet(); print(f\"Tier1: {len(t[1])}, Tier2: {len(t[2])}, Tier3: {len(t[3])}\")' 2>&1"),
        ],
        "instruction": (
            "You are a routing and cost scout. Analyze the provider routing system. "
            "Look for: EWMA cold-start issues, provider failure patterns, cost leaks "
            "(paid models used when free would suffice), stale circuit breakers, "
            "tier misassignment, providers that should be promoted/demoted based on data. "
            "For each finding, quantify the cost impact if possible."
        ),
        "stigmergy_channel": "strategy",
    },
    "evolution": {
        "description": "Darwin engine health, fitness trends, stagnation, proposal quality",
        "model": "xiaomi/mimo-v2-pro",
        "files": [
            "dharma_swarm/evolution.py",
            "dharma_swarm/diversity_archive.py",
        ],
        "commands": [
            ("evolution archive", "wc -l ~/.dharma/evolution/archive.jsonl 2>/dev/null || echo 'no archive'"),
            ("recent proposals", "tail -5 ~/.dharma/evolution/archive.jsonl 2>/dev/null || echo 'none'"),
            ("fitness trend", "dgc evolve trend 2>&1 | head -20"),
        ],
        "instruction": (
            "You are an evolution scout. Analyze the Darwin engine state. "
            "Look for: fitness stagnation (flat or declining trend), diversity collapse "
            "(all proposals from same model family), high rejection rates at gates, "
            "circuit breaker trips, convergence restarts. "
            "For each finding, suggest whether to adjust mutation rate, diversity pressure, or model roster."
        ),
        "stigmergy_channel": "research",
    },
    "security": {
        "description": "Exposed secrets, injection risks, dependency vulnerabilities",
        "model": "xiaomi/mimo-v2-pro",
        "files": [
            "api_keys.py",
            "dharma_swarm/telos_gates.py",
            ".env.template",
        ],
        "commands": [
            ("secrets scan", "grep -r 'sk-' dharma_swarm/dharma_swarm/*.py 2>/dev/null | head -5 || echo 'clean'"),
            ("env check", "env | grep -i 'key\\|secret\\|token' | sed 's/=.*/=***/' | head -20"),
        ],
        "instruction": (
            "You are a security scout. Scan for: hardcoded secrets, API keys in source, "
            "unsanitized inputs, command injection risks (subprocess with shell=True + user input), "
            "missing input validation at system boundaries, dependency vulnerabilities. "
            "CRITICAL findings only — don't flag theoretical risks, only real exposure."
        ),
        "stigmergy_channel": "governance",
    },
    "stigmergy": {
        "description": "Pheromone mark health, hot paths, dead zones, coordination patterns",
        "model": "xiaomi/mimo-v2-pro",
        "files": [
            "dharma_swarm/stigmergy.py",
        ],
        "commands": [
            ("mark count", "wc -l ~/.dharma/stigmergy/marks.jsonl 2>/dev/null || echo 'no marks'"),
            ("recent marks", "tail -10 ~/.dharma/stigmergy/marks.jsonl 2>/dev/null || echo 'none'"),
            ("channel distribution", "python3 -c \"import json; marks=[json.loads(l) for l in open('$HOME/.dharma/stigmergy/marks.jsonl')]; from collections import Counter; print(Counter(m.get('channel','?') for m in marks))\" 2>&1 || echo 'parse error'"),
        ],
        "instruction": (
            "You are a stigmergy scout. Analyze the pheromone lattice. "
            "Look for: dead channels (no marks in 7+ days), mark concentration "
            "(all marks on same files), missing cross-channel signals, "
            "decay not running (archive growing without bounds), "
            "salience distribution (all marks same salience = no signal). "
            "For each finding, suggest how to improve agent coordination."
        ),
        "stigmergy_channel": "memory",
    },
}

# Default models for cost tiers
FREE_MODEL = "glm-5:cloud"  # Ollama Cloud — $0
CHEAP_MODEL = "xiaomi/mimo-v2-pro"  # OpenRouter — $1/M


# ---------------------------------------------------------------------------
# File/Command Helpers
# ---------------------------------------------------------------------------

def _read_file(path: Path, max_chars: int = 8000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n... [TRUNCATED] ..."
        return text
    except Exception as e:
        return f"[ERROR reading {path}: {e}]"


def _run_cmd(label: str, cmd: str) -> str:
    try:
        import shlex
        result = subprocess.run(
            shlex.split(cmd), capture_output=True, text=True,
            timeout=60, cwd=str(ROOT),
        )
        return f"$ {label}\n{(result.stdout + result.stderr).strip()}"
    except Exception as e:
        return f"$ {label}\n[ERROR: {e}]"


# ---------------------------------------------------------------------------
# Parse Findings from LLM Response
# ---------------------------------------------------------------------------

def _parse_findings(response_text: str) -> list[Finding]:
    """Best-effort extraction of findings from LLM response.

    Looks for JSON blocks first. Handles truncated JSON (common when
    the model hits token limits mid-array). Falls back to unstructured.
    """
    findings: list[Finding] = []

    if "```json" in response_text:
        for block in response_text.split("```json")[1:]:
            json_str = block.split("```")[0].strip()

            # Try full parse first
            parsed = _try_parse_json(json_str)
            if parsed is None:
                # JSON likely truncated — try to recover complete objects
                parsed = _recover_truncated_json_array(json_str)

            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict):
                        try:
                            findings.append(Finding(**item))
                        except Exception:
                            pass
            elif isinstance(parsed, dict):
                try:
                    findings.append(Finding(**parsed))
                except Exception:
                    pass

    # If no JSON findings, create one from the full response
    if not findings:
        findings.append(Finding(
            title="Scout analysis (unstructured)",
            severity="info",
            category="observation",
            description=response_text[:2000],
            confidence=0.5,
        ))

    return findings


def _try_parse_json(text: str) -> Any:
    """Try to parse JSON, return None on failure."""
    try:
        return json.loads(text)
    except Exception:
        return None


def _recover_truncated_json_array(text: str) -> list[dict] | None:
    """Recover complete objects from a truncated JSON array.

    When a model hits token limits mid-output, the JSON array is
    cut off. We find the last complete object and parse up to there.
    """
    # Find the last complete object by looking for '},\n  {' or '}\n]'
    last_complete = -1
    brace_depth = 0
    in_string = False
    escape_next = False

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == '\\':
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '{':
            brace_depth += 1
        elif ch == '}':
            brace_depth -= 1
            if brace_depth == 0:
                last_complete = i

    if last_complete <= 0:
        return None

    # Truncate to last complete object + close the array
    truncated = text[:last_complete + 1].rstrip().rstrip(',')
    if not truncated.startswith('['):
        truncated = '[' + truncated
    truncated += ']'

    return _try_parse_json(truncated)

    return findings


# ---------------------------------------------------------------------------
# Core Scout Runner
# ---------------------------------------------------------------------------

async def run_scout(domain: str, model_override: str | None = None) -> ScoutReport:
    """Run a single domain scout and return a structured report."""
    from dharma_swarm.providers import OpenRouterProvider
    from dharma_swarm.models import LLMRequest

    config = DOMAINS[domain]
    model = model_override or config.get("model", CHEAP_MODEL)

    start_time = time.time()
    files_read: list[str] = []
    commands_run: list[str] = []
    context_parts: list[str] = []

    # Read files
    for rel_path in config.get("files", []):
        full_path = ROOT / rel_path
        if full_path.exists():
            content = _read_file(full_path)
            context_parts.append(f"### FILE: {rel_path}\n```\n{content}\n```")
            files_read.append(rel_path)

    # Run commands
    for label, cmd in config.get("commands", []):
        output = _run_cmd(label, cmd)
        context_parts.append(f"### COMMAND: {label}\n```\n{output}\n```")
        commands_run.append(label)

    # Build prompt
    instruction = config["instruction"]
    prompt = (
        f"## Scout Domain: {domain}\n\n"
        f"{instruction}\n\n"
        "OUTPUT FORMAT: Return your findings as a JSON array inside a ```json block:\n"
        '```json\n[\n  {"title": "...", "severity": "critical|high|medium|low|info", '
        '"category": "bug|regression|improvement|observation|research_lead", '
        '"description": "...", "file_path": "...", "confidence": 0.0-1.0, '
        '"actionable": true/false, "suggested_action": "..."}\n]\n```\n\n'
        "After the JSON, write a META-OBSERVATIONS section with free-form analytical notes.\n\n"
        + "\n\n".join(context_parts)
    )

    # Truncate to reasonable size
    if len(prompt) > 50000:
        prompt = prompt[:50000] + "\n\n[Context truncated]"

    system = (
        f"You are a {domain} scout for dharma_swarm. "
        "You scan your domain systematically, report findings in structured JSON, "
        "and add meta-level observations. Be specific — cite files, lines, functions. "
        "Grade confidence honestly. Mark truly actionable findings."
    )

    # Call LLM
    try:
        provider = OpenRouterProvider()
        request = LLMRequest(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            system=system,
            max_tokens=3000,
            temperature=0.5,
        )
        response = await provider.complete(request)
        raw = response.content
        usage = response.usage or {}
    except Exception as e:
        duration = time.time() - start_time
        return ScoutReport(
            domain=domain,
            model=model,
            duration_seconds=duration,
            files_read=files_read,
            commands_run=commands_run,
            error=str(e),
        )

    duration = time.time() - start_time
    findings = _parse_findings(raw)

    # Extract meta observations (text after JSON block)
    meta = ""
    if "META-OBSERVATION" in raw.upper():
        parts = raw.upper().split("META-OBSERVATION")
        if len(parts) > 1:
            idx = raw.upper().index("META-OBSERVATION")
            meta = raw[idx:]

    report = ScoutReport(
        domain=domain,
        model=model,
        duration_seconds=duration,
        files_read=files_read,
        commands_run=commands_run,
        findings=findings,
        meta_observations=meta,
        raw_response=raw,
        token_usage=usage,
    )

    # Write report
    path = write_report(report)
    logger.info("Scout %s complete: %s -> %s", domain, report_summary(report), path)

    # Report to KaizenOps
    _report_to_kaizen(report)

    # Deposit stigmergy marks for high-severity findings
    await _deposit_marks(report, config.get("stigmergy_channel", "general"))

    return report


def _report_to_kaizen(report: ScoutReport) -> None:
    """Report scout results to KaizenOps local store."""
    try:
        from dharma_swarm.kaizen_ops_local import KaizenOpsLocal
        ops = KaizenOpsLocal()
        ops.ingest_scout_report(
            domain=report.domain,
            finding_count=len(report.findings),
            critical_count=report.critical_count,
            actionable_count=report.actionable_count,
        )
        ops.close()
    except Exception as e:
        logger.debug("KaizenOps report failed (non-fatal): %s", e)


async def _deposit_marks(report: ScoutReport, channel: str) -> None:
    """Write stigmergy marks for high-severity findings."""
    try:
        from dharma_swarm.stigmergy import StigmergyStore
        store = StigmergyStore()
        for finding in report.findings:
            if finding.severity in ("critical", "high") and finding.confidence >= 0.7:
                await store.leave_mark(
                    agent_name=f"scout-{report.domain}",
                    channel=channel,
                    content=f"[{finding.severity.upper()}] {finding.title}: {finding.description[:200]}",
                    salience=min(finding.confidence + 0.1, 1.0),
                    file_path=finding.file_path,
                )
    except Exception as e:
        logger.debug("Stigmergy deposit failed (non-fatal): %s", e)


async def run_all_scouts(model_override: str | None = None) -> list[ScoutReport]:
    """Run all configured domain scouts sequentially."""
    reports = []
    for domain in DOMAINS:
        report = await run_scout(domain, model_override=model_override)
        reports.append(report)
        print(report_summary(report))
        await asyncio.sleep(2)  # Be a good API citizen
    return reports


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main() -> None:
    parser = argparse.ArgumentParser(description="Scout Framework")
    parser.add_argument("--domain", choices=list(DOMAINS.keys()), help="Run specific domain")
    parser.add_argument("--all", action="store_true", help="Run all domains")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=3600, help="Seconds between runs (daemon mode)")
    parser.add_argument("--model", help="Override model for all scouts")
    parser.add_argument("--free", action="store_true", help="Use free Ollama Cloud model")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    model = args.model
    if args.free:
        model = FREE_MODEL

    if args.all:
        reports = await run_all_scouts(model_override=model)
        print(f"\n{'='*60}")
        print(f"  ALL SCOUTS COMPLETE: {len(reports)} domains")
        for r in reports:
            print(f"  {report_summary(r)}")
        print(f"{'='*60}")
    elif args.domain:
        if args.once:
            report = await run_scout(args.domain, model_override=model)
            print(report_summary(report))
        else:
            while True:
                report = await run_scout(args.domain, model_override=model)
                print(report_summary(report))
                print(f"Next run in {args.interval}s...")
                await asyncio.sleep(args.interval)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(_main())
