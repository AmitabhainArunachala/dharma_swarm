"""DHARMA COMMAND — Tool definitions and executors for the agentic chat loop.

Gives the dashboard Claude real system access: filesystem, shell, search,
swarm control, evolution, stigmergy, traces, git.
"""

from __future__ import annotations

import asyncio
import glob as globmod
import json
import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Safety: scope filesystem operations to these roots
ALLOWED_ROOTS = [
    Path.home() / "dharma_swarm",
    Path.home() / ".dharma",
]

PROJECT_ROOT = Path.home() / "dharma_swarm"


def _path_allowed(path_str: str) -> bool:
    """Check if a path is within allowed roots."""
    try:
        resolved = Path(path_str).resolve()
        return any(
            resolved == root or root in resolved.parents
            for root in ALLOWED_ROOTS
        )
    except (ValueError, OSError):
        return False


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format for OpenRouter)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file. Returns the file content with line numbers. "
                "Scoped to ~/dharma_swarm/ and ~/.dharma/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file (relative to ~/dharma_swarm/)",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (1-indexed). Default: 1",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of lines to read. Default: 200",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file. Creates the file if it doesn't exist, "
                "overwrites if it does. Scoped to ~/dharma_swarm/ and ~/.dharma/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Replace a specific string in a file with new content. "
                "The old_string must appear exactly once in the file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "The exact string to find and replace",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The replacement string",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": (
                "Execute a shell command and return stdout/stderr. "
                "Working directory is ~/dharma_swarm/. "
                "Timeout: 30 seconds. Use for: running tests, git commands, "
                "restarting agents, checking processes, viewing logs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (max 60). Default: 30",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": (
                "Search file contents using regex patterns (like ripgrep). "
                "Returns matching lines with file paths and line numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory or file to search in. Default: ~/dharma_swarm/",
                    },
                    "glob": {
                        "type": "string",
                        "description": "File glob filter, e.g. '*.py', '*.ts'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results. Default: 30",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": (
                "Find files matching a glob pattern. "
                "Returns matching file paths sorted by modification time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Glob pattern, e.g. '**/*.py', 'api/routers/*.py'",
                    },
                    "path": {
                        "type": "string",
                        "description": "Base directory. Default: ~/dharma_swarm/",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "swarm_status",
            "description": (
                "Get detailed swarm status: all agents with their states, "
                "task counts, health report, anomalies, recent traces."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "include_traces": {
                        "type": "boolean",
                        "description": "Include recent trace entries. Default: false",
                    },
                    "include_anomalies": {
                        "type": "boolean",
                        "description": "Include anomaly details. Default: true",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evolution_query",
            "description": (
                "Query the evolution archive. Get entries, fitness trends, "
                "lineage chains, and stats."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "get", "lineage", "stats", "trend"],
                        "description": "What to query",
                    },
                    "entry_id": {
                        "type": "string",
                        "description": "Entry ID (for get/lineage actions)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries to return. Default: 20",
                    },
                    "status": {
                        "type": "string",
                        "description": "Filter by status (for list action)",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stigmergy_query",
            "description": (
                "Query stigmergy marks. Search by file path, agent, salience, "
                "or get hot paths and density stats."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["recent", "hot_paths", "high_salience", "density", "search"],
                        "description": "What to query",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search term (for search action)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results. Default: 20",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trace_query",
            "description": (
                "Query trace entries with full payloads. "
                "Filter by agent, action, state, time range."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "description": "Filter by agent name/id",
                    },
                    "action": {
                        "type": "string",
                        "description": "Filter by action type",
                    },
                    "state": {
                        "type": "string",
                        "description": "Filter by state (done, failed, etc.)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max entries. Default: 30",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_control",
            "description": (
                "Control swarm agents: spawn new agents, stop existing ones, "
                "or get detailed agent state."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["spawn", "stop", "inspect"],
                        "description": "What to do",
                    },
                    "agent_id": {
                        "type": "string",
                        "description": "Agent ID (for stop/inspect)",
                    },
                    "name": {
                        "type": "string",
                        "description": "Name for new agent (for spawn)",
                    },
                    "role": {
                        "type": "string",
                        "description": "Role for new agent (for spawn)",
                    },
                },
                "required": ["action"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool executors
# ---------------------------------------------------------------------------

def _resolve_path(path_str: str) -> Path:
    """Resolve a path, treating relative paths as relative to PROJECT_ROOT."""
    p = Path(path_str)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p.resolve()


async def exec_read_file(args: dict) -> str:
    path = _resolve_path(args["path"])
    if not _path_allowed(str(path)):
        return f"ERROR: Path {path} is outside allowed scope"
    if not path.exists():
        return f"ERROR: File not found: {path}"
    if not path.is_file():
        return f"ERROR: Not a file: {path}"

    offset = max(1, args.get("offset", 1))
    limit = min(500, args.get("limit", 200))

    try:
        lines = path.read_text(errors="replace").splitlines()
        selected = lines[offset - 1 : offset - 1 + limit]
        numbered = [
            f"{offset + i:>5} | {line}" for i, line in enumerate(selected)
        ]
        header = f"# {path} ({len(lines)} lines total, showing {offset}-{offset + len(selected) - 1})\n"
        return header + "\n".join(numbered)
    except Exception as e:
        return f"ERROR reading {path}: {e}"


async def exec_write_file(args: dict) -> str:
    path = _resolve_path(args["path"])
    if not _path_allowed(str(path)):
        return f"ERROR: Path {path} is outside allowed scope"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"])
        return f"OK: Wrote {len(args['content'])} bytes to {path}"
    except Exception as e:
        return f"ERROR writing {path}: {e}"


async def exec_edit_file(args: dict) -> str:
    path = _resolve_path(args["path"])
    if not _path_allowed(str(path)):
        return f"ERROR: Path {path} is outside allowed scope"
    if not path.exists():
        return f"ERROR: File not found: {path}"

    try:
        content = path.read_text()
        old = args["old_string"]
        new = args["new_string"]
        count = content.count(old)
        if count == 0:
            return f"ERROR: old_string not found in {path}"
        if count > 1:
            return f"ERROR: old_string found {count} times in {path} (must be unique)"
        updated = content.replace(old, new, 1)
        path.write_text(updated)
        return f"OK: Edited {path} (replaced 1 occurrence, {len(old)} → {len(new)} chars)"
    except Exception as e:
        return f"ERROR editing {path}: {e}"


_DANGEROUS_PATTERNS = [
    re.compile(r"rm\s+(-\w*[rf]\w*\s+)+/(?:\s|$)"),  # rm -rf /
    re.compile(r"rm\s+(-\w*[rf]\w*\s+)+~"),            # rm -rf ~
    re.compile(r"mkfs\b"),
    re.compile(r"dd\s+.*if\s*="),
    re.compile(r">\s*/dev/"),
    re.compile(r"chmod\s+.*777\s+/"),
    re.compile(r"curl\s+.*\|\s*(?:ba)?sh"),             # curl | sh
    re.compile(r"wget\s+.*\|\s*(?:ba)?sh"),
    re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}"),          # fork bomb
    re.compile(r">\s*/etc/"),
    re.compile(r"sudo\s"),
]


async def exec_shell(args: dict) -> str:
    command = args["command"]
    timeout = min(60, args.get("timeout", 30))

    # Gate check (S3 control — telos gates evaluate before execution)
    try:
        from dharma_swarm.telos_gates import check_action
        gate = check_action(action=f"shell_exec: {command[:200]}", content=command)
        if gate.decision.value == "BLOCK":
            logger.warning("Gate blocked shell command: %s — %s", command[:100], gate.reason)
            return f"ERROR: Gate blocked command: {gate.reason}"
    except Exception:
        logger.debug("Gate evaluation failed for shell command", exc_info=True)

    # Pattern-based blocklist (defense in depth)
    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(command):
            logger.warning("Blocked dangerous shell command: %s", command[:200])
            return f"ERROR: Blocked dangerous command pattern"

    # Audit log (P6 — witness everything)
    logger.info("shell_exec: %s", command[:300])

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
        out = stdout.decode(errors="replace")[:8000]
        err = stderr.decode(errors="replace")[:2000]
        result = f"exit_code: {proc.returncode}\n"
        if out:
            result += f"stdout:\n{out}\n"
        if err:
            result += f"stderr:\n{err}\n"
        return result
    except asyncio.TimeoutError:
        return f"ERROR: Command timed out after {timeout}s"
    except Exception as e:
        return f"ERROR: {e}"


async def exec_grep(args: dict) -> str:
    pattern = args["pattern"]
    search_path = _resolve_path(args.get("path", str(PROJECT_ROOT)))
    file_glob = args.get("glob", "")
    max_results = min(50, args.get("max_results", 30))

    if not _path_allowed(str(search_path)):
        return f"ERROR: Path {search_path} is outside allowed scope"

    cmd_parts = ["rg", "--no-heading", "-n", "--max-count", str(max_results)]
    if file_glob:
        cmd_parts.extend(["--glob", file_glob])
    cmd_parts.extend(["--", pattern, str(search_path)])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        out = stdout.decode(errors="replace")[:6000]
        if not out.strip():
            return f"No matches for pattern '{pattern}'"
        return out
    except asyncio.TimeoutError:
        return "ERROR: Search timed out"
    except FileNotFoundError:
        # Fallback to grep if rg not available
        return "ERROR: ripgrep (rg) not found"
    except Exception as e:
        return f"ERROR: {e}"


async def exec_glob(args: dict) -> str:
    pattern = args["pattern"]
    base = _resolve_path(args.get("path", str(PROJECT_ROOT)))

    if not _path_allowed(str(base)):
        return f"ERROR: Path {base} is outside allowed scope"

    try:
        matches = sorted(
            globmod.glob(str(base / pattern), recursive=True),
            key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0,
            reverse=True,
        )[:50]
        if not matches:
            return f"No files matching '{pattern}' in {base}"
        return "\n".join(matches)
    except Exception as e:
        return f"ERROR: {e}"


async def exec_swarm_status(args: dict) -> str:
    parts = []
    try:
        from api.main import get_swarm, get_trace_store, get_monitor

        swarm = get_swarm()
        try:
            status = await swarm.status()
            parts.append(
                f"Swarm: {len(status.agents)} agents, "
                f"running={status.tasks_running}, completed={status.tasks_completed}, "
                f"failed={status.tasks_failed}, pending={status.tasks_pending}, "
                f"uptime={status.uptime_seconds:.0f}s"
            )
            parts.append("\nAgents:")
            for a in status.agents:
                line = f"  {a.name} ({a.role}) — {a.status}"
                if hasattr(a, "current_task") and a.current_task:
                    line += f" [task: {a.current_task}]"
                parts.append(line)
        except Exception as e:
            parts.append(f"Swarm status error: {e}")

        monitor = get_monitor()
        include_anomalies = args.get("include_anomalies", True)
        try:
            report = await monitor.check_health()
            hs = report.overall_status.value if hasattr(report.overall_status, "value") else str(report.overall_status)
            parts.append(
                f"\nHealth: {hs}, {report.total_traces} total traces, "
                f"{report.traces_last_hour} last hour, "
                f"failure_rate={report.failure_rate:.2%}, "
                f"mean_fitness={report.mean_fitness:.4f}"
            )
            if include_anomalies and report.anomalies:
                parts.append("\nAnomalies:")
                for a in report.anomalies:
                    parts.append(f"  [{a.severity}] {a.anomaly_type}: {a.description}")
                    if a.related_traces:
                        parts.append(f"    related traces: {', '.join(a.related_traces[:5])}")
        except Exception as e:
            parts.append(f"Health error: {e}")

        if args.get("include_traces", False):
            try:
                trace_store = get_trace_store()
                traces = await trace_store.get_recent(limit=20)
                parts.append("\nRecent traces:")
                for t in traces:
                    parts.append(f"  [{t.timestamp}] {t.agent_id} — {t.action} → {t.state}")
            except Exception as e:
                parts.append(f"Traces error: {e}")

    except Exception as e:
        parts.append(f"Status gather error: {e}")

    return "\n".join(parts)


async def exec_evolution_query(args: dict) -> str:
    action = args["action"]
    try:
        from dharma_swarm.archive import EvolutionArchive
        archive = EvolutionArchive()
        await archive.load()

        if action == "list":
            status_filter = args.get("status")
            limit = min(50, args.get("limit", 20))
            entries = await archive.list_entries(status=status_filter)
            entries = sorted(entries, key=lambda e: e.timestamp, reverse=True)[:limit]
            lines = [f"Evolution archive: {len(entries)} entries (showing {limit})"]
            for e in entries:
                lines.append(
                    f"  {e.id[:12]} | {e.component} | {e.change_type} | "
                    f"fitness={e.fitness.weighted():.3f} | {e.status} | {e.timestamp}"
                )
            return "\n".join(lines)

        elif action == "get":
            entry_id = args.get("entry_id", "")
            entry = await archive.get_entry(entry_id)
            if not entry:
                return f"Entry not found: {entry_id}"
            return json.dumps({
                "id": entry.id,
                "timestamp": str(entry.timestamp),
                "parent_id": entry.parent_id,
                "component": entry.component,
                "change_type": entry.change_type,
                "description": entry.description,
                "fitness": {
                    "correctness": entry.fitness.correctness,
                    "elegance": entry.fitness.elegance,
                    "dharmic_alignment": entry.fitness.dharmic_alignment,
                    "performance": entry.fitness.performance,
                    "weighted": entry.fitness.weighted(),
                },
                "status": entry.status,
                "gates_passed": entry.gates_passed,
                "gates_failed": entry.gates_failed,
                "agent_id": entry.agent_id,
                "model": entry.model,
            }, indent=2)

        elif action == "lineage":
            entry_id = args.get("entry_id", "")
            chain = archive.lineage(entry_id)
            if hasattr(chain, "__await__"):
                chain = await chain
            lines = [f"Lineage for {entry_id}:"]
            for e in chain:
                lines.append(f"  {e.id[:12]} ← {e.parent_id or 'ROOT'} | {e.component} | fitness={e.fitness.weighted():.3f}")
            return "\n".join(lines)

        elif action == "stats":
            stats = archive.stats()
            if hasattr(stats, "__await__"):
                stats = await stats
            return json.dumps(stats, indent=2, default=str)

        elif action == "trend":
            limit = min(100, args.get("limit", 30))
            entries = await archive.list_entries()
            entries = sorted(entries, key=lambda e: e.timestamp)[-limit:]
            lines = ["Fitness trend (chronological):"]
            for e in entries:
                lines.append(f"  {e.timestamp} | {e.component} | {e.fitness.weighted():.4f}")
            return "\n".join(lines)

        return f"Unknown action: {action}"
    except Exception as e:
        return f"Evolution query error: {e}"


async def exec_stigmergy_query(args: dict) -> str:
    action = args["action"]
    limit = min(50, args.get("limit", 20))
    try:
        from dharma_swarm.stigmergy import StigmergyStore
        stig = StigmergyStore()

        if action == "density":
            return f"Stigmergy density: {stig.density()} marks"

        elif action == "recent":
            marks = stig.recent(limit=limit) if hasattr(stig, "recent") else []
            if not marks:
                # Fallback: read the JSONL file directly
                marks_file = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"
                if marks_file.exists():
                    lines = marks_file.read_text().strip().splitlines()[-limit:]
                    parsed = []
                    for line in lines:
                        try:
                            parsed.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                    return json.dumps(parsed[-limit:], indent=2, default=str)
            return json.dumps([vars(m) if hasattr(m, "__dict__") else str(m) for m in marks], indent=2, default=str)

        elif action == "hot_paths":
            if hasattr(stig, "hot_paths"):
                paths = stig.hot_paths(limit=limit)
                return json.dumps(paths, indent=2, default=str)
            return "hot_paths not available on this StigmergyStore version"

        elif action == "high_salience":
            if hasattr(stig, "high_salience"):
                marks = stig.high_salience(limit=limit)
                return json.dumps([vars(m) if hasattr(m, "__dict__") else str(m) for m in marks], indent=2, default=str)
            return "high_salience not available on this StigmergyStore version"

        elif action == "search":
            query = args.get("query", "")
            marks_file = Path.home() / ".dharma" / "stigmergy" / "marks.jsonl"
            if not marks_file.exists():
                return "Stigmergy marks file not found"
            results = []
            for line in marks_file.read_text().strip().splitlines():
                if query.lower() in line.lower():
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                if len(results) >= limit:
                    break
            return json.dumps(results, indent=2, default=str)

        return f"Unknown action: {action}"
    except Exception as e:
        return f"Stigmergy query error: {e}"


async def exec_trace_query(args: dict) -> str:
    try:
        from api.main import get_trace_store
        store = get_trace_store()
        limit = min(50, args.get("limit", 30))

        traces = await store.get_recent(limit=limit)

        # Apply filters
        agent_filter = args.get("agent", "")
        action_filter = args.get("action", "")
        state_filter = args.get("state", "")

        filtered = []
        for t in traces:
            if agent_filter and agent_filter.lower() not in getattr(t, "agent_id", "").lower():
                continue
            if action_filter and action_filter.lower() not in getattr(t, "action", "").lower():
                continue
            if state_filter and state_filter.lower() != getattr(t, "state", "").lower():
                continue
            filtered.append(t)

        lines = [f"Traces ({len(filtered)} results):"]
        for t in filtered:
            entry = {
                "id": getattr(t, "id", "?"),
                "timestamp": str(getattr(t, "timestamp", "")),
                "agent": getattr(t, "agent_id", "?"),
                "action": getattr(t, "action", "?"),
                "state": getattr(t, "state", "?"),
                "metadata": getattr(t, "metadata", {}),
            }
            lines.append(json.dumps(entry, default=str))
        return "\n".join(lines)
    except Exception as e:
        return f"Trace query error: {e}"


async def exec_agent_control(args: dict) -> str:
    action = args["action"]
    try:
        from api.main import get_swarm
        swarm = get_swarm()

        if action == "spawn":
            name = args.get("name", "")
            role = args.get("role", "researcher")
            if not name:
                return "ERROR: name is required for spawn"
            agent = await swarm.spawn_agent(name=name, role=role)
            return f"OK: Spawned agent '{name}' with role '{role}', id={getattr(agent, 'id', '?')}"

        elif action == "stop":
            agent_id = args.get("agent_id", "")
            if not agent_id:
                return "ERROR: agent_id is required for stop"
            await swarm.stop_agent(agent_id)
            return f"OK: Stopped agent {agent_id}"

        elif action == "inspect":
            agent_id = args.get("agent_id", "")
            if not agent_id:
                return "ERROR: agent_id is required for inspect"
            status = await swarm.status()
            for a in status.agents:
                if a.id == agent_id or a.name == agent_id:
                    return json.dumps(vars(a) if hasattr(a, "__dict__") else str(a), indent=2, default=str)
            return f"Agent not found: {agent_id}"

        return f"Unknown action: {action}"
    except Exception as e:
        return f"Agent control error: {e}"


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

EXECUTORS = {
    "read_file": exec_read_file,
    "write_file": exec_write_file,
    "edit_file": exec_edit_file,
    "shell_exec": exec_shell,
    "grep_search": exec_grep,
    "glob_files": exec_glob,
    "swarm_status": exec_swarm_status,
    "evolution_query": exec_evolution_query,
    "stigmergy_query": exec_stigmergy_query,
    "trace_query": exec_trace_query,
    "agent_control": exec_agent_control,
}


async def execute_tool(name: str, arguments: dict) -> str:
    """Execute a tool by name and return the result string."""
    executor = EXECUTORS.get(name)
    if not executor:
        return f"ERROR: Unknown tool '{name}'"
    try:
        return await executor(arguments)
    except Exception as e:
        logger.exception("Tool execution error: %s", name)
        return f"ERROR executing {name}: {e}"
