# Terminal Convergence Refactor Sequence

## Goal

Clean up the terminal architecture without reducing capability.

The target state is:

- one shared operator brain in `dharma_swarm/operator_core/`
- one primary shell in `terminal/`
- one transitional gateway in `dharma_swarm/terminal_bridge.py`
- zero duplicated session, routing, permission, or runtime truth semantics
- Bun TUI as the elite coding cockpit
- dashboard as a later second shell over the same brain

This sequence is ordered to preserve power while reducing architectural noise.

## Keep, Move, Retire

### Keep as canonical foundations

- `dharma_swarm/operator_core/contracts.py`
- `dharma_swarm/operator_core/adapters.py`
- `dharma_swarm/operator_core/session_views.py`
- `dharma_swarm/tui/engine/events.py`
- `dharma_swarm/tui/engine/adapters/*`
- `dharma_swarm/tui/model_routing.py`
- `dharma_swarm/tui/commands/system_commands.py`
- `terminal/src/*`

### Move into operator-core

- `dharma_swarm/tui/engine/session_store.py`
- `dharma_swarm/tui/engine/governance.py`
- routing-normalization seams currently in `dharma_swarm/terminal_bridge.py`
- runtime snapshot assembly seams currently in `dharma_swarm/terminal_bridge.py`

### Retire as architecture authorities

- `dharma_swarm/tui/app.py`
- `dharma_swarm/tui/screens/*`
- `dharma_swarm/tui/widgets/*`

These can remain temporarily, but they should stop owning domain truth.

## File-by-File Plan

### Phase 1: Freeze the brain boundary

Create:

- `dharma_swarm/operator_core/events.py`
- `dharma_swarm/operator_core/runtime_views.py`
- `dharma_swarm/operator_core/routing.py`
- `dharma_swarm/operator_core/permissions.py`
- `dharma_swarm/operator_core/session_store.py`
- `dharma_swarm/operator_core/bridge_api.py`

Move or wrap:

- `dharma_swarm/tui/engine/session_store.py` -> shared session-store implementation under `operator_core/session_store.py`
- `dharma_swarm/tui/engine/governance.py` -> shared permission/governance implementation under `operator_core/permissions.py`
- route/model policy shaping out of `terminal_bridge.py` -> `operator_core/routing.py`
- operator/runtime snapshot shaping out of `terminal_bridge.py` -> `operator_core/runtime_views.py`

Keep transitional shims:

- old `tui/engine/session_store.py` should import from `operator_core.session_store`
- old `tui/engine/governance.py` should import from `operator_core.permissions`

Exit condition:

- all shared semantics have one canonical implementation under `operator_core`

### Phase 2: Shrink the bridge into a gateway

`dharma_swarm/terminal_bridge.py` should stop owning business logic.

Move out:

- `_build_model_policy_summary`
- `_build_operator_snapshot`
- `_build_agent_routes`
- `_build_evolution_surface`
- session catalog/detail assembly
- runtime shaping logic

Keep in bridge:

- stdio lifecycle
- request routing
- adapter invocation
- shell request/response transport
- temporary text rendering only where the Bun shell still needs strings

Add:

- bridge request handlers should call `operator_core.bridge_api`
- bridge responses should carry both:
  - typed payload
  - temporary `content` string for backward compatibility

Exit condition:

- bridge becomes a thin transport and compatibility layer

### Phase 3: Separate shell state from domain state

In `terminal/src/`, keep only UI-local state.

Domain truth that should no longer live in Bun state reducers:

- routing semantics
- session semantics
- permission semantics
- runtime truth assembly

Keep in Bun state:

- active tab
- focus
- model picker visibility
- composer content
- transcript render objects
- local pane selection

Refactor targets:

- `terminal/src/types.ts`
- `terminal/src/state.ts`
- `terminal/src/protocol.ts`
- `terminal/src/app.tsx`

Add:

- typed transcript items instead of plain line strings
- shell view-model mappers that consume operator-core payloads

Exit condition:

- Bun shell becomes a presentation and interaction layer over operator-core truth

### Phase 4: Replace string transcripts with typed transcript objects

Current weakness:

- transcript lines are still `kind + text`

Target:

- `kind + structured payload + render segments`

Add:

- `terminal/src/transcriptTypes.ts`
- `terminal/src/transcriptMappers.ts`

Target item classes:

- heading
- subheading
- assistant_text
- command
- tool_call
- tool_result
- approval
- warning
- error
- state_block

Refactor:

- `terminal/src/protocol.ts` should output structured transcript items
- `terminal/src/components/TranscriptPane.tsx` should render them directly

Exit condition:

- the cockpit becomes cleaner while remaining more powerful

### Phase 5: Make sessions first-class in the Bun shell

Current state:

- sessions are visible only indirectly through bridge calls and the Notes rail

Target:

- dedicated `Sessions` pane and session inspector

Files to add:

- `terminal/src/components/SessionsPane.tsx`
- `terminal/src/sessionProtocol.ts`

Files to update:

- `terminal/src/types.ts`
- `terminal/src/state.ts`
- `terminal/src/app.tsx`
- `terminal/src/mockContent.ts`

Features:

- recent sessions
- replay integrity
- provider/model route
- compaction preview
- fork ancestry
- current status

Exit condition:

- session memory stops feeling bolted on

### Phase 6: Make permissions first-class in the Bun shell

Current state:

- shared permission decisions exist, but shell does not yet surface them cleanly

Target:

- visible approval lane
- blocked action lane
- explicit rationale and risk classes

Files to add:

- `terminal/src/components/ApprovalPane.tsx`
- `terminal/src/permissionProtocol.ts`

Files to update:

- `terminal/src/app.tsx`
- `terminal/src/protocol.ts`
- `terminal/src/types.ts`

Exit condition:

- every blocked or gated action becomes legible

### Phase 7: Reduce Bun pane sprawl

Converge toward these top-level panes:

- Chat
- Repo
- Runtime
- Control
- Agents
- Models
- Sessions
- Ontology
- Evolution

Likely absorb/remove:

- `mission` -> move into startup/session bootstrap
- `notes` -> replace with `sessions`
- `commands` -> collapse into command palette and inline command help
- `thinking` and `tools` -> remain as subviews or filters, not necessarily top-level panes

Exit condition:

- fewer panes, stronger panes

### Phase 8: Demote the Python Textual shell

Once Bun covers:

- prompt loop
- transcript
- sessions
- runtime truth
- permissions
- routing
- model switching

Then:

- mark `dharma_swarm/tui/app.py` as deprecated shell
- preserve engine/adapters only where still reused
- stop adding new domain features to `tui/screens/*` and `tui/widgets/*`

Exit condition:

- there is only one authoritative operator shell

## Delete / Deprecate Candidates

### Mark deprecated first

- `dharma_swarm/tui/app.py`
- `dharma_swarm/tui/screens/btw.py`
- `dharma_swarm/tui/screens/command_center.py`
- `dharma_swarm/tui/screens/main.py`
- `dharma_swarm/tui/screens/splash.py`
- `dharma_swarm/tui/widgets/*`

### Delete only after Bun parity

- shell-specific state and rendering logic from `dharma_swarm/tui/app.py`
- duplicated stream rendering code in Textual widgets
- duplicated command-center UI logic in Textual once Bun has equivalent or better surfaces

## What Not To Do

- do not delete provider adapters
- do not delete canonical event definitions
- do not move shell rendering concerns into operator-core
- do not create dashboard-only or Bun-only semantics for sessions or permissions
- do not add more placeholder panes
- do not keep `terminal_bridge.py` as a permanent mega-file

## Immediate Next Refactors

If doing this in the next work session, the highest-value exact order is:

1. create `operator_core/session_store.py` and make old TUI session store a shim
2. create `operator_core/permissions.py` and make old governance module a shim
3. create `operator_core/runtime_views.py` and move operator/runtime snapshot assembly there
4. create `operator_core/bridge_api.py` and route bridge handlers through it
5. add `Sessions` pane to Bun and replace `Notes`
6. convert Bun transcript from string lines to typed transcript items
7. add approval/permission transcript items and approval pane
8. mark Textual shell deprecated

## Standard

The cleanup is successful if:

- the system feels simpler
- the runtime truth is stronger
- the cockpit is cleaner
- permissions are more visible
- session memory is more powerful
- the Bun shell is clearly the primary shell
- the dashboard can later consume the same brain without rework

The cleanup fails if:

- the architecture looks cleaner but loses inspectability
- shared semantics drift back into shell code
- the Bun shell becomes prettier but less capable
- the Python shell remains a second authority
