#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
STATE_DIR="${HOME}/.dharma"
CONCLAVE_DIR="${STATE_DIR}/build_conclave"
RUN_FILE="${CONCLAVE_DIR}/latest_run.txt"
INDEX_SESSION="${INDEX_SESSION_NAME:-dgc_repo_index}"

cd "${ROOT}"

if [[ -f "${RUN_FILE}" ]]; then
  RUN_DIR="$(cat "${RUN_FILE}")"
  echo "Run dir: ${RUN_DIR}"
else
  RUN_DIR=""
  echo "Run dir: (none)"
fi

echo
echo "== Dashboard =="
bash scripts/dashboard_ctl.sh status || true

echo
echo "== Repo Index =="
if tmux has-session -t "${INDEX_SESSION}" 2>/dev/null; then
  echo "Session '${INDEX_SESSION}': RUNNING"
else
  echo "Session '${INDEX_SESSION}': NOT RUNNING"
fi
if [[ -n "${RUN_DIR}" ]]; then
  summary_file="${RUN_DIR}/index/summary.txt"
  if [[ -f "${summary_file}" ]]; then
    echo
    echo "--- ${summary_file} ---"
    tail -n 20 "${summary_file}" || true
  fi
  for log_file in semantic_digest.log semantic_brief.log xray.log; do
    target="${RUN_DIR}/index/${log_file}"
    if [[ -f "${target}" ]]; then
      echo
      echo "--- ${target} ---"
      tail -n 20 "${target}" || true
    fi
  done
fi

echo
echo "== Director =="
bash scripts/status_allout_tmux.sh || true

echo
echo "== Codex Night =="
bash scripts/status_codex_overnight_tmux.sh || true

echo
echo "== Caffeine =="
bash scripts/status_caffeine_tmux.sh || true
