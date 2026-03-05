#!/usr/bin/env bash
set -euo pipefail

MODE="check"
if [[ "${1:-}" == "--fix" ]]; then
  MODE="fix"
fi

LEGACY_PATTERNS=(
  'DHARMIC_GODEL_CLAW/src/core/dgc_tui.py'
  'dgc-core/daemon/dgc_daemon.py'
)
CANONICAL_PATTERNS=(
  '/opt/homebrew/bin/dgc'
  'dharma_swarm.swarm'
  '/Users/dhyana/dharma_swarm/scripts/overnight_autopilot.py'
  '/Users/dhyana/dharma_swarm/scripts/verification_lane.py'
)

PS_ERR=0

list_pids() {
  local pattern="$1"
  local ps_out
  if ! ps_out="$(ps auxww 2>/dev/null)"; then
    PS_ERR=1
    return 0
  fi
  printf "%s\n" "$ps_out" | rg -F "$pattern" | rg -v 'rg -F' | awk '{print $2}' | tr '\n' ' '
}

echo "=== Split-Brain Guard ==="
echo "Mode: $MODE"

legacy_found=0
for p in "${LEGACY_PATTERNS[@]}"; do
  pids="$(list_pids "$p" || true)"
  if [[ -n "${pids// }" ]]; then
    legacy_found=1
    echo "LEGACY: $p"
    echo "  pids: $pids"
    if [[ "$MODE" == "fix" ]]; then
      for pid in $pids; do
        kill "$pid" 2>/dev/null || true
      done
    fi
  fi
done

if [[ "$MODE" == "fix" ]]; then
  still_legacy=0
  sleep 1
  for p in "${LEGACY_PATTERNS[@]}"; do
    pids="$(list_pids "$p" || true)"
    if [[ -n "${pids// }" ]]; then
      still_legacy=1
      echo "WARNING: still running legacy pattern: $p"
      echo "  pids: $pids"
    fi
  done
fi

echo "\nCanonical process hints:"
for p in "${CANONICAL_PATTERNS[@]}"; do
  pids="$(list_pids "$p" || true)"
  if [[ -n "${pids// }" ]]; then
    echo "CANONICAL: $p"
    echo "  pids: $pids"
  fi
done

if [[ $PS_ERR -eq 1 ]]; then
  echo "\nUnable to inspect process table. Re-run with elevated permissions."
  exit 2
fi

if [[ $legacy_found -eq 1 ]]; then
  if [[ "$MODE" == "check" ]]; then
    echo "\nSplit-brain risk detected. Run: scripts/split_brain_guard.sh --fix"
    exit 1
  fi

  if [[ "${still_legacy:-0}" -eq 1 ]]; then
    echo "\nSplit-brain cleanup attempted, but legacy processes remain."
    exit 1
  else
    echo "\nSplit-brain cleanup attempted."
    exit 0
  fi
fi

echo "\nNo legacy split-brain processes detected."
exit 0
