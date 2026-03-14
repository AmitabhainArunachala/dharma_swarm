# dharmic-agora deployment status report

Timestamp: 2026-03-13T21:19:43Z

## Summary
- Service listener is up on `157.245.193.15:8800` and reports `SAB Basin API` `0.3.1`.
- Expected `/health` endpoint is not reachable on the documented public surfaces.
- Health-equivalent endpoint on the live service is `/api/node/status`, which returns `healthy` with `gate_count=12` and zero sparks.
- Public `443` is serving `OpenClaw Control`, not SAB health JSON.
- The 8 non-required quality gates exist in code but have no live pass/fail telemetry because `gate_averages` is empty.

## Evidence
- `GET http://157.245.193.15:8800/openapi.json` -> title `SAB Basin API`, version `0.3.1`
- `GET http://157.245.193.15:8800/api/node/status` -> `{"status":"healthy","gate_count":12,"totals":{"sparks":0},"gate_averages":{}}`
- `GET http://157.245.193.15:8800/health` -> `404`
- `GET https://157.245.193.15/health` -> `200` HTML for `OpenClaw Control`

## Spec mismatch
- Local spec server defines `GET /health`: `/Users/dhyana/agni-workspace/dharmic-agora/agora/api_server.py:4252`
- Deployed service unit launches `agora.app:app`: `/Users/dhyana/agni-workspace/dharmic-agora/deploy/sab-agora.service:18`
- `agora.app` health-style endpoint is `GET /api/node/status`: `/Users/dhyana/agni-workspace/dharmic-agora/agora/app.py:1282`
- nginx proxies `/health` anyway: `/Users/dhyana/agni-workspace/dharmic-agora/deploy/sab-agora.nginx.conf:54`
