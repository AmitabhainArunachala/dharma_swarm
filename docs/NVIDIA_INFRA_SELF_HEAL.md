# NVIDIA Infra Self-Heal Runbook

Purpose: make the allout loop recover NVIDIA RAG + Data Flywheel endpoints automatically.

Note: NVIDIA RAG blueprint services generally require Linux + NVIDIA GPU runtime.
On macOS hosts, self-heal reports `local_nvidia_gpu_runtime_unavailable` and
you should point DGC to a remote GPU deployment for RAG/ingest endpoints.

## Dormant vs armed mode

Use `DGC_ACCELERATOR_MODE=dormant` when you want unattended loops to ignore the
accelerator lane entirely instead of repeatedly probing dead localhost endpoints.
Use `DGC_ACCELERATOR_MODE=enabled` when real local/remote endpoints are ready.

The tmux launchers now auto-load `~/.dharma/env/nvidia_remote.env`, so the
persisted mode travels with the loop without manual `source` steps.

## Prerequisites

1. Docker Desktop is running.
2. NVIDIA blueprint repos exist:
- `~/DHARMIC_GODEL_CLAW/cloned_source/nvidia-rag`
- `~/DHARMIC_GODEL_CLAW/cloned_source/data-flywheel`
3. NVIDIA key is set for RAG blueprint compose:
- `export NGC_API_KEY=...`
4. Optional fallback key mapping:
- `export NVIDIA_API_KEY=...` (script maps to `NGC_API_KEY` if missing)

## Optional path overrides

Use when repos/files are moved:

```bash
export DGC_NVIDIA_RAG_REPO=~/path/to/nvidia-rag
export DGC_NVIDIA_RAG_COMPOSE_RAG=~/path/to/docker-compose-rag-server.yaml
export DGC_NVIDIA_RAG_COMPOSE_INGEST=~/path/to/docker-compose-ingestor-server.yaml
export DGC_NVIDIA_FLYWHEEL_REPO=~/path/to/data-flywheel
export DGC_NVIDIA_FLYWHEEL_COMPOSE=~/path/to/docker-compose.yaml
```

## Self-heal toggles

```bash
export ALLOUT_SELF_HEAL_INFRA=1
export ALLOUT_HEAL_NO_BUILD=1
export ALLOUT_HEAL_ALLOW_BUILD=0
export ALLOUT_HEAL_COMPOSE_TIMEOUT_SEC=180
export ALLOUT_HEAL_RETRIES=4
export ALLOUT_HEAL_WAIT_SEC=2
export ALLOUT_HEAL_COOLDOWN_SEC=300
```

`ALLOUT_HEAL_ALLOW_BUILD=1` allows a second compose attempt with image build/pull
when `--no-build` fails.

## Launch one verification cycle

```bash
cd ~/dharma_swarm
DGC_NVIDIA_RAG_URL=http://127.0.0.1:8081/v1 \
DGC_NVIDIA_INGEST_URL=http://127.0.0.1:8082/v1 \
DGC_DATA_FLYWHEEL_URL=http://127.0.0.1:8000/api \
ALLOUT_EXECUTE=1 \
ALLOUT_ACTIONS_PER_CYCLE=20 \
python3 scripts/thinkodynamic_director.py --hours 0.1 --poll-seconds 1 --max-cycles 1
```

## One-shot remote wiring + launch gate

Use the helper to persist env, probe all endpoints, and refuse launcher start
unless checks pass:

```bash
cd ~/dharma_swarm
scripts/wire_nvidia_remote.sh \
  --rag-url https://<rag-host>/v1 \
  --ingest-url https://<ingest-host>/v1 \
  --flywheel-url https://<flywheel-host>/api \
  --nim-key '<NVIDIA_NIM_API_KEY>' \
  --flywheel-key '<DGC_DATA_FLYWHEEL_API_KEY>' \
  --launcher caffeine --target-jst 08:00
```

Alternative launch mode:

```bash
scripts/wire_nvidia_remote.sh \
  --rag-url https://<rag-host>/v1 \
  --ingest-url https://<ingest-host>/v1 \
  --flywheel-url https://<flywheel-host>/api \
  --launcher allout --allout-hours forever
```

Persisted env file (default):

```bash
~/.dharma/env/nvidia_remote.env
```

To bypass probe gate intentionally:

```bash
scripts/wire_nvidia_remote.sh ... --force
```

## Mission preflight before overnight/tmux loops

By default, tmux launchers run a mission preflight in non-blocking mode.

```bash
cd ~/dharma_swarm
scripts/mission_preflight.sh
```

Strict knobs:

```bash
# Fail if core lane has gaps
MISSION_STRICT_CORE=1 MISSION_BLOCK_ON_FAIL=1 scripts/mission_preflight.sh

# Also fail when mission-critical files are local-only (not tracked in git)
MISSION_REQUIRE_TRACKED=1 MISSION_BLOCK_ON_FAIL=1 scripts/mission_preflight.sh
```

Launcher envs:

```bash
MISSION_PREFLIGHT=1           # default: run preflight
MISSION_STRICT_CORE=1         # default: strict core check
MISSION_REQUIRE_TRACKED=0     # default: advisory only for local-only files
MISSION_BLOCK_ON_FAIL=0       # default: warn but continue
```

## Failure diagnostics exposed in action verify fields

- `diag=missing_ngc_api_key`
- `diag=docker_socket_permission_denied`
- `diag=docker_socket_blocked`
- `diag=docker_not_running`
- `diag=host_network_unsupported`
- `diag=missing_image_manifest`

Read latest log:

```bash
LATEST=$(ls -1t ~/.dharma/logs/allout | head -n 1)
tail -n 120 ~/.dharma/logs/allout/$LATEST/allout.log
```
