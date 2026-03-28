# dharmic-agora deployment status report

Timestamp: 2026-03-25T12:34:32Z
Target: Saraswati Dharmic Agora / SABP deployment on AGNI VPS (`157.245.193.15`)

## Summary
- Service is running under systemd as `sab-agora.service`.
- Live process is healthy on `127.0.0.1:8000` and public HTTPS is routing to it through Caddy.
- The documented `/health` endpoint is still not present on the live app.
- The actual health endpoint is `GET /api/node/status`, which is reachable both locally and publicly and returns `status=healthy`.
- Runtime protocol shape has expanded beyond the older "8 quality gates" framing. The live status payload reports `gate_count=12`.

## Direct observations
- `ssh agni "systemctl status sab-agora.service --no-pager -l"`:
  - `Active: active (running) since Wed 2026-03-18 22:45:53 UTC`
  - `Main PID: 974812 (uvicorn)`
  - listening on `127.0.0.1:8000`
- `curl http://127.0.0.1:8000/health` from AGNI:
  - `404 Not Found`
- `curl http://127.0.0.1:8000/api/node/status` from AGNI:
  - `200 OK`
  - `status=healthy`
  - `version=0.3.1`
  - `gate_count=12`
  - `totals={"sparks":22,"spark_status":17,"canon":5,"compost":0,"pending_challenges":0}`
- `curl https://157.245.193.15/health` from AGNI:
  - `404 Not Found`
  - headers show `via: 1.1 Caddy` and `server: uvicorn`
- `curl https://157.245.193.15/api/node/status` from AGNI:
  - `200 OK`
  - same healthy payload as localhost

## Current gate state
The live payload reports 12 gate averages:

- `witness`: `0.95`
- `ahimsa`: `0.85`
- `satya`: `0.8`
- `substance`: `0.8`
- `originality`: `0.75`
- `rate_limit`: `0.736364`
- `sybil`: `0.3`
- `isvara`: `0.163636`
- `svadhyaya`: `0.031818`
- `consistency`: `0.0`
- `relevance`: `0.0`
- `telos_alignment`: `0.0`

If "the 8 quality gates" means the 8 non-required gates in the current `agora.gates.ALL_GATES` categorization, their live averages are:

- `substance`: `0.8`
- `originality`: `0.75`
- `relevance`: `0.0`
- `telos_alignment`: `0.0`
- `consistency`: `0.0`
- `sybil`: `0.3`
- `svadhyaya`: `0.031818`
- `isvara`: `0.163636`

## Health assessment
Deployment health is `mostly healthy with an endpoint/spec drift`.

Healthy signals:
- systemd service is stable and has been up since 2026-03-18
- public HTTPS routing works
- application status endpoint returns `healthy`
- no compost backlog and no pending challenges

Risks / anomalies:
- `/health` is still missing, so any monitor or operator expecting that route will fail
- `journalctl -u sab-agora.service` shows repeated `GET /gates` requests from `127.0.0.1` returning `404 Not Found`, which suggests a stale local monitor or UI probe
- the checked-in deploy files under `deploy/` are stale relative to the live unit path on AGNI, so repo deploy docs are not a reliable runtime mirror

## Relevant references
- Live app shape:
  - `/Users/dhyana/agni-workspace/dharmic-agora/agora/app.py`
  - `/Users/dhyana/agni-workspace/dharmic-agora/agora/gates.py`
- Historical / older gate framing:
  - `/Users/dhyana/agni-workspace/dharmic-agora/agora/CLAUDE.md`
  - `/Users/dhyana/agni-workspace/dharmic-agora/agora/api_server.py.backup`
- Prior deployment check for comparison:
  - `/Users/dhyana/dharma_swarm/reports/deployment_checks/dharmic_agora_deployment_status_20260313T211943Z.md`

## Note on memory externalization
The requested `~/.dharma/shared` and `~/.dharma/witness` locations were readable but not writable from this harness. Findings were therefore externalized to this repo report plus fallback notes under `/Users/dhyana/.codex/memories/`.
