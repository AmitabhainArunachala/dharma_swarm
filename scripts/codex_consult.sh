#!/bin/bash
# codex_consult.sh — Claude-Codex tandem consultation
# Usage: ./scripts/codex_consult.sh "Your prompt here" [output_file]
#
# Invokes Codex in non-interactive exec mode, captures response.
# Designed to be called from Claude Code sessions for tandem work.

set -euo pipefail

PROMPT="${1:?Usage: codex_consult.sh \"prompt\" [output_file]}"
OUTPUT_FILE="${2:-/tmp/codex_tandem_response.md}"
CODEX_BIN="/Users/dhyana/.npm-global/bin/codex"
WORKDIR="/Users/dhyana/dharma_swarm"

if [ ! -x "$CODEX_BIN" ]; then
    echo "ERROR: codex binary not found at $CODEX_BIN" >&2
    exit 1
fi

echo "[tandem] Consulting Codex (GPT-5.4)..." >&2
echo "[tandem] Prompt: ${PROMPT:0:120}..." >&2

"$CODEX_BIN" exec \
    "$PROMPT" \
    -C "$WORKDIR" \
    --full-auto \
    --ephemeral \
    -o "$OUTPUT_FILE" \
    2>/dev/null

if [ -f "$OUTPUT_FILE" ]; then
    echo "[tandem] Codex response captured ($(wc -c < "$OUTPUT_FILE" | tr -d ' ') bytes)" >&2
    cat "$OUTPUT_FILE"
else
    echo "[tandem] WARNING: No response captured" >&2
    exit 1
fi
