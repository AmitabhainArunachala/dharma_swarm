#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORT_DIR="$ROOT/reports/verification"
mkdir -p "$REPORT_DIR"

RUNS=1
if [[ "${1:-}" == "--triple" ]]; then
  RUNS=3
fi

TS="$(date +%Y%m%d_%H%M%S)"
REPORT="$REPORT_DIR/wave2_acceptance_${TS}.md"
STATUS=0

log() {
  printf "%s\n" "$1" | tee -a "$REPORT" >/dev/null
}

run_cmd() {
  local title="$1"
  local cmd="$2"
  log "## ${title}"
  log "\
\`\`\`bash\n${cmd}\n\`\`\`"
  local out
  if out=$(cd "$ROOT" && /bin/zsh -lc "$cmd" 2>&1); then
    log "\
\`\`\`text"
    printf "%s\n" "$out" | tee -a "$REPORT" >/dev/null
    log "\`\`\`"
  else
    local rc=$?
    STATUS=1
    log "\
\`\`\`text"
    printf "FAILED (exit %s)\n%s\n" "$rc" "$out" | tee -a "$REPORT" >/dev/null
    log "\`\`\`"
  fi
  log ""
}

run_optional_cmd() {
  local title="$1"
  local cmd="$2"
  log "## ${title} (optional)"
  log "\
\`\`\`bash\n${cmd}\n\`\`\`"
  local out
  if out=$(cd "$ROOT" && /bin/zsh -lc "$cmd" 2>&1); then
    log "\
\`\`\`text"
    printf "%s\n" "$out" | tee -a "$REPORT" >/dev/null
    log "\`\`\`"
  else
    local rc=$?
    log "\
\`\`\`text"
    printf "SKIPPED (exit %s)\n%s\n" "$rc" "$out" | tee -a "$REPORT" >/dev/null
    log "\`\`\`"
  fi
  log ""
}

log "# Wave 2 Acceptance Gate"
log "- Timestamp: $(date -u +"%Y-%m-%d %H:%M:%SZ")"
log "- Repo: $ROOT"
log "- Pytest runs: $RUNS"
log ""

run_cmd "Git Snapshot" "git status -sb"
run_cmd "DGC Resolution (interactive zsh)" "type dgc; which dgc; command -v dgc"
run_cmd "DGC Resolution (non-interactive)" "which dgc || true"
run_optional_cmd "Split-Brain Process Snapshot" "ps auxww | rg -i 'dharma_swarm|DHARMIC_GODEL_CLAW/src/core/dgc_tui.py|dgc-core/bin/dgc|/opt/homebrew/bin/dgc' || true"

run_cmd "Core Module Import Smoke" "python3 -c \"import importlib; mods=['dharma_swarm.dharma_kernel','dharma_swarm.dharma_corpus','dharma_swarm.policy_compiler','dharma_swarm.anekanta_gate','dharma_swarm.dogma_gate','dharma_swarm.steelman_gate','dharma_swarm.canary','dharma_swarm.evolution','dharma_swarm.telos_gates']; [print('OK', m) or importlib.import_module(m) for m in mods]\""

run_cmd "Gate Count Smoke" "python3 -c \"from dharma_swarm.telos_gates import TelosGatekeeper; print('gate_count=', len(TelosGatekeeper.GATES)); print('gates=', ','.join(sorted(TelosGatekeeper.GATES.keys())))\""

for i in $(seq 1 "$RUNS"); do
  run_cmd "Full Test Suite Run ${i}/${RUNS}" "python3 -m pytest tests/ -q --tb=short"
done

run_cmd "CLI Smoke: Canonical dgc status" "/opt/homebrew/bin/dgc status"
run_cmd "CLI Smoke: Canonical dgc gates" "/opt/homebrew/bin/dgc gates 'echo hello'"

log "## Final Verdict"
if [[ $STATUS -eq 0 ]]; then
  log "PASS"
else
  log "FAIL"
fi

printf "Report written to %s\n" "$REPORT"
exit "$STATUS"
