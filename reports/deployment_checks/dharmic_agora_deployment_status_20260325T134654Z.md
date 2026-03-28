# dharmic-agora deployment status report

Timestamp: 2026-03-25T13:46:54Z
Target: Saraswati Dharmic Agora / SABP deployment on AGNI VPS (`157.245.193.15`)

## Summary
- Service is running under systemd as `sab-agora.service`.
- The app is listening on `127.0.0.1:8000`, with Caddy exposing `*:80` and `*:443`.
- `GET /health` is not implemented on the live service and returns `404 Not Found`.
- The live health surface is `GET /api/node/status`, which returns `200 OK` with `status=healthy`.
- The live payload reports `gate_count=12`, not the older "8 quality gates" framing from the task prompt.

## Direct observations
- `ssh agni "systemctl is-active sab-agora.service"`:
  - `active`
- `ssh agni "systemctl show -p ActiveEnterTimestamp -p ExecMainPID sab-agora.service"`:
  - `ActiveEnterTimestamp=Wed 2026-03-18 22:45:53 UTC`
  - `ExecMainPID=974812`
- `ssh agni "ss -ltnp '( sport = :8000 or sport = :443 or sport = :80 )'"`:
  - `127.0.0.1:8000` served by `python3` / `uvicorn`
  - `*:80` and `*:443` served by `caddy`
- `ssh agni "curl -sS -o /tmp/sab_local_health.out -w '%{http_code}\n' http://127.0.0.1:8000/health"`:
  - `404`
  - body: `{"detail":"Not Found"}`
- `ssh agni "curl -sS http://127.0.0.1:8000/api/node/status"`:
  - `200 OK`
  - `status=healthy`
  - `version=0.3.1`
  - `gate_count=12`
- `ssh agni "curl -k -sS -D - -o /tmp/sab_public_health.out https://157.245.193.15/health"`:
  - `HTTP/2 404`
  - headers include `via: 1.1 Caddy` and `server: uvicorn`
  - body: `{"detail":"Not Found"}`
- `ssh agni "curl -k -sS https://157.245.193.15/api/node/status"`:
  - `200 OK`
  - same healthy payload as localhost

## Current gate state
The live status payload reports these 12 gate averages:

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

If the requested "8 quality gates" means the non-required gates in the current `ALL_GATES` list, those 8 are:

- `substance`: `0.8`
- `originality`: `0.75`
- `relevance`: `0.0`
- `telos_alignment`: `0.0`
- `consistency`: `0.0`
- `sybil`: `0.3`
- `svadhyaya`: `0.031818`
- `isvara`: `0.163636`

## Health assessment
Deployment health is `running and reachable, with endpoint/spec drift`.

Healthy signals:
- systemd service is active and has been stable since 2026-03-18
- Caddy is exposing the service on ports `80` and `443`
- the live status endpoint returns `healthy`
- the payload shows no compost backlog and no pending challenges

Risks / anomalies:
- `/health` is still missing, so any monitor expecting that route will fail
- the service logs still show repeated `GET /gates` requests from `127.0.0.1` returning `404`, which suggests a stale monitor or UI probe
- the task prompt still asks about "8 quality gates", but the live runtime and current code expose 12 total gates with 8 non-required gates layered on top of 4 required gates

## Code references
- Live status route and payload shape:
  - `/Users/dhyana/agni-workspace/dharmic-agora/agora/app.py:1282`
  - `/Users/dhyana/agni-workspace/dharmic-agora/agora/app.py:1321`
- Current gate registry:
  - `/Users/dhyana/agni-workspace/dharmic-agora/agora/gates.py:490`
- Task source carrying the older wording:
  - `/Users/dhyana/dharma_swarm/dharma_swarm/startup_crew.py:123`

## Shared-notes hygiene
`/Users/dhyana/.dharma/shared/validator_notes.md` contains multiple stale or unsupported claims that `/health` is reachable and that all 8 gates pass. The live AGNI probe above contradicts those notes. Treat them as unverified unless backed by command output.
