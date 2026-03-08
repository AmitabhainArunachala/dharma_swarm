#!/usr/bin/env bash
set -euo pipefail

ROOT="${HOME}/dharma_swarm"
DEFAULT_PERSIST_FILE="${HOME}/.dharma/env/nvidia_remote.env"

PERSIST_FILE="${DEFAULT_PERSIST_FILE}"
RAG_URL="${DGC_NVIDIA_RAG_URL:-}"
INGEST_URL="${DGC_NVIDIA_INGEST_URL:-}"
FLYWHEEL_URL="${DGC_DATA_FLYWHEEL_URL:-}"
NIM_KEY="${NVIDIA_NIM_API_KEY:-}"
FLYWHEEL_KEY="${DGC_DATA_FLYWHEEL_API_KEY:-}"
AUTONOMY_PROFILE="${AUTONOMY_PROFILE:-workspace_auto}"
MISSION_PROFILE="${MISSION_PROFILE:-${AUTONOMY_PROFILE}}"
TARGET_JST="04:00"
LAUNCHER="none"   # none | caffeine | allout
ALLOUT_HOURS="forever"
RETRIES=5
WAIT_SEC=2
FORCE=0
PERSIST=1

mask_secret() {
  local value="$1"
  if [[ -z "${value}" ]]; then
    echo "(empty)"
    return
  fi
  local len=${#value}
  if (( len <= 8 )); then
    printf '***%s' "${value: -2}"
    return
  fi
  printf '%s***%s' "${value:0:4}" "${value: -4}"
}

usage() {
  cat <<'USAGE'
Usage:
  scripts/wire_nvidia_remote.sh [options]

Required (unless already exported in env):
  --rag-url URL           NVIDIA RAG base URL, e.g. https://rag.example.com/v1
  --ingest-url URL        NVIDIA ingest base URL, e.g. https://ingest.example.com/v1
  --flywheel-url URL      Data Flywheel base URL, e.g. https://flywheel.example.com/api

Optional:
  --nim-key KEY           NVIDIA NIM API key (stored in persist file unless --no-persist)
  --flywheel-key KEY      Data Flywheel API key
  --profile NAME          Sets AUTONOMY_PROFILE and MISSION_PROFILE (default: workspace_auto)
  --autonomy-profile NAME Sets AUTONOMY_PROFILE only
  --mission-profile NAME  Sets MISSION_PROFILE only
  --launcher MODE         none|caffeine|allout (default: none)
  --target-jst HH:MM      For caffeine launcher (default: 04:00)
  --allout-hours VALUE    For allout launcher, e.g. 6 or forever (default: forever)
  --persist-file PATH     Persist env file path (default: ~/.dharma/env/nvidia_remote.env)
  --no-persist            Do not write persist file
  --retries N             Probe retries per endpoint (default: 5)
  --wait-sec N            Sleep between retries (default: 2)
  --force                 Start launcher even if probes fail
  -h, --help              Show this help

Examples:
  scripts/wire_nvidia_remote.sh \
    --rag-url https://rag.example.com/v1 \
    --ingest-url https://ingest.example.com/v1 \
    --flywheel-url https://fly.example.com/api \
    --nim-key '***' \
    --launcher caffeine --target-jst 08:00

  scripts/wire_nvidia_remote.sh \
    --launcher allout --allout-hours forever --force
USAGE
}

log() {
  printf '[wire-nvidia] %s\n' "$*"
}

require_value() {
  local key="$1"
  local value="$2"
  if [[ -z "${value}" ]]; then
    echo "Missing required value for ${key}" >&2
    usage
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rag-url)
      RAG_URL="$2"
      shift 2
      ;;
    --ingest-url)
      INGEST_URL="$2"
      shift 2
      ;;
    --flywheel-url)
      FLYWHEEL_URL="$2"
      shift 2
      ;;
    --nim-key)
      NIM_KEY="$2"
      shift 2
      ;;
    --flywheel-key)
      FLYWHEEL_KEY="$2"
      shift 2
      ;;
    --profile)
      AUTONOMY_PROFILE="$2"
      MISSION_PROFILE="$2"
      shift 2
      ;;
    --autonomy-profile)
      AUTONOMY_PROFILE="$2"
      shift 2
      ;;
    --mission-profile)
      MISSION_PROFILE="$2"
      shift 2
      ;;
    --launcher)
      LAUNCHER="$2"
      shift 2
      ;;
    --target-jst)
      TARGET_JST="$2"
      shift 2
      ;;
    --allout-hours)
      ALLOUT_HOURS="$2"
      shift 2
      ;;
    --persist-file)
      PERSIST_FILE="$2"
      shift 2
      ;;
    --no-persist)
      PERSIST=0
      shift
      ;;
    --retries)
      RETRIES="$2"
      shift 2
      ;;
    --wait-sec)
      WAIT_SEC="$2"
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ (-z "${RAG_URL}" || -z "${INGEST_URL}" || -z "${FLYWHEEL_URL}") && -f "${PERSIST_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${PERSIST_FILE}"
  RAG_URL="${RAG_URL:-${DGC_NVIDIA_RAG_URL:-}}"
  INGEST_URL="${INGEST_URL:-${DGC_NVIDIA_INGEST_URL:-}}"
  FLYWHEEL_URL="${FLYWHEEL_URL:-${DGC_DATA_FLYWHEEL_URL:-}}"
  NIM_KEY="${NIM_KEY:-${NVIDIA_NIM_API_KEY:-}}"
  FLYWHEEL_KEY="${FLYWHEEL_KEY:-${DGC_DATA_FLYWHEEL_API_KEY:-}}"
  AUTONOMY_PROFILE="${AUTONOMY_PROFILE:-workspace_auto}"
  MISSION_PROFILE="${MISSION_PROFILE:-${AUTONOMY_PROFILE}}"
  log "Loaded defaults from ${PERSIST_FILE}"
fi

require_value "--rag-url" "${RAG_URL}"
require_value "--ingest-url" "${INGEST_URL}"
require_value "--flywheel-url" "${FLYWHEEL_URL}"

if [[ ! -d "${ROOT}" ]]; then
  echo "Missing repo directory: ${ROOT}" >&2
  exit 1
fi

probe_endpoint() {
  local name="$1"
  local url="$2"
  local code="000"
  local body=""
  local tmp
  tmp="$(mktemp)"

  for attempt in $(seq 1 "${RETRIES}"); do
    code="$(curl -sS -o "${tmp}" -w "%{http_code}" "${url}" || true)"
    body="$(tail -c 240 "${tmp}" 2>/dev/null || true)"
    if [[ "${code}" == "200" || "${code}" == "401" || "${code}" == "403" ]]; then
      log "PASS ${name}: ${url} (code=${code})"
      rm -f "${tmp}"
      return 0
    fi
    log "WARN ${name}: attempt ${attempt}/${RETRIES} code=${code}"
    sleep "${WAIT_SEC}"
  done

  log "FAIL ${name}: ${url} (last_code=${code})"
  if [[ -n "${body}" ]]; then
    log "FAIL ${name}: response_tail=${body}"
  fi
  rm -f "${tmp}"
  return 1
}

probe_flywheel() {
  local base="${FLYWHEEL_URL%/}"
  local primary="${base}/jobs"
  local alt
  if [[ "${base}" == */api ]]; then
    alt="${base%/api}/jobs"
  else
    alt="${base}/api/jobs"
  fi

  if probe_endpoint "flywheel_primary" "${primary}"; then
    return 0
  fi
  probe_endpoint "flywheel_alt" "${alt}"
}

if [[ "${PERSIST}" == "1" ]]; then
  mkdir -p "$(dirname "${PERSIST_FILE}")"
  umask 077
  cat > "${PERSIST_FILE}" <<ENVVARS
# Generated by scripts/wire_nvidia_remote.sh
# Updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)
export DGC_NVIDIA_RAG_URL='${RAG_URL}'
export DGC_NVIDIA_INGEST_URL='${INGEST_URL}'
export DGC_DATA_FLYWHEEL_URL='${FLYWHEEL_URL}'
export NVIDIA_NIM_API_KEY='${NIM_KEY}'
export DGC_DATA_FLYWHEEL_API_KEY='${FLYWHEEL_KEY}'
export AUTONOMY_PROFILE='${AUTONOMY_PROFILE}'
export MISSION_PROFILE='${MISSION_PROFILE}'
ENVVARS
  chmod 600 "${PERSIST_FILE}"
  log "Persisted env to ${PERSIST_FILE}"
fi

export DGC_NVIDIA_RAG_URL="${RAG_URL}"
export DGC_NVIDIA_INGEST_URL="${INGEST_URL}"
export DGC_DATA_FLYWHEEL_URL="${FLYWHEEL_URL}"
export NVIDIA_NIM_API_KEY="${NIM_KEY}"
export DGC_DATA_FLYWHEEL_API_KEY="${FLYWHEEL_KEY}"
export AUTONOMY_PROFILE="${AUTONOMY_PROFILE}"
export MISSION_PROFILE="${MISSION_PROFILE}"

log "Configuration:"
log "  RAG_URL=${DGC_NVIDIA_RAG_URL}"
log "  INGEST_URL=${DGC_NVIDIA_INGEST_URL}"
log "  FLYWHEEL_URL=${DGC_DATA_FLYWHEEL_URL}"
log "  NVIDIA_NIM_API_KEY=$(mask_secret "${NVIDIA_NIM_API_KEY}")"
log "  DGC_DATA_FLYWHEEL_API_KEY=$(mask_secret "${DGC_DATA_FLYWHEEL_API_KEY}")"
log "  AUTONOMY_PROFILE=${AUTONOMY_PROFILE}"
log "  MISSION_PROFILE=${MISSION_PROFILE}"

ok=1
probe_endpoint "rag_health" "${DGC_NVIDIA_RAG_URL%/}/health?check_dependencies=true" || ok=0
probe_endpoint "ingest_health" "${DGC_NVIDIA_INGEST_URL%/}/health?check_dependencies=true" || ok=0
probe_flywheel || ok=0

if [[ "${ok}" != "1" && "${FORCE}" != "1" ]]; then
  log "Blocking launcher: one or more endpoint probes failed."
  log "Use --force to bypass this check intentionally."
  exit 3
fi

if [[ "${ok}" != "1" && "${FORCE}" == "1" ]]; then
  log "FORCE enabled: continuing despite failed probes."
fi

cd "${ROOT}"

if [[ "${LAUNCHER}" == "none" ]]; then
  log "Wiring complete. No launcher started."
  log "Run: source '${PERSIST_FILE}'"
  log "Then: scripts/start_caffeine_nvidia_tmux.sh 08:00"
  exit 0
fi

case "${LAUNCHER}" in
  caffeine)
    log "Starting caffeine launcher (target JST ${TARGET_JST})"
    exec scripts/start_caffeine_nvidia_tmux.sh "${TARGET_JST}"
    ;;
  allout)
    log "Starting allout launcher (hours=${ALLOUT_HOURS})"
    exec scripts/start_allout_tmux.sh "${ALLOUT_HOURS}"
    ;;
  *)
    echo "Invalid --launcher value: ${LAUNCHER} (expected none|caffeine|allout)" >&2
    exit 2
    ;;
esac
