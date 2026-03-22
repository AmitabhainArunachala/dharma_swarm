# Codex All-Night Mission — Operator Contract, Agent Wiring, and KaizenOps

Date: 2026-03-20
Mode: contract-first overnight ship

## Objective

By morning, DHARMA SWARM should present one coherent operator loop:

- live agents are visible through one canonical contract
- live agents publish bus presence and can receive shared lifecycle broadcasts
- live agents are registered in the canonical telemetry plane
- live agents can be synced to KaizenOps from one explicit control surface
- the dashboard reads truthful runtime state instead of inferred client state

## Hard Scope

1. Keep the canonical live surfaces truthful:
   - `api/routers/agents.py`
   - `api/routers/telemetry.py`
   - `dharma_swarm/swarm.py`
   - `dharma_swarm/agent_runner.py`
   - telemetry and KaizenOps registration contracts

2. Treat communication as runtime bus readiness:
   - shared bus heartbeat
   - shared lifecycle topic subscriptions
   - no fake “agents can chat” claim unless there is a real inbox loop

3. Treat KaizenOps registration as explicit ingest:
   - export canonical agent identity + roster events
   - never silently claim success if KaizenOps is offline

## Success Criteria

- `POST /api/agents/sync` returns one result per live agent
- each result includes communication topics and KaizenOps status
- `GET /api/telemetry/agents` returns canonical agent identities
- `GET /api/telemetry/teams` returns roster membership
- live agents write heartbeats + subscriptions to the shared message bus
- touched tests are green

## Do Not Do

- no new speculative dashboard surfaces
- no GraphQL expansion unless directly required for the above
- no aesthetic-only polish
- no new agent protocol beyond the canonical message bus presence

## Morning Handoff Must Include

- which agents are live
- whether KaizenOps sync was attempted
- whether KaizenOps actually accepted events
- any remaining fake or partial surfaces
