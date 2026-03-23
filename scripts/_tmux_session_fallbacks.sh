#!/usr/bin/env bash

resolve_tmux_session() {
  local preferred="$1"
  shift || true

  if tmux has-session -t "${preferred}" 2>/dev/null; then
    printf '%s\n' "${preferred}"
    return 0
  fi

  local candidate
  for candidate in "$@"; do
    [[ -n "${candidate}" ]] || continue
    if tmux has-session -t "${candidate}" 2>/dev/null; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  done

  return 1
}
