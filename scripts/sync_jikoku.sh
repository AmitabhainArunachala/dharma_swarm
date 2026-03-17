#!/usr/bin/env bash
# sync_jikoku.sh — Pull JIKOKU span logs from VPSes to local aggregation dir.
#
# Runs on Mac (hub). VPSes can't reach Mac (NAT in Bali).
# Each VPS writes to ~/.dharma/jikoku/JIKOKU_LOG.jsonl locally.
# This script rsyncs those files into subdirectories for SwarmLens to read.
#
# Usage:
#   bash ~/dharma_swarm/scripts/sync_jikoku.sh          # one-shot
#   */5 * * * * bash ~/dharma_swarm/scripts/sync_jikoku.sh  # crontab

set -euo pipefail

LOCAL_DIR="$HOME/.dharma/jikoku"
mkdir -p "$LOCAL_DIR/agni" "$LOCAL_DIR/rushabdev"

# AGNI VPS (157.245.193.15 via ssh alias "agni")
rsync -az --timeout=10 \
  agni:.dharma/jikoku/JIKOKU_LOG.jsonl \
  "$LOCAL_DIR/agni/JIKOKU_LOG.jsonl" 2>/dev/null || true

# RUSHABDEV VPS (167.172.95.184 via ssh alias "rushabdev")
rsync -az --timeout=10 \
  rushabdev:.dharma/jikoku/JIKOKU_LOG.jsonl \
  "$LOCAL_DIR/rushabdev/JIKOKU_LOG.jsonl" 2>/dev/null || true
