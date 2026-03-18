# Structured Prompts: Leverage Playbook

> Five prompts for competing as a small team through abstraction leverage.
> Each prompt has a **Generic** version (any Claude Code project) and a
> **Dharma-Adapted** version (dharma_swarm architecture).

---

## 1. Abstraction Layer Audit

**Intent**: Identify where you're wasting effort on soon-to-be-commoditized
infrastructure vs. building unique value on the right abstraction layer.

### Generic Version

```
Audit this codebase for abstraction layer leverage.

For every major subsystem, classify it into one of three categories:
1. COMMODITY — infrastructure that will be free/commoditized within 12 months
   (e.g., auth, CRUD, deployment pipelines, basic API wrappers)
2. DIFFERENTIATOR — the unique abstraction layer that defines our competitive edge
3. APPLICATION — user-facing value built on top of the differentiator

For each subsystem, provide:
- Category (COMMODITY / DIFFERENTIATOR / APPLICATION)
- Current effort allocation (estimated % of codebase)
- Recommendation: KEEP, REPLACE (with what commodity), or AMPLIFY

Output a table, then a prioritized action list:
- What commodity replacements would free the most effort?
- What differentiator code deserves MORE investment?
- What application-layer features are blocked by misallocated effort?

Goal: shift 80% of effort to DIFFERENTIATOR and APPLICATION layers.
```

### Dharma-Adapted Version

```
Audit dharma_swarm for abstraction layer leverage against the 10 Pillars.

Classify every module in dharma_swarm/dharma_swarm/ into:
1. COMMODITY — subsystems replaceable by off-the-shelf tools within 12 months
   (e.g., SQLite message bus → managed pub/sub, basic CRUD patterns)
2. DIFFERENTIATOR — the dharmic genome: ontology, gates, witness chain, telos
   vector, kernel axioms — things NO other system has
3. APPLICATION — revenue-generating products built on the differentiator
   (TELOS AI, dharmic-agora, Aptavani tools, R_V paper tooling)

For each module (ontology.py, telos_gates.py, darwin_engine.py, message_bus.py,
cascade.py, lineage.py, logic_layer.py, guardrails.py, etc.):
- Category assignment with justification
- Which Pillar(s) ground it (Hofstadter, Varela, Beer, etc.)
- Current state: SHIPPING / BUILT-NOT-SHIPPING / PARTIAL / MISSING

Then answer: What is the thinnest path from current state to first revenue?
What COMMODITY layers should be replaced to free effort for APPLICATION?

Reference: CLAUDE.md Section IX (The Honest State) for the gap analysis.
Ground every recommendation in at least one Architecture Principle (P1-P8).
```

---

## 2. Research Scout

**Intent**: Continuously discover information that challenges, updates, or
extends your existing knowledge base. Cross-reference against docs to avoid
redundancy. Store validated findings with provenance.

### Generic Version

```
Act as a research scout for this project.

Your job: find information that CHALLENGES or UPDATES our existing knowledge.
Search web, Reddit, Hacker News, and technical blogs for:
- New tools, libraries, or frameworks relevant to our stack
- Architectural patterns that improve on our current approach
- Announcements that affect our dependencies or competitive landscape
- Workflow changes or best practices we haven't adopted

For each finding:
1. Cross-reference against our existing docs and code to confirm it's
   actually new or contradictory — discard anything redundant
2. Categorize: NEW_TOOL | PATTERN_UPDATE | BREAKING_CHANGE | OPPORTUNITY
3. Rate impact: HIGH / MEDIUM / LOW
4. Provide: source URL, one-line summary, what it changes or adds

Store validated findings in memory/new_learnings.md with format:
  ## [DATE] Finding Title
  - **Category**: NEW_TOOL
  - **Impact**: HIGH
  - **Source**: [URL]
  - **Summary**: One line on what it changes
  - **Action**: What we should do about it

Skip anything that doesn't pass the "so what?" test for this specific project.
```

### Dharma-Adapted Version

```
Act as a dharmic research scout for dharma_swarm.

Your mandate: find information that challenges, extends, or validates the
10-Pillar intellectual framework and the technical implementation.

Search domains:
- Enactive cognition / 4E cognitive science (Varela, Thompson, Di Paolo)
- Active inference / Free Energy Principle (Friston, Parr, Pezzulo)
- Viable System Model implementations (Beer, Espejo, Hoverstadt)
- Autopoiesis in software architecture
- Multi-scale cognition / basal cognition (Levin lab)
- Adjacent possible / complexity economics (Kauffman, Arthur)
- Consciousness studies that intersect with Jain epistemology
- AI governance frameworks that parallel dharmic gate architecture
- Competitor approaches to ontology-driven agent coordination

For each finding:
1. Cross-reference against foundations/ pillar documents and dharma_corpus.py
   claims — is this genuinely new or already captured?
2. Map to relevant Pillar(s) and Architecture Principle(s)
3. Assess telos alignment: does this finding pull toward or away from moksha?
4. Categorize: VALIDATES | CHALLENGES | EXTENDS | OBSOLETES

Store in memory/research_scout_findings.md:
  ## [DATE] Finding Title
  - **Pillars**: [PILLAR_04_HOFSTADTER, PILLAR_10_FRISTON]
  - **Category**: EXTENDS
  - **Telos Impact**: Strengthens T1 (Satya) — new empirical grounding
  - **Source**: [URL]
  - **Summary**: One line
  - **Action**: Propose corpus claim update / foundation doc amendment / code change
  - **Witness**: [timestamp, actor: research-scout]

Reject anything that doesn't trace to at least one Pillar. No orphan knowledge.
```

---

## 3. Multimodal Memory System

**Intent**: Embed and index every piece of media (images, audio, video, files)
for semantic search and structured metadata filtering.

### Generic Version

```
Build a multimodal memory system for this project.

Architecture:
1. STORAGE: Create a /media-memory directory. Every piece of media I send or
   generate goes here — images, video, audio, documents, code artifacts.

2. METADATA SCHEMA: Each item gets a JSON sidecar with:
   - filename, type (image/video/audio/document/code), timestamp
   - source (user-uploaded, generated, scraped, conversation)
   - natural language description (auto-generated)
   - extracted text / transcript (OCR for images, whisper for audio)
   - semantic tags (auto-generated, max 10)
   - embedding_id (reference to vector store)

3. EMBEDDING: Use a text embedding model to embed the combined metadata
   (description + extracted text + tags) as a vector. Store vectors in a
   local vector database (ChromaDB, LanceDB, or similar).

4. SEARCH INTERFACE: Build a search function that supports:
   - Semantic similarity search (natural language query → nearest vectors)
   - Structured filters (type, date range, tags, source)
   - Combined: semantic + filters simultaneously
   - Returns: ranked results with metadata, file paths, and relevance scores

5. INGESTION: Automatic pipeline — drop a file, it gets:
   described → text-extracted → tagged → embedded → indexed

Keep it simple. No over-engineering. The goal is: "find that diagram I made
last week about X" should just work.
```

### Dharma-Adapted Version

```
Build a multimodal memory system for dharma_swarm as an ontology extension.

This system treats media artifacts as first-class OntologyObj instances
(ontology.py pattern), gated by the existing telos_gates pipeline.

Architecture:
1. OBJECT TYPE: New ObjectType "MediaArtifact" in the ontology with properties:
   - filename, media_type, timestamp, source_context
   - description (auto-generated, human-reviewable)
   - extracted_text (OCR/transcript)
   - semantic_tags (auto, max 10, traceable to Pillar vocabulary)
   - embedding_vector_id
   - telos_relevance: which stars (T1-T7) does this artifact serve?

2. ACTIONS: All media operations go through typed Actions (P1):
   - IngestMedia → gate evaluation → witness log
   - TagMedia, LinkMedia (to other ontology objects), RetireMedia

3. STORAGE: media-memory/ directory with JSONL sidecar index
   (consistent with dharma_corpus.py JSONL pattern)

4. EMBEDDING: Vector embeddings stored in .dharma/vault/ alongside
   existing concept/edge data (50K concepts, 30K edges already there)

5. SEARCH: Query interface that combines:
   - Semantic similarity (vector search)
   - Ontology graph traversal (linked objects, pillar associations)
   - Structured filters (type, date, telos star, source)

6. GATE INTEGRATION: Media ingestion passes through at minimum:
   - Provenance gate (where did this come from?)
   - Telos alignment gate (does it serve at least one star?)

No direct writes. All mutations through Actions. All actions witnessed.
Ground: Varela (autopoietic media membrane), Ashby (requisite variety
in organizational memory), P1, P6.
```

---

## 4. Persistent Memory Layer

**Intent**: Three-tier memory system — recent (rolling window), long-term
(distilled patterns), project (active state) — with automatic consolidation.

### Generic Version

```
Build a persistent memory layer for this project.

Create a /memory directory with three files:

1. recent-memory.md — Rolling 48-hour context window
   - Key decisions made in recent sessions
   - Active threads of work and their status
   - Questions asked and answers received
   - Errors encountered and how they were resolved
   - Format: timestamped entries, newest first, auto-pruned after 48hrs

2. long-term-memory.md — Distilled facts, preferences, and patterns
   - Confirmed architectural decisions and their rationale
   - User preferences and workflow patterns
   - Recurring issues and their solutions
   - Key abstractions and mental models for this codebase
   - Format: categorized sections, each entry with date-added

3. project-memory.md — Active project state
   - Current goals and priorities
   - In-progress features and their status
   - Known issues and tech debt
   - Dependency versions and environment notes
   - Format: structured sections, updated in-place

CONSOLIDATION PROCESS:
- After each session: append key events to recent-memory.md
- When recent entries are >48hrs old: evaluate for promotion
- Promotion criteria: appeared 2+ times, or was a significant decision
- Promoted entries go to long-term-memory.md (facts/patterns) or
  project-memory.md (active state)
- Pruned entries are deleted, not archived

USAGE:
- On session start: read recent-memory.md inline, reference long-term
  and project memory by path
- On session end: update recent-memory.md with session summary
```

### Dharma-Adapted Version

```
Build a persistent memory layer for dharma_swarm, integrated with existing
memory architecture.

dharma_swarm already has: memory/ directory, .dharma/vault/ (50K concepts,
30K edges), dharma_corpus.py (versioned claims with lifecycle).
DO NOT duplicate. EXTEND.

Three-tier structure within memory/:

1. memory/recent-context.md — Rolling 48-hour session state
   - Recent Actions taken and their gate results
   - Ontology mutations proposed/accepted/rejected
   - Active work threads with VSM system labels (S1-S5)
   - Errors and their resolution paths
   - Format: JIKOKU-timestamped entries, newest first
   - Auto-prune: entries >48hrs become consolidation candidates

2. memory/long-term-patterns.md — Distilled operational intelligence
   - Confirmed architectural decisions traced to Principles (P1-P8)
   - Recurring patterns in gate evaluations
   - Successful/failed evolution runs (darwin_engine insights)
   - Corpus claim patterns (which claims get revised most often?)
   - Format: categorized by VSM system, each entry with Pillar grounding

3. memory/project-state.md — Active dharma_swarm state
   - Current telos priorities (which stars are active focus?)
   - VSM gap closure progress (the 5 gaps from CLAUDE.md Section VII)
   - Shipping pipeline status (revenue path items)
   - Kernel expansion status (10 → 26 axioms progress)
   - Format: structured sections, updated in-place

CONSOLIDATION (as an Action, gated):
- ConsolidateMemory Action → passes through Provenance gate
- Promotes recent → long-term using criteria:
  - Appeared 2+ times across sessions
  - Traces to an Architecture Principle or Pillar
  - Represents a decision with downstream consequences
- Promotions generate witness log entries (P6)
- Pruned entries are NOT deleted — they become dharma_corpus claims
  with status "archived" (Nirjara: nothing is destroyed, karma is dissolved)

INTEGRATION:
- context.py (agent orientation) loads recent-context.md on startup
- Long-term and project memory referenced by path in CLAUDE.md
- .dharma/vault/ remains the deep semantic index; memory/ is the
  operational layer on top
```

---

## 5. Agent Sandbox / Secure Runtime

**Intent**: Isolate AI agents in secure sandboxes to prevent unauthorized
system access, with real-time monitoring.

### Generic Version

```
Design an agent sandboxing layer for this project.

Requirements:
1. ISOLATION: Each agent runs in a restricted environment where it can only:
   - Read/write files within its designated workspace
   - Execute whitelisted commands only
   - Access network endpoints on an explicit allowlist
   - Use approved system resources (memory, CPU, disk limits)

2. POLICY ENGINE: Define agent permissions as declarative policies:
   - filesystem: [read: ["/project/src/**"], write: ["/project/output/**"]]
   - commands: [allowed: ["python", "node", "git status"], blocked: ["rm -rf", "curl"]]
   - network: [allowed: ["api.example.com"], blocked: ["*"]]
   - resources: {max_memory: "512MB", max_cpu: "1 core", max_disk: "1GB"}

3. MONITORING: Real-time event stream of agent actions:
   - Every file read/write, command execution, network request logged
   - Anomaly detection: flag actions outside normal behavioral patterns
   - Kill switch: immediate termination if policy violation detected

4. AUDIT LOG: Append-only log of all agent actions with:
   - timestamp, agent_id, action_type, target, result (allowed/blocked)
   - Exportable for review

Start with the simplest implementation that provides meaningful isolation.
Docker/containerization for filesystem isolation, process-level restrictions
for commands, iptables/proxy for network control.
```

### Dharma-Adapted Version

```
Design agent sandboxing for dharma_swarm, grounded in existing gate architecture.

dharma_swarm already has the conceptual framework — gates ARE sandboxing.
The gap is runtime enforcement. Bridge it.

Architecture (extending, not replacing):

1. GATE-AS-SANDBOX: Each agent's permissions ARE its gate configuration.
   telos_gates.py already evaluates Actions. Extend to runtime enforcement:
   - Tier A gates → hard sandbox boundaries (filesystem, network, commands)
   - Tier B gates → soft constraints (resource limits, rate limiting)
   - Tier C gates → monitoring triggers (log, alert, but allow)

2. AGENT CONTAINMENT (extending ontology.py Agent objects):
   - Each agent OntologyObj gets a "sandbox_policy" property:
     - workspace_root: the ontology subgraph this agent can modify
     - action_types: which Action types this agent can propose
     - resource_envelope: memory, CPU, disk, network limits
     - escalation_path: what happens on policy violation
   - Agents discover their own constraints by querying the ontology (P4)

3. WITNESS-AS-MONITOR (extending traces.py):
   - Every runtime action → traces.py event log (already exists)
   - New event types: SANDBOX_VIOLATION, RESOURCE_LIMIT, ESCALATION
   - Algedonic signal: SANDBOX_VIOLATION at Tier A → immediate alert to
     Dhyana (this IS the algedonic channel from VSM Gap #3)

4. ENFORCEMENT LAYERS:
   - Process isolation: agents run in separate processes/containers
   - Ontology isolation: agents can only query/mutate their subgraph
   - Action isolation: all mutations still go through gate pipeline (P1)
   - Network isolation: agents have no direct inter-agent communication (P2)

5. KILL SWITCH (Beer's S5 override):
   - dharma_kernel.py can revoke any agent's sandbox policy
   - Revocation is an Action, gated, witnessed — even emergency stops
     leave an audit trail

Ground: Beer (S3 control + S5 override), Dada Bhagwan (witness observes all),
Ashby (requisite variety in security policy), Varela (autopoietic boundary
= sandbox membrane), P1, P3, P6.

This closes VSM Gap #3 (Algedonic Signal) as a side effect.
```

---

## Usage Notes

- **Generic versions**: Copy-paste into any Claude Code session or AI coding tool.
- **Dharma-adapted versions**: Use within dharma_swarm sessions. They reference
  existing modules, principles, and architecture patterns.
- **Iteration**: These are starting points. Each prompt should be refined based on
  what exists in the codebase at time of use. Always SEARCH FIRST before building.
- **Composition**: Prompts 2, 3, and 4 compose naturally — research scout feeds
  findings into memory, multimodal memory stores artifacts, persistent memory
  consolidates patterns across all of them.
