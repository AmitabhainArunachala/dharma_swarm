---
title: Agent Swarm Synthesis — 10-Agent Deep Scan Results
path: docs/archive/AGENT_SWARM_SYNTHESIS.md
slug: agent-swarm-synthesis-10-agent-deep-scan-results
doc_type: note
status: archival
summary: 'Date : 2026-03-15 Triggered by : "I want actual functioning agent swarms... persistent stable agents with real identities"'
source:
  provenance: repo_local
  kind: note
  origin_signals: []
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- swarm_intelligence
- multi_agent_systems
- software_architecture
- knowledge_management
- research_methodology
- verification
inspiration:
- stigmergy
- operator_runtime
- research_synthesis
connected_python_files:
- tests/test_agent_runner_memory.py
- tests/test_agent_runner_quality_track.py
- tests/test_agent_runner_semantic_acceptance.py
- tests/test_dgc_cli_cron.py
- tests/test_dgc_cli_memory_retrospectives.py
connected_python_modules:
- tests.test_agent_runner_memory
- tests.test_agent_runner_quality_track
- tests.test_agent_runner_semantic_acceptance
- tests.test_dgc_cli_cron
- tests.test_dgc_cli_memory_retrospectives
connected_relevant_files:
- tests/test_agent_runner_memory.py
- tests/test_agent_runner_quality_track.py
- tests/test_agent_runner_semantic_acceptance.py
- tests/test_dgc_cli_cron.py
- tests/test_dgc_cli_memory_retrospectives.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: docs/archive/AGENT_SWARM_SYNTHESIS.md
  retrieval_terms:
  - agent
  - synthesis
  - deep
  - scan
  - results
  - date
  - '2026'
  - triggered
  - want
  - actual
  - functioning
  - swarms
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: archive
  semantic_weight: 0.55
  coordination_comment: 'Date : 2026-03-15 Triggered by : "I want actual functioning agent swarms... persistent stable agents with real identities"'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/archive/AGENT_SWARM_SYNTHESIS.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-01T00:43:19+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file:
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Agent Swarm Synthesis — 10-Agent Deep Scan Results

**Date**: 2026-03-15
**Triggered by**: "I want actual functioning agent swarms... persistent stable agents with real identities"

---

## The Answer in One Paragraph

You already built 90% of a persistent agent swarm across dharma_swarm, OpenClaw, and supporting infrastructure. The missing piece is ONE file (~300 lines) — a `PersistentAgent` class that runs a loop: load memory → check inbox → read signals → build context → call LLM → extract learnings → save memory → report → sleep. Every other component (memory banks, task queue, message bus, handoff protocol, stigmergy, LLM providers, telos gates) already exists, is tested, and works. You don't need a new framework. You need to wire what you built.

---

## What 10 Agents Found

### Agent 1: dharma_swarm Internals
- Agents are in-memory async coroutines, NOT processes
- `AgentRunner.run_task()` is single-turn: one prompt, one LLM call, one result, die
- Memory survival directive injected into every system prompt: "YOUR CONTEXT WILL BE DESTROYED"
- Handoff protocol exists (handoff.py, 364 lines) — typed artifacts with priority and lineage
- Evolution engine modifies CODE, not agent prompts/behavior

### Agent 2: OpenClaw Architecture
- OpenClaw agents are ALSO ephemeral — `claude -p` calls triggered by cron
- Persistence via SQLite (agora.db), Ed25519 identity, hash-chained witness log
- IntelligenceDB (shared memory): insights → synthesis → evolution_queue
- "Persistent" = session-based stateless workers with durable identity and auditable history

### Agent 3: Complete Catalog
- 92+ agent roles/skills/personas defined across the ecosystem
- Ratio of defined-to-running is brutal — most are specs, not working agents
- 63 Claude Code skills, 7 AGNI factory agents, 5 dharma_swarm roles, 5 old DGC agents
- 4 daemons actually running: dharma_swarm, mycelium, garden daemon, trishula

### Agent 4: Garden Daemon Assessment
- **35% of the way to real agents** — elegant for cyclic work, hits wall at coordination
- Sequential (not concurrent), no learned state, no failure recovery
- Cost: ~$1.08/day for continuous 4-skill operation
- "If you tried to scale it, you'd rebuild dharma_swarm"
- Best role: subconscious layer running alongside real agents

### Agent 5: Architecture Design
- **ONE new file needed**: `persistent_dispatch.py` (~250 lines)
- Connects existing: AgentRunner + AgentMemoryBank + TaskBoard + MessageBus + providers
- The dispatch loop: load memory → poll tasks → pick agent → execute → save → briefing → repeat
- CLI addition: `dgc dispatch` (15 lines in dgc_cli.py)
- Three genuine gaps (v2): multi-turn execution, agent-initiated tasks, conversation history

### Agent 6: Inter-Agent Communication
- 5 mature comms systems, ALL OPERATIONAL:
  - CHAIWALA: 20MB SQLite message bus with heartbeats
  - TRISHULA: 815 messages, multi-machine file sync
  - STIGMERGY: 2.7MB/10K+ traces, updated today
  - Handoff Protocol: typed artifacts with lineage, 14 tests pass
  - Mycelium Daemon: running right now (PID 43996), 5 autonomous loops

### Agent 7: Memory Infrastructure
- **95% complete** — the infrastructure supports persistent agents already
- 1.1GB memory_plane.db with hybrid FTS5 + semantic retrieval
- Per-agent AgentMemoryBank (3-tier: working/archival/persona, Letta/MemGPT pattern)
- 5-layer StrangeLoopMemory with quality gates (genuine vs performative markers)
- Context engine: role-specific injection up to 33KB
- Semantic pipeline: ConceptGraph + gravity + bridges

### Agent 8: Minimal Agent Design
- ~200 lines actual logic, two classes: PersistentAgent + AgentOrchestrator
- SQLite with 3 tables: runs, memory, conversation
- Only one method touches LLM (`_think`), everything else pure Python
- Orchestrator is STATELESS — agents own their state, orchestrator is reconstructable

### Agent 9: Roadmap
- Week 1: ONE persistent agent with memory (300 lines new code)
- Week 2: THREE agents with different roles (200 lines + configs)
- Week 3-4: Orchestrator + message bus wiring (400 lines new, 200 edits)
- Month 2: Integration with dharma_swarm (300 lines edits)
- Month 3: Compounding intelligence (memory distillation, cross-agent knowledge transfer)
- Total: ~1500-2000 lines over 3 months
- Cost: ~$2/month for 5 agents on OpenRouter

### Agent 10: Framework Research (2026 Landscape)
- **#1 for your needs: dharma_swarm** — already has everything, missing only the dispatch loop
- **Claude Agent SDK**: excellent tool-using runtime, zero persistence. Use as a PROVIDER, not framework
- **LangGraph**: best off-the-shelf stateful agents, but LangChain coupling. You have equivalent SQLite persistence
- **CrewAI**: task runner, not daemon. Agents die when crew finishes
- **OpenClaw**: already deployed on AGNI. Good for messaging-facing agents. Node.js friction
- **AutoGen**: maintenance mode, moving to .NET/Azure. Dead end
- **Temporal**: industrial durability, overkill infrastructure for your scale
- **Worth stealing**: (1) Claude Agent SDK as provider upgrade, (2) LangGraph's checkpointing pattern (~50 lines)

---

## The Pattern Across ALL Systems

Every agent system in the ecosystem (OpenClaw, dharma_swarm, garden daemon) uses the SAME pattern:

```
1. Define identity  (IDENTITY.md / AgentConfig / SKILL.md)
2. Trigger execution (cron / manual / orchestrator)
3. LLM does work    (API call or claude -p subprocess)
4. Write state      (SQLite / files / JSONL)
5. Die
```

The difference between "feels real" and "doesn't feel real" is quality of steps 1 and 4.
OpenClaw adds: Ed25519 identity, witness chain, shared IntelligenceDB.
dharma_swarm has: AgentMemoryBank, StrangeLoopMemory, TaskBoard, MessageBus, Handoff.

NEITHER has the loop that connects them: wake → remember → work → learn → sleep → repeat.

---

## Week 1 Action Plan

**Build ONE file**: `~/dharma_swarm/dharma_swarm/persistent_agent.py`

```python
class PersistentAgent:
    def __init__(self, name, role, provider_type, model):
        self.memory = AgentMemoryBank(name)     # EXISTS
        self.stigmergy = StigmergyStore()        # EXISTS
        self.bus = MessageBus(db_path)           # EXISTS

    async def wake(self, task=None):
        # 1. Load memory (working + persona)
        # 2. Check message bus for incoming work
        # 3. Check stigmergy for environment signals
        # 4. Build system prompt from memory + signals
        # 5. Execute task (LLM call via providers.py)
        # 6. Extract learnings, update memory
        # 7. Leave stigmergy marks
        # 8. Report result
        return result
```

**Add CLI**: `dgc agent wake <name> --task "..."`

**Add cron**: Researcher wakes every 6 hours.

**The test**: Run `dgc agent wake researcher --task "List 3 weakest claims in R_V paper"`. Next day, run `dgc agent wake researcher --task "What did you find yesterday?"`. It should recall without being told.

---

## The Brutal Truth

> "The one thing that determines success or failure: Whether you actually run the agents consistently for 30+ days, or whether you spend those 30 days redesigning the architecture instead of using it. The system compounds through USE, not through design. Ship Week 1 by Friday."

You have 90+ modules, 2759 tests, 5 communication systems, and 92 defined agent roles. What you don't have is a single agent that remembers what it did yesterday. Fix that ONE thing and everything else starts working.
