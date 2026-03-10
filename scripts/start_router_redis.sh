#!/usr/bin/env bash
set -euo pipefail

NAME="${DGC_ROUTER_REDIS_CONTAINER:-dgc-router-redis}"
PORT="${DGC_ROUTER_REDIS_PORT:-6379}"
URL="${DGC_ROUTER_REDIS_URL:-redis://127.0.0.1:${PORT}/0}"
DOCKER_BIN="${DGC_DOCKER_BIN:-/Applications/Docker.app/Contents/Resources/bin/docker}"

if command -v redis-server >/dev/null 2>&1; then
  if nc -z 127.0.0.1 "${PORT}" >/dev/null 2>&1; then
    echo "Redis already listening on 127.0.0.1:${PORT}"
  else
    redis-server --daemonize yes --port "${PORT}" --save "" --appendonly no
    echo "Started local redis-server on 127.0.0.1:${PORT}"
  fi
else
  if [[ ! -x "${DOCKER_BIN}" ]] && ! command -v docker >/dev/null 2>&1; then
    echo "No redis-server or docker found. Install one to run shared router state."
    exit 1
  fi
  if [[ ! -x "${DOCKER_BIN}" ]]; then
    DOCKER_BIN="$(command -v docker)"
  fi

  if "${DOCKER_BIN}" ps --filter "name=^/${NAME}$" --format '{{.Names}}' | grep -qx "${NAME}"; then
    echo "Redis container already running: ${NAME}"
  elif "${DOCKER_BIN}" ps -a --filter "name=^/${NAME}$" --format '{{.Names}}' | grep -qx "${NAME}"; then
    "${DOCKER_BIN}" start "${NAME}" >/dev/null
    echo "Started existing Redis container: ${NAME}"
  else
    "${DOCKER_BIN}" run -d \
      --name "${NAME}" \
      -p "${PORT}:6379" \
      --restart unless-stopped \
      redis:7-alpine \
      --save "" \
      --appendonly no >/dev/null
    echo "Started new Redis container: ${NAME}"
  fi

  echo -n "Container health ping: "
  "${DOCKER_BIN}" exec "${NAME}" redis-cli ping
fi

echo "Router Redis URL: ${URL}"
echo "Export this before running DGC (if not sourced from .env):"
echo "  export DGC_ROUTER_REDIS_URL=${URL}"
