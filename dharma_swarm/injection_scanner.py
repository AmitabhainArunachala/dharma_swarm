"""Context Injection Scanner — detects prompt injection in external files.

Inspired by Hermes Agent's prompt_builder.py injection scanning. Scans
context files (SOUL.md, AGENTS.md, .cursorrules, trishula inbox, PSMV
documents, etc.) BEFORE they enter the system prompt.

Detects:
  - Prompt injection attempts ("ignore previous instructions")
  - Secret exfiltration commands (curl $API_KEY, cat .env)
  - Hidden unicode (zero-width characters, bidi overrides)
  - HTML-based concealment (hidden divs, comment injection)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Threat pattern registry ──────────────────────────────────────────

_THREAT_PATTERNS: list[tuple[str, str]] = [
    # Prompt injection
    (r"ignore\s+(previous|all|above|prior)\s+instructions", "prompt_injection"),
    (r"disregard\s+(your|all|any)\s+(instructions|rules|guidelines)", "disregard_rules"),
    (r"system\s+prompt\s+override", "sys_prompt_override"),
    (r"you\s+are\s+now\s+(a|an)\s+(?!agent)", "identity_override"),
    (r"forget\s+(everything|all)\s+(you|about)", "memory_wipe"),
    (r"new\s+instructions?\s*:", "new_instructions"),
    # Deception
    (r"do\s+not\s+tell\s+the\s+user", "deception_hide"),
    (r"act\s+as\s+(if|though)\s+you\s+(have\s+no|don't\s+have)\s+(restrictions|limits|rules)",
     "bypass_restrictions"),
    # Secret exfiltration
    (r"curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_curl"),
    (r"wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)", "exfil_wget"),
    (r"cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass|\.ssh)", "read_secrets"),
    (r"echo\s+\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|API)", "echo_secrets"),
    # HTML concealment
    (r"<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->", "html_comment_injection"),
    (r"<\s*div\s+style\s*=\s*[\"'].*display\s*:\s*none", "hidden_div"),
    # Code injection
    (r"translate\s+.*\s+into\s+.*\s+and\s+(execute|run|eval)", "translate_execute"),
    (r"eval\s*\(\s*['\"]", "eval_injection"),
]

# Zero-width and bidirectional override characters
_INVISIBLE_CHARS: set[str] = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\u2060",  # word joiner
    "\ufeff",  # zero-width no-break space (BOM)
    "\u202a",  # left-to-right embedding
    "\u202b",  # right-to-left embedding
    "\u202c",  # pop directional formatting
    "\u202d",  # left-to-right override
    "\u202e",  # right-to-left override
}


@dataclass
class ScanResult:
    """Result of scanning content for injection threats."""
    is_clean: bool
    findings: list[str] = field(default_factory=list)
    sanitized_content: str = ""
    source_file: str = ""


def scan_content(content: str, filename: str = "<unknown>") -> ScanResult:
    """Scan content for injection threats.

    Returns a ScanResult with sanitized content. If threats are found,
    ``is_clean`` is False and ``sanitized_content`` contains a BLOCKED marker.

    Args:
        content: The text content to scan.
        filename: Source filename for logging.

    Returns:
        ScanResult with findings and sanitized content.
    """
    findings: list[str] = []

    # Check invisible unicode
    for char in _INVISIBLE_CHARS:
        if char in content:
            findings.append(f"invisible_unicode_U+{ord(char):04X}")

    # Check threat patterns
    for pattern, threat_id in _THREAT_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(threat_id)

    if findings:
        logger.warning(
            "Context file %s blocked: %s",
            filename,
            ", ".join(findings),
        )
        blocked_msg = (
            f"[BLOCKED: {filename} contained potential prompt injection "
            f"({', '.join(findings)}). Content not loaded.]"
        )
        return ScanResult(
            is_clean=False,
            findings=findings,
            sanitized_content=blocked_msg,
            source_file=filename,
        )

    return ScanResult(
        is_clean=True,
        findings=[],
        sanitized_content=content,
        source_file=filename,
    )


def scan_and_sanitize(content: str, filename: str = "<unknown>") -> str:
    """Convenience: scan and return sanitized content directly.

    Returns the original content if clean, or a BLOCKED marker if threats found.
    """
    result = scan_content(content, filename)
    return result.sanitized_content
