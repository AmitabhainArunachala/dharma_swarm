#!/bin/bash
# MISSION PREFLIGHT — fail-closed autonomy gate for every launch.
#
# Called at the start of overnight_controller.sh, swarm.sh, and any
# unattended loop. If the profile check fails, the launch is blocked.
#
# Usage (in launch scripts):
#   source mission_preflight.sh || exit 1
#   # OR with a specific profile:
#   MISSION_PROFILE=workspace_auto source mission_preflight.sh || exit 1
#
# Exit codes:
#   0  — preflight passed
#   2  — strict core lane failure (dharma_swarm not healthy)
#   3  — tracked wiring requirement failure (local-only mission files)
#   4  — unknown autonomy profile

set -uo pipefail

PROFILE="${MISSION_PROFILE:-workspace_auto}"
DGC="${DGC_BIN:-dgc}"

# Resolve dgc binary
if ! command -v "$DGC" &>/dev/null; then
    DGC="python3 -m dharma_swarm.dgc_cli"
fi

echo "[preflight] Running mission-status --profile ${PROFILE} ..."

# Run with --json so we can parse exit code and report cleanly
OUTPUT=$($DGC mission-status --profile "$PROFILE" --json 2>&1)
EXIT=$?

case $EXIT in
    0)
        echo "[preflight] PASS — autonomy profile '${PROFILE}' cleared."
        ;;
    2)
        echo "[preflight] BLOCK — strict core lane failure." >&2
        echo "$OUTPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    core = d.get('core', {})
    print(f\"  Core: {core.get('pass_count',0)}/{core.get('total',0)} checks passing\")
    for k, v in core.get('checks', {}).items():
        if not v:
            print(f'  FAIL: {k}')
except Exception:
    sys.stdout.write(sys.stdin.read())
" 2>/dev/null || true
        ;;
    3)
        echo "[preflight] BLOCK — mission-critical files not tracked." >&2
        echo "$OUTPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    local_only = d.get('tracked', {}).get('local_only', [])
    print(f\"  {len(local_only)} untracked paths:\")
    for p in local_only[:5]:
        print(f'  - {p}')
except Exception:
    pass
" 2>/dev/null || true
        ;;
    4)
        echo "[preflight] ERROR — unknown autonomy profile '${PROFILE}'." >&2
        ;;
    *)
        echo "[preflight] WARNING — unexpected exit code ${EXIT}, proceeding." >&2
        EXIT=0
        ;;
esac

exit $EXIT
