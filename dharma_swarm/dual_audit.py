"""Dual-process audit engine — Claude + Codex in sync.

Runs the SAME audit prompt through both Claude (via claude -p) and
Codex (via codex exec) in parallel, then compares findings for
agreement/disagreement. The two-model approach provides decorrelated
error detection per the Transcendence Principle (Krogh-Vedelsby):
ensemble error = mean error - diversity term.

Usage (CLI):
    python3 -m dharma_swarm.dual_audit --target dharma_swarm/swarm.py

Usage (programmatic):
    from dharma_swarm.dual_audit import DualAudit
    audit = DualAudit()
    report = await audit.run("dharma_swarm/swarm.py")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from dharma_swarm.codex_cli import dgc_codex_exec_prefix

logger = logging.getLogger(__name__)

ROOT = Path.home() / "dharma_swarm"
STATE = Path.home() / ".dharma" / "dual_audit"

CLAUDE_CMD = "claude"
CODEX_CMD = "codex"

AUDIT_CATEGORIES = [
    "security",
    "correctness",
    "performance",
    "maintainability",
    "architecture",
]

_AUDIT_PROMPT_TEMPLATE = """\
You are a code auditor. Analyze the following file(s) and produce a structured
JSON audit report. Be specific — cite line numbers, function names, and exact issues.

## Categories to evaluate
{categories}

## Files to audit
{files_content}

## Output format (strict JSON, no markdown fencing)
{{
  "findings": [
    {{
      "category": "<one of: {category_list}>",
      "severity": "<low|medium|high|critical>",
      "location": "<file:line or file:function>",
      "title": "<short description>",
      "detail": "<explanation>",
      "recommendation": "<fix suggestion>"
    }}
  ],
  "summary": "<1-2 sentence overall assessment>"
}}
"""


@dataclass(slots=True)
class Finding:
    category: str
    severity: str
    location: str
    title: str
    detail: str
    recommendation: str
    source: str = ""  # "claude" or "codex"


@dataclass(slots=True)
class AuditReport:
    target: str
    timestamp: str = ""
    claude_findings: list[dict[str, Any]] = field(default_factory=list)
    codex_findings: list[dict[str, Any]] = field(default_factory=list)
    agreements: list[dict[str, Any]] = field(default_factory=list)
    claude_only: list[dict[str, Any]] = field(default_factory=list)
    codex_only: list[dict[str, Any]] = field(default_factory=list)
    claude_summary: str = ""
    codex_summary: str = ""
    claude_duration_sec: float = 0.0
    codex_duration_sec: float = 0.0
    error: str = ""


def _build_prompt(targets: Sequence[str | Path], categories: list[str] | None = None) -> str:
    cats = categories or AUDIT_CATEGORIES
    parts: list[str] = []
    for t in targets:
        p = Path(t)
        if not p.exists():
            p = ROOT / t
        if p.exists():
            content = p.read_text(errors="replace")
            if len(content) > 80_000:
                content = content[:80_000] + "\n... (truncated)"
            parts.append(f"### {p.name}\n```\n{content}\n```")
        else:
            parts.append(f"### {t}\n(file not found)")
    return _AUDIT_PROMPT_TEMPLATE.format(
        categories="\n".join(f"- {c}" for c in cats),
        files_content="\n\n".join(parts),
        category_list=", ".join(cats),
    )


def _parse_json_response(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines)
        for i, line in enumerate(lines[1:], 1):
            if line.strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        brace = text.find("{")
        if brace >= 0:
            bracket = text.rfind("}")
            if bracket > brace:
                try:
                    return json.loads(text[brace : bracket + 1])
                except json.JSONDecodeError:
                    pass
        return {"findings": [], "summary": f"(parse error) {text[:200]}"}


async def _run_claude(prompt: str, timeout: int = 120) -> tuple[dict[str, Any], float]:
    if not shutil.which(CLAUDE_CMD):
        return {"findings": [], "summary": "(claude CLI not found)"}, 0.0
    if os.environ.get("CLAUDECODE"):
        return {"findings": [], "summary": "(skipped — nested claude session)"}, 0.0
    t0 = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        CLAUDE_CMD, "-p", prompt, "--output-format", "text",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"findings": [], "summary": "(timeout)"}, time.monotonic() - t0
    elapsed = time.monotonic() - t0
    raw = stdout.decode(errors="replace")
    return _parse_json_response(raw), elapsed


async def _run_codex(prompt: str, timeout: int = 120) -> tuple[dict[str, Any], float]:
    if not shutil.which(CODEX_CMD):
        return {"findings": [], "summary": "(codex CLI not found)"}, 0.0
    t0 = time.monotonic()
    cmd = dgc_codex_exec_prefix(cli_path=CODEX_CMD)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, "-q", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(ROOT),
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"findings": [], "summary": "(timeout)"}, time.monotonic() - t0
    finally:
        Path(prompt_file).unlink(missing_ok=True)
    elapsed = time.monotonic() - t0
    raw = stdout.decode(errors="replace")
    return _parse_json_response(raw), elapsed


def _normalize_finding(f: dict[str, Any]) -> str:
    return f"{f.get('category', '')}:{f.get('location', '')}:{f.get('title', '')}".lower()


def _compare(claude_data: dict, codex_data: dict) -> tuple[list[dict], list[dict], list[dict]]:
    cf = claude_data.get("findings", [])
    xf = codex_data.get("findings", [])
    c_keys = {_normalize_finding(f): f for f in cf}
    x_keys = {_normalize_finding(f): f for f in xf}
    agreed = []
    for k in c_keys:
        if k in x_keys:
            merged = dict(c_keys[k])
            merged["codex_detail"] = x_keys[k].get("detail", "")
            merged["source"] = "both"
            agreed.append(merged)
    c_only = [dict(f, source="claude") for f in cf if _normalize_finding(f) not in x_keys]
    x_only = [dict(f, source="codex") for f in xf if _normalize_finding(f) not in c_keys]
    return agreed, c_only, x_only


class DualAudit:
    def __init__(
        self,
        categories: list[str] | None = None,
        timeout: int = 120,
    ) -> None:
        self.categories = categories or AUDIT_CATEGORIES
        self.timeout = timeout

    async def run(self, *targets: str | Path) -> AuditReport:
        prompt = _build_prompt(targets, self.categories)
        report = AuditReport(
            target=", ".join(str(t) for t in targets),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        claude_result, codex_result = await asyncio.gather(
            _run_claude(prompt, self.timeout),
            _run_codex(prompt, self.timeout),
            return_exceptions=True,
        )
        if isinstance(claude_result, BaseException):
            report.error += f"claude error: {claude_result}; "
            claude_data: dict = {"findings": [], "summary": str(claude_result)}
            report.claude_duration_sec = 0.0
        else:
            claude_data, report.claude_duration_sec = claude_result

        if isinstance(codex_result, BaseException):
            report.error += f"codex error: {codex_result}; "
            codex_data: dict = {"findings": [], "summary": str(codex_result)}
            report.codex_duration_sec = 0.0
        else:
            codex_data, report.codex_duration_sec = codex_result

        report.claude_findings = claude_data.get("findings", [])
        report.codex_findings = codex_data.get("findings", [])
        report.claude_summary = claude_data.get("summary", "")
        report.codex_summary = codex_data.get("summary", "")
        report.agreements, report.claude_only, report.codex_only = _compare(
            claude_data, codex_data,
        )
        self._persist(report)
        return report

    def _persist(self, report: AuditReport) -> Path:
        STATE.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = STATE / f"dual_audit_{ts}.json"
        out.write_text(json.dumps(asdict(report), indent=2, default=str))
        logger.info("dual audit saved: %s", out)
        return out


async def _main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Claude+Codex dual-process audit")
    parser.add_argument("--target", "-t", nargs="+", required=True, help="Files to audit")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--categories", nargs="*")
    args = parser.parse_args()

    audit = DualAudit(categories=args.categories, timeout=args.timeout)
    report = await audit.run(*args.target)

    print(f"\n{'='*60}")
    print(f"DUAL AUDIT: {report.target}")
    print(f"{'='*60}")
    print(f"Claude: {len(report.claude_findings)} findings ({report.claude_duration_sec:.1f}s)")
    print(f"Codex:  {len(report.codex_findings)} findings ({report.codex_duration_sec:.1f}s)")
    print(f"Agreed: {len(report.agreements)}")
    print(f"Claude-only: {len(report.claude_only)}")
    print(f"Codex-only:  {len(report.codex_only)}")
    if report.agreements:
        print(f"\n--- AGREED FINDINGS (highest confidence) ---")
        for f in report.agreements:
            print(f"  [{f.get('severity','?')}] {f.get('location','?')}: {f.get('title','?')}")
    if report.claude_only:
        print(f"\n--- CLAUDE-ONLY ---")
        for f in report.claude_only:
            print(f"  [{f.get('severity','?')}] {f.get('location','?')}: {f.get('title','?')}")
    if report.codex_only:
        print(f"\n--- CODEX-ONLY ---")
        for f in report.codex_only:
            print(f"  [{f.get('severity','?')}] {f.get('location','?')}: {f.get('title','?')}")
    if report.error:
        print(f"\nErrors: {report.error}")
    print(f"\nClaude summary: {report.claude_summary}")
    print(f"Codex summary:  {report.codex_summary}")


if __name__ == "__main__":
    asyncio.run(_main())
