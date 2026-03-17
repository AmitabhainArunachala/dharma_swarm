# Context Agent Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-time autonomous context agent that serves as the ecosystem's nervous system — monitoring, distilling, cross-pollinating, and pre-assembling context for all agents and sessions.

**Architecture:** Two-layer agent: (1) NervousSystem (pure Python, always on, 60s cadence) handles file watching, freshness scoring, package assembly. (2) Intelligence (Ollama Cloud, event-driven) handles distillation, cross-pollination, question generation, and dream-mode speculation. Runs as 6th loop in orchestrate-live.

**Tech Stack:** Python 3.11+, watchdog 6.0.0, dharma_swarm providers (Ollama Cloud), signal_bus, stigmergy, asyncio

---

## Task 1: Core Context Agent Module

**Files:**
- Create: `dharma_swarm/dharma_swarm/context_agent.py`
- Test: `dharma_swarm/tests/test_context_agent.py`

### Subtasks:

- [ ] Write ContextAgent class with NervousSystem + Intelligence layers
- [ ] Implement `sense()` — scan all 11 tiers, compute freshness scores
- [ ] Implement `assess_health()` — context health score formula
- [ ] Implement `distill_notes()` — compress agent notes >50KB via Ollama Cloud
- [ ] Implement `cross_pollinate()` — detect connections across agent notes, write bridge notes
- [ ] Implement `generate_questions()` — extract latent inquiries from patterns
- [ ] Implement `dream()` — speculative juxtaposition during quiet hours
- [ ] Implement `prepare_packages()` — pre-assemble context per recipe
- [ ] Implement `run_cycle()` — main loop entry point
- [ ] Write tests for each method
- [ ] Commit

## Task 2: Orchestrator Integration

**Files:**
- Modify: `dharma_swarm/dharma_swarm/orchestrate_live.py:414-421`

- [ ] Add `run_context_agent_loop()` async function
- [ ] Add as 6th task in orchestrate()
- [ ] Add DGC_CONTEXT_AGENT_INTERVAL env var (default 180s)
- [ ] Test daemon startup with context agent
- [ ] Commit

## Task 3: Recognition Engine Integration

**Files:**
- Modify: `dharma_swarm/dharma_swarm/meta_daemon.py`

- [ ] Add `_read_context_health()` signal source
- [ ] Add context health section to `_build_seed()`
- [ ] Test seed generation includes context health
- [ ] Commit

## Task 4: Context.py Distilled Notes

**Files:**
- Modify: `dharma_swarm/dharma_swarm/context.py`

- [ ] Update `read_agent_notes()` to prefer distilled versions when available
- [ ] Fall back to raw notes (tail) if distilled not available
- [ ] Test both paths
- [ ] Commit

## Task 5: Update Context Engineer Skill

**Files:**
- Modify: `~/.claude/skills/context-engineer/SKILL.md`

- [ ] Add section on pre-assembled packages
- [ ] Update session-start recipe to check packages/ first
- [ ] Document bridge notes and latent inquiries as context sources
- [ ] Commit
