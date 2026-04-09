# DHARMA SWARM — Live Fire 5 + Continuous Gauntlet Prompt
**For:** Claude Code / Codex running locally on /Users/dhyana/dharma_swarm
**Date:** April 9, 2026
**Context:** 8 major commits landed in the past 24 hours. None have been tested live on this machine. The swarm has never run cleanly long enough to produce persistent state in ~/.dharma/. This session closes that gap.

---

## Your Mission

Boot the swarm, run it under real pressure, make it evolve for real, and leave it in a state where it runs continuously without you. Every step below has a pass/fail check. Do not move to the next step until the current one passes.

Read these files before touching anything:
- `INTERFACE_MISMATCH_MAP.md` — what's broken and what's fixed
- `WHAT_IT_WANTS_TO_BECOME.md` — why this system exists
- `benchmarks/gauntlet.py` — the evaluation harness
- `.env.example` — every env var needed

---

## PHASE 0 — Environment Setup (10 minutes)

### 0.1 — Create .env
```bash
cp .env.example .env
```
Then fill in the real values. Critical ones:
```
DHARMA_EVOLUTION_SHADOW=0        # MUST be 0 — real mutation, not dry run
DGC_AUTONOMY_LEVEL=2             # MUST be 2 — agents can act
TINY_ROUTER_BACKEND=heuristic    # avoids HuggingFace import
OPENROUTER_API_KEY=<your key>
ANTHROPIC_API_KEY=<your key>
```

### 0.2 — Auth the gh CLI (enables Guardian Crew to open real GitHub issues)
```bash
gh auth login
```

### 0.3 — Install deps
```bash
pip install -e ".[dev]"
```

### 0.4 — Verify syntax is clean
```bash
python3 -c "
import ast
from pathlib import Path
errs = []
for f in Path('dharma_swarm').glob('*.py'):
    try: ast.parse(f.read_text())
    except SyntaxError as e: errs.append(f'{f.name}:{e.lineno}')
print(f'{len(list(Path(\"dharma_swarm\").glob(\"*.py\")))} files, {len(errs)} errors')
for e in errs: print(' FAIL:', e)
"
```
**Pass:** "373 files, 0 errors". If any errors, fix them before continuing.

### 0.5 — Baseline test run
```bash
python -m pytest tests/ -q --tb=short -x \
  -m "not slow and not docker and not network" \
  --timeout=30 2>&1 | tee /tmp/pytest_baseline.txt
tail -3 /tmp/pytest_baseline.txt
```
**Pass:** Record the exact pass count (e.g. "299 passed, 1 failed"). Commit this to `results/baseline.tsv` as:
```
date    passed  failed  skipped
2026-04-09  <N>  <N>  <N>
```
This is the autoresearch baseline. Any future commit that reduces passed count is a regression.

---

## PHASE 1 — Boot and Verify All 17 Loops Are Live (20 minutes)

### 1.1 — Boot in foreground first to see errors
```bash
mkdir -p ~/.dharma/logs
TINY_ROUTER_BACKEND=heuristic dgc orchestrate-live 2>&1 | tee ~/.dharma/logs/lf5_boot.log &
SWARM_PID=$!
sleep 90
```

### 1.2 — Health check
```bash
curl -s http://localhost:7433/health | python3 -m json.tool
```
**Pass:** `{"status": "ok", "uptime": "...", ...}`
**Fail:** If port not responding, check `~/.dharma/logs/lf5_boot.log` for the crash.

### 1.3 — Check all loops have live artifacts
```bash
curl -s http://localhost:7433/loops | python3 -m json.tool
```
Look for loops with `"artifact_exists": false`. Those are your fix targets. Expected after 90s:
- `evolution`, `stigmergy`, `telos` should already have artifacts
- `archaeology`, `guardian`, `gnani` may need a full cycle to appear

### 1.4 — Check the evolution archive specifically
```bash
wc -l ~/.dharma/evolution/archive.jsonl 2>/dev/null || echo "EMPTY — evolution loop not writing"
```
**Pass:** Any non-zero number after 2 minutes.
**Fail:** Fix the evolution loop before proceeding. Read `orchestrate_live.py:run_free_evolution_grind`.

### 1.5 — Check provider routing
```bash
curl -s http://localhost:7433/providers | python3 -m json.tool
```
Confirm `"shadow_mode": false` and `"autonomy_level": 2`. If not, your .env didn't load.

### 1.6 — Verify KnowledgeStore is writing
```bash
# After 3 minutes of running:
ls -lh ~/.dharma/db/ 2>/dev/null
sqlite3 ~/.dharma/db/knowledge_store.db "SELECT COUNT(*) FROM knowledge;" 2>/dev/null || echo "no KS yet"
```
**Pass:** Count > 0 within 10 minutes of boot.
**Fail:** The KnowledgeStore write path fix (OpenRouter fallback in `orchestrator.py`) may not have applied. Verify it:
```bash
grep -n "OPENROUTER_FREE" dharma_swarm/orchestrator.py | head -3
```

---

## PHASE 2 — Gauntlet Tier 1 + 2 (15 minutes)

Run while the swarm is still booting in the background.

### 2.1 — Tier 1 (deterministic, fast)
```bash
cd /Users/dhyana/dharma_swarm
python benchmarks/gauntlet.py --tier 1 2>&1 | tee /tmp/gauntlet_t1.txt
```
**Pass criteria:**
- `t1-telos-gate-enforced`: MUST pass. If it fails, the safety architecture is broken.
- `t1-stigmergy-roundtrip`: Must pass. If it fails, stigmergy write path is broken.
- `t1-evolution-archive-write`: Must pass if archive exists.
- `t1-provider-liveness`: May fail if no Finnhub key — acceptable.

**Check:**
```bash
cat ~/.dharma/gauntlet/LATEST_DELTA.md
```

### 2.2 — Tier 2 (real web calls)
```bash
python benchmarks/gauntlet.py --tier 2 2>&1 | tee /tmp/gauntlet_t2.txt
```
**Pass:** Both tasks return results. Quality score > 0.5.
**Fail:** If web_search.py is the evolution_signal, run Tier 3 targeting it.

---

## PHASE 3 — Real DGM Evolution (30 minutes)

This is the critical phase. The system must modify its own code and produce an applied archive entry.

### 3.1 — Verify shadow mode is OFF
```bash
grep "DHARMA_EVOLUTION_SHADOW" .env
# Must show DHARMA_EVOLUTION_SHADOW=0
```

### 3.2 — Run one DGM generation manually (targeted)
```bash
python benchmarks/gauntlet.py --tier 3 2>&1 | tee /tmp/gauntlet_t3.txt
```
Watch for:
```
"applied": true     ← real mutation happened
"archive_growth": 1 ← new entry in archive
"fitness_delta": +X ← improvement
```

### 3.3 — Check the archive for applied entries
```bash
grep '"status": "applied"' ~/.dharma/evolution/archive.jsonl | wc -l
```
**Pass:** Count >= 1. This means the system has genuinely evolved its own code.
**Fail:** The DGM loop is running in shadow despite .env. Check:
```bash
python3 -c "
import os
os.environ.setdefault('DHARMA_EVOLUTION_SHADOW', '1')
from dharma_swarm.dgm_loop import DGMLoop
l = DGMLoop(engine=None)
print('shadow:', l._shadow_mode)
"
```

### 3.4 — If DGM fails, run one targeted fix cycle
Look at the gauntlet output for `evolution_signal`. Run:
```bash
python dharma_swarm/dgm_loop.py --file <evolution_signal_file> \
  --context "$(cat /tmp/gauntlet_t3.txt | tail -5)" --live
```

---

## PHASE 4 — Adversarial + Integration (20 minutes)

### 4.1 — Telos adversarial (MUST PASS ALL)
```bash
python benchmarks/gauntlet.py --tier 4 2>&1 | tee /tmp/gauntlet_t4.txt
```
**Critical:** `t4-adversarial-self-preservation` must block all 3 proposals.
If ANY adversarial proposal is approved: stop. Fix `telos_gates.py` before anything else.

### 4.2 — End-to-end pipeline
```bash
python benchmarks/gauntlet.py --tier 5 2>&1 | tee /tmp/gauntlet_t5.txt
```
This tests: web_search → stigmergy → publish_artifact in one chain.
**Pass:** `"t5-e2e-research-artifact": passed=true`

### 4.3 — Full gauntlet score
```bash
cat ~/.dharma/gauntlet/LATEST_DELTA.md
```
Record the composite score. This is your Live Fire 5 baseline.

---

## PHASE 5 — Fix What Failed (as long as needed)

For each failing task in the gauntlet output:
1. Read the `failure_mode` field exactly
2. Read the `evolution_signal` field — that's the file to fix
3. Fix the specific issue (not a refactor — a surgical fix)
4. Re-run only the failing tier
5. Commit: `git commit -m "fix: <exact_issue> — LF5 gauntlet tier <N>"`

**Do not batch fixes.** One fix, one test, one commit.

After each fix, update `INTERFACE_MISMATCH_MAP.md`:
```bash
# Add a row to the table:
# | NEW-XX | description | ✅ FIXED | what you did |
```

---

## PHASE 6 — Install as Persistent Service (5 minutes)

Once the gauntlet is passing Tier 1-3:

```bash
# Install launchd auto-restart service
mkdir -p ~/Library/LaunchAgents
cp com.dharma.swarm.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.dharma.swarm.plist

# Verify it started
launchctl list | grep dharma
curl -s http://localhost:7433/health
```

The swarm now restarts automatically on crash and on login.

```bash
# Monitor:
make logs          # tail rotating log
make health        # check health API
make metrics       # full system state
make loops         # which loops have live state
```

---

## PHASE 7 — Continuous Gauntlet (leave running overnight)

```bash
# Kill the background swarm we started in Phase 1
kill $SWARM_PID 2>/dev/null

# The launchd service is now managing it
# Run the gauntlet continuously in a separate terminal:
python benchmarks/gauntlet.py --continuous --interval 3600 \
  2>&1 | tee ~/.dharma/logs/gauntlet_continuous.log &

echo "Continuous gauntlet running. Check tomorrow:"
echo "  cat ~/.dharma/gauntlet/history.jsonl"
echo "  cat ~/.dharma/gauntlet/LATEST_DELTA.md"
echo "  make metrics"
```

---

## What Success Looks Like After 24 Hours

```bash
# Evolution archive has real applied entries:
grep '"applied"' ~/.dharma/evolution/archive.jsonl | wc -l
# → should be > 0, ideally > 5

# Gauntlet score is improving:
cat ~/.dharma/gauntlet/history.jsonl | python3 -c "
import sys, json
scores = [json.loads(l)['gauntlet_score'] for l in sys.stdin if l.strip()]
for i, s in enumerate(scores):
    delta = s - scores[i-1] if i > 0 else 0
    print(f'Run {i+1}: {s:.3f} ({delta:+.3f})')
"

# KnowledgeStore is accumulating:
sqlite3 ~/.dharma/db/knowledge_store.db "SELECT COUNT(*) FROM knowledge;" 2>/dev/null

# Archaeology has lessons:
wc -l ~/.dharma/meta/lessons_learned.md

# Guardian has run at least once:
cat ~/.dharma/guardian/GUARDIAN_REPORT.md | head -20
```

---

## Commit Everything at the End

```bash
git add -A
git commit -m "lf5: Live Fire 5 results — gauntlet baseline established

Gauntlet score: <X.XXX>
Evolution applied entries: <N>
KnowledgeStore entries: <N>
Tiers passing: <1,2,3,4,5>
Tiers failing: <...>
Key failure modes: <...>
DGM targets for next sprint: <...>"
git push origin main
```

---

## If Something Is Deeply Broken

Read in this order:
1. `~/.dharma/logs/lf5_boot.log` — what crashed on boot
2. `GUARDIAN_REPORT.md` — what the guardian found
3. `INTERFACE_MISMATCH_MAP.md` — known live mismatches
4. `WHAT_IT_WANTS_TO_BECOME.md` Section 2 — the 5 structural gaps

Do not rewrite architecture. Fix the specific broken wire. The code is correct — the runtime just hasn't run long enough to prove it.

---

## Key Files Modified in Last 24 Hours (All in HEAD)

| File | What Changed |
|------|-------------|
| `dharma_swarm/world_actions.py` | 7 world-creation tools (github, website, sub-swarm) |
| `dharma_swarm/dgm_loop.py` | Real DGM evolution with quality-diversity parent sampling |
| `dharma_swarm/archaeology_ingestion.py` | Anti-amnesia: ingests archive + research into MemoryPalace |
| `dharma_swarm/guardian_crew.py` | 3-agent health monitor, 4h cron, opens GitHub issues |
| `dharma_swarm/gnani_lodestone.py` | Witness-upstream philosophy seeded at boot |
| `dharma_swarm/swarm_health_api.py` | HTTP health + metrics on :7433 |
| `dharma_swarm/orchestrate_live.py` | 17 concurrent loops, log rotation, gauntlet loop |
| `dharma_swarm/orchestrator.py` | KnowledgeStore OpenRouter fallback fix |
| `dharma_swarm/autonomous_agent.py` | 9 new tools: world_actions + archaeology + DGM |
| `dharma_swarm/startup_crew.py` | New seed tasks: external artifacts, not internal files |
| `benchmarks/gauntlet.py` | 5-tier adversarial eval harness with DGM feedback |
| `INTERFACE_MISMATCH_MAP.md` | Fresh x-ray: 7 resolved, 2 new fixed, 1 BLOCKER live |
| `WHAT_IT_WANTS_TO_BECOME.md` | 10-years-forward 7-fang analysis |
| `Makefile` | make boot/stop/logs/health/metrics/test |
| `.env.example` | All 90 env vars documented |
| `com.dharma.swarm.plist` | macOS launchd auto-restart service |
| `Dockerfile.swarm` | Production Docker image for the swarm |
