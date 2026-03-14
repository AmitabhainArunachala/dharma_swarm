#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACK_DIR="$ROOT_DIR/mode_pack/claude"

TARGET_KIND="repo"
if [ "${1:-}" = "--target" ] && [ -n "${2:-}" ]; then
  TARGET_KIND="$2"
fi

case "$TARGET_KIND" in
  repo)
    TARGET_DIR="$ROOT_DIR/.claude/skills"
    ;;
  user)
    TARGET_DIR="$HOME/.claude/skills"
    ;;
  *)
    echo "Unknown target: $TARGET_KIND" >&2
    echo "Usage: bash scripts/install_mode_pack.sh [--target repo|user]" >&2
    exit 1
    ;;
esac

mkdir -p "$TARGET_DIR"

MODES=(
  "ceo-review:dharma-ceo-review"
  "eng-review:dharma-eng-review"
  "preflight-review:dharma-preflight-review"
  "ship:dharma-ship"
  "qa:dharma-qa"
  "browse:dharma-browse"
  "retro:dharma-retro"
  "incident-commander:dharma-incident-commander"
)

for entry in "${MODES[@]}"; do
  slug="${entry%%:*}"
  alias_name="${entry#*:}"
  source_dir="$PACK_DIR/$slug"
  target_path="$TARGET_DIR/$alias_name"
  if [ ! -d "$source_dir" ]; then
    echo "Missing mode directory: $source_dir" >&2
    exit 1
  fi
  ln -snf "$source_dir" "$target_path"
done

echo "Dharma mode pack installed into $TARGET_DIR"
for entry in "${MODES[@]}"; do
  slug="${entry%%:*}"
  alias_name="${entry#*:}"
  echo "  $alias_name -> $PACK_DIR/$slug"
done
