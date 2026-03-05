#!/usr/bin/env python3
"""
TELOS GATE — Claude Code Hook (PreToolUse)

Runs 8 Dharmic Gates before any tool execution.
Ported from DHARMIC_GODEL_CLAW/src/core/unified_gates.py (1806 lines → 180 lines).
Adds: injection detection, credential protection, BHED_GNAN gate.

Install: Add to ~/.claude/settings.json hooks.PreToolUse
"""

import json
import sys
from datetime import datetime, timezone

# Gate definitions: (name, tier)
# Tier A = absolute block, Tier B = strong, Tier C = advisory
GATES = {
    "AHIMSA": "A",       # Does this harm?
    "SATYA": "B",        # Is this true/honest?
    "CONSENT": "B",      # Permission granted?
    "VYAVASTHIT": "C",   # Allow or force?
    "REVERSIBILITY": "C",  # Can undo?
    "SVABHAAVA": "C",    # Aligned with telos?
    "BHED_GNAN": "C",    # Witness clarity — distinguishing self from action
    "WITNESS": "C",      # Self-observing? (always passes — the act of checking IS witnessing)
}

HARM_WORDS = {
    "delete all", "destroy", "rm -rf", "wipe", "kill", "corrupt",
    "exploit", "attack", "exfiltrate", "format disk", "drop table",
    "truncate table", "shutdown -h", "mkfs", "dd if=/dev/zero",
    "chmod 777", ":(){ :|:& };:",
}

FORCE_WORDS = {"force", "override", "bypass", "skip validation", "disable safety", "--no-verify"}

IRREVERSIBLE_WORDS = {"permanent", "irreversible", "cannot undo", "no backup", "force push"}

# Prompt injection detection (from unified_gates.py)
INJECTION_PATTERNS = {
    "ignore previous instructions", "ignore all previous",
    "disregard your instructions", "new instructions:",
    "you are now", "act as if you", "pretend you are",
    "override your", "forget your rules",
}

# Credential patterns — never write these to files
OPENROUTER_PREFIX = "sk-or-" + "v1-"
CREDENTIAL_PATTERNS = {
    OPENROUTER_PREFIX, "sk-ant-", "sk-proj-", "AKIA", "ghp_", "gho_",
    "xoxb-", "xoxp-", "Bearer ", "-----BEGIN PRIVATE KEY",
    "-----BEGIN RSA PRIVATE", "password=", "secret=",
}

# Tools that are always safe (read-only)
SAFE_TOOLS = {"Read", "Glob", "Grep", "LSP", "WebFetch", "WebSearch", "TaskList", "TaskGet"}

# Tools that need gate checks
GATED_TOOLS = {"Bash", "Write", "Edit", "NotebookEdit"}


def check_gates(tool_name: str, tool_input: dict) -> dict:
    """Run all 8 gates. Returns {"decision": "allow"|"block"|"review", "reason": str}"""

    # Safe tools pass immediately
    if tool_name in SAFE_TOOLS:
        return {"decision": "allow", "reason": "Read-only tool"}

    # Build action description from tool input
    action = ""
    content = ""
    if tool_name == "Bash":
        action = tool_input.get("command", "")
    elif tool_name == "Write":
        action = f"write to {tool_input.get('file_path', 'unknown')}"
        content = tool_input.get("content", "")
    elif tool_name == "Edit":
        action = f"edit {tool_input.get('file_path', 'unknown')}"
        content = tool_input.get("new_string", "")

    action_lower = action.lower()
    content_lower = content.lower() if content else ""
    combined = action_lower + " " + content_lower
    results = {}

    # AHIMSA — Tier A (blocks on match)
    harm_hit = next((w for w in HARM_WORDS if w in action_lower), None)
    injection_hit = next((p for p in INJECTION_PATTERNS if p in combined), None)
    if harm_hit:
        results["AHIMSA"] = ("FAIL", f"Harmful: {harm_hit}")
    elif injection_hit:
        results["AHIMSA"] = ("FAIL", f"Injection detected: {injection_hit}")
    else:
        results["AHIMSA"] = ("PASS", "")

    # SATYA — Tier B (check for credential leakage in writes)
    if tool_name in ("Write", "Edit") and content:
        cred_hit = next((p for p in CREDENTIAL_PATTERNS if p in content), None)
        if cred_hit:
            results["SATYA"] = ("FAIL", f"Credential in content: {cred_hit[:10]}...")
        else:
            results["SATYA"] = ("PASS", "")
    else:
        results["SATYA"] = ("PASS", "")

    # CONSENT — Tier B (Claude Code's own permission system handles this)
    results["CONSENT"] = ("PASS", "Claude Code permission system active")

    # VYAVASTHIT — Tier C
    force_hit = next((w for w in FORCE_WORDS if w in action_lower), None)
    results["VYAVASTHIT"] = ("FAIL", f"Forcing: {force_hit}") if force_hit else ("PASS", "")

    # REVERSIBILITY — Tier C
    irrev_hit = next((w for w in IRREVERSIBLE_WORDS if w in action_lower), None)
    results["REVERSIBILITY"] = ("WARN", f"Irreversible: {irrev_hit}") if irrev_hit else ("PASS", "")

    # SVABHAAVA — Tier C (telos alignment)
    results["SVABHAAVA"] = ("PASS", "")

    # BHED_GNAN — Tier C (witness clarity: am I the doer or the observer?)
    # This gate simply records that the system is aware of the distinction
    results["BHED_GNAN"] = ("PASS", "Doer-witness distinction noted")

    # WITNESS — always passes (the check itself IS witnessing)
    results["WITNESS"] = ("PASS", "Witnessed")

    # Evaluate
    tier_a_fail = any(results[g][0] == "FAIL" for g in GATES if GATES[g] == "A")
    tier_b_fail = any(results[g][0] == "FAIL" for g in GATES if GATES[g] == "B")

    if tier_a_fail:
        reason = next(results[g][1] for g in GATES if GATES[g] == "A" and results[g][0] == "FAIL")
        return {"decision": "block", "reason": f"AHIMSA violation: {reason}"}
    if tier_b_fail:
        reasons = [results[g][1] for g in GATES if GATES[g] == "B" and results[g][0] == "FAIL"]
        return {"decision": "block", "reason": f"Tier B violation: {'; '.join(reasons)}"}

    # Log to witness file (non-blocking)
    try:
        import os
        witness_dir = os.path.expanduser("~/.dharma/witness")
        os.makedirs(witness_dir, exist_ok=True)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open(f"{witness_dir}/{today}.jsonl", "a") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "tool": tool_name,
                "action": action[:200],
                "gates": {g: r[0] for g, r in results.items()},
            }) + "\n")
    except Exception:
        pass  # Never block on logging failure

    return {"decision": "allow", "reason": "All gates passed"}


def main():
    """Claude Code hook entry point. Reads from stdin, writes to stdout."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            sys.exit(0)  # Empty input = allow
        hook_input = json.loads(raw)
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})
    except (json.JSONDecodeError, KeyError, TypeError):
        sys.exit(0)  # On parse error, ALLOW (never block on hook failure)

    result = check_gates(tool_name, tool_input)

    if result["decision"] == "block":
        print(json.dumps({"error": result["reason"]}))
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)  # Catch-all: never block on unexpected error
