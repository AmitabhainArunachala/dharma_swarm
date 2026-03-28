# Witness Entry: dharmic-agora deployment status

Timestamp: 2026-03-25T13:46:54Z
Task source: `/Users/dhyana/dharma_swarm/dharma_swarm/startup_crew.py:123-129`
Primary report: `/Users/dhyana/dharma_swarm/reports/deployment_checks/dharmic_agora_deployment_status_20260325T134654Z.md`

## Findings
- `sab-agora.service` is active on AGNI.
- The app listens on `127.0.0.1:8000` and is exposed via Caddy on `*:80` and `*:443`.
- `GET /health` returns `404 Not Found` on both localhost and the public HTTPS route.
- `GET /api/node/status` returns `200 OK` with `status=healthy`, `version=0.3.1`, and `gate_count=12`.
- The current runtime has 12 total gates. The requested "8 quality gates" only matches the 8 non-required gates in the current registry.

## Integrity Note
Older shared notes claiming that `/health` is reachable or that all 8 gates pass are contradicted by direct AGNI command output gathered at 2026-03-25T13:46Z.

## Write Failure Note
The sandbox denied writes to:
- `/Users/dhyana/.dharma/shared/codex_notes.md`
- `/Users/dhyana/.dharma/witness/20260325T134654Z_codex_dharmic_agora_deployment.md`

Fallback persistence was completed in:
- this witness file
- `/Users/dhyana/dharma_swarm/reports/deployment_checks/dharmic_agora_deployment_status_20260325T134654Z.md`
- `/Users/dhyana/.codex/memories/dharmic_agora_deployment_status_20260325T134654Z.md`
