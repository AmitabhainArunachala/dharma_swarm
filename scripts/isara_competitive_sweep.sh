#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/dhyana/dharma_swarm"
OUT="$ROOT/docs/reports/ISARA_LOCAL_APPENDIX_2026-03-27.md"

cd "$ROOT"

{
  echo "# ISARA Local Appendix"
  echo
  echo "Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "## Repo X-Ray"
  echo
  echo '```json'
  python3 scripts/repo_xray.py --format json
  echo '```'
  echo
  echo "## Key Runtime Surfaces"
  echo
  echo "### monitor.py"
  echo
  echo '```python'
  sed -n '1,220p' dharma_swarm/monitor.py
  echo '```'
  echo
  echo "### message_bus.py"
  echo
  echo '```python'
  sed -n '1,220p' dharma_swarm/message_bus.py
  echo '```'
  echo
  echo "### checkpoint.py"
  echo
  echo '```python'
  sed -n '1,220p' dharma_swarm/checkpoint.py
  echo '```'
  echo
  echo "### adaptive_autonomy.py"
  echo
  echo '```python'
  sed -n '1,220p' dharma_swarm/adaptive_autonomy.py
  echo '```'
  echo
  echo "### orchestrator.py"
  echo
  echo '```python'
  sed -n '1,220p' dharma_swarm/orchestrator.py
  echo '```'
  echo
  echo "### swarm.py"
  echo
  echo '```python'
  sed -n '1,220p' dharma_swarm/swarm.py
  echo '```'
  echo
  echo "### swarmlens_app.py"
  echo
  echo '```python'
  sed -n '1,220p' dharma_swarm/swarmlens_app.py
  echo '```'
  echo
  echo "### ginko_brier.py"
  echo
  echo '```python'
  sed -n '1,180p' dharma_swarm/ginko_brier.py
  echo '```'
  echo
  echo "### ginko_orchestrator.py grep snapshot"
  echo
  echo '```text'
  rg -n "Brier|SATYA|cron|cycle|report|portfolio|signals|scanner" dharma_swarm/ginko_orchestrator.py
  echo '```'
  echo
  echo "## Benchmark and Gap Markers"
  echo
  echo
  echo "### BENCHMARK_SUMMARY.md"
  echo
  echo '```text'
  sed -n '1,220p' docs/reports/BENCHMARK_SUMMARY.md
  echo '```'
  echo
  echo "### DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md"
  echo
  echo '```text'
  sed -n '1,140p' docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md
  echo '```'
  echo
  echo "## End"
} > "$OUT"

echo "Wrote $OUT"
