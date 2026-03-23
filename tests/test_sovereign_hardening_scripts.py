from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path("/Users/dhyana/dharma_swarm")


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _build_fake_bin(bin_dir: Path) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    tmux_script = """#!/usr/bin/env bash
set -euo pipefail

existing=":${TMUX_EXISTING_SESSIONS:-}:"

case "${1:-}" in
  has-session)
    shift
    if [[ "${1:-}" == "-t" ]]; then
      session="${2:-}"
      if [[ "${existing}" == *":${session}:"* ]]; then
        exit 0
      fi
      exit 1
    fi
    ;;
  kill-session)
    shift
    if [[ "${1:-}" == "-t" ]]; then
      session="${2:-}"
      printf '%s\n' "${session}" >> "${TMUX_KILL_LOG:?}"
      exit 0
    fi
    ;;
  ls)
    IFS=':' read -r -a sessions <<< "${TMUX_EXISTING_SESSIONS:-}"
    for session in "${sessions[@]}"; do
      [[ -n "${session}" ]] && printf '%s: 1 windows\n' "${session}"
    done
    exit 0
    ;;
esac

exit 1
"""
    launchctl_script = """#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  print)
    exit 1
    ;;
  bootout|bootstrap|kickstart)
    exit 0
    ;;
esac
exit 0
"""
    ps_script = """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "auxww" ]]; then
  cat <<'EOF'
USER       PID %CPU %MEM    VSZ   RSS TTY      STAT STARTED      TIME COMMAND
EOF
  exit 0
fi
exec /bin/ps "$@"
"""
    _write_executable(bin_dir / "tmux", tmux_script)
    _write_executable(bin_dir / "launchctl", launchctl_script)
    _write_executable(bin_dir / "ps", ps_script)
    return bin_dir


def _prepare_home(tmp_path: Path) -> tuple[Path, Path]:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    os.symlink(REPO_ROOT, home_dir / "dharma_swarm")

    run_dir = home_dir / ".dharma" / "sovereign_hardening" / "run-001"
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True)
    (run_dir / "manifest.env").write_text("RUN_ID='run-001'\n", encoding="utf-8")
    latest_run = home_dir / ".dharma" / "sovereign_hardening" / "latest_run.txt"
    latest_run.parent.mkdir(parents=True, exist_ok=True)
    latest_run.write_text(str(run_dir), encoding="utf-8")
    return home_dir, run_dir


def _run_script(script_name: str, *, home_dir: Path, bin_dir: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    base_env = os.environ.copy()
    base_env.update(
        {
            "HOME": str(home_dir),
            "PATH": f"{bin_dir}:/opt/homebrew/bin:/usr/bin:/bin",
        }
    )
    base_env.update(env)
    return subprocess.run(
        ["/bin/bash", str(REPO_ROOT / "scripts" / script_name)],
        capture_output=True,
        text=True,
        env=base_env,
        check=False,
    )


def test_status_sovereign_hardening_reports_legacy_tmux_fallbacks(tmp_path: Path) -> None:
    home_dir, _ = _prepare_home(tmp_path)
    bin_dir = _build_fake_bin(tmp_path / "bin")
    result = _run_script(
        "status_sovereign_hardening_night.sh",
        home_dir=home_dir,
        bin_dir=bin_dir,
        env={
            "TMUX_EXISTING_SESSIONS": "dgc_allout:dgc_codex_night:dgc_caffeine",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Session 'dgc_allout': RUNNING" in result.stdout
    assert "Session 'dgc_codex_night': RUNNING" in result.stdout
    assert "Session 'dgc_caffeine': RUNNING" in result.stdout


def test_stop_sovereign_hardening_stops_legacy_tmux_fallbacks(tmp_path: Path) -> None:
    home_dir, _ = _prepare_home(tmp_path)
    bin_dir = _build_fake_bin(tmp_path / "bin")
    kill_log = tmp_path / "tmux-kills.log"
    result = _run_script(
        "stop_sovereign_hardening_night.sh",
        home_dir=home_dir,
        bin_dir=bin_dir,
        env={
            "TMUX_EXISTING_SESSIONS": "dgc_allout:dgc_codex_night:dgc_caffeine",
            "TMUX_KILL_LOG": str(kill_log),
        },
    )

    assert result.returncode == 0, result.stderr
    killed = kill_log.read_text(encoding="utf-8").splitlines()
    assert killed == ["dgc_allout", "dgc_codex_night", "dgc_caffeine"]
