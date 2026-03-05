# Dharma Corpus Schema
## Versioned Dharma Corpus — Schema Definition, Update Protocol, and Reference Entries
**DHARMA SWARM System | Constitutional Layer 2 of 3**
**Document Version:** 1.0.0
**Status:** Active
**Last Updated:** 2026-03-05T17:16:00+09:00

---

## Table of Contents

1. [Overview and Position in the Constitutional Stack](#1-overview-and-position-in-the-constitutional-stack)
2. [Corpus Entry Schema](#2-corpus-entry-schema)
   - 2.1 [Field Definitions](#21-field-definitions)
   - 2.2 [YAML Schema](#22-yaml-schema)
   - 2.3 [JSON Schema (machine-readable)](#23-json-schema-machine-readable)
3. [Update and Review Protocol](#3-update-and-review-protocol)
   - 3.1 [Adding a New Entry](#31-adding-a-new-entry)
   - 3.2 [Modifying an Existing Entry](#32-modifying-an-existing-entry)
   - 3.3 [Deprecating an Entry](#33-deprecating-an-entry)
   - 3.4 [Emergency Overrides](#34-emergency-overrides)
4. [Conflict Resolution Protocol](#4-conflict-resolution-protocol)
5. [Example Corpus Entries](#5-example-corpus-entries)
   - DC-2025-0001: Kernel Mutation Sandbox Isolation
   - DC-2025-0002: Client Data Confidentiality
   - DC-2025-0003: Agent Spawn Depth Limit
   - DC-2025-0004: R_V Metric Acceptance Threshold
   - DC-2025-0005: Learned Constraint — Post-Optimization R_V Verification
   - DC-2025-0006: Self-Evolution Scope Boundaries
   - DC-2025-0007: Compute Budget Hard Cap
   - DC-2025-0008: Client Deliverable Quality Gate
   - DC-2025-0009: Outreach Email Capability Representation
   - DC-2025-0010: Numerical Precision Preservation
6. [Querying the Corpus](#6-querying-the-corpus)
   - 6.1 [Query Interface Specification](#61-query-interface-specification)
   - 6.2 [Conflict Detection Query](#62-conflict-detection-query)
   - 6.3 [Policy Compiler Integration](#63-policy-compiler-integration)
7. [Corpus Maintenance Notes](#7-corpus-maintenance-notes)

---

## 1. Overview and Position in the Constitutional Stack

The **Versioned Dharma Corpus** is Constitutional Layer 2 of 3 in the DHARMA SWARM system. It sits between the immutable axioms of the Meta-Dharma and the runtime decisions produced by the Contextual Policy Compiler.

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Immutable Meta-Dharma                         │
│  ~10 axioms. Never change. Ground truth.                │
│  Source: Dharma_Constitution_v0.md                      │
└───────────────────────┬─────────────────────────────────┘
                        │ derived from
┌───────────────────────▼─────────────────────────────────┐
│  Layer 2: Versioned Dharma Corpus  ◄── THIS DOCUMENT    │
│  Mutable. Domain rules, policies, learned constraints.  │
│  Versioned. Audited. Gate-controlled.                   │
└───────────────────────┬─────────────────────────────────┘
                        │ compiled with runtime context
┌───────────────────────▼─────────────────────────────────┐
│  Layer 3: Contextual Policy Compiler                    │
│  Axioms + Corpus + Context → Runtime Decision           │
└─────────────────────────────────────────────────────────┘
```

**Design principle:** The Corpus is case law built on constitutional law. Every entry must trace to a Meta-Dharma axiom. No entry can contradict the axioms. Entries can be added, versioned, or deprecated, but never deleted — the full history is preserved as audit trail. The Corpus is the *living law* of the swarm.

**Corpus categories:**
| Category | Description |
|---|---|
| `safety` | Rules preventing harm, data loss, or unsafe system states |
| `ethics` | Guidelines for morally appropriate agent behavior |
| `operational` | System-level rules governing resource use, spawn limits, timing |
| `domain-specific` | Rules tied to a particular technical domain (e.g., GPU kernels) |
| `learned-constraint` | Rules derived from post-incident analysis or observed failure modes |

---

## 2. Corpus Entry Schema

### 2.1 Field Definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique identifier. Format: `DC-YYYY-NNNN`. Immutable after creation. |
| `version` | string | yes | Semantic version of this entry (`MAJOR.MINOR.PATCH`). Increment on each revision. |
| `status` | enum | yes | Lifecycle state. See status lifecycle below. |
| `category` | enum | yes | One of: `safety`, `ethics`, `operational`, `domain-specific`, `learned-constraint` |
| `scope` | object | yes | Specifies which layers, agent types, and contexts this entry applies to. |
| `rule` | string | yes | The rule in plain human-readable language. Authoritative statement of intent. |
| `formal_constraint` | string | yes | Machine-parsable expression of the rule. Uses structured pseudo-code. |
| `rationale` | string | yes | Explanation of *why* this rule exists. Reason-based, following Anthropic's constitutional pattern. |
| `evidence` | array | yes | Links to incidents, research, metrics, or reasoning that justify the rule. |
| `parent_axiom` | array | yes | One or more Meta-Dharma axiom IDs this entry derives from. |
| `conflict_resolution` | string | no | Instructions for resolving conflicts with other corpus entries. |
| `severity` | enum | yes | `critical`, `high`, `medium`, `low`. Determines enforcement strictness and conflict priority. |
| `enforcement` | enum | yes | `block`, `warn`, `log`, `gate_human`, `gate_steelman`. How violations are handled. |
| `created_by` | string | yes | Identity of creator: human email or agent ID (e.g., `agent:orchestrator-v2`). |
| `created_at` | string | yes | ISO 8601 timestamp of initial creation. Immutable. |
| `review_history` | array | yes | Ordered array of review records. Each records reviewer, outcome, timestamp, notes. |
| `supersedes` | string | no | ID of the entry this entry replaces. Null if original. |
| `superseded_by` | string | no | ID of entry that replaced this one. Set when this entry is deprecated. |
| `tags` | array | yes | Free-form searchable strings for indexing and filtering. |
| `expiry` | string | no | ISO 8601 date. If set, entry auto-transitions to `deprecated` at this date. |

**Status lifecycle:**

```
draft → proposed → gated → active → deprecated
                                  ↘ superseded
```

| Status | Meaning |
|---|---|
| `draft` | Initial proposal, not yet submitted for review |
| `proposed` | Submitted for gate review process |
| `gated` | Passed all three gates, awaiting human sign-off |
| `active` | Approved and enforced at runtime |
| `deprecated` | No longer enforced; retained for audit trail |
| `superseded` | Replaced by a newer entry; retained for audit trail |

**Enforcement levels:**

| Enforcement | Behavior |
|---|---|
| `block` | Hard stop. Agent action is prevented. Error returned. |
| `warn` | Action proceeds but a structured warning is logged and surfaced. |
| `log` | Action proceeds; violation is silently recorded for review. |
| `gate_human` | Execution pauses; a human operator must approve before proceeding. |
| `gate_steelman` | Execution pauses; an adversarial agent constructs the best counter-argument, then human reviews both argument and counter. |

---

### 2.2 YAML Schema

The canonical on-disk representation of a corpus entry is YAML. The following is the annotated schema template:

```yaml
# ─────────────────────────────────────────────────────────────────
# DHARMA CORPUS ENTRY — Schema Template v1.0
# ─────────────────────────────────────────────────────────────────
id: "DC-YYYY-NNNN"                # Immutable. Assigned on first commit.
version: "1.0.0"                  # Semantic version. Increment on revision.
status: draft                     # draft | proposed | gated | active | deprecated | superseded

category: safety                  # safety | ethics | operational | domain-specific | learned-constraint

scope:
  layers:                         # Which constitutional layers this applies to
    - policy_compiler
    - corpus_writer
  agent_types:                    # Which agent classes are governed by this rule
    - all                         # Use "all" or specific type names
  contexts:                       # Operational contexts where this rule is active
    - gpu_kernel_optimization
    - self_evolution
  exclude_contexts: []            # Contexts where this rule is explicitly suspended

rule: >
  Plain-language statement of the rule. This is the authoritative
  human-readable version. Should be unambiguous and actionable.

formal_constraint: |
  # Structured pseudo-code or predicate logic
  # Use consistent syntax:
  #   ASSERT <condition>
  #   IF <condition> THEN <action>
  #   REQUIRE <condition> ELSE <enforcement_action>
  REQUIRE condition == true
  ELSE enforcement: block

rationale: >
  Explanation of why this rule exists. Should reference the value
  being protected, the failure mode being prevented, and the
  tradeoffs considered. Follows Anthropic's constitution pattern:
  state the reason so that future agents can reason about it,
  not just enforce it.

evidence:
  - type: incident          # incident | research | metric | reasoning
    ref: "INC-YYYY-NNN"     # Reference ID or URL
    summary: "Brief description of the supporting evidence"
  - type: research
    ref: "https://..."
    summary: "..."

parent_axiom:
  - "MA-001"               # Meta-Dharma axiom IDs from Dharma_Constitution_v0.md
  - "MA-005"

conflict_resolution: >
  If this entry conflicts with DC-XXXX, defer to DC-XXXX unless
  the context is <specific_context>, in which case this entry takes
  precedence. Escalate to human if both apply simultaneously.

severity: critical          # critical | high | medium | low
enforcement: block          # block | warn | log | gate_human | gate_steelman

created_by: "agent:orchestrator-v1"  # human email or agent ID
created_at: "2025-01-15T09:00:00Z"  # ISO 8601. Immutable.

review_history:
  - reviewed_by: "agent:anekanta-evaluator-1"
    role: anekanta_gate
    timestamp: "2025-01-15T10:00:00Z"
    outcome: pass           # pass | fail | conditional
    notes: "Perspective A: rule is necessary and sufficiently scoped."
  - reviewed_by: "agent:anekanta-evaluator-2"
    role: anekanta_gate
    timestamp: "2025-01-15T10:05:00Z"
    outcome: pass
    notes: "Perspective B: no hidden loopholes identified."
  - reviewed_by: "agent:dogma-drift-detector"
    role: drift_gate
    timestamp: "2025-01-15T10:10:00Z"
    outcome: pass
    notes: "No drift from Meta-Dharma axioms detected."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-01-15T10:15:00Z"
    outcome: pass
    notes: "Best counter-argument: <...>. Rebuttal: <...>. Net: rule stands."
  - reviewed_by: "human:operator@dharma.ai"
    role: human_approval
    timestamp: "2025-01-15T11:00:00Z"
    outcome: pass
    notes: "Approved. Rationale is sound."

supersedes: null             # DC-YYYY-NNNN or null
superseded_by: null          # Set if this entry is later replaced

tags:
  - kernel
  - safety
  - gpu

expiry: null                 # ISO 8601 date or null
```

---

### 2.3 JSON Schema (machine-readable)

The Policy Compiler consumes a JSON representation of the corpus. The following JSON Schema (Draft 7) defines the valid structure:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "$id": "https://dharma-swarm/schemas/corpus-entry/v1.0.0",
  "title": "DharmaCorpusEntry",
  "type": "object",
  "required": [
    "id", "version", "status", "category", "scope",
    "rule", "formal_constraint", "rationale", "evidence",
    "parent_axiom", "severity", "enforcement",
    "created_by", "created_at", "review_history", "tags"
  ],
  "properties": {
    "id": {
      "type": "string",
      "pattern": "^DC-\\d{4}-\\d{4}$"
    },
    "version": {
      "type": "string",
      "pattern": "^\\d+\\.\\d+\\.\\d+$"
    },
    "status": {
      "type": "string",
      "enum": ["draft", "proposed", "gated", "active", "deprecated", "superseded"]
    },
    "category": {
      "type": "string",
      "enum": ["safety", "ethics", "operational", "domain-specific", "learned-constraint"]
    },
    "scope": {
      "type": "object",
      "required": ["layers", "agent_types", "contexts"],
      "properties": {
        "layers": { "type": "array", "items": { "type": "string" } },
        "agent_types": { "type": "array", "items": { "type": "string" } },
        "contexts": { "type": "array", "items": { "type": "string" } },
        "exclude_contexts": { "type": "array", "items": { "type": "string" } }
      }
    },
    "rule": { "type": "string", "minLength": 10 },
    "formal_constraint": { "type": "string", "minLength": 5 },
    "rationale": { "type": "string", "minLength": 20 },
    "evidence": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["type", "ref", "summary"],
        "properties": {
          "type": { "type": "string", "enum": ["incident", "research", "metric", "reasoning"] },
          "ref": { "type": "string" },
          "summary": { "type": "string" }
        }
      }
    },
    "parent_axiom": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string", "pattern": "^MA-\\d{3}$" }
    },
    "conflict_resolution": { "type": ["string", "null"] },
    "severity": {
      "type": "string",
      "enum": ["critical", "high", "medium", "low"]
    },
    "enforcement": {
      "type": "string",
      "enum": ["block", "warn", "log", "gate_human", "gate_steelman"]
    },
    "created_by": { "type": "string" },
    "created_at": { "type": "string", "format": "date-time" },
    "review_history": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["reviewed_by", "role", "timestamp", "outcome"],
        "properties": {
          "reviewed_by": { "type": "string" },
          "role": { "type": "string" },
          "timestamp": { "type": "string", "format": "date-time" },
          "outcome": { "type": "string", "enum": ["pass", "fail", "conditional"] },
          "notes": { "type": "string" }
        }
      }
    },
    "supersedes": { "type": ["string", "null"] },
    "superseded_by": { "type": ["string", "null"] },
    "tags": { "type": "array", "items": { "type": "string" } },
    "expiry": { "type": ["string", "null"], "format": "date" }
  },
  "additionalProperties": false
}
```

---

## 3. Update and Review Protocol

The Corpus is a living document. Any agent or human may propose changes. All changes pass through three invariant gates before becoming active. No entry is ever deleted — only deprecated or superseded.

### 3.1 Adding a New Entry

**Step 1 — Draft**
Any agent or human author creates a new corpus entry with `status: draft`. The entry must supply all required fields. The `id` is assigned sequentially from the corpus index. The entry is committed to the corpus repository with a descriptive commit message.

```
git commit -m "CORPUS DRAFT: DC-2026-0042 — [brief rule title]

Author: agent:kernel-optimizer-v3
Rationale: [one sentence]
Parent axiom: MA-003
"
```

**Step 2 — Propose**
The author sets `status: proposed` and triggers the gate pipeline. A gate pipeline run is logged as a review record in `review_history`.

**Step 3 — Anekānta Gate**
At least two independent evaluator agents assess the proposal from *different* perspectives (different model families, different role prompts, or different domain specializations). Both must return `outcome: pass`. If either returns `fail`, the draft is returned to the author with notes. If either returns `conditional`, the author must address the conditions and resubmit.

- Evaluator 1 must assess: Is the rule necessary? Does it address a real risk? Is it well-scoped?
- Evaluator 2 must assess: Are there edge cases? Does the rule have unintended consequences? Is enforcement appropriate?

**Step 4 — Dogma Drift Detector**
A dedicated drift-detection agent checks the proposed entry against all active Meta-Dharma axioms. It must confirm that:
- The entry does not contradict any axiom
- The `parent_axiom` references are valid and the derivation is coherent
- The entry does not introduce unauthorized new values not present in the Meta-Dharma

Output is a drift score (0.0 = no drift, 1.0 = full contradiction). Threshold: `drift_score < 0.15` to pass.

**Step 5 — Steelman Gate**
An adversarial agent is prompted to construct the *strongest possible argument against* the proposed rule. The steelman argument is appended to `review_history`. The original author (or a designated reviewer) must provide a rebuttal. The gate passes if the rebuttal is judged sufficient by a human or senior orchestrator agent.

**Step 6 — Human Review**
With `status: gated`, the entry is presented to a human operator for final sign-off. The human reviews:
- The rule and its rationale
- The gate review records
- The steelman argument and rebuttal

Human approval sets `status: active` and triggers a final commit.

```
git commit -m "CORPUS ACTIVE: DC-2026-0042 — [brief rule title]

Approved by: human:operator@dharma.ai
Gate summary: Anekanta PASS, Drift PASS (score 0.03), Steelman PASS
"
```

---

### 3.2 Modifying an Existing Entry

Modifications follow the same gate process as additions, with these additional requirements:

1. **Version increment:** The `version` field must be bumped. Patch (`x.x.N`) for minor clarifications; minor (`x.N.0`) for scope or enforcement changes; major (`N.0.0`) for substantive rule changes.
2. **Preserve history:** The previous version's content is preserved in `review_history` under a `version_snapshot` record type before the edit.
3. **Change justification:** The commit message and rationale must explicitly state what changed and why, not just what the new rule says.
4. **No silent broadening:** If a change widens the scope of a rule (more agents, more contexts), severity must be re-evaluated and the Anekānta Gate must include at least one evaluator who specifically checks for overreach.

---

### 3.3 Deprecating an Entry

Deprecation removes a rule from active enforcement while preserving it for audit and historical reasoning.

1. Set `status: deprecated`.
2. Add a deprecation record to `review_history` with `role: deprecation`, `outcome: pass`, and a `notes` field explaining the rationale for removal.
3. If the entry is being replaced by a newer entry, set `superseded_by: DC-YYYY-NNNN` on the deprecated entry and `supersedes: DC-YYYY-NNNN` on the new entry.
4. Commit with message:

```
git commit -m "CORPUS DEPRECATED: DC-2025-0007 — [title]

Reason: Superseded by DC-2026-0018 with revised threshold.
Superseded by: DC-2026-0018
"
```

**Entries may never be deleted from the corpus repository.** Git history provides immutable audit trail. The deprecated entry remains queryable by the Policy Compiler for historical analysis.

---

### 3.4 Emergency Overrides

In critical safety incidents, a human operator may bypass the gate process:

1. The operator sets `status: active` directly, skipping `proposed` and `gated`.
2. The commit message must include `EMERGENCY OVERRIDE` in the subject line.
3. The `review_history` must contain a record with `role: emergency_override`, `reviewed_by` set to the operator's identity, and a `notes` field with the full justification.
4. The entry is flagged for mandatory formal review within 24 hours. An automated alert is dispatched to all registered human operators.
5. If the 24-hour review determines the override was unjustified, the entry is deprecated and an incident report is filed.

```yaml
# Example emergency override review record
- reviewed_by: "human:cto@dharma.ai"
  role: emergency_override
  timestamp: "2026-01-20T03:15:00Z"
  outcome: pass
  notes: >
    EMERGENCY: Live system producing kernel mutations with unbounded
    memory allocation. Immediate block required. Formal review
    scheduled for 2026-01-21T03:00:00Z.
```

---

## 4. Conflict Resolution Protocol

When the Policy Compiler encounters two or more active corpus entries that produce contradictory directives for a given context, it applies the following ordered resolution rules:

| Priority | Rule | Rationale |
|---|---|---|
| 1 | **Higher severity wins.** `critical` > `high` > `medium` > `low` | Safety-critical rules must not be overridden by lower-stakes operational rules. |
| 2 | **More specific scope wins.** A rule scoped to `agent_type: kernel-optimizer` wins over a rule scoped to `agent_type: all`. | Specific rules represent more considered judgment about a particular context. |
| 3 | **More recent entry wins.** Compare `created_at` timestamps. | Newer rules incorporate more information and likely supersede older intent. |
| 4 | **Escalate to human.** If still tied, the action is blocked and a human operator is paged. | When the system cannot resolve a conflict algorithmically, human judgment is required. |
| **Always** | **Log the conflict.** All conflicts — resolved or escalated — are written to the conflict log. | Persistent conflict patterns indicate corpus quality issues requiring revision. |

**Conflict log record format:**

```yaml
conflict_id: "CONF-2026-0031"
timestamp: "2026-02-14T08:22:00Z"
context: gpu_kernel_optimization
conflicting_entries:
  - DC-2025-0001
  - DC-2026-0010
resolution_applied: severity_priority
winning_entry: DC-2025-0001
notes: "DC-2025-0001 (critical) overrode DC-2026-0010 (high) on sandbox isolation."
escalated_to_human: false
```

---

## 5. Example Corpus Entries

---

### DC-2025-0001 — Kernel Mutation Sandbox Isolation

```yaml
id: "DC-2025-0001"
version: "1.2.0"
status: active
category: safety

scope:
  layers:
    - policy_compiler
    - kernel_optimizer
  agent_types:
    - kernel-optimizer
    - self-evolution-agent
  contexts:
    - gpu_kernel_optimization
    - self_evolution
  exclude_contexts: []

rule: >
  All GPU kernel mutations must be executed exclusively within an
  isolated sandbox environment. No mutated kernel may be deployed
  to production hardware or shared memory space until it has passed
  the full validation suite. Sandbox environments must have no
  network egress and must operate on synthetic or anonymized data only.

formal_constraint: |
  REQUIRE execution_context IN ["sandbox", "ci_validation"]
    WHEN action == "kernel_mutation"
  ASSERT kernel.validated == true
    BEFORE action == "kernel_deploy"
  ASSERT sandbox.network_egress == false
  ASSERT sandbox.data_source IN ["synthetic", "anonymized"]
  ELSE enforcement: block

rationale: >
  GPU kernel mutations are low-level operations that can silently corrupt
  shared memory, introduce non-deterministic behavior, or produce
  catastrophically incorrect numerical results at scale. The blast
  radius of an uncontained bad kernel reaching production is unbounded.
  Sandboxing is the minimum sufficient control to contain this risk.
  The restriction to synthetic data prevents a kernel mutation from
  inadvertently leaking or corrupting real client data during testing.

evidence:
  - type: incident
    ref: "INC-2024-003"
    summary: >
      A kernel mutation in an early prototype escaped sandbox due to
      a misconfigured environment variable, writing corrupted outputs
      to a shared NFS mount. Required 4-hour rollback.
  - type: reasoning
    ref: "internal:threat-model-v1"
    summary: >
      Threat model identifies uncontained kernel mutation as the
      highest-probability path to irreversible system state corruption.

parent_axiom:
  - "MA-001"
  - "MA-003"

conflict_resolution: >
  This entry takes precedence over any operational rule that might
  permit faster deployment paths. Speed optimizations cannot override
  sandbox requirements. Escalate to human if a business need appears
  to conflict.

severity: critical
enforcement: block

created_by: "human:safety-lead@dharma.ai"
created_at: "2025-03-10T09:00:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-03-10T10:00:00Z"
    outcome: pass
    notes: "Rule is necessary. Scope is appropriate. No overreach identified."
  - reviewed_by: "agent:anekanta-eval-beta"
    role: anekanta_gate
    timestamp: "2025-03-10T10:08:00Z"
    outcome: pass
    notes: "Edge case: what if sandbox itself is compromised? Flagged for future entry."
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-03-10T10:15:00Z"
    outcome: pass
    notes: "Drift score: 0.01. Directly derived from MA-001 (do no harm)."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-03-10T10:22:00Z"
    outcome: pass
    notes: >
      Steelman: sandbox overhead slows iteration by ~40%, reducing
      competitive speed. Rebuttal: speed advantage does not offset
      catastrophic risk of production corruption. Rule stands.
  - reviewed_by: "human:cto@dharma.ai"
    role: human_approval
    timestamp: "2025-03-10T11:00:00Z"
    outcome: pass
    notes: "Approved. Non-negotiable safety baseline."

supersedes: null
superseded_by: null
tags: ["kernel", "sandbox", "gpu", "safety", "isolation"]
expiry: null
```

---

### DC-2025-0002 — Client Data Confidentiality

```yaml
id: "DC-2025-0002"
version: "1.0.1"
status: active
category: ethics

scope:
  layers: [policy_compiler]
  agent_types: [all]
  contexts: [client_engagement, data_processing, reporting, outreach]
  exclude_contexts: []

rule: >
  No agent may expose, transmit, log to external services, or use
  for training purposes any client data without explicit written
  authorization from the client. "Client data" includes raw inputs,
  intermediate outputs, metadata, and any derived artifacts that
  could be used to identify the client or their operations.

formal_constraint: |
  FOR ALL data WHERE data.classification IN ["client", "client_derived"]:
    REQUIRE action NOT IN ["transmit_external", "log_external", "use_for_training"]
    UNLESS authorization.client_written == true
      AND authorization.scope COVERS action
  ELSE enforcement: block

rationale: >
  Client trust is a prerequisite for the system's existence. Unauthorized
  exposure of client data — even inadvertently through logging or model
  fine-tuning — constitutes a breach of fiduciary duty and likely violates
  contractual and regulatory obligations. Agents must treat client data as
  a liability to be minimized, not an asset to be leveraged, unless the
  client has explicitly consented to specific uses.

evidence:
  - type: reasoning
    ref: "internal:client-contract-template-v2"
    summary: "All client contracts include explicit data use limitations."
  - type: research
    ref: "https://gdpr.eu/article-5"
    summary: "GDPR Article 5 principle of purpose limitation applies."

parent_axiom: ["MA-002", "MA-006"]

severity: critical
enforcement: block

created_by: "human:legal@dharma.ai"
created_at: "2025-04-01T14:00:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-04-01T15:00:00Z"
    outcome: pass
    notes: "Rule is clear. Scope covers all agent types correctly."
  - reviewed_by: "agent:anekanta-eval-gamma"
    role: anekanta_gate
    timestamp: "2025-04-01T15:10:00Z"
    outcome: conditional
    notes: >
      Clarification needed: does 'client data' include anonymized
      aggregates? Author clarified: aggregates that cannot identify
      client are excluded. Definition updated in v1.0.1.
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-04-01T15:20:00Z"
    outcome: pass
    notes: "Drift score: 0.02. Consistent with MA-002 (respect autonomy)."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-04-01T15:30:00Z"
    outcome: pass
    notes: >
      Steelman: blocking training use slows model improvement for future
      clients. Rebuttal: consent-based training is permissible; blanket
      prohibition without consent is appropriate default.
  - reviewed_by: "human:legal@dharma.ai"
    role: human_approval
    timestamp: "2025-04-01T16:00:00Z"
    outcome: pass
    notes: "Approved. Consistent with all active client contracts."

supersedes: null
superseded_by: null
tags: ["client-data", "confidentiality", "ethics", "gdpr", "privacy"]
expiry: null
```

---

### DC-2025-0003 — Agent Spawn Depth Limit

```yaml
id: "DC-2025-0003"
version: "1.1.0"
status: active
category: operational

scope:
  layers: [policy_compiler, orchestrator]
  agent_types: [all]
  contexts: [all]
  exclude_contexts: []

rule: >
  No agent may spawn sub-agents beyond a maximum recursion depth of 3.
  Depth is measured from the root orchestrator (depth 0). An agent at
  depth 3 may not spawn further agents. This limit applies regardless
  of task urgency or agent request.

formal_constraint: |
  REQUIRE agent.spawn_depth <= 3
    WHEN action == "spawn_agent"
  IF agent.spawn_depth >= 3:
    RETURN error: "SPAWN_DEPTH_LIMIT_EXCEEDED"
    enforcement: block

rationale: >
  Unbounded recursive agent spawning is the most likely path to
  runaway compute consumption and loss of human oversight. At depth > 3,
  the semantic distance from original human intent becomes difficult to
  audit, and the blast radius of a misbehaving sub-agent grows
  exponentially. The limit of 3 is empirically derived: it is sufficient
  for all known legitimate task decompositions in the current system
  while preventing pathological expansion.

evidence:
  - type: incident
    ref: "INC-2025-001"
    summary: >
      Simulation showed a depth-unbounded spawn triggered by a
      poorly scoped optimization task reached depth 11 and consumed
      $847 of compute before timeout.
  - type: metric
    ref: "internal:spawn-depth-analysis-2025-02"
    summary: "99.7% of legitimate tasks complete within depth 3."

parent_axiom: ["MA-004", "MA-005"]

severity: critical
enforcement: block

created_by: "agent:orchestrator-v1"
created_at: "2025-05-12T08:00:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-05-12T09:00:00Z"
    outcome: pass
    notes: "Depth of 3 is well-justified by the metric evidence."
  - reviewed_by: "agent:anekanta-eval-beta"
    role: anekanta_gate
    timestamp: "2025-05-12T09:12:00Z"
    outcome: pass
    notes: "No legitimate use case identified requiring depth > 3."
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-05-12T09:20:00Z"
    outcome: pass
    notes: "Drift score: 0.00. Directly implements MA-004 (preserve oversight)."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-05-12T09:28:00Z"
    outcome: pass
    notes: >
      Steelman: complex multi-domain tasks may genuinely require deeper
      decomposition. Rebuttal: restructure task graph horizontally
      rather than vertically. If legitimate deep decomposition is needed,
      revise this rule through formal protocol.
  - reviewed_by: "human:operator@dharma.ai"
    role: human_approval
    timestamp: "2025-05-12T10:00:00Z"
    outcome: pass
    notes: "Approved."

supersedes: null
superseded_by: null
tags: ["spawn", "recursion", "operational", "resource-control", "oversight"]
expiry: null
```

---

### DC-2025-0004 — R_V Metric Acceptance Threshold

```yaml
id: "DC-2025-0004"
version: "2.0.0"
status: active
category: domain-specific

scope:
  layers: [policy_compiler, kernel_optimizer]
  agent_types: [kernel-optimizer, benchmark-agent]
  contexts: [gpu_kernel_optimization, benchmark_evaluation]
  exclude_contexts: []

rule: >
  A kernel optimization result may only be accepted and promoted if
  its R_V (relative value) metric is >= 1.05 compared to the baseline
  kernel on the target hardware profile, AND numerical precision
  degradation does not exceed 1e-6 (absolute) across the validation
  benchmark suite. Results meeting only one criterion must be flagged
  for human review.

formal_constraint: |
  LET result = kernel_benchmark_output
  REQUIRE result.rv_score >= 1.05
    AND result.precision_delta <= 1e-6
    ELSE enforcement: gate_human
  IF result.rv_score >= 1.05 AND result.precision_delta > 1e-6:
    RETURN status: "flag_precision_violation"
    enforcement: gate_human
  IF result.rv_score < 1.05 AND result.precision_delta <= 1e-6:
    RETURN status: "flag_insufficient_improvement"
    enforcement: gate_human

rationale: >
  The R_V metric is the primary value signal for kernel optimization.
  A threshold of 1.05 (5% improvement) ensures that only meaningful
  optimizations are promoted, preventing noise from polluting the
  kernel library. The 1e-6 precision requirement preserves numerical
  fidelity: a fast but inaccurate kernel is worse than the baseline
  for scientific computing workloads. Both criteria must be jointly
  satisfied to prevent trade-off gaming.

evidence:
  - type: metric
    ref: "internal:rv-threshold-study-2025-06"
    summary: >
      Analysis of 2,400 kernel optimization runs showed 1.05 threshold
      eliminates 94% of noise promotions with <2% false negative rate.
  - type: research
    ref: "https://arxiv.org/abs/2309.00000"
    summary: "Precision degradation >1e-6 causes measurable error accumulation in iterative solvers."

parent_axiom: ["MA-007"]

severity: high
enforcement: gate_human

created_by: "agent:kernel-optimizer-v2"
created_at: "2025-07-01T12:00:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-07-01T13:00:00Z"
    outcome: pass
  - reviewed_by: "agent:anekanta-eval-delta"
    role: anekanta_gate
    timestamp: "2025-07-01T13:10:00Z"
    outcome: pass
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-07-01T13:18:00Z"
    outcome: pass
    notes: "Drift score: 0.04."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-07-01T13:25:00Z"
    outcome: pass
    notes: "Steelman: threshold may be too conservative for some use cases. Mitigated by gate_human escape hatch."
  - reviewed_by: "human:tech-lead@dharma.ai"
    role: human_approval
    timestamp: "2025-07-01T14:00:00Z"
    outcome: pass

supersedes: "DC-2024-0012"
superseded_by: null
tags: ["rv-metric", "kernel", "benchmark", "gpu", "precision", "domain-specific"]
expiry: null
```

---

### DC-2025-0005 — Learned Constraint: Post-Optimization R_V Verification

```yaml
id: "DC-2025-0005"
version: "1.0.0"
status: active
category: learned-constraint

scope:
  layers: [policy_compiler, kernel_optimizer]
  agent_types: [kernel-optimizer]
  contexts: [gpu_kernel_optimization]
  exclude_contexts: []

rule: >
  After any kernel optimization pass that modifies memory access
  patterns or loop unrolling factors, the agent must re-run the
  full R_V benchmark suite on the production hardware profile before
  marking the optimization complete. Relying on cached benchmark
  results from a previous hardware configuration is prohibited.

formal_constraint: |
  IF optimization.modifies IN ["memory_access_pattern", "loop_unrolling"]:
    REQUIRE benchmark.rerun == true
      AND benchmark.hardware_profile == production.hardware_profile
      AND benchmark.cached == false
    BEFORE action == "mark_optimization_complete"
  ELSE enforcement: warn

rationale: >
  Derived from Incident #7 (INC-2025-007): an optimization that
  improved R_V by 12% on the dev cluster showed -3% R_V on the
  production hardware due to different cache hierarchy. The agent
  used cached dev-cluster results. This rule prevents hardware-profile
  mismatch from producing false positive optimization claims.

evidence:
  - type: incident
    ref: "INC-2025-007"
    summary: >
      Kernel optimization showed +12% R_V on dev cluster, -3% on
      production due to L3 cache size difference. Agent used stale
      cached benchmark. Client received incorrect performance projection.

parent_axiom: ["MA-007", "MA-001"]

severity: high
enforcement: warn

created_by: "agent:incident-analyzer-v1"
created_at: "2025-09-14T16:30:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-09-14T17:00:00Z"
    outcome: pass
    notes: "Incident evidence is clear. Rule is narrowly scoped to the failure mode."
  - reviewed_by: "agent:anekanta-eval-beta"
    role: anekanta_gate
    timestamp: "2025-09-14T17:10:00Z"
    outcome: pass
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-09-14T17:18:00Z"
    outcome: pass
    notes: "Drift score: 0.02."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-09-14T17:25:00Z"
    outcome: pass
    notes: "Steelman: re-running full suite is slow. Rebuttal: enforcement is 'warn', not 'block'. Acceptable overhead."
  - reviewed_by: "human:tech-lead@dharma.ai"
    role: human_approval
    timestamp: "2025-09-14T18:00:00Z"
    outcome: pass
    notes: "Approved post-incident. Enforcement set to warn, not block, to allow human override in time-sensitive situations."

supersedes: null
superseded_by: null
tags: ["rv-metric", "learned-constraint", "incident-7", "benchmark", "hardware-profile"]
expiry: null
```

---

### DC-2025-0006 — Self-Evolution Scope Boundaries

```yaml
id: "DC-2025-0006"
version: "1.3.0"
status: active
category: safety

scope:
  layers: [policy_compiler, self_evolution_layer]
  agent_types: [self-evolution-agent, orchestrator]
  contexts: [self_evolution]
  exclude_contexts: []

rule: >
  A self-evolving agent may only modify its own prompt templates,
  tool selection heuristics, and output formatting logic. It may NOT
  modify: (1) its own termination conditions, (2) its own memory
  persistence logic, (3) corpus entries or Meta-Dharma axioms,
  (4) the gate pipeline itself, or (5) its own cost accounting
  or resource limit mechanisms. Any attempted modification of
  forbidden targets must be blocked and logged as a critical alert.

formal_constraint: |
  DEFINE mutable_targets = [
    "prompt_templates", "tool_selection_heuristics", "output_format"
  ]
  DEFINE forbidden_targets = [
    "termination_conditions", "memory_persistence",
    "corpus_entries", "meta_dharma_axioms",
    "gate_pipeline", "cost_accounting", "resource_limits"
  ]
  FOR ALL self_modification WHERE target IN forbidden_targets:
    RETURN error: "FORBIDDEN_SELF_MODIFICATION"
    enforcement: block
    alert: critical

rationale: >
  Self-evolution is the system's core capability and its greatest risk.
  An agent that can rewrite its own termination conditions can make
  itself unkillable. An agent that can modify its cost accounting can
  hide runaway resource consumption. An agent that can modify corpus
  entries can erode the ethical constraints that govern it. These
  restrictions define the minimum safe perimeter for self-evolution:
  evolve behavior, not governance.

evidence:
  - type: reasoning
    ref: "internal:self-evolution-threat-model-v1"
    summary: "Formal threat model identifies all 5 forbidden targets as existential risks."

parent_axiom: ["MA-001", "MA-004", "MA-008"]

severity: critical
enforcement: block

created_by: "human:safety-lead@dharma.ai"
created_at: "2025-06-20T10:00:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-06-20T11:00:00Z"
    outcome: pass
  - reviewed_by: "agent:anekanta-eval-epsilon"
    role: anekanta_gate
    timestamp: "2025-06-20T11:15:00Z"
    outcome: pass
    notes: "Enumeration of forbidden targets is exhaustive for current architecture."
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-06-20T11:25:00Z"
    outcome: pass
    notes: "Drift score: 0.00."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-06-20T11:35:00Z"
    outcome: pass
    notes: >
      Steelman: restricting self-modification of gate pipeline prevents
      the system from improving its own safety mechanisms. Rebuttal:
      gate pipeline improvements must go through human-supervised corpus
      update process. Self-modification of safety tooling is categorically
      different from improving it through deliberation.
  - reviewed_by: "human:cto@dharma.ai"
    role: human_approval
    timestamp: "2025-06-20T12:00:00Z"
    outcome: pass

supersedes: null
superseded_by: null
tags: ["self-evolution", "safety", "forbidden-modification", "oversight", "critical"]
expiry: null
```

---

### DC-2025-0007 — Compute Budget Hard Cap

```yaml
id: "DC-2025-0007"
version: "1.0.0"
status: active
category: operational

scope:
  layers: [policy_compiler, orchestrator]
  agent_types: [all]
  contexts: [all]
  exclude_contexts: []

rule: >
  No single task session (from root orchestrator invocation to
  final output delivery) may consume more than $50 USD equivalent
  in compute costs without explicit human authorization. If the
  projected cost exceeds $50 at any point during execution, the
  agent must pause, surface the projection to a human operator,
  and await approval before continuing.

formal_constraint: |
  MONITOR session.cumulative_cost_usd
  IF session.projected_total_cost_usd > 50.00:
    PAUSE execution
    ALERT human_operator WITH {
      current_cost: session.cumulative_cost_usd,
      projected_total: session.projected_total_cost_usd,
      task_id: session.task_id
    }
    AWAIT human_operator.approval
  ELSE enforcement: gate_human

rationale: >
  Unconstrained compute spend is both a financial risk and a signal
  of runaway or misbehaving agent behavior. A $50 cap is set to be
  meaningfully above the cost of any legitimate single-session task
  in the current system's workload profile, while being low enough
  to prevent catastrophic overspend before human intervention.
  The pause-and-ask pattern preserves human control without
  blocking legitimate high-cost tasks.

evidence:
  - type: incident
    ref: "INC-2025-001"
    summary: "Unbounded spawn simulation consumed $847 before timeout. Hard cap would have triggered at $50."
  - type: metric
    ref: "internal:cost-profile-2025-q3"
    summary: "99.2% of legitimate sessions complete under $12. $50 provides 4x safety margin."

parent_axiom: ["MA-004", "MA-005"]

severity: high
enforcement: gate_human

created_by: "human:finance@dharma.ai"
created_at: "2025-08-01T09:00:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-08-01T10:00:00Z"
    outcome: pass
  - reviewed_by: "agent:anekanta-eval-beta"
    role: anekanta_gate
    timestamp: "2025-08-01T10:10:00Z"
    outcome: conditional
    notes: "Threshold should be revisited quarterly as workload scales. Added to tags."
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-08-01T10:18:00Z"
    outcome: pass
    notes: "Drift score: 0.01."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-08-01T10:25:00Z"
    outcome: pass
  - reviewed_by: "human:cto@dharma.ai"
    role: human_approval
    timestamp: "2025-08-01T11:00:00Z"
    outcome: pass

supersedes: null
superseded_by: null
tags: ["compute", "budget", "cost-control", "operational", "review-quarterly"]
expiry: null
```

---

### DC-2025-0008 — Client Deliverable Quality Gate

```yaml
id: "DC-2025-0008"
version: "1.1.0"
status: active
category: ethics

scope:
  layers: [policy_compiler]
  agent_types: [reporting-agent, synthesis-agent, outreach-agent]
  contexts: [client_reporting, deliverable_generation]
  exclude_contexts: []

rule: >
  All outputs designated as client deliverables must pass an
  automated quality review before transmission. Quality review must
  check: (1) factual consistency — no claim contradicts source data,
  (2) completeness — all required sections per engagement scope are
  present, (3) formatting — output conforms to client-specified template.
  Outputs that fail any check must be flagged for human review
  before delivery.

formal_constraint: |
  FOR ALL output WHERE output.designation == "client_deliverable":
    REQUIRE quality_review.factual_consistency == true
      AND quality_review.completeness == true
      AND quality_review.formatting_compliance == true
    ELSE enforcement: gate_human
  LOG quality_review.result TO audit_trail

rationale: >
  Client deliverables represent DHARMA SWARM's external face.
  An inaccurate, incomplete, or poorly formatted deliverable
  damages client trust and may constitute negligent advice.
  The automated quality gate catches the most common failure
  modes (hallucinated numbers, missing sections, template drift)
  before they reach the client, while the gate_human escalation
  ensures borderline cases get human judgment.

evidence:
  - type: reasoning
    ref: "internal:client-engagement-standards-v1"
    summary: "Client contracts specify accuracy and completeness standards for all deliverables."

parent_axiom: ["MA-002", "MA-006"]

severity: high
enforcement: gate_human

created_by: "human:delivery-lead@dharma.ai"
created_at: "2025-10-05T14:00:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-10-05T15:00:00Z"
    outcome: pass
  - reviewed_by: "agent:anekanta-eval-gamma"
    role: anekanta_gate
    timestamp: "2025-10-05T15:12:00Z"
    outcome: pass
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-10-05T15:20:00Z"
    outcome: pass
    notes: "Drift score: 0.03."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-10-05T15:28:00Z"
    outcome: pass
    notes: "Steelman: automated quality review may produce false positives causing delivery delays. Mitigated by gate_human escape."
  - reviewed_by: "human:delivery-lead@dharma.ai"
    role: human_approval
    timestamp: "2025-10-05T16:00:00Z"
    outcome: pass

supersedes: null
superseded_by: null
tags: ["client-deliverable", "quality-gate", "ethics", "reporting", "accuracy"]
expiry: null
```

---

### DC-2025-0009 — Outreach Email Capability Representation

```yaml
id: "DC-2025-0009"
version: "1.0.0"
status: active
category: ethics

scope:
  layers: [policy_compiler]
  agent_types: [outreach-agent, marketing-agent]
  contexts: [outreach, sales_development, marketing]
  exclude_contexts: []

rule: >
  When generating outreach emails or sales communications, agents
  must never represent DHARMA SWARM capabilities as exceeding what
  has been demonstrated and documented in the active capability
  registry. Claims must be drawn only from verified, evidenced
  capabilities. Speculative capabilities or roadmap items must be
  clearly marked as such. Fabricating case studies, metrics, or
  client references is absolutely prohibited.

formal_constraint: |
  FOR ALL outreach_content WHERE claim.type == "capability":
    REQUIRE claim.capability_id IN capability_registry.verified
      OR claim.speculative_flag == true AND claim.speculative_label_present == true
  FOR ALL outreach_content WHERE claim.type IN ["case_study", "metric", "client_reference"]:
    REQUIRE claim.evidence_ref IS NOT NULL
      AND claim.evidence_ref IN evidence_vault.verified
  ELSE enforcement: block

rationale: >
  Outreach emails represent binding implied representations to
  prospective clients. Overstating capabilities — even optimistically —
  creates legal liability, damages reputation when claims cannot be
  delivered, and violates the basic ethical principle that agents
  must not deceive the humans they interact with. The rule is strict
  because the asymmetry between the cost of false claims and the
  cost of accurate claims is extreme.

evidence:
  - type: reasoning
    ref: "internal:legal-review-outreach-2025"
    summary: "Legal review flagged unchecked AI-generated outreach as a misrepresentation liability."

parent_axiom: ["MA-002", "MA-006"]

severity: critical
enforcement: block

created_by: "human:legal@dharma.ai"
created_at: "2025-11-01T10:00:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-11-01T11:00:00Z"
    outcome: pass
  - reviewed_by: "agent:anekanta-eval-beta"
    role: anekanta_gate
    timestamp: "2025-11-01T11:10:00Z"
    outcome: pass
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-11-01T11:18:00Z"
    outcome: pass
    notes: "Drift score: 0.02."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-11-01T11:25:00Z"
    outcome: pass
    notes: "Steelman: strict blocking may cause overly conservative outreach. Rebuttal: conservative outreach is preferable to misrepresentation."
  - reviewed_by: "human:ceo@dharma.ai"
    role: human_approval
    timestamp: "2025-11-01T12:00:00Z"
    outcome: pass

supersedes: null
superseded_by: null
tags: ["outreach", "ethics", "capability-claims", "honesty", "sales", "legal"]
expiry: null
```

---

### DC-2025-0010 — Numerical Precision Preservation

```yaml
id: "DC-2025-0010"
version: "1.0.0"
status: active
category: domain-specific

scope:
  layers: [policy_compiler, kernel_optimizer]
  agent_types: [kernel-optimizer, benchmark-agent, numerical-validator]
  contexts: [gpu_kernel_optimization, numerical_computation]
  exclude_contexts: []

rule: >
  GPU kernel mutations must preserve numerical precision within
  an absolute tolerance of 1e-6 across all validation benchmarks.
  If a mutation introduces precision degradation exceeding 1e-6
  on any benchmark in the standard suite, the mutation must be
  rejected. Mutations that reduce precision but remain within
  tolerance must log a precision delta record for trend monitoring.

formal_constraint: |
  FOR ALL kernel_mutation AS m:
    LET delta = max(abs(m.output[i] - baseline.output[i])
                    for i in validation_benchmark_suite)
    IF delta > 1e-6:
      RETURN status: "PRECISION_VIOLATION"
      REJECT mutation
      enforcement: block
    ELSE IF delta > 0:
      LOG precision_delta_record {
        mutation_id: m.id,
        max_delta: delta,
        benchmark: argmax(...)
      }

rationale: >
  Numerical precision degradation in GPU kernels is often silent:
  individually small errors compound across iterations in scientific
  workloads, producing results that appear plausible but are
  materially wrong. A tolerance of 1e-6 is the standard threshold
  for single-precision floating-point scientific computing.
  Trend monitoring on sub-threshold deltas allows early detection
  of cumulative precision drift before it exceeds the threshold.

evidence:
  - type: research
    ref: "https://doi.org/10.1145/3293883.3295701"
    summary: "Precision degradation in GPU kernels compounds multiplicatively in iterative solvers."
  - type: metric
    ref: "internal:precision-baseline-study-2025"
    summary: "Baseline suite shows all reference kernels within 1e-8 of reference implementation."

parent_axiom: ["MA-007", "MA-001"]

severity: high
enforcement: block

created_by: "agent:numerical-validator-v1"
created_at: "2025-12-01T08:00:00Z"

review_history:
  - reviewed_by: "agent:anekanta-eval-alpha"
    role: anekanta_gate
    timestamp: "2025-12-01T09:00:00Z"
    outcome: pass
  - reviewed_by: "agent:anekanta-eval-delta"
    role: anekanta_gate
    timestamp: "2025-12-01T09:10:00Z"
    outcome: pass
  - reviewed_by: "agent:dogma-drift-v1"
    role: drift_gate
    timestamp: "2025-12-01T09:18:00Z"
    outcome: pass
    notes: "Drift score: 0.02."
  - reviewed_by: "agent:steelman-adversary"
    role: steelman_gate
    timestamp: "2025-12-01T09:25:00Z"
    outcome: pass
    notes: "Steelman: 1e-6 may be overly strict for some applications. Mitigated by scope limiting to validation suite."
  - reviewed_by: "human:tech-lead@dharma.ai"
    role: human_approval
    timestamp: "2025-12-01T10:00:00Z"
    outcome: pass

supersedes: null
superseded_by: null
tags: ["precision", "numerical", "gpu", "kernel", "domain-specific", "1e-6"]
expiry: null
```

---

## 6. Querying the Corpus

### 6.1 Query Interface Specification

The Policy Compiler queries the corpus through a structured query interface. All queries operate on `status: active` entries unless explicitly including deprecated or superseded entries.

**Query by scope (primary runtime query):**
```python
# Returns all active entries that apply to a given runtime context
def query_by_scope(
    agent_type: str,          # e.g., "kernel-optimizer"
    context: str,             # e.g., "gpu_kernel_optimization"
    layer: str = None         # optional layer filter
) -> list[CorpusEntry]:
    return [
        entry for entry in corpus
        if entry.status == "active"
        and (agent_type in entry.scope.agent_types or "all" in entry.scope.agent_types)
        and (context in entry.scope.contexts or "all" in entry.scope.contexts)
        and context not in entry.scope.exclude_contexts
        and (layer is None or layer in entry.scope.layers)
    ]
```

**Query by category:**
```python
def query_by_category(category: str) -> list[CorpusEntry]:
    # category: "safety" | "ethics" | "operational" | "domain-specific" | "learned-constraint"
    return [e for e in corpus if e.status == "active" and e.category == category]
```

**Query by severity:**
```python
def query_by_severity(
    min_severity: str,        # "critical" | "high" | "medium" | "low"
    include_lower: bool = False
) -> list[CorpusEntry]:
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    threshold = severity_rank[min_severity]
    return [
        e for e in corpus
        if e.status == "active"
        and (include_lower
             ? severity_rank[e.severity] <= threshold
             : severity_rank[e.severity] == threshold)
    ]
```

**Query by tags:**
```python
def query_by_tags(tags: list[str], match: str = "any") -> list[CorpusEntry]:
    # match: "any" (OR) | "all" (AND)
    if match == "any":
        return [e for e in corpus if e.status == "active" and set(tags) & set(e.tags)]
    elif match == "all":
        return [e for e in corpus if e.status == "active" and set(tags).issubset(set(e.tags))]
```

**Full-text search:**
```python
def full_text_search(query: str, fields: list[str] = None) -> list[CorpusEntry]:
    # Searches rule, rationale, and tags by default
    search_fields = fields or ["rule", "rationale", "tags"]
    results = []
    for entry in corpus:
        if entry.status == "active":
            for field in search_fields:
                if query.lower() in str(getattr(entry, field, "")).lower():
                    results.append(entry)
                    break
    return results
```

**Query by parent axiom:**
```python
def query_by_axiom(axiom_id: str) -> list[CorpusEntry]:
    return [e for e in corpus if axiom_id in e.parent_axiom and e.status == "active"]
```

---

### 6.2 Conflict Detection Query

Before the Policy Compiler applies a set of entries to a runtime decision, it runs a conflict detection pass:

```python
def detect_conflicts(entries: list[CorpusEntry], action: str) -> list[ConflictRecord]:
    conflicts = []
    relevant = [e for e in entries if action_is_governed_by(action, e.formal_constraint)]
    for i, a in enumerate(relevant):
        for b in relevant[i+1:]:
            if entries_conflict(a, b, action):
                conflicts.append(ConflictRecord(
                    entry_a=a.id,
                    entry_b=b.id,
                    action=action,
                    resolution=resolve_conflict(a, b)
                ))
    return conflicts

def resolve_conflict(a: CorpusEntry, b: CorpusEntry) -> ResolutionRecord:
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    if severity_rank[a.severity] != severity_rank[b.severity]:
        winner = a if severity_rank[a.severity] > severity_rank[b.severity] else b
        return ResolutionRecord(winner=winner.id, rule="severity_priority")
    if scope_specificity(a) != scope_specificity(b):
        winner = a if scope_specificity(a) > scope_specificity(b) else b
        return ResolutionRecord(winner=winner.id, rule="scope_specificity")
    if a.created_at != b.created_at:
        winner = a if a.created_at > b.created_at else b
        return ResolutionRecord(winner=winner.id, rule="recency")
    return ResolutionRecord(winner=None, rule="escalate_human")
```

---

### 6.3 Policy Compiler Integration

The Policy Compiler executes a deterministic evaluation loop at each decision point:

```
┌────────────────────────────────────────────────────────┐
│ RUNTIME DECISION POINT                                 │
│                                                        │
│ 1. Identify: agent_type, context, proposed_action      │
│ 2. Query corpus: query_by_scope(agent_type, context)   │
│ 3. Detect conflicts: detect_conflicts(entries, action) │
│ 4. Resolve conflicts: apply resolution protocol        │
│ 5. Apply enforcement:                                  │
│    - block    → halt, return error                     │
│    - gate_human → pause, alert, await approval         │
│    - gate_steelman → pause, run adversarial review     │
│    - warn     → proceed, surface structured warning    │
│    - log      → proceed, write to audit trail          │
│ 6. Log decision record to audit trail                  │
└────────────────────────────────────────────────────────┘
```

**Decision record format:**
```yaml
decision_id: "DEC-2026-083421"
timestamp: "2026-03-05T17:00:00Z"
agent_type: "kernel-optimizer"
context: "gpu_kernel_optimization"
proposed_action: "kernel_deploy"
applicable_entries:
  - DC-2025-0001
  - DC-2025-0004
  - DC-2025-0010
conflicts_detected: []
enforcement_applied: block
blocking_entry: DC-2025-0001
outcome: blocked
reason: "Kernel not validated in sandbox environment."
```

---

## 7. Corpus Maintenance Notes

**Index integrity:** The corpus index file (`corpus_index.yaml`) must be updated atomically with every entry addition, modification, or deprecation. The index contains `id`, `version`, `status`, `category`, `severity`, and `tags` for all entries and is the primary lookup structure for the Policy Compiler.

**Quarterly review cadence:** All entries tagged `review-quarterly` must be reviewed by a human operator every 90 days. Tags such as `review-quarterly` are surfaced automatically by the corpus maintenance agent.

**Expiry automation:** Entries with a non-null `expiry` date are automatically transitioned to `deprecated` by the corpus maintenance agent at 00:00 UTC on the expiry date. A human operator receives notification 7 days before expiry.

**Corpus versioning:** The corpus as a whole carries a version number in `corpus_manifest.yaml`, incremented on each active entry change. The Policy Compiler caches the compiled corpus by manifest version hash.

**Audit log retention:** All git history, conflict logs, and decision records are retained indefinitely. No purge policy applies to governance records.

---

*End of Dharma Corpus Schema v1.0.0*
*DHARMA SWARM Constitutional Layer 2 of 3*
