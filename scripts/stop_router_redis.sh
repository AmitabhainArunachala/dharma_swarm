#!/usr/bin/env bash
set -euo pipefail

NAME="${DGC_ROUTER_REDIS_CONTAINER:-dgc-router-redis}"
PORT="${DGC_ROUTER_REDIS_PORT:-6379}"
DOCKER_BIN="${DGC_DOCKER_BIN:-/Applications/Docker.app/Contents/Resources/bin/docker}"

stopped=0

if [[ -x "${DOCKER_BIN}" ]] || command -v docker >/dev/null 2>&1; then
  if [[ ! -x "${DOCKER_BIN}" ]]; then
    DOCKER_BIN="$(command -v docker)"
  fi
  if "${DOCKER_BIN}" ps --filter "name=^/${NAME}$" --format '{{.Names}}' | grep -qx "${NAME}"; then
    "${DOCKER_BIN}" stop "${NAME}" >/dev/null
    echo "Stopped Redis container: ${NAME}"
    stopped=1
  fi
fi

if command -v redis-cli >/dev/null 2>&1; then
  if redis-cli -h 127.0.0.1 -p "${PORT}" ping >/dev/null 2>&1; then
    redis-cli -h 127.0.0.1 -p "${PORT}" shutdown nosave >/dev/null 2>&1 || true
    echo "Requested local redis shutdown on port ${PORT}"
    stopped=1
  fi
fi

if [[ "${stopped}" -eq 0 ]]; then
  echo "No running router Redis instance found."
fi
