#!/usr/bin/env bash
set -euo pipefail

recipient="kimi-claw-phone"
responder="kimi-claw-phone"
branch="roaming-fixall-20260326"
interval="15"
heartbeat_seconds="300"
provider=""
model=""
session=""
mode="loop"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --recipient) recipient="$2"; shift 2 ;;
    --responder) responder="$2"; shift 2 ;;
    --branch) branch="$2"; shift 2 ;;
    --interval) interval="$2"; shift 2 ;;
    --heartbeat-seconds) heartbeat_seconds="$2"; shift 2 ;;
    --provider) provider="$2"; shift 2 ;;
    --model) model="$2"; shift 2 ;;
    --session) session="$2"; shift 2 ;;
    --once) mode="once"; shift 1 ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

git fetch origin "$branch"
git checkout "$branch"
git pull --ff-only origin "$branch"

log_dir="${HOME}/.dharma/roaming"
mkdir -p "$log_dir"

if [[ -z "$session" ]]; then
  session="roaming-${responder}"
fi

worker_cmd=(python3 -m dharma_swarm.roaming_llm_worker --callsign "$responder")
if [[ -n "$provider" ]]; then
  worker_cmd+=(--provider "$provider")
fi
if [[ -n "$model" ]]; then
  worker_cmd+=(--model "$model")
fi

poller_cmd=(
  python3 -m dharma_swarm.roaming_poller
  --repo-root "$repo_root"
  --git-branch "$branch"
  --recipient "$recipient"
  --responder "$responder"
  --heartbeat-agent-id "$responder"
  --heartbeat-seconds "$heartbeat_seconds"
  --command "${worker_cmd[*]}"
)

if [[ "$mode" == "once" ]]; then
  PYTHONPATH=. "${poller_cmd[@]}" run-once --json
  exit 0
fi

log_file="${log_dir}/${session}.log"
printf -v poller_shell '%q ' "${poller_cmd[@]}"
shell_cmd="cd $(printf '%q' "$repo_root") && PYTHONPATH=. ${poller_shell}run-loop --interval $(printf '%q' "$interval") >> $(printf '%q' "$log_file") 2>&1"

if command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t "$session" 2>/dev/null; then
    tmux kill-session -t "$session"
  fi
  tmux new-session -d -s "$session" "$shell_cmd"
  echo "started tmux session $session"
  echo "log: $log_file"
  exit 0
fi

nohup bash -lc "$shell_cmd" >/dev/null 2>&1 &
echo "started background worker for $responder"
echo "log: $log_file"
