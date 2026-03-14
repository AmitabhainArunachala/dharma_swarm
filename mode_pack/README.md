# Dharma Swarm Mode Pack

The mode pack is the canonical shared workflow layer for the system.

It is not another vague prompt bank. It is a set of explicit operating modes
with:

- a machine-readable contract
- Claude skill wrappers
- runtime aliases for Codex, DGC, and OpenClaw
- one installer for repo-local usage

## Why it exists

The system already has strong infrastructure:

- `DGC` for execution and delegation
- `Dharma Swarm` for intelligence and orchestration
- `KaizenOps` for audit and control
- `OpenClaw` for agent shells

What was missing was a clean layer of explicit cognitive gears.

This pack provides that layer.

## Canonical modes

| Slug | Purpose |
|------|---------|
| `ceo-review` | Reframe the problem and find the strongest product wedge |
| `eng-review` | Lock architecture, interfaces, failure modes, and tests |
| `preflight-review` | Review a diff or plan for production-grade risks |
| `ship` | Execute the release workflow for a ready branch |
| `qa` | Run structured product QA with evidence |
| `browse` | Use browser automation as an operational tool |
| `retro` | Turn completed work into concrete learning |
| `incident-commander` | Coordinate live incident response and recovery |

## Files

- `contracts/mode_pack.v1.json`
  Machine-readable source of truth.

- `claude/<mode>/SKILL.md`
  Repo-local Claude skill wrappers.

- `../dharma_swarm/mode_pack.py`
  Python loader for the contract.

- `../scripts/install_mode_pack.sh`
  Symlink installer for repo-local or user-level Claude skill usage.

## Install into this repo

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/install_mode_pack.sh --target repo
```

This creates symlinks in:

```text
/Users/dhyana/dharma_swarm/.claude/skills/
```

Aliases are prefixed with `dharma-` to avoid collisions with `gstack`.

Examples:

- `dharma-ceo-review`
- `dharma-eng-review`
- `dharma-preflight-review`
- `dharma-ship`
- `dharma-qa`
- `dharma-browse`
- `dharma-retro`
- `dharma-incident-commander`

## Install for user-level Claude Code

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/install_mode_pack.sh --target user
```

This installs into:

```text
~/.claude/skills/
```

## Runtime mapping

The contract contains aliases for:

- `claude_skill`
- `codex_mode`
- `dgc_lane`
- `openclaw_profile`

That keeps one canonical mode vocabulary while allowing each runtime to expose
its own surface name.

## Design rules

- Modes are explicit and narrow.
- Each mode has required outputs.
- Each mode has escalation triggers.
- Each mode has non-goals.
- Modes are designed to hand off cleanly to the next mode.

The intended sequence is:

```text
ceo-review -> eng-review -> implementation -> preflight-review -> ship -> qa -> retro
```

Incidents route through:

```text
incident-commander -> eng-review / qa / ship
```
