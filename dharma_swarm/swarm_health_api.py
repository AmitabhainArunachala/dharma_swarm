"""Swarm Health API — lightweight HTTP health + metrics endpoint for dgc orchestrate-live.

Exposes:
    GET /health         → liveness probe (k8s/launchd compatible)
    GET /metrics        → structured JSON metrics for dashboards
    GET /loops          → status of all 15 concurrent loops
    GET /providers      → current provider chain + circuit breaker state
    GET /telos          → TelosGraph progress summary
    GET /archaeology    → latest lessons_learned.md excerpt

Starts on port 7433 (configurable via DHARMA_API_PORT) as a background task
in orchestrate_live.py. All endpoints are read-only — no mutation exposed.

Usage:
    # Called from orchestrate_live task_factories:
    "health-api": lambda: run_health_api(shutdown_event),

    # Check from anywhere:
    curl http://localhost:7433/health
    curl http://localhost:7433/metrics | python3 -m json.tool
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_PORT = int(os.environ.get("DHARMA_API_PORT", "7433"))
_HOST = os.environ.get("DHARMA_API_HOST", "127.0.0.1")
_STATE_DIR = Path(os.environ.get("DHARMA_STATE_DIR", Path.home() / ".dharma"))
_START_TIME = time.monotonic()


def _uptime() -> str:
    elapsed = int(time.monotonic() - _START_TIME)
    h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_lines(path: Path, n: int = 10) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
    except Exception:
        return []


def _loop_status() -> list[dict]:
    """Check which loops have live artifacts."""
    checks = [
        ("evolution", _STATE_DIR / "evolution" / "archive.jsonl"),
        ("stigmergy", _STATE_DIR / "stigmergy" / "marks.jsonl"),
        ("telos", _STATE_DIR / "telos" / "objectives.jsonl"),
        ("memory-palace", _STATE_DIR / "lancedb" / "palace_docs.lance"),
        ("knowledge-store", _STATE_DIR / "db" / "knowledge_store.db"),
        ("archaeology", _STATE_DIR / "meta" / "lessons_learned.md"),
        ("guardian", _STATE_DIR / "guardian" / "GUARDIAN_REPORT.md"),
        ("gnani", _STATE_DIR / "meta" / "gnani_seeded"),
        ("telos-substrate", _STATE_DIR / "meta" / "telos_seeded"),
        ("sub-swarms", _STATE_DIR / "sub_swarms"),
    ]
    result = []
    for name, path in checks:
        exists = path.exists()
        age_h = None
        if exists and path.is_file():
            age_h = round((time.time() - path.stat().st_mtime) / 3600, 1)
        result.append({
            "loop": name,
            "artifact_exists": exists,
            "age_hours": age_h,
            "status": "ok" if exists else "no-data",
        })
    return result


def _provider_status() -> dict:
    cb_path = _STATE_DIR / "meta" / "circuit_breakers.json"
    return {
        "circuit_breakers": _read_json(cb_path),
        "shadow_mode": os.environ.get("DHARMA_EVOLUTION_SHADOW", "1") == "1",
        "autonomy_level": int(os.environ.get("DGC_AUTONOMY_LEVEL", "1")),
    }


def _telos_summary() -> dict:
    obj_path = _STATE_DIR / "telos" / "objectives.jsonl"
    if not obj_path.exists():
        return {"status": "no-data"}
    try:
        lines = [l for l in obj_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        objs = [json.loads(l) for l in lines]
        total = len(objs)
        active = sum(1 for o in objs if o.get("status") == "active")
        avg_progress = sum(o.get("progress", 0) for o in objs) / total if total else 0
        high_priority = sorted(
            [o for o in objs if o.get("priority", 0) >= 8],
            key=lambda o: -o.get("progress", 0)
        )[:5]
        return {
            "total_objectives": total,
            "active": active,
            "avg_progress": round(avg_progress, 3),
            "top_objectives": [
                {"name": o.get("name", "")[:60], "progress": o.get("progress", 0)}
                for o in high_priority
            ],
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _evolution_summary() -> dict:
    arch = _STATE_DIR / "evolution" / "archive.jsonl"
    if not arch.exists():
        return {"status": "no-data"}
    try:
        lines = [l for l in arch.read_text(encoding="utf-8").splitlines() if l.strip()]
        entries = [json.loads(l) for l in lines[-200:]]
        applied = sum(1 for e in entries if e.get("status") == "applied")
        rolled = sum(1 for e in entries if e.get("status") == "rolled_back")
        return {
            "total_entries": len(lines),
            "recent_applied": applied,
            "recent_rolled_back": rolled,
            "shadow_mode": os.environ.get("DHARMA_EVOLUTION_SHADOW", "1") == "1",
        }
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def _route(path: str) -> tuple[str, str]:
    if path == "/health" or path == "/":
        return "200 OK", json.dumps({
            "status": "ok",
            "uptime": _uptime(),
            "timestamp": _utc_now(),
            "version": "dharma_swarm",
        })

    if path == "/metrics":
        return "200 OK", json.dumps({
            "uptime": _uptime(),
            "timestamp": _utc_now(),
            "loops": _loop_status(),
            "evolution": _evolution_summary(),
            "providers": _provider_status(),
            "telos": _telos_summary(),
        }, indent=2)

    if path == "/loops":
        return "200 OK", json.dumps(_loop_status(), indent=2)

    if path == "/providers":
        return "200 OK", json.dumps(_provider_status(), indent=2)

    if path == "/telos":
        return "200 OK", json.dumps(_telos_summary(), indent=2)

    if path == "/archaeology":
        lessons = _STATE_DIR / "meta" / "lessons_learned.md"
        excerpt = "\n".join(_read_lines(lessons, 30)) if lessons.exists() else "No lessons yet."
        return "200 OK", json.dumps({"lessons_excerpt": excerpt, "timestamp": _utc_now()})

    if path == "/guardian":
        report = _STATE_DIR / "guardian" / "GUARDIAN_REPORT.md"
        content = report.read_text(encoding="utf-8", errors="ignore") if report.exists() else "No report yet."
        return "200 OK", json.dumps({"report": content[:5000], "timestamp": _utc_now()})

    return "404 Not Found", json.dumps({"error": "not found", "path": path})


def _http_response(status: str, body: str) -> bytes:
    response = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body.encode())}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
        f"{body}"
    )
    return response.encode()


async def _handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Handle one HTTP request — minimal HTTP/1.1 server without dependencies."""
    try:
        raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
        request = raw.decode(errors="ignore")
        first_line = request.splitlines()[0] if request.splitlines() else ""
        method, path_qs, *_ = (first_line.split() + ["", ""])[:3]
        path = path_qs.split("?")[0]
        status, body = _route(path)
        writer.write(_http_response(status, body))
        await writer.drain()
    except Exception as exc:
        logger.debug("Health API request failed: %s", exc)
    finally:
        writer.close()


def _serve_health_sync(shutdown_event: asyncio.Event) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((_HOST, _PORT))
        sock.listen(128)
        sock.settimeout(1.0)
        logger.info("Swarm health API listening on http://%s:%d", _HOST, _PORT)
        while not shutdown_event.is_set():
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(2.0)
                try:
                    raw = conn.recv(4096)
                    request = raw.decode(errors="ignore")
                    first_line = request.splitlines()[0] if request.splitlines() else ""
                    _method, path_qs, *_ = (first_line.split() + ["", ""])[:3]
                    path = path_qs.split("?")[0]
                    status, body = _route(path)
                    conn.sendall(_http_response(status, body))
                except Exception as exc:
                    logger.debug("Health API request failed: %s", exc)
        logger.info("Swarm health API stopped")
    finally:
        sock.close()


async def run_health_api(shutdown_event: asyncio.Event) -> None:
    """Run the health API server until shutdown."""
    try:
        await asyncio.to_thread(_serve_health_sync, shutdown_event)
    except OSError as exc:
        logger.warning("Health API failed to start on port %d: %s", _PORT, exc)
    except Exception as exc:
        logger.error("Health API crashed: %s", exc)
