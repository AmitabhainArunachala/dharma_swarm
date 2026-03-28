"""Synthesis Agent — Tier 2 intelligence that reads all scout reports.

Reads every scout's latest.json, cross-references findings, detects
contradictions, grades scout quality, and produces:
  1. A synthesis report (~/.dharma/scouts/synthesis/{date}.md)
  2. An action queue for the overnight director
  3. Research seeds for the garden daemon

This is the connective tissue between observation (scouts) and action
(overnight director, evolution engine, coding agents).

Usage:
    python3 -m dharma_swarm.synthesis_agent --once
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from dharma_swarm.scout_report import (
    Finding,
    ScoutReport,
    read_all_latest,
    report_summary,
)

logger = logging.getLogger(__name__)

SCOUTS_DIR = Path.home() / ".dharma" / "scouts"
SYNTHESIS_DIR = SCOUTS_DIR / "synthesis"
OVERNIGHT_QUEUE = Path.home() / ".dharma" / "overnight" / "queue.yaml"
SEEDS_DIR = Path.home() / ".dharma" / "seeds"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _date_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")


# ---------------------------------------------------------------------------
# Pre-synthesis: structured context assembly (NO LLM needed for this)
# ---------------------------------------------------------------------------

def _build_cross_reference(reports: dict[str, ScoutReport]) -> dict[str, Any]:
    """Pure-Python cross-referencing before sending to the LLM.

    Finds patterns the LLM should focus on:
    - Files mentioned by multiple scouts
    - Severity clusters
    - Contradictions (same file, different assessments)
    - Coverage gaps (domains with zero actionable findings)
    """
    file_mentions: dict[str, list[str]] = {}  # file -> [domains that mention it]
    all_findings: list[tuple[str, Finding]] = []  # (domain, finding) pairs
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    scout_quality: dict[str, dict] = {}

    for domain, report in reports.items():
        for finding in report.findings:
            all_findings.append((domain, finding))
            severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
            if finding.file_path:
                file_mentions.setdefault(finding.file_path, []).append(domain)

        # Grade scout quality
        structured_count = sum(1 for f in report.findings if f.title != "Scout analysis (unstructured)")
        scout_quality[domain] = {
            "total_findings": len(report.findings),
            "structured": structured_count,
            "actionable": report.actionable_count,
            "high_confidence": len(report.high_confidence_findings),
            "parse_quality": "good" if structured_count == len(report.findings) else "partial" if structured_count > 0 else "failed",
        }

    # Files touched by multiple scouts = convergence points
    convergence_files = {f: domains for f, domains in file_mentions.items() if len(domains) > 1}

    # Domains with zero actionable findings = possible gaps
    thin_domains = [d for d, r in reports.items() if r.actionable_count == 0]

    return {
        "total_findings": len(all_findings),
        "severity_counts": severity_counts,
        "convergence_files": convergence_files,
        "thin_domains": thin_domains,
        "scout_quality": scout_quality,
    }


def _build_synthesis_prompt(reports: dict[str, ScoutReport], xref: dict[str, Any]) -> str:
    """Build the prompt for the frontier synthesis model."""

    # Compile all findings into a structured briefing
    findings_text = ""
    for domain, report in sorted(reports.items()):
        findings_text += f"\n### {domain.upper()} ({len(report.findings)} findings)\n"
        for f in report.findings:
            flag = " **[ACTIONABLE]**" if f.actionable else ""
            findings_text += (
                f"- **[{f.severity.upper()}|conf:{f.confidence}]** {f.title}{flag}\n"
                f"  {f.description[:200]}\n"
            )
            if f.suggested_action:
                findings_text += f"  *Suggested:* {f.suggested_action[:150]}\n"
        if report.meta_observations:
            findings_text += f"\n*Meta:* {report.meta_observations[:400]}\n"

    # Cross-reference briefing
    xref_text = "\n### CROSS-REFERENCE ANALYSIS (pre-computed)\n"
    xref_text += f"- Total findings: {xref['total_findings']}\n"
    xref_text += f"- Severity: {xref['severity_counts']}\n"
    if xref["convergence_files"]:
        xref_text += f"- **Convergence files** (mentioned by multiple scouts):\n"
        for f, domains in xref["convergence_files"].items():
            xref_text += f"  - `{f}` mentioned by: {', '.join(domains)}\n"
    if xref["thin_domains"]:
        xref_text += f"- **Thin domains** (0 actionable): {xref['thin_domains']}\n"
    xref_text += f"- Scout quality: {json.dumps(xref['scout_quality'], indent=2)}\n"

    prompt = f"""## SCOUT SYNTHESIS BRIEFING
*{_utc_now()}* | {len(reports)} scouts reporting

You are the Synthesis Agent — a frontier model reading structured reports from
domain scout agents. Your job is NOT to repeat what they found. Your job is to:

1. **READ BETWEEN THE LINES** — What did the scouts miss? What connections exist
   across domains that no single scout could see?

2. **GRADE SCOUT ACCURACY** — Based on your knowledge, which findings are correct
   and which are wrong or overstated? Be specific.

3. **EXTRACT NOVEL INSIGHTS** — What emerges from the combination of all reports
   that wasn't visible to any individual scout?

4. **PRIORITIZE RUTHLESSLY** — If we could only do ONE thing from all these findings,
   what would have the highest impact? Then the second. Then the third. Max 5.

5. **ROUTE TO ACTION** — For each priority item, specify:
   - TYPE: code_fix | test_addition | config_change | architecture_refactor | research_needed
   - URGENCY: now | this_week | next_sprint | backlog
   - AGENT: which agent type should handle it (coding, architect, researcher)
   - ACCEPTANCE: how do we know it's done?

{findings_text}

{xref_text}

## OUTPUT FORMAT

### 1. Cross-Domain Insights (what no single scout could see)
[Your analysis]

### 2. Scout Accuracy Grades
| Scout | Grade | Notes |
|-------|-------|-------|
[Grade each A/B/C/D/F]

### 3. Priority Actions (max 5, ordered by impact)
For each:
- **What**: one sentence
- **Why**: why this matters more than everything else
- **Type**: code_fix | test_addition | config_change | architecture_refactor | research_needed
- **Urgency**: now | this_week | next_sprint | backlog
- **Agent**: coding | architect | researcher | human
- **Acceptance criterion**: mechanical pass/fail test
- **Estimated effort**: hours

### 4. Research Seeds (insights worth deeper investigation)
[Novel questions or connections that deserve follow-up]

### 5. What the Scouts Missed
[Blind spots across all scouts — domains or concerns not covered]
"""
    return prompt


# ---------------------------------------------------------------------------
# Synthesis execution
# ---------------------------------------------------------------------------

async def run_synthesis(model: str = "claude-opus-4-6") -> Path | None:
    """Run the synthesis agent on all latest scout reports."""
    reports = read_all_latest()
    if not reports:
        logger.warning("No scout reports found at %s", SCOUTS_DIR)
        return None

    print(f"Synthesis Agent — reading {len(reports)} scout reports")
    for domain, report in sorted(reports.items()):
        print(f"  {report_summary(report)}")

    # Pre-compute cross-references (free, no LLM)
    xref = _build_cross_reference(reports)
    print(f"\nCross-reference: {xref['total_findings']} total findings, "
          f"{len(xref['convergence_files'])} convergence files, "
          f"{len(xref['thin_domains'])} thin domains")

    # Build prompt
    prompt = _build_synthesis_prompt(reports, xref)
    print(f"\nSynthesis prompt: {len(prompt)} chars")

    # Call frontier model
    start = time.time()
    try:
        from dharma_swarm.runtime_provider import (
            complete_via_preferred_runtime_providers,
        )
        from dharma_swarm.models import ProviderType

        # Use the preferred runtime chain — Ollama Cloud first, then up
        # For synthesis we want quality, so override to a strong model
        response, config = await complete_via_preferred_runtime_providers(
            messages=[{"role": "user", "content": prompt}],
            system=(
                "You are the Synthesis Agent — the most capable model in the system. "
                "You read reports from cheaper scout models and add what they cannot: "
                "cross-domain insight, accuracy correction, and ruthless prioritization. "
                "Be specific. Cite file names. Grade honestly. The builder wants truth."
            ),
            max_tokens=4000,
            temperature=0.4,
        )
        raw = response.content
        provider_used = config.provider.value
        model_used = config.default_model or "unknown"
    except Exception as e:
        logger.error("Synthesis LLM call failed: %s", e)
        print(f"ERROR: {e}")
        return None

    duration = time.time() - start
    print(f"\nSynthesis complete: {len(raw)} chars via {provider_used}/{model_used} in {duration:.1f}s")

    # Write synthesis report
    SYNTHESIS_DIR.mkdir(parents=True, exist_ok=True)
    date_stamp = _date_stamp()
    report_path = SYNTHESIS_DIR / f"{date_stamp}.md"

    header = (
        f"# Scout Synthesis Report\n"
        f"*{_utc_now()}* | Model: {model_used} via {provider_used} | "
        f"Duration: {duration:.1f}s\n\n"
        f"**Input:** {len(reports)} scouts, {xref['total_findings']} findings, "
        f"{xref['severity_counts']} severity distribution\n\n"
        f"---\n\n"
    )
    report_path.write_text(header + raw, encoding="utf-8")

    # Also write latest pointer
    (SYNTHESIS_DIR / "latest.md").write_text(header + raw, encoding="utf-8")

    print(f"Report written: {report_path}")

    # Extract action items and write to overnight queue
    _write_action_queue(raw, date_stamp)

    return report_path


def _write_action_queue(synthesis_text: str, date_stamp: str) -> None:
    """Extract priority actions from synthesis and append to overnight queue."""
    OVERNIGHT_QUEUE.parent.mkdir(parents=True, exist_ok=True)

    # Simple extraction: look for the Priority Actions section
    actions_section = ""
    if "Priority Actions" in synthesis_text:
        idx = synthesis_text.index("Priority Actions")
        # Find next major section
        rest = synthesis_text[idx:]
        for marker in ["### 4.", "### 5.", "## "]:
            if marker in rest[20:]:
                end = rest.index(marker, 20)
                actions_section = rest[:end]
                break
        else:
            actions_section = rest[:2000]

    if actions_section:
        entry = (
            f"\n# From synthesis {date_stamp}\n"
            f"{actions_section}\n"
        )
        with open(OVERNIGHT_QUEUE, "a", encoding="utf-8") as f:
            f.write(entry)
        print(f"Action queue updated: {OVERNIGHT_QUEUE}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def _main() -> None:
    parser = argparse.ArgumentParser(description="Synthesis Agent")
    parser.add_argument("--once", action="store_true", help="Run once")
    parser.add_argument("--model", default="claude-opus-4-6", help="Synthesis model")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    if args.once:
        path = await run_synthesis(model=args.model)
        if path:
            print(f"\nSynthesis report: {path}")
        else:
            print("No synthesis produced.")


if __name__ == "__main__":
    asyncio.run(_main())
