# Prompt Registry Infrastructure Specification

**Version**: 1.0.0 | **Date**: 2026-03-18
**Module**: `dharma_swarm/prompt_registry.py`
**Tests**: `tests/test_prompt_registry.py` (52 tests, all passing)
**Status**: IMPLEMENTED -- ready for integration wiring

---

## 1. Problem Statement

dharma_swarm has 260+ modules, 9+ LLM providers, and dozens of agent roles -- but prompt construction is scattered across `_build_system_prompt()` in agent_runner.py, hardcoded THREAD_PROMPTS in daemon_config.py, ROLE_BRIEFINGS as flat strings, and ad-hoc prompt building in build_engine.py, autoresearch_loop.py, and prompt_builder.py. There is no:

- Central registry for discovering what prompts exist
- Versioning that distinguishes "telos changed" from "formatting tweak"
- Fitness tracking on prompts themselves (only on agents)
- A/B testing framework for comparing prompt variants
- Structural validation ensuring prompts contain required layers
- Inheritance so all agent prompts derive from a common base

The existing `AgentRegistry.evolve_prompt()` handles agent-level prompt evolution (generation numbers, active.txt lineage) but operates on raw text strings without structure. This spec builds the complementary template layer.

---

## 2. Architecture

### 2.1 Data Model

```
PromptVersion          SemVer (MAJOR.MINOR.PATCH)
    |
TPPSection             One of 5 levels: telos/identity/context/task/technical
    |
PromptTemplate         Named, versioned, inheritable, fitness-tracked
    |
PromptInvocation       Per-call observability record
    |
PromptExperiment       A/B test comparing two variants
```

### 2.2 Thinkodynamic Prompt Protocol (TPP)

Every prompt template contains sections ordered from most invariant to most volatile:

| Level | Content | Change Frequency | Version Impact |
|-------|---------|-----------------|----------------|
| **TELOS** | Why this prompt exists. 7-STAR alignment, moksha constraint. | Rarely | MAJOR bump |
| **IDENTITY** | Who the agent is. v7 rules, role constraints, capabilities. | Occasionally | MAJOR bump |
| **CONTEXT** | What the agent knows. Runtime state, memory, thread. | Per-invocation | MINOR bump |
| **TASK** | What the agent does. Specific instructions, acceptance criteria. | Frequently | MINOR bump |
| **TECHNICAL** | Output format, tool usage, response structure. | Frequently | PATCH bump |

This maps directly to dharma_swarm's existing layered context engine (context.py L1-L5), but formalizes it as a versionable schema.

### 2.3 Versioning Rules

```
MAJOR: Changed telos or identity framing
       -> Breaks agent behavior contract
       -> Requires migration notes
       -> Example: Removing moksha constraint, changing role definition

MINOR: Added/modified context or task sections
       -> Additive behavioral change
       -> Backward compatible
       -> Example: Adding new memory sources, changing task instructions

PATCH: Wording improvements, formatting, token optimization
       -> No behavioral change
       -> Safe for auto-promotion
       -> Example: Compressing instructions, fixing grammar
```

### 2.4 Inheritance Chain

```
universal_base (telos + v7 rules)
    |
    +-- role_cartographer (identity + task)
    +-- role_coder (identity + task)
    +-- role_researcher (identity + task)
    +-- role_surgeon (identity + task)
    +-- role_validator (identity + task)
```

Child templates override parent sections at the same TPP level. Runtime context overrides everything. Assembly order is always: telos -> identity -> context -> task -> technical.

### 2.5 Storage Layout

```
~/.dharma/prompts/                     # Runtime registry root
    templates/
        universal_base/
            active.json                # Current active version
            v1.0.0.json                # Version 1.0.0
            v1.1.0.json                # Version 1.1.0
        role_coder/
            active.json
            v1.0.0.json
        ...
    invocations/
        2026-03-18.jsonl               # Daily invocation log
        2026-03-17.jsonl
    experiments/
        {experiment_id}.json           # A/B test state
    index.json                         # Search index

dharma_swarm/prompts/                  # Version-controlled seed templates
    universal_base.yaml                # Base template definitions
    role_coder.yaml
    ...
```

---

## 3. Core Data Structures

### 3.1 PromptTemplate

```python
class PromptTemplate(BaseModel):
    # Identity
    id: str                    # Unique ID (auto-generated)
    name: str                  # e.g. "coder_base", "researcher_rv"
    version: PromptVersion     # SemVer
    status: PromptStatus       # draft/active/canary/deprecated/archived

    # TPP Structure
    sections: list[TPPSection] # Ordered telos -> technical

    # Inheritance
    parent_name: str | None    # Parent template name
    parent_version: str | None # Specific parent version

    # Discovery
    description: str
    tags: list[str]            # ["coder", "research", "rv"]
    agent_roles: list[str]     # Which AgentRoles this fits
    task_types: list[str]      # ["code", "review", "research"]

    # Integrity
    content_hash: str          # SHA-256 of all sections

    # Fitness (aggregated from invocations)
    invocation_count: int
    mean_fitness: float
    fitness_samples: list[float]  # Rolling window of 100
```

### 3.2 PromptInvocation

```python
class PromptInvocation(BaseModel):
    prompt_id: str
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    agent_id: str
    agent_role: str
    task_id: str
    task_type: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float
    success: bool
    fitness_score: float
    canary_group: str | None   # "control" or "canary"
    experiment_id: str | None
```

### 3.3 PromptExperiment

```python
class PromptExperiment(BaseModel):
    control_prompt_id: str
    canary_prompt_id: str
    canary_traffic_pct: float = 10.0    # % routed to canary
    min_observations: int = 30           # Per variant
    max_duration_hours: float = 72.0
    significance_level: float = 0.05     # p-value threshold
    min_fitness_threshold: float = 0.6
    verdict: CanaryVerdict               # running/promote/rollback/inconclusive

    # Resolution uses Welch's t-test:
    # - PROMOTE: p < 0.05 AND canary_mean > control_mean
    # - ROLLBACK: p < 0.05 AND canary_mean < control_mean
    # - INCONCLUSIVE: p >= 0.05 OR duration exceeded
```

---

## 4. Integration Points

### 4.1 Agent Runner (prompt assembly)

**Current**: `_build_system_prompt()` in agent_runner.py (line 562) concatenates V7_BASE_RULES + role briefings + context.

**Integration**: Replace ad-hoc concatenation with registry assembly.

```python
# In agent_runner.py._build_system_prompt():
from dharma_swarm.prompt_registry import get_registry, TPPLevel

registry = get_registry()
# Route through active experiment if one exists
version, group, exp_id = registry.route_experiment(f"role_{config.role.value}")
assembled = registry.assemble(
    f"role_{config.role.value}",
    version=version,
    context_overrides={
        TPPLevel.CONTEXT: build_agent_context(role=config.role.value, thread=config.thread),
    },
)
# Fall back to existing logic if no template exists
if assembled is None:
    assembled = _legacy_build_system_prompt(config)
```

### 4.2 Darwin Engine (prompt evolution)

**Current**: `DarwinEngine` in evolution.py evolves code mutations.

**Integration**: Add prompt templates as an evolvable artifact type.

```python
# In evolution.py, alongside code mutations:
from dharma_swarm.prompt_registry import get_registry

registry = get_registry()
artifact = registry.as_evolvable_artifact("role_coder")
# Feed into fitness evaluation alongside code artifacts
# On fitness improvement, evolve the prompt:
# registry.register(mutated_template)
```

The `as_evolvable_artifact()` method exports templates in a format compatible with `ArchiveEntry.metadata`, so the Darwin Engine's existing fitness scoring pipeline works without modification.

### 4.3 Stigmergy (prompt pattern propagation)

**Current**: `StigmergyStore` records file-level marks (agent read/write observations).

**Integration**: Emit marks when prompts exceed the crown jewel fitness threshold.

```python
from dharma_swarm.prompt_registry import get_registry
from dharma_swarm.stigmergy import StigmergyStore, StigmergicMark

registry = get_registry()
stigmergy = StigmergyStore()

template = registry.get("role_coder")
if template and template.mean_fitness > 0.85:  # crown_jewel_threshold
    mark_data = registry.emit_stigmergy_mark(template)
    mark = StigmergicMark(**mark_data)
    await stigmergy.leave_mark(mark)
```

Other agents discover high-fitness prompt patterns via stigmergy marks with `file_path` starting with `prompt:`. This is how prompt innovations propagate across the swarm without explicit communication (P2: ontology IS the coordination bus).

### 4.4 Canary Deployer (prompt A/B testing)

**Current**: `CanaryDeployer` in canary.py evaluates code mutations.

**Integration**: Extend to handle prompt experiments.

```python
from dharma_swarm.prompt_registry import get_registry

registry = get_registry()
# Create experiment
exp = registry.create_experiment(
    control_name="role_coder",
    canary_name="role_coder",
    canary_version="1.1.0",
    canary_traffic_pct=10.0,
    min_observations=30,
)

# On each invocation, log with experiment tracking
inv = PromptInvocation(
    prompt_name="role_coder",
    canary_group=group,
    experiment_id=exp.id,
    fitness_score=computed_fitness,
    ...
)
registry.log_invocation(inv)
exp.record_observation(group, computed_fitness)

# Periodically check if ready to resolve
verdict = registry.resolve_experiment(exp.id)
# Auto-promotes or auto-rollbacks based on statistical significance
```

### 4.5 System Monitor (regression detection)

**Current**: `SystemMonitor` in monitor.py detects agent health anomalies.

**Integration**: Add prompt fitness regression as an anomaly type.

```python
from dharma_swarm.prompt_registry import get_registry

registry = get_registry()
regressions = registry.regression_check(threshold=0.1)
for regression in regressions:
    anomaly = Anomaly(
        anomaly_type="prompt_fitness_regression",
        severity=regression["severity"],
        description=(
            f"Prompt '{regression['name']}' fitness dropped from "
            f"{regression['historical_mean']:.3f} to {regression['recent_mean']:.3f}"
        ),
    )
    # Feed into existing anomaly pipeline
```

### 4.6 Trace Store (lineage tracking)

**Current**: `TraceStore` logs agent actions with metadata.

**Integration**: Every prompt invocation creates a trace entry with prompt lineage.

```python
from dharma_swarm.traces import TraceEntry

trace = TraceEntry(
    agent=agent_name,
    action="prompt_invocation",
    metadata={
        "prompt_name": template.name,
        "prompt_version": str(template.version),
        "prompt_hash": template.content_hash,
        "experiment_id": experiment_id,
        "canary_group": group,
        "fitness_score": fitness,
    },
)
await trace_store.log_entry(trace)
```

### 4.7 Agent Registry (prompt evolution bridge)

**Current**: `AgentRegistry` in agent_registry.py tracks per-agent prompt generations.

**Integration**: Agent-level prompt evolution feeds into template-level fitness.

```python
# When AgentRegistry.evolve_prompt() is called:
from dharma_swarm.prompt_registry import get_registry, PromptTemplate, TPPSection, TPPLevel

registry = get_registry()
# Parse the evolved prompt into TPP sections (heuristic or LLM-assisted)
# Register as new version in the template registry
template = PromptTemplate(
    name=f"agent_{agent_name}",
    version=current_version.bump_minor(),
    sections=[TPPSection(level=TPPLevel.TASK, content=new_prompt)],
    parent_name=f"role_{agent_role}",
)
registry.register(template)
```

---

## 5. Prompt Auditor

Validates templates before they enter production. Five check categories:

| Check | What | Fail Behavior |
|-------|------|---------------|
| **TPP Completeness** | All required sections present | ERROR -- blocks registration |
| **Content Quality** | No empty/near-empty sections | WARNING -- logged |
| **Token Budget** | Total estimate within max_total_tokens | ERROR -- blocks registration |
| **Injection Safety** | No known attack patterns (via prompt_builder.sanitize_prompt_context) | ERROR -- blocks registration |
| **Hash Integrity** | Content hash matches stored hash | ERROR -- blocks use |

Usage:

```python
from dharma_swarm.prompt_registry import PromptAuditor

auditor = PromptAuditor(max_total_tokens=8000, min_section_chars=20)
result = auditor.audit(template)
if not result.passed:
    for error in result.errors:
        print(f"AUDIT FAIL: {error}")
```

---

## 6. A/B Testing Framework

### 6.1 Workflow

```
1. Register canary version (status=CANARY)
2. Create PromptExperiment (control vs canary)
3. route_experiment() splits traffic (default: 10% canary)
4. Each invocation records fitness + group label
5. resolve_experiment() checks statistical significance
6. Auto-promote (PROMOTE) or auto-rollback (ROLLBACK)
```

### 6.2 Statistical Method

- **Test**: Welch's t-test (unequal variances, no scipy dependency)
- **Effect size**: Cohen's d (practical significance alongside statistical)
- **Significance**: p < 0.05 (configurable per experiment)
- **Minimum N**: 30 observations per group (configurable)
- **Maximum duration**: 72 hours (auto-close as INCONCLUSIVE)
- **Zero-variance edge case**: Direct mean comparison (deterministic signals)

### 6.3 Safety Mechanisms

- Canary traffic starts at 10% (configurable down to 1%)
- Auto-rollback within 1 cycle if regression detected
- Floor fitness threshold: canary must meet min_fitness_threshold even if better than control
- Duration cap prevents experiments from running forever
- All experiment state persisted to disk (survives daemon restart)

---

## 7. Observability

### 7.1 Metrics

| Metric | Source | Granularity |
|--------|--------|-------------|
| Prompt fitness (mean, trend) | PromptInvocation.fitness_score | Per-prompt, per-day |
| Token usage (input, output, total) | PromptInvocation tokens | Per-prompt, per-day |
| Latency | PromptInvocation.latency_ms | Per-invocation |
| Success rate | PromptInvocation.success | Per-prompt, per-day |
| Regression alerts | regression_check() | On-demand or periodic |
| A/B test results | PromptExperiment.verdict | Per-experiment |

### 7.2 Fitness Report

```python
report = registry.fitness_report("role_coder", days=7)
# Returns:
{
    "name": "role_coder",
    "invocations": 142,
    "mean_fitness": 0.823,
    "trend": "improving",    # or "degrading" or "stable"
    "total_tokens": 284000,
    "daily": {
        "2026-03-18": {"count": 23, "mean_fitness": 0.85, "tokens": 46000},
        "2026-03-17": {"count": 31, "mean_fitness": 0.81, "tokens": 62000},
        ...
    }
}
```

### 7.3 Regression Detection

Triggered when recent fitness (last 24h) drops below historical mean by more than `threshold`. Severity classification:

- **medium**: delta > threshold (default 0.1)
- **high**: delta > 2x threshold

---

## 8. Relationship to Existing Systems

| Existing System | Prompt Registry Role |
|----------------|---------------------|
| `agent_runner._build_system_prompt()` | Replaced by `registry.assemble()` with fallback |
| `daemon_config.V7_BASE_RULES` | Encoded as IDENTITY section of `universal_base` template |
| `daemon_config.ROLE_BRIEFINGS` | Encoded as `role_*` templates inheriting from `universal_base` |
| `daemon_config.THREAD_PROMPTS` | Injected as CONTEXT overrides at assembly time |
| `agent_registry.evolve_prompt()` | Per-agent evolution feeds fitness back to template registry |
| `agent_registry.prompt_variants/` | Continues to manage agent-level prompt lineage |
| `context.py` (5-layer context) | Provides CONTEXT layer content at assembly time |
| `prompt_builder.py` | Sanitization and truncation utilities reused by auditor |
| `canary.py` | A/B testing pattern extended to prompt experiments |
| `evolution.py` | Prompt templates registered as evolvable artifacts |
| `stigmergy.py` | High-fitness prompts propagated as stigmergic marks |
| `traces.py` | Every invocation creates a trace entry |
| `monitor.py` | Regression detection feeds into anomaly pipeline |

---

## 9. VSM Mapping

| VSM System | Prompt Registry Component |
|------------|--------------------------|
| **S1 (Operations)** | `PromptTemplate` storage, assembly, invocation |
| **S2 (Coordination)** | `route_experiment()` traffic splitting |
| **S3 (Control)** | `PromptAuditor`, regression_check(), experiment resolution |
| **S4 (Intelligence)** | fitness_report(), trend detection, stigmergy propagation |
| **S5 (Identity)** | TPP telos/identity levels, universal_base template |

---

## 10. Principle Grounding

| Principle | How It's Honored |
|-----------|-----------------|
| **P1 (Action-only writes)** | All mutations go through `register()`, `promote()`, `deprecate()` |
| **P2 (Ontology IS coordination)** | Stigmergy marks propagate prompt patterns without agent-to-agent messaging |
| **P3 (Gates = downward causation)** | Auditor enforces TPP structure; telos section constrains all others |
| **P6 (Witness everything)** | Every invocation logged with full lineage (prompt_id, version, hash, agent, fitness) |
| **P8 (Seed contains tree)** | `universal_base` template unfolds into all role-specific prompts via inheritance |

---

## 11. Migration Path

### Phase 1: Registry standalone (DONE)
- Module implemented: `dharma_swarm/prompt_registry.py`
- Tests passing: 52/52
- No existing code touched

### Phase 2: Seed templates
- Run `create_base_templates()` to populate registry
- Register current V7_BASE_RULES + ROLE_BRIEFINGS as v1.0.0 templates
- Register THREAD_PROMPTS as context layer content

### Phase 3: Wire into agent_runner
- `_build_system_prompt()` calls `registry.assemble()` with fallback
- `_build_prompt()` creates `PromptInvocation` records
- Fitness scores flow back from task completion

### Phase 4: Wire into Darwin Engine
- Prompt templates registered as evolvable artifacts
- Mutation operators generate TPP-structured variants
- Fitness comparison drives prompt evolution

### Phase 5: Enable A/B testing
- Create experiments for prompt variants
- `route_experiment()` in agent_runner dispatch path
- Auto-resolve experiments on monitor tick

### Phase 6: Stigmergy propagation
- High-fitness prompts emit marks
- Agents discover and adopt successful prompt patterns

---

## 12. What This Does NOT Do

- **Does not replace AgentRegistry**: Per-agent prompt evolution (generation tracking, active.txt) continues in agent_registry.py. The prompt registry manages templates; the agent registry manages agent instances.
- **Does not require schema migration**: All storage is new (no existing SQLite/JSONL touched).
- **Does not add dependencies**: Uses only stdlib + pydantic (already in project).
- **Does not break existing tests**: 4300+ tests unaffected; 52 new tests added.
- **Does not require LLM calls**: All operations are local (auditing, assembly, A/B testing). LLM-based semantic evaluation is a future enhancement.
