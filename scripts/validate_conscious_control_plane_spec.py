#!/usr/bin/env python3
"""Validate the Conscious Control Plane implementation contract.

This script is intentionally split into:

1. manifest linting
2. static artifact/content checks
3. optional command execution

It is safe to run before implementation with ``--lint-manifest``.
It will fail static checks until the spec is implemented.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "spec-forge" / "conscious-control-plane" / "validation_manifest.json"


def _load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text())
    required_keys = {"artifact_checks", "content_checks", "command_checks"}
    missing = required_keys - set(data)
    if missing:
        raise ValueError(f"manifest missing keys: {sorted(missing)}")
    for key in required_keys:
        if not isinstance(data[key], list):
            raise ValueError(f"manifest key {key} must be a list")
    return data


def _lint_manifest(data: dict) -> list[str]:
    errors: list[str] = []

    for check in data["artifact_checks"]:
        for key in ("id", "path", "kind", "description"):
            if key not in check:
                errors.append(f"artifact check missing {key}: {check}")

    for check in data["content_checks"]:
        for key in ("id", "path", "must_contain", "description"):
            if key not in check:
                errors.append(f"content check missing {key}: {check}")
        if "must_contain" in check and not isinstance(check["must_contain"], list):
            errors.append(f"content check must_contain must be a list: {check}")

    for check in data["command_checks"]:
        for key in ("id", "command", "description"):
            if key not in check:
                errors.append(f"command check missing {key}: {check}")

    return errors


def _run_static_checks(data: dict) -> tuple[list[dict], bool]:
    results: list[dict] = []
    all_ok = True

    for check in data["artifact_checks"]:
        path = REPO_ROOT / check["path"]
        ok = path.exists()
        results.append(
            {
                "id": check["id"],
                "type": "artifact",
                "path": check["path"],
                "ok": ok,
                "description": check["description"],
                "detail": "exists" if ok else "missing",
            }
        )
        all_ok &= ok

    for check in data["content_checks"]:
        path = REPO_ROOT / check["path"]
        ok = path.exists()
        detail = "file missing"
        if ok:
            text = path.read_text(encoding="utf-8", errors="ignore")
            missing_tokens = [token for token in check["must_contain"] if token not in text]
            ok = not missing_tokens
            detail = "all tokens present" if ok else f"missing tokens: {missing_tokens}"
        results.append(
            {
                "id": check["id"],
                "type": "content",
                "path": check["path"],
                "ok": ok,
                "description": check["description"],
                "detail": detail,
            }
        )
        all_ok &= ok

    return results, all_ok


def _run_command_checks(data: dict) -> tuple[list[dict], bool]:
    results: list[dict] = []
    all_ok = True

    for check in data["command_checks"]:
        proc = subprocess.run(
            check["command"],
            cwd=REPO_ROOT,
            shell=True,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        results.append(
            {
                "id": check["id"],
                "type": "command",
                "command": check["command"],
                "ok": ok,
                "description": check["description"],
                "returncode": proc.returncode,
                "stdout_tail": proc.stdout[-400:],
                "stderr_tail": proc.stderr[-400:],
            }
        )
        all_ok &= ok

    return results, all_ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--lint-manifest", action="store_true")
    parser.add_argument("--run-commands", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    manifest = _load_manifest(args.manifest)
    lint_errors = _lint_manifest(manifest)

    if args.lint_manifest:
        payload = {
            "manifest": str(args.manifest),
            "ok": not lint_errors,
            "lint_errors": lint_errors,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"manifest: {args.manifest}")
            print("ok" if not lint_errors else "failed")
            for err in lint_errors:
                print(f"- {err}")
        return 0 if not lint_errors else 1

    static_results, static_ok = _run_static_checks(manifest)
    command_results: list[dict] = []
    commands_ok = True
    if args.run_commands:
        command_results, commands_ok = _run_command_checks(manifest)

    payload = {
        "manifest": str(args.manifest),
        "lint_errors": lint_errors,
        "static_results": static_results,
        "command_results": command_results,
        "ok": (not lint_errors) and static_ok and commands_ok,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"manifest: {args.manifest}")
        print(f"lint_ok: {not lint_errors}")
        print(f"static_ok: {static_ok}")
        print(f"commands_run: {args.run_commands}")
        print(f"commands_ok: {commands_ok}")
        for result in static_results + command_results:
            status = "PASS" if result["ok"] else "FAIL"
            subject = result.get("path") or result.get("command")
            print(f"[{status}] {result['id']} {subject}")
            if not result["ok"]:
                detail = result.get("detail")
                if detail:
                    print(f"  {detail}")

    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
