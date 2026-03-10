#!/usr/bin/env bash
set -euo pipefail

NAME="${DGC_ROUTER_REDIS_CONTAINER:-dgc-router-redis}"
PORT="${DGC_ROUTER_REDIS_PORT:-6379}"
DOCKER_BIN="${DGC_DOCKER_BIN:-/Applications/Docker.app/Contents/Resources/bin/docker}"

echo "Redis TCP check (127.0.0.1:${PORT}):"
if nc -z 127.0.0.1 "${PORT}" >/dev/null 2>&1; then
  echo "  UP"
else
  echo "  DOWN"
fi

if command -v redis-cli >/dev/null 2>&1; then
  echo "redis-cli ping:"
  if redis-cli -h 127.0.0.1 -p "${PORT}" ping >/dev/null 2>&1; then
    redis-cli -h 127.0.0.1 -p "${PORT}" ping
  else
    echo "  unavailable"
  fi
fi

if [[ -x "${DOCKER_BIN}" ]] || command -v docker >/dev/null 2>&1; then
  if [[ ! -x "${DOCKER_BIN}" ]]; then
    DOCKER_BIN="$(command -v docker)"
  fi
  echo "Docker container status (${NAME}):"
  "${DOCKER_BIN}" ps -a --filter "name=^/${NAME}$" --format "  {{.Names}}  {{.Status}}" || true
fi
