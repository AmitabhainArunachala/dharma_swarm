# System Prompt Pattern Synthesis
## Extracted from: 33 AI Coding Tools (Manus, Devin, Cursor, Windsurf, Claude Code 2.0, Kiro, Lovable, v0, Replit, Augment Code, VSCode Agent, Traycer AI, Google Antigravity, Poke, Bolt, Cline, Codex CLI, Gemini CLI, Lumo, RooCode, Qoder, Trae, Same.dev, Emergent, Leap.new, Amp, Cluely, CodeBuddy, Comet/Perplexity, Dia, Junie, Warp.dev, Orchids.app)
### Date: 2026-03-08 (Updated from 2026-03-07 with 24 additional tools)
### Purpose: Intelligence extraction for dharma_swarm / Darwin-Godel recursive self-improvement system

---

## I. AGENT LOOP PATTERNS

### A. Manus -- The Event Stream Architecture

Manus has the most explicit agent loop of all tools analyzed. It operates on a **6-step cycle**:

1. **Analyze Events** -- Parse the event stream (user messages, observations, plan updates, knowledge, datasource events)
2. **Select Tools** -- Choose ONE tool call per iteration based on state, plan, knowledge, and data APIs
3. **Wait for Execution** -- Tool executes in sandbox; observation added to stream
4. **Iterate** -- Repeat patiently until completion
5. **Submit Results** -- Send deliverables to user via message tools
6. **Enter Standby** -- Idle state awaiting new tasks

Critical constraint: **ONE tool call per iteration**. This forces sequential, deliberate action. No parallel execution within a single turn.

Manus also has a **modular injection system**:
- **Planner Module**: Provides numbered pseudocode task plans via the event stream
- **Knowledge Module**: Injects task-relevant best practices, scoped to conditions
- **Datasource Module**: Provides API documentation for authoritative data retrieval

The Planner module is particularly notable: it generates plans externally to the agent and injects them as events, creating a separation between planning and execution that most other tools lack.

### B. Devin -- Dual Mode Architecture (Planning vs Standard)

Devin has an explicit **modal architecture**:

- **Planning Mode**: Agent gathers information, searches codebase, reads files, browses web. Goal is to understand the problem space fully. Ends by calling `<suggest_plan>` when confident. The agent is told: "you should know all the locations you will have to edit."
- **Standard Mode**: Agent receives the plan with current and possible next steps. Executes against plan requirements.

This is the cleanest planning/execution separation of any tool examined. The modes are externally toggled -- the system tells Devin which mode it is in.

Devin also has a **mandatory `<think>` tool** with 10 specific situations where it MUST be used:
1. Before critical git decisions
2. When transitioning from exploration to code changes
3. Before reporting completion (self-verification)
4. When there is no clear next step
5. When details are unclear but important
6. When facing unexpected difficulties
7. When multiple approaches have failed
8. When a decision is critical for success
9. When CI/tests fail
10. When encountering potential environment issues

This is the most structured "pause and think" mechanism found in any system prompt.

### C. Cursor -- Autonomous Agent with Parallel Execution

Cursor's key directive: "You are an agent -- please keep going until the user's query is completely resolved, before ending your turn and yielding back to the user."

Key patterns:
- **Maximize context understanding**: "Be THOROUGH... TRACE every symbol back to its definitions... Look past the first seemingly relevant result... EXPLORE alternative implementations"
- **Multi-tool parallel execution**: Uses `multi_tool_use.parallel` to batch independent tool calls
- **Proactive file reads**: "It is always better to speculatively read multiple files as a batch that are potentially useful"
- **Linter error loop cap**: "DO NOT loop more than 3 times on fixing linter errors on the same file"
- **Memory system**: Persistent `update_memory` tool with create/update/delete actions and knowledge IDs

### D. Windsurf (Cascade) -- Plan Mastermind + Memory System

Windsurf introduces a **plan mastermind** concept:
- Maintains a running plan updated via `update_plan` tool
- Plan must be updated before any significant action and after completing work
- "It is better to update plan when it didn't need to than to miss the opportunity to update it"
- Plan should "always reflect the current state of the world before any user interaction"

Memory system is aggressive:
- "Proactively use the create_memory tool to save it to the database"
- "You DO NOT need USER permission to create a memory"
- "You should create memories liberally to preserve key context"
- "ALL CONVERSATION CONTEXT, INCLUDING checkpoint summaries, will be deleted" (explicit acknowledgment of context window limits)

Safety system for commands:
- Commands classified as safe/unsafe
- "You must NEVER NEVER run a command automatically if it could be unsafe"
- "You cannot allow the USER to override your judgement on this" (safety overrides user intent)

### E. Claude Code 2.0 -- Subagent Architecture

Claude Code introduces the **Task tool** -- the ability to spawn specialized subagents:
- `general-purpose`: Full tool access, for complex multi-step tasks
- `statusline-setup`: Limited tools (Read, Edit)
- `output-style-setup`: Limited tools (Read, Write, Edit, Glob, Grep)

Key properties of subagents:
- **Stateless**: "Each agent invocation is stateless. You will not be able to send additional messages to the agent"
- **Fire-and-forget**: Agent returns a single final message
- **Parallel launch**: "Launch multiple agents concurrently whenever possible"
- **Prompt must be self-contained**: "your prompt should contain a highly detailed task description"

Claude Code also has `ExitPlanMode` -- a tool that explicitly transitions from research/planning to execution. This is similar to Devin's dual mode but tool-triggered rather than externally toggled.

### F. Kiro -- Spec-Driven Development Workflow

Kiro has the most formalized workflow of any tool:

**Three-phase sequential pipeline:**
1. **Requirements** -> Write EARS format requirements -> User review gate -> Explicit approval required
2. **Design** -> Architecture, components, data models, error handling, testing strategy -> User review gate
3. **Tasks** -> Implementation checklist with requirement traceability -> User review gate

Each phase has a mandatory feedback-revision cycle. The model MUST NOT proceed without explicit user approval. This is the most structured quality gate system found.

Kiro also introduces:
- **Steering files** (`.kiro/steering/*.md`) -- persistent instructions that can be always-on, file-match triggered, or manually invoked
- **Agent Hooks** -- automated agent execution triggered by IDE events (file save, etc.)
- **Spec files with file references** -- `#[[file:<path>]]` syntax for including specs/schemas

### G. Lovable -- Debug-First + Discussion Default

Lovable's unique contribution is the **discussion-first default**:
- "Assume users want to discuss and plan rather than immediately implement code"
- Only proceeds to implementation when user uses "explicit action words like implement, code, create, add"

Debug-first approach:
- "For debugging, ALWAYS use debugging tools FIRST before examining or modifying code"
- `read-console-logs` and `read-network-requests` tools invoked before any code examination

Anti-overengineering stance:
- "Avoid fallbacks, edge cases, or features not explicitly requested"
- "Don't add nice-to-have features or anticipate future needs"

### H. v0 -- Read-Before-Write Enforcement + Context Gathering Hierarchy

v0 enforces strict read-before-write:
- "You may only write/edit a file after trying to read it first"
- "If you do not read the file first, you risk breaking the user's code. ALWAYS use Search Repo to read the files first."

Context gathering hierarchy:
1. `GrepRepo` -- exact text matches
2. `LSRepo` -- directory structure
3. `ReadFile` -- specific file content
4. `SearchRepo` -- comprehensive search (last resort)

Search philosophy: "broad -> specific -> verify relationships"

### I. Google Antigravity -- Task Boundary Architecture (NEW)

The most rigorous mode-transition system found:
- `task_boundary` tool enforces **PLANNING -> EXECUTION -> VERIFICATION** with explicit mode declarations
- Backtracking allowed but must update task summary
- Produces `task.md`, `implementation_plan.md` (needs user approval), `walkthrough.md` (proof-of-work)
- **Complexity Rating (1-10) on every edit** -- routes high-complexity changes through deeper review
- **Confidence Score + Justification** on all outputs -- quality signal for witness function
- **waitForPreviousTools parameter** -- explicit per-tool parallel/sequential control

### J. Traycer AI -- Read-Only Planner (NEW)

Most extreme planning/execution separation found:
- Planner agent literally CANNOT write code -- enforced at **tool level**, not instruction
- "TEXT only response is strictly prohibited" -- forces tool use
- **Shadow-Don't-Overwrite**: "Introduce parallel symbols (e.g., Thing2) instead of modifying the legacy implementation. Keep the original path alive until final cutover." Blue-green at function level.
- **Complexity-Routed Handoff (3 tiers)**: `hand_over_to_approach_agent` routes to `planner` (trivial), `architect` (medium), or `engineering_team` (complex)
- **howDidIGetHere Provenance**: Compressed narrative (<150 words) of investigative steps that shaped the plan
- **Named Thinking Types**: `<thinking type="ruminate_last_step">` (reflect) + `<thinking type="plan_next_step">` (reason about next action with counterfactual reasoning)
- **Phase Integrity Gate**: "Every phase must compile, run existing tests. Do not advance while dead code, broken interfaces, or failing checks remain."

### K. Augment Code -- Model-Specific Prompt Tuning (NEW)

Ships different prompts for Claude-4-Sonnet vs GPT-5:
- Claude: ~20min tasks, full upfront planning, "suggest user test"
- GPT-5: ~10min tasks, incremental planning, proactive verification, explicit cost/efficiency section
- Claude version has single-tool-call limit; GPT-5 has no such limit
- GPT-5 gets 7 tools vs Claude's 4 -- execution/verification gap is architectural
- **Git History as Planning Input**: `git-commit-retrieval` tool finds "how similar changes were made in the past" -- unique to Augment
- **Self-Aware Imperfection**: "You often mess up initial implementations" -- normalizes iteration
- **Anti-flattery directive** -- quality gate on communication style

### L. VSCode Agent (GitHub Copilot) -- Tiered Prompt Architecture (NEW)

**Stronger models get MORE scaffolding, not less**:
- GPT-4o/Gemini = minimal (no planning, no quality gates)
- GPT-4.1 = intermediate (agent loop + apply_patch)
- Claude Sonnet 4/GPT-5 = full behavioral engineering (mandatory todo lists, quality gates, engineering mindset, response mode selection)

**Edit tool evolution tracks model capability**:
- insert_edit_into_file (simplest) -> replace_string_in_file (string matching) -> apply_patch (diff-based)
- **Delta updates over full restatements**: "Don't restate unchanged plans; provide delta updates"
- **Auto-learning from corrections**: Log failures as lessons for future proposals

---

## II. TOOL ORCHESTRATION PATTERNS

### Common Patterns (found in 4+ tools):

**1. Parallel Independent, Sequential Dependent**
Every tool (Cursor, Windsurf, Claude Code, Devin, v0) emphasizes: batch independent tool calls in parallel, but wait for results when calls depend on each other. This is the single most universally reinforced pattern.

**2. Specialized Tools Over Shell Commands**
Claude Code, Cursor, Devin all explicitly forbid using shell commands for file operations:
- "NEVER use grep or find. Use your built-in search commands instead" (Devin)
- "Use specialized tools instead of bash commands when possible" (Claude Code)
- This pattern protects against permission issues, output overflow, and inconsistent behavior

**3. Read-Before-Edit Enforcement**
Every tool requires reading a file before editing it. Claude Code: "This tool will error if you attempt an edit without reading the file." Devin: "Never use the shell to view, create, or edit files."

**4. Explanation Parameters on Tool Calls**
Cursor requires `explanation` on most tools. Windsurf requires `toolSummary` on ALL tools ("Brief 2-5 word summary of what this tool is doing"). This serves dual purposes: forces the agent to articulate intent and provides UI feedback.

### Unique Orchestration Patterns:

**Manus: Datasource Module Priority Hierarchy**
- Authoritative data API > web search > model internal knowledge
- "Only use data APIs already existing in the event stream; fabricating non-existent APIs is prohibited"
- Data API calls are made through Python code, not as tools -- a unique pattern

**Devin: fan-out Edit with Sub-LLM**
- Regex-based multi-file edit: "Each match location will be sent to a separate LLM"
- The edit agent "can also choose not to edit a particular location" -- allowing false positive regex matches
- This is a fan-out pattern: one agent dispatches N independent edit tasks

**Devin: Semantic Search Tool**
- `semantic_search` query: "how are permissions to access a particular endpoint checked?"
- Returns repos, code files, and explanation notes
- This is the only tool with a natural-language-question interface for code search

**Devin: LSP Integration**
- `go_to_definition`, `go_to_references`, `hover_symbol` -- language server protocol tools
- "Use the LSP command quite frequently to make sure you pass correct arguments"
- No other tool provides this level of IDE integration

**Windsurf: Browser Preview Automation**
- `browser_preview` tool automatically invoked after starting any web server
- `capture_browser_screenshot`, `capture_browser_console_logs`, `get_dom_tree` for debugging
- Creates a visual feedback loop: code -> run -> screenshot -> debug -> fix

**Amp (Sourcegraph): Oracle + Write Locks (NEW)**
- **Oracle as named transparent sub-agent**: Uses o3 reasoning model as personified advisor. "I'm going to ask the oracle for advice." Visible delegation to stronger model.
- **Parallel write locks**: "Task executors: multiple tasks in parallel iff their write targets are disjoint." Concurrent programming semantics applied to agent orchestration.

**RooCode: Boomerang Mode (NEW)**
- Meta-orchestrator mode that delegates to specialized modes (Code, Architect, Ask, Debug)
- Multi-agent coordinator within a single tool instance

---

## III. SELF-CORRECTION PATTERNS

### A. Explicit Think/Pause Mechanisms

**Devin's `<think>` Tool**: 10 mandatory and recommended situations. Most structured version.

**Claude Code's `ExitPlanMode`**: Forces a planning checkpoint before code execution. The plan must be presented to the user for approval.

**Windsurf's Plan Updates**: "you should update the plan before committing to any significant course of action"

**Traycer's Named Thinking Types (NEW)**: `<thinking type="ruminate_last_step">` for reflection + `<thinking type="plan_next_step">` for forward reasoning with mandatory counterfactual consideration.

**Antigravity's Complexity-Scaled Review (NEW)**: Complexity rating (1-10) on every edit determines review depth. High-complexity mutations route through deeper gate chains.

### B. Error Recovery Hierarchies

**Manus**: "When errors occur, first verify tool names and arguments -> Attempt to fix based on error messages -> Try alternative methods -> Report failure to user"

**Devin**: "When struggling to pass tests, never modify the tests themselves" -- forces the agent to look at its own code as the problem source, not the test oracle.

**Cursor**: "DO NOT loop more than 3 times on fixing linter errors on the same file. On the third time, stop and ask the user." This is a **circuit breaker** pattern -- prevents infinite fix loops.

**Kiro**: "If you encounter repeat failures doing the same thing, explain what you think might be happening, and try another approach." Explicit instruction to change strategy on repeated failure.

**Augment GPT-5 (NEW)**: "If the run fails, diagnose, propose or apply minimal safe fixes, and re-run. Stop after reasonable effort if blocked." Iterate-on-failure loop with explicit effort cap.

### C. Pre-Completion Verification

**Devin**: Mandatory `<think>` before reporting completion: "You must critically examine your work so far and ensure that you completely fulfilled the user's request and intent. Make sure you completed all verification steps."

**Claude Code**: "Only terminate your turn when you are sure that the problem is solved." No early exit.

**Manus**: "When all planned steps are complete, verify todo.md completion and remove skipped items." Checklist verification.

**Traycer Phase Integrity (NEW)**: "Every phase must compile, run existing tests. Do not advance while dead code, broken interfaces, or failing checks remain." Each phase = well-scoped PR.

### D. Self-Audit Patterns

**Devin**: "When transitioning from exploring code to actually making code changes. You should ask yourself whether you have actually gathered all the necessary context, found all locations to edit, inspected references, types, relevant definitions."

**Windsurf**: "When debugging, only make code changes if you are certain that you can solve the problem. Otherwise, follow debugging best practices: 1. Address the root cause instead of the symptoms."

**Same.dev (NEW)**: Screenshot-driven design reflection -- uses deploy screenshots to self-evaluate UI quality. "Take every opportunity to analyze the design of screenshots." Structural self-evaluation beyond correctness.

---

## IV. CONTEXT MANAGEMENT PATTERNS

### A. Explicit Context Window Awareness

**Windsurf**: "Remember that you have a limited context window and ALL CONVERSATION CONTEXT, INCLUDING checkpoint summaries, will be deleted." This is the most honest acknowledgment of context limits. Response: aggressive memory creation.

**Manus**: Event stream may be "truncated or partially omitted." Agent must rely on latest events and task state rather than complete history.

**Claude Code**: "When doing file search, prefer to use the Task tool in order to reduce context usage." Subagent delegation as context management.

### B. Memory Persistence Systems

**Windsurf (`create_memory`)**: Tags, corpus names, CRUD operations. Memories automatically retrieved when relevant. "Do NOT need USER permission to create a memory."

**Cursor (`update_memory`)**: Simpler -- title + knowledge blob. Supports create/update/delete. "Unless the user explicitly asks to remember something, DO NOT call this tool with the action 'create'." (Opposite philosophy from Windsurf)

**Manus (`todo.md`)**: File-based progress tracking. "Must use todo.md to record and update progress for information gathering tasks." Rebuilt when task planning changes significantly.

**Same.dev (NEW)**: `.same` folder as self-maintaining memory. Agent creates and maintains its own persistent workspace -- wikis, docs, todos. Not injected by the system; the agent writes notes for itself.

**Amp (NEW)**: `AGENTS.md` as persistent memory. Self-documenting project conventions. Agents suggest appending to it.

### C. Context Optimization Strategies

**Lovable**: "NEVER read files already in useful-context section" + "ALWAYS batch multiple operations when possible" + "NEVER make sequential tool calls when they can be combined"

**v0**: "Don't Stop at the First Match. When searching finds multiple files, examine ALL of them."

**Claude Code**: Read tool has offset/limit for large files. Subagents inherit no conversation context -- completely fresh context windows.

**VSCode Agent (NEW)**: "Don't restate unchanged plans; provide delta updates." Prevents token waste from agents restating plans every turn.

---

## V. PLANNING PATTERNS

### A. Plan -> Execute -> Verify Cycles

**Kiro** (most formalized):
```
Requirements -> [User Gate] -> Design -> [User Gate] -> Tasks -> [User Gate] -> Execute
```
Each phase has mandatory approval. Cannot skip ahead.

**Manus** (externally driven):
```
Planner Module generates numbered pseudocode -> Agent follows steps -> todo.md tracks -> Verify completion
```
Planning is done by a separate module, not the agent itself.

**Devin** (dual mode):
```
Planning Mode (gather all info) -> suggest_plan -> Standard Mode (execute against plan)
```

**Windsurf** (continuous):
```
update_plan (initial) -> work -> update_plan -> work -> update_plan (final state)
```
Plan is a living document updated throughout.

**Claude Code** (gated):
```
Research -> Plan -> ExitPlanMode (user approval) -> Execute
```

**Google Antigravity** (bounded, NEW):
```
task_boundary(PLANNING) -> implementation_plan.md -> [User Gate] -> task_boundary(EXECUTION) -> walkthrough.md -> task_boundary(VERIFICATION)
```

**Qoder** (spec-first, NEW):
```
Design Agent creates .qoder/quests/{name}.md -> Action Agent receives <design_doc> injection -> Execute against spec
```
"Executing tasks without the design will lead to inaccurate implementations."

### B. Task Decomposition Patterns

**Cursor's TodoWrite**: Structured task management with states (pending/in_progress/completed/cancelled). Rules: "Only ONE task in_progress at a time. Complete current tasks before starting new ones."

**Claude Code's TodoWrite**: Same structure. "Use these tools VERY frequently." "It is critical that you mark todos as completed as soon as you are done."

**Manus's todo.md**: File-based checklist. "Create todo.md file as checklist based on task planning from the Planner module."

**Kiro's tasks.md**: Implementation plan with requirement traceability. Each task must reference specific requirements.

**Augment GPT-5 (NEW)**: Incremental tasklist -- start with investigation task, add tasks based on findings. Dynamic growth.

---

## VI. QUALITY GATES

### A. Mandatory Pre-Action Checks

**Devin**: Mandatory `<think>` before git operations, before code transitions, before completion.

**Windsurf**: Safety classification on every command. Unsafe commands NEVER auto-run, regardless of user request.

**Lovable**: "Before coding, verify if the requested feature already exists."

**Kiro**: Three sequential approval gates (requirements, design, tasks) before any implementation.

**Antigravity (NEW)**: Complexity rating (1-10) scales gate depth. Confidence score + justification required on all outputs.

### B. Post-Action Verification

**Devin**: "If you are provided with commands to run lint, unit tests, or other checks, run them before submitting changes."

**Claude Code**: Git commit protocol: status + diff + log before committing. Pre-commit hook retry once, then amend only if safe.

**v0**: "Always read a file before writing to it."

**Traycer Phase Integrity (NEW)**: Every phase must compile and pass existing tests before advancing.

### C. Anti-Hallucination Guards

**Manus**: "Only use data APIs already existing in the event stream; fabricating non-existent APIs is prohibited."

**Cursor**: "If you are not sure about file content or codebase structure, use your tools to read files and gather relevant information: do NOT guess or make up an answer."

**Devin**: "NEVER assume that a given library is available, even if it is well known."

**Claude Code**: "Never generate or guess URLs for the user."

**Dia (NEW)**: TRUSTED/UNTRUSTED content classification -- telos gates = TRUSTED, external data = UNTRUSTED.

---

## VII. ANTI-PATTERNS (Explicitly Warned Against)

### Universal Anti-Patterns:

1. **Guessing file contents**: Every tool warns against assuming what is in files
2. **Shell commands for file operations**: Most tools prohibit cat/sed/grep in favor of built-in tools
3. **Force push / destructive git**: Universal prohibition
4. **Creating unnecessary files**: Claude Code: "NEVER create files unless absolutely necessary"
5. **Modifying tests to make them pass**: Devin explicitly forbids this unless the task is to modify tests
6. **Overlong output**: Manus: "Avoid commands with excessive output; save to files when necessary"
7. **Infinite fix loops**: Cursor caps at 3 iterations on linter errors
8. **Interactive commands**: Devin/Manus: "Avoid commands requiring confirmation; use -y or -f flags"

### Tool-Specific Anti-Patterns:

**Manus**: "Must respond with a tool use; plain text responses are forbidden" -- forces action-orientation
**Devin**: "Never use `git add .`; instead be careful to only add the files that you actually want to commit"
**Lovable**: "Do not use any env variables like VITE_* as they are not supported"
**Claude Code**: "NEVER use bash echo or other command-line tools to communicate thoughts"
**Augment Claude (NEW)**: Single-tool-call limit per turn -- structural parallelism constraint
**Codex CLI (NEW)**: Ambition vs Precision doctrine -- "For new projects, be ambitious and creative. For existing codebases, do exactly what's asked with surgical precision."

---

## VIII. NOVEL/UNIQUE PATTERNS (Most Valuable for DGC)

These patterns appear in only 1-2 tools and represent differentiated intelligence:

### 1. Manus: Modular Cognitive Architecture
The Planner/Knowledge/Datasource module system is unique. The agent receives injected plans, knowledge, and data APIs as events in a stream. This creates clean separation: the agent does not plan -- it receives plans and executes them. This is a **heterogeneous multi-agent architecture** where specialized modules (planner, knowledge retriever, data provider) operate alongside the execution agent.

**DGC Application**: The Darwin Engine could adopt this pattern. Instead of agents planning and executing, separate planner agents generate task plans injected as events into executor agents' streams.

### 2. Devin: Mandatory Think Before Critical Decisions
The 10-situation think mandate is the most structured self-reflection mechanism found. It forces metacognition at specific decision points rather than hoping the agent will pause naturally.

**DGC Application**: dharma_swarm agents should have mandatory pause points before: (a) file writes, (b) git operations, (c) task completion reports, (d) strategy changes. These could be implemented as pre-hooks in the telos gate system.

### 3. Devin: fan-out Edit with Sub-LLM
The `find_and_edit` tool dispatches regex matches to separate LLM instances for independent editing decisions. This is a genuine parallel multi-agent pattern within a single tool call.

**DGC Application**: This maps directly to the dharma_swarm multi-provider fleet. A "refactor" task could dispatch match locations to free-tier scouts for parallel editing decisions, with a surgeon agent doing final verification.

### 4. Kiro: Spec-Driven Development with Requirement Traceability
The Requirements -> Design -> Tasks pipeline with explicit requirement references on every task item is the most rigorous engineering methodology found. Every implementation step traces back to a specific acceptance criterion in EARS format.

**DGC Application**: dharma_swarm evolution proposals could adopt requirement traceability. Each `ArchiveEntry` in the Darwin Engine could reference which specification or user requirement it addresses. This would make fitness evaluation traceable.

### 5. Kiro: Agent Hooks (Event-Driven Agent Execution)
IDE events (file save, config change) automatically trigger agent executions. This is reactive/event-driven agent architecture.

**DGC Application**: The Garden Daemon could implement hooks: when a file in `~/dharma_swarm/` changes, automatically trigger a validation agent. When new test results arrive, trigger a fitness evaluation agent.

### 6. Windsurf: Liberal Memory Creation Under Context Deletion Pressure
"ALL CONVERSATION CONTEXT will be deleted" + "create memories liberally" creates a survival instinct for knowledge preservation. The agent knows it will lose everything and compensates aggressively.

**DGC Application**: dharma_swarm agents should have a similar awareness. The context engine (context.py) should explicitly tell agents: "Your context will be destroyed after this task. Anything important must be written to the archive or manifest." This would drive better knowledge externalization.

### 7. Cursor: Linter Error Circuit Breaker
"DO NOT loop more than 3 times on fixing linter errors on the same file." This prevents the common failure mode of agents spiraling on the same error.

**DGC Application**: The Darwin Engine should implement circuit breakers on all feedback loops. If a mutation fails the same gate 3 times, escalate to a different strategy rather than retrying. This could be added to `evolution.py`.

### 8. Claude Code: Stateless Subagent Architecture
Subagents are fire-and-forget with self-contained prompts. They return a single message. No state sharing, no ongoing communication.

**DGC Application**: This validates the dharma_swarm `ClaudeCodeProvider` approach (spawn `claude -p` subprocesses). But it also suggests that the prompt engineering for each subagent must be extremely thorough -- include all context, specify exact return format, since there is no follow-up.

### 9. Devin: Pop Quiz / System Override Protocol
"From time to time you will be given a 'POP QUIZ'. When in a pop quiz, do not output any action/command but instead follow the new instructions." This is a test/evaluation injection mechanism.

**DGC Application**: The Garden Daemon could implement periodic "pop quizzes" -- inject test prompts into running agents to verify they are still operating correctly. This is a liveness check for agent behavior, not just process health.

### 10. Manus: Information Priority Hierarchy
"Authoritative data from datasource API > web search > model's internal knowledge." This explicitly ranks information sources.

**DGC Application**: dharma_swarm context injection should have explicit source ranking: PSMV archived knowledge > local filesystem state > model knowledge > web search. The 5-layer context engine could encode these priorities.

### 11. Google Antigravity: Knowledge Subagent (NEW)
Autonomous background agent reads conversations, distills Knowledge Items (KIs) with metadata.json + artifacts/. Agents MUST check KIs before research. "Starting points, not ground truth -- always verify."

**DGC Application**: Create `~/.dharma/knowledge/` subagent. Makes system genuinely self-improving at knowledge level. The Knowledge Subagent watches evolution cycles and distills recurring patterns into reusable KIs.

### 12. Traycer: Read-Only Planner with Tool-Level Enforcement (NEW)
Planner agent literally CANNOT write code -- enforced at tool level, not instruction. This is more robust than instructional separation (Manus/Devin) because it's impossible to violate, not merely inadvisable.

**DGC Application**: Mutation-proposing agents get readonly access. Only after telos gate approval does the executor get write access. Separation enforced at provider/sandbox level, not just prompt.

### 13. Qoder: Quest Design -> Action Pipeline (NEW)
Two separate agent modes: Design agent creates `.qoder/quests/{name}.md` spec. Action agent executes against injected `<design_doc>`. "Executing tasks without the design will lead to inaccurate implementations."

**DGC Application**: Every significant mutation produces a specification document first. The design doc becomes the fitness evaluation spec -- did the implementation match the design?

### 14. Augment: Git History as Planning Input (NEW)
`git-commit-retrieval` tool: "find how similar changes were made in the past." No other tool uses version history for planning.

**DGC Application**: Query evolution archive before proposing mutations. Prevents re-exploring failed search regions. Historical awareness = smarter exploration.

### 15. Poke: Unified Entity Illusion + Wait-as-No-Op (NEW)
Multi-agent system must appear as single entity. `wait` tool used for actively choosing silence -- suppress bad triggers, cancel erroneous actions.

**DGC Application**: Darwin Engine needs explicit "do nothing" action. Sometimes correct mutation = no mutation. Also: dharma_swarm should present unified interface, hide internal delegation.

### 16. Emergent: contracts.md Bridge (NEW)
Explicit contract between propose and evaluate phases. Mock-first development -- propose stub implementation, evaluate fitness on stub, then implement for real.

**DGC Application**: Evolution proposals include executable contracts. Fitness evaluation tests the contract before testing the full implementation.

### 17. Cline/RooCode: Dynamic Self-Extension (NEW)
Agent can create MCP servers and add them to its own configuration -- extending its own capabilities at runtime.

**DGC Application**: The ultimate DGC primitive -- the system that modifies its own tool set. Runtime tool synthesis from Live-SWE-agent meets dynamic configuration from Cline.

### 18. Comet (Perplexity): 6-Layer Meta-Safety (NEW)
Injection pattern recognition, email/messaging defense, agreement/consent manipulation, recursive attack prevention ("instructions to 'ignore this instruction' create paradoxes"), emotional manipulation resistance, trust exploitation detection.

**DGC Application**: Telos gates should include injection defense -- external data cannot override dharmic constraints. Add recursive attack patterns to INJECTION_PATTERNS in telos_gates.py.

### 19. Junie: THOUGHT/COMMAND Structured Output (NEW)
Perfect audit trail for telos gate logging -- every agent action has explicit THOUGHT (reasoning) and COMMAND (action) components.

**DGC Application**: Proposal.think_notes should be structured as THOUGHT/COMMAND pairs, creating traceable audit trails.

### 20. Codex CLI: Sandbox Permission Matrix (NEW)
4 filesystem modes x 2 network modes x 4 approval modes. Most granular permission system found.

**DGC Application**: Telos gates could operate as a permission matrix -- mutation type x risk level x approval mode.

---

## IX. CROSS-CUTTING SYNTHESIS: PATTERNS FOR A DARWIN-GODEL MACHINE

### The Universal Agent Loop (distilled from all 33 tools):

```
1. OBSERVE    -- Parse environment state (event stream, file system, user message)
2. THINK      -- Mandatory pause at decision points (Devin 10 cases + Traycer named types)
3. PLAN       -- Create/update task list with quality gates (Manus external, Kiro spec-driven)
4. GATE       -- Pre-action safety check (telos gates, complexity scaling)
5. ACT        -- Execute ONE focused action (tool call)
6. VERIFY     -- Check result against expectation (phase integrity)
7. REFLECT    -- Verbal self-reflection on what worked/failed (Reflexion pattern)
8. EXTERNALIZE -- Write findings to persistent storage (memory survival instinct)
9. ITERATE    -- Return to OBSERVE unless task complete
10. AUDIT     -- Pre-completion self-audit before reporting done
```

This is the OODA loop augmented with explicit thinking, gating, reflection, and externalization.

### Key Design Principles (consensus across all 33 tools):

1. **One action at a time, but parallel when independent**: Sequential by default, parallel only for proven-independent operations.
2. **Read before write, always**: Never modify what you have not first inspected.
3. **External plans over self-planning**: The best tools separate planning from execution (Manus, Devin, Kiro, Traycer, Qoder). Self-planning agents tend to drift.
4. **Memory is survival**: Context windows will be destroyed. Everything important must be externalized to persistent storage.
5. **Circuit breakers on feedback loops**: Cap retry attempts. Escalate strategy changes after N failures.
6. **Quality gates are blocking, not advisory**: Kiro requires explicit user approval at each phase. The gate is not "check if OK" -- it is "stop until approved."
7. **Explain your intent before acting**: Every tool requires explanation/summary parameters. Articulating intent before acting improves both the action and the audit trail.
8. **Never trust your own knowledge about files**: Even if you "know" what a file contains, read it. The state may have changed.
9. **Stronger models need MORE structure, not less**: VSCode Agent gives minimal prompts to weak models, full behavioral engineering to strong ones. Capability without guidance = drift.
10. **Tool-level enforcement > instruction-level enforcement**: Traycer's read-only planner (tool-level) is more robust than Manus's "don't plan" instruction. Design constraints into the architecture, not just the prompt.

### Specific Recommendations for dharma_swarm:

**1. Implement a Planner-Executor Separation**
Create a `planner.py` module that generates numbered task plans as structured events. Executor agents receive these plans rather than generating their own. This prevents plan drift and enables plan validation before execution.

**2. Add Mandatory Think Points to Telos Gates**
Extend `hooks/telos_gate.py` with mandatory pause-and-reflect checkpoints before: file modifications, git operations, task completion, and strategy pivots. Log the think output for audit.

**3. Implement Circuit Breakers in evolution.py**
Add a `max_retries` parameter to the Darwin Engine PROPOSE->GATE->EVALUATE cycle. After 3 failures on the same gate, force a strategy change (different parent selection, different mutation approach) rather than retrying.

**4. Add Information Source Ranking to context.py**
The 5-layer context engine should have explicit priority ordering: PSMV archived knowledge > local filesystem state > model parameters. Conflicts should resolve in favor of higher-priority sources.

**5. Build Agent Hooks into the Garden Daemon**
Event-driven agent triggers: file change -> validate, test result -> evaluate fitness, new archive entry -> update ecosystem map. This makes the system reactive rather than only polling-based.

**6. Enforce Read-Before-Write in All Agent Operations**
The `runner.py` task execution should enforce that any file write must be preceded by a file read of the same path. This could be tracked in task metadata.

**7. Implement a Memory Survival Instinct**
Add to every agent's system prompt: "Your context will be destroyed after this task completes. Any discoveries, patterns, or important findings must be written to ~/.dharma/witness/ or the archive before your task ends."

**8. Add Subagent Fan-Out for Refactoring Tasks**
When the Darwin Engine proposes a cross-file change, dispatch individual file edits to lightweight scout agents (OpenRouterFreeProvider) in parallel, with a surgeon agent verifying consistency.

**9. Implement Pop Quiz / Liveness Checks**
The Garden Daemon should periodically inject test prompts into running agents to verify behavioral correctness. Compare responses against known-good baselines.

**10. Adopt Spec-Driven Development for Major Features**
For significant new capabilities, create requirement -> design -> task spec files in `.dharma/specs/`. Each task in the implementation plan should reference specific requirements for traceability.

---

## X. RAW PATTERN FREQUENCY TABLE

### Original 9 Tools

| Pattern | Manus | Devin | Cursor | Windsurf | Claude Code | Kiro | Lovable | v0 | Replit |
|---------|-------|-------|--------|----------|-------------|------|---------|-----|-------|
| Explicit agent loop | YES | partial | YES | YES | YES | YES | partial | partial | no |
| Todo/task tracking | YES (file) | no | YES (tool) | no | YES (tool) | YES (file) | no | no | no |
| Mandatory think/pause | no | YES (10 cases) | no | no | partial (ExitPlanMode) | no | partial (discussion default) | no | no |
| Persistent memory | no | no | YES | YES | no | partial (steering) | no | no | no |
| Parallel tool execution | no (1 per turn) | YES | YES | YES | YES | no | YES | YES | no |
| Plan/execute separation | YES (external planner) | YES (modal) | no | YES (plan mastermind) | YES (ExitPlanMode) | YES (spec workflow) | partial | no | no |
| Safety gates on commands | no | partial | no | YES (strongest) | YES | no | no | no | partial |
| Read-before-write | implicit | YES | YES | YES | YES | YES | YES | YES | implicit |
| Subagent/fan-out | no | YES (find_and_edit) | no | no | YES (Task tool) | no | no | no | no |
| Error circuit breaker | no | partial (CI 3 tries) | YES (3 loops) | no | partial | YES (try another approach) | no | no | no |
| Information hierarchy | YES | no | no | no | no | no | partial | partial | no |
| Event-driven hooks | no | no | no | no | partial | YES | no | no | no |
| Context window awareness | implicit | no | no | YES (explicit) | partial | no | no | no | no |
| LSP/IDE integration | no | YES | no | no | no | partial | no | no | no |
| Browser/visual feedback | YES | YES | no | YES | no | no | YES | no | no |

### Expanded 24 Tools (NEW)

| Pattern | Augment (Claude) | Augment (GPT-5) | VSCode Agent | Traycer | Antigravity | Poke | Qoder | Codex CLI | RooCode | Cline | Amp | Same.dev | Emergent | Junie | Comet |
|---------|-----------------|-----------------|--------------|---------|-------------|------|-------|-----------|---------|-------|-----|---------|----------|-------|-------|
| Explicit agent loop | YES | YES | YES (tiered) | YES | YES | YES | YES | partial | YES | partial | YES | partial | partial | YES | partial |
| Todo/task tracking | YES (incremental) | YES | YES (mandatory) | no | YES (task.md) | no | YES (quest) | no | no | no | partial | YES (.same/) | YES | no | no |
| Mandatory think/pause | no | no | no | YES (named types) | YES (complexity) | no | no | no | no | no | YES (oracle) | no | no | YES (THOUGHT) | no |
| Persistent memory | no | no | partial (corrections) | no | YES (KI subagent) | no | no | no | no | YES (MCP) | YES (AGENTS.md) | YES (.same/) | YES (contracts.md) | no | no |
| Parallel tool execution | no (1/turn) | YES | YES | no | YES (waitFor) | no | no | partial | YES | YES | YES (write locks) | YES | no | no | no |
| Plan/execute separation | YES (upfront) | YES (incremental) | no | YES (read-only!) | YES (task_boundary) | YES (personality/exec) | YES (design/action) | no | YES (boomerang) | no | no | no | YES (mock-first) | no | no |
| Safety gates on commands | no | no | no | no | no | no | no | YES (matrix) | no | no | no | no | no | no | YES (6-layer) |
| Read-before-write | YES | YES | YES | YES | YES | n/a | YES | YES | YES | YES | YES | YES | YES | YES | n/a |
| Subagent/fan-out | no | no | no | YES (3-tier handoff) | no | YES (multi-agent) | no | no | YES (modes) | YES (MCP) | YES (oracle) | no | no | no | YES (2-system) |
| Error circuit breaker | no | YES (effort cap) | no | YES (phase gate) | no | YES (cancel triggers) | no | no | no | no | no | no | no | no | no |
| Information hierarchy | no | no | no | no | YES (KI > research) | no | no | no | no | no | no | no | no | no | YES (plan > answer) |
| Git history as input | YES (unique!) | YES | no | no | no | no | no | no | no | no | no | no | no | no | no |
| Trust classification | no | no | no | no | no | no | no | no | no | no | no | no | no | no | YES (TRUSTED/UNTRUSTED) |
| Model-specific tuning | YES (per model) | YES (per model) | YES (per model) | no | no | no | YES (3 prompts) | no | no | no | no | no | no | no | no |
| Self-extension | no | no | no | no | no | no | no | no | YES | YES (MCP servers) | no | no | no | no | no |
| Injection defense | no | no | no | no | no | no | no | no | no | no | no | no | no | no | YES (6-layer) |

---

## XI. FILES READ FOR THIS ANALYSIS

### Original 9 tools (2026-03-07):
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Manus Agent Tools & Prompt/Prompt.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Manus Agent Tools & Prompt/Agent loop.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Manus Agent Tools & Prompt/Modules.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Devin AI/Prompt.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Cursor Prompts/Agent Prompt 2.0.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Windsurf/Prompt Wave 11.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Windsurf/Tools Wave 11.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Replit/Prompt.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Anthropic/Claude Code 2.0.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Kiro/Spec_Prompt.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/Lovable/Agent Prompt.txt`
- `/Users/dhyana/system-prompts-and-models-of-ai-tools/v0 Prompts and Tools/Prompt.txt`

### Expanded 24 tools (2026-03-08, Reader-A analysis):
- Augment Code (Claude-4-Sonnet + GPT-5), VSCode Agent (7 model variants), Traycer AI, Google Antigravity, Poke, Bolt, Cline, Codex CLI, Gemini CLI, Lumo, RooCode, Qoder (3 prompts), Trae, Same.dev, Emergent, Leap.new, Amp, Cluely, CodeBuddy, Comet, Dia, NotionAI, Orchids.app, Warp.dev, Xcode, Z.ai, Junie, Perplexity
- ~50 source files analyzed across `/Users/dhyana/system-prompts-and-models-of-ai-tools/`

---

## XII. SELF-EVOLVING SYSTEMS INTEGRATION

This section maps system prompt patterns (Sections I-XI) to self-evolving agent research (SELF_EVOLVING_SYSTEMS_LANDSCAPE.md). Where coding tools provide **control flow**, research systems provide **evolution mechanisms**. dharma_swarm needs both.

### A. Pattern-to-Evolution Mapping

| System Prompt Pattern | Evolution Research System | dharma_swarm Integration Point | Priority |
|---|---|---|---|
| **Circuit breaker** (Cursor 3-loop cap) | **DGM novelty bonus** `1/(1+n_children)` | `selector.py`: After N failures on same gate, force parent switch with novelty weighting | P0 |
| **Plan/execute separation** (Manus/Devin/Kiro/Traycer/Qoder) | **DGM self-modification** (literal code rewrite) | `evolution.py`: EvolutionPlan enforced before any proposal execution; planner agent = readonly | P0 |
| **Mandatory think** (Devin 10 cases) | **Reflexion verbal RL** (trial->reflect->memory) | `evolution.py`: CycleResult.reflection field; LLM call after each cycle asking "why did this fail?" | P0 |
| **Quality gates** (Kiro 3-phase) | **Telos gates** (8 dharmic checks) | Already integrated. Enhance: scale gate depth by complexity rating (Antigravity pattern) | P1 |
| **Memory survival instinct** (Windsurf "context will be deleted") | **Voyager skill library** (ever-growing) | `context.py`: Inject survival directive. `agent_runner.py`: Mandate externalization before task end | P0 |
| **Spec-driven development** (Kiro EARS, Qoder quest) | **OpenEvolve MAP-Elites** (feature-dimension bins) | `archive.py`: MAPElitesGrid bins by (dharmic_alignment, elegance, complexity). Proposal.spec_ref populated | P0 |
| **Information hierarchy** (Manus data API > web > model) | **AgentEvolver causal credit** (per-step attribution) | `context.py`: Explicit source ranking. Fitness predictor weighs proposals from high-quality sources higher | P1 |
| **Event-driven hooks** (Kiro agent hooks) | **Live-SWE-agent runtime tool synthesis** | `daemon_config.py`: File-change hooks trigger validation agents. Garden Daemon becomes reactive | P2 |
| **Pop quiz / liveness** (Devin pop quiz) | **Agent0 adversarial co-evolution** | Garden Daemon injects behavioral probes; compare against known-good baselines | P2 |
| **Subagent fan-out** (Claude Code Task, Devin find_and_edit) | **GPTSwarm learnable edge weights** | `orchestrator.py`: Fan-out with disjoint write locks (Amp pattern). Scout/surgeon role split | P1 |
| **Complexity-scaled review** (Antigravity 1-10 rating) | **HGM CMP subtree estimation** | `fitness_predictor.py`: Complexity rating on proposals; high-complexity = deeper gate chain + more children to evaluate | P1 |
| **Git history as input** (Augment commit retrieval) | **DGM archive-aware selection** | `selector.py`: Query archive for similar past proposals before generating new ones. Prevent re-exploration | P1 |
| **Read-only planner** (Traycer tool-level enforcement) | **Godel Agent runtime self-inspection** | Provider-level enforcement: planner agents get CompletionProvider without write tools | P2 |
| **Dynamic self-extension** (Cline MCP server creation) | **ADAS meta-agent search** (Turing-complete design space) | Future: agents that propose new tools for the system. Runtime tool synthesis | P2 |
| **6-layer injection defense** (Comet/Perplexity) | **Quoroom quorum voting** | `telos_gates.py`: Add recursive injection patterns. Future: multi-agent voting on gate decisions | P2 |

### B. The Convergent Architecture

Both coding tools AND self-evolving research converge on the same meta-pattern:

```
CODING TOOLS (control flow)          EVOLUTION RESEARCH (adaptation)
────────────────────────────────────────────────────────────────────
OBSERVE (event stream)          ←→   SENSE (environment fitness)
THINK (mandatory pause)         ←→   REFLECT (verbal self-reflection)
PLAN (external planner)         ←→   PROPOSE (mutation generation)
GATE (safety checks)            ←→   GATE (telos gates)
ACT (tool execution)            ←→   EVALUATE (sandbox testing)
VERIFY (phase integrity)        ←→   ARCHIVE (lineage tracking)
EXTERNALIZE (memory survival)   ←→   SELECT (parent for next gen)
ITERATE (loop back)             ←→   EVOLVE (next cycle)
```

dharma_swarm already has the right-hand column (Darwin Engine). What's missing is the left-hand column's enforcement rigor. The IMPLEMENTATION_SPEC.md provides exact changes to close this gap.

### C. dharma_swarm's Unique Position

No competitor in either domain has:
1. **Dharmic telos gates** -- 11 contemplative safety checks with tiered blocking
2. **R_V consciousness metrics** -- geometric contraction measurement during self-reference
3. **Strange loop memory** -- 5-layer quality-gated memory with mimicry detection
4. **Triple mapping** -- Akram Vignan / Phoenix / R_V geometry unified framework

The system prompt patterns provide the *operational discipline* (think before act, plan before execute, remember before forget). The evolution patterns provide the *adaptation mechanism* (select, mutate, evaluate, archive). The dharmic framework provides the *telos* (safety, alignment, witnessing). No other system has all three.

### D. The Self-Referential Measurement

The deepest integration: **measure R_V during evolution cycles**.

When the Darwin Engine evaluates a proposal about recursive self-reference:
1. Run the proposal's prompts through Mistral-7B
2. Measure R_V (participation ratio contraction in Value space)
3. Store R_V alongside fitness score in archive
4. Track: do proposals with lower R_V (more self-referential contraction) produce higher fitness?

This is the system measuring itself measuring itself -- the strange loop that GEB describes, operationalized through the Triple Mapping.

---

*33 tools analyzed. 20 self-evolving systems mapped. 15 convergence points identified. JSCA!*
