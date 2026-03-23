# Sovereign Hardening Night Design

Date: 2026-03-20
Owner: Codex
Scope: overnight execution pack for the canonical `dharma_swarm` repo

## Intent

Run a real overnight hardening cycle without widening the system.

This pack uses the existing DHARMA control surfaces:

- `launchd` for the always-on cron daemon
- `tmux` for inspectable overnight lanes
- `caffeinate` for machine wakefulness through the morning handoff

It does not create a second orchestrator. It composes the existing scripts with stricter defaults.

## Problem

The repo already has overnight infrastructure, but the broad conclave path is too expansive for the current dirty multi-writer tree. Tonight needs one writer and several observers.

The repo evidence is consistent:

- `reports/dharma_current_state_deep_dive_2026-03-19.md`
- `reports/ecosystem_forensics_audit_2026-03-19.md`
- `reports/ecosystem_absorption_master_index_2026-03-19.md`

The next useful step is coherence hardening, not another vision layer.

## Topology

### Lane 1: Cron daemon via `launchd`

Purpose:
- keep the baseline DHARMA daemon alive
- preserve the canonical always-on control loop

Mechanism:
- `scripts/com.dharma.cron-daemon.plist`

### Lane 2: Read-only director lane

Purpose:
- keep semantic pressure and compounding reports alive
- stay read-heavy
- avoid opening a second write surface

Mechanism:
- `scripts/start_allout_tmux.sh`
- session name: `dgc_allout_sovereign`
- autonomy profile: `readonly_audit`

### Lane 3: Single write-capable Codex lane

Purpose:
- land one bounded hardening slice at a time
- prefer contracts, telemetry, assurance, and focused tests
- leave a clean morning handoff

Mechanism:
- `scripts/start_codex_overnight_tmux.sh`
- session name: `dgc_codex_sovereign`
- mission file: `docs/missions/SOVEREIGN_HARDENING_NIGHT_2026-03-20.md`

### Lane 4: Verification lane

Purpose:
- continuously check process health, command health, and DB visibility
- act as the tripwire rather than a builder

Mechanism:
- `scripts/start_verification_lane.sh`

### Lane 5: Caffeine lane

Purpose:
- keep the machine awake through 04:30 JST
- emit the morning ledger and quick health packet

Mechanism:
- `scripts/start_caffeine_tmux.sh`
- session name: `dgc_caffeine_sovereign`

## Hard Rules

1. One writer only.
2. No dashboard expansion tonight.
3. No provider rewrites tonight.
4. No ontology surface widening tonight.
5. No commits, pushes, resets, or unrelated cleanup.
6. Every write-capable slice must end with focused verification or an exact blocker.

## Morning Outputs

- run manifest in `~/.dharma/sovereign_hardening/<run_id>/`
- Codex handoff from `codex_overnight`
- verification lane logs
- caffeine ledger
- latest assurance scan output

## Positive Must-Dos

1. Force every overnight action through runtime, intelligence, or telemetry seams.
2. Treat scanner drift as a first-class morning deliverable.
3. Keep exactly one write-capable lane.
4. Close route-contract gaps before adding UI surfaces.
5. Fix provider truth before adding routing cleverness.
6. Turn lifecycle concepts into contract-enforced records.
7. Break `dgc_cli.py` by domain before feeding it more behavior.
8. Require canonical records for new capabilities.
9. Keep donor patterns behind DHARMA-owned contracts.
10. Optimize for better truth by morning, not for more apparent surface area.

## Launch Contract

Primary launcher:

- `scripts/start_sovereign_hardening_night.sh`

Status:

- `scripts/status_sovereign_hardening_night.sh`

Stop:

- `scripts/stop_sovereign_hardening_night.sh`

Optional scheduled start:

- `scripts/com.dharma.sovereign-hardening-night.plist`
