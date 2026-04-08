# Repo X-Ray: dharma_swarm
*Generated 2026-04-04T09:23:56 UTC*

## Overview
- **Path**: `/home/user/workspace/dharma_swarm`
- **Files analyzed**: 1231
- **Total lines**: 417,937 (353,018 non-blank)
- **Languages**: python: 1121 files (391,000 lines) | docs: 524 files (0 lines) | typescript: 108 files (26,868 lines) | config: 101 files (0 lines) | javascript: 2 files (69 lines)

## Architecture
### Top Modules
- **dharma_swarm**: 498 files, 216,846 lines, 1342 classes, 7001 functions — Contains 0 classes, 0 functions
- **tests**: 493 files, 136,490 lines, 1612 classes, 10195 functions — Contains 0 classes, 6 functions
- **dashboard**: 109 files, 26,792 lines, 0 classes, 0 functions
- **scripts**: 66 files, 20,712 lines, 20 classes, 439 functions — Contains 1 classes, 42 functions
- **api**: 23 files, 7,200 lines, 64 classes, 230 functions — Contains 0 classes, 0 functions
- **tools**: 16 files, 4,716 lines, 22 classes, 148 functions — Contains 2 classes, 14 functions
- **experiments**: 16 files, 3,154 lines, 23 classes, 111 functions — Contains 2 classes, 8 functions
- **(root)**: 4 files, 1,235 lines, 0 classes, 19 functions — Contains 0 classes, 5 functions
- **analysis**: 1 files, 442 lines, 0 classes, 9 functions — Contains 0 classes, 9 functions
- **hooks**: 1 files, 183 lines, 0 classes, 2 functions — Contains 0 classes, 2 functions
- **reports**: 1 files, 145 lines, 0 classes, 0 functions
- **spinouts**: 2 files, 12 lines, 0 classes, 1 functions — Contains 0 classes, 0 functions
- **benchmarks**: 1 files, 10 lines, 0 classes, 0 functions — Contains 0 classes, 0 functions

### Module Connections
- `(root)` → `dharma_swarm`
- `analysis` → `dharma_swarm`
- `api` → `dharma_swarm`
- `benchmarks` → `dharma_swarm`
- `dharma_swarm` → `api`
- `scripts` → `dharma_swarm`
- `tests` → `dharma_swarm`
- `tests` → `api`
- `tests` → `tools`

## Code Quality Signals
**Overall Grade: C** (score: 0.59)

- **Test ratio**: 72% (516 test files)
- **Docstring coverage**: 42%
- **Naming conventions**: 100%
- **Type annotation rate**: 86%
- **Avg complexity per file**: 47.5

## Complexity Hotspots
Functions with the highest cyclomatic complexity:

- `execute_single_step` in `scripts/allout_autopilot.py:698` — complexity=95, 304 lines
- `execute_single_step` in `scripts/strange_loop.py:1007` — complexity=95, 304 lines
- `tick` in `dharma_swarm/swarm.py:1999` — complexity=88, 355 lines
- `analyze_repo` in `dharma_swarm/xray.py:424` — complexity=87, 312 lines
- `run_task` in `dharma_swarm/agent_runner.py:1789` — complexity=85, 596 lines
- `check` in `dharma_swarm/telos_gates.py:382` — complexity=85, 328 lines
- `_handle_command` in `dharma_swarm/tui_legacy.py:809` — complexity=78, 278 lines
- `_dispatch_async` in `dharma_swarm/tui/app.py:1972` — complexity=77, 349 lines
- `resolve_runtime_provider_config` in `dharma_swarm/runtime_provider.py:153` — complexity=76, 261 lines
- `run_backtest` in `dharma_swarm/ginko_backtest.py:430` — complexity=72, 376 lines

## Largest Files
- `dharma_swarm/thinkodynamic_director.py` — 4,757 lines (complexity=786)
- `dharma_swarm/telos_substrate.py` — 4,324 lines (complexity=50)
- `dharma_swarm/evolution.py` — 2,888 lines (complexity=340)
- `dharma_swarm/agent_runner.py` — 2,711 lines (complexity=499)
- `dharma_swarm/swarm.py` — 2,691 lines (complexity=449)
- `dharma_swarm/providers.py` — 2,676 lines (complexity=481)
- `dharma_swarm/tui/app.py` — 2,254 lines (complexity=511)

## External Dependencies
217 external packages: `./ChatInterface, ./ChatOverlay, ./HealthBadge, ./api, ./controlPlanePageMeta.ts, ./controlPlaneRouteDeck.js, ./controlPlaneShell.ts, ./controlPlaneSurfaces.ts, ./dashboardNav.ts, ./dashboardPath.js, ./providers, ./runtimeControlPlane.ts, ./runtimeOperatorHandbook.ts, ./types, ./types.ts, ./useVizEvents, ./useVizSnapshot, @/components/chat/ChatInterface, @/components/chat/ChatOverlayWrapper, @/components/chat/ChatPanel`
*...and 197 more*

## Internal Coupling
Files with the most internal imports:

- `dharma_swarm/swarm.py` imports 55 internal modules
- `dharma_swarm/agent_runner.py` imports 35 internal modules
- `dharma_swarm/orchestrate_live.py` imports 33 internal modules
- `dharma_swarm/evolution.py` imports 30 internal modules
- `dharma_swarm/organism.py` imports 20 internal modules
- `api/main.py` imports 18 internal modules
- `scripts/system_integration_probe.py` imports 18 internal modules

## Risk Flags
- 🟡 **size**: Large file (767 lines). Consider splitting. (`api/chat_tools.py`)
- 🟡 **size**: Large file (1245 lines). Consider splitting. (`api/module_truth.py`)
- 🟡 **size**: Large file (1207 lines). Consider splitting. (`api/routers/chat.py`)
- 🟡 **size**: Large file (1085 lines). Consider splitting. (`dashboard/src/app/dashboard/agents/[id]/page.tsx`)
- 🟡 **size**: Large file (557 lines). Consider splitting. (`dashboard/src/app/dashboard/claude/page.tsx`)
- 🟡 **size**: Large file (1794 lines). Consider splitting. (`dashboard/src/app/dashboard/glm5/page.tsx`)
- 🟡 **size**: Large file (584 lines). Consider splitting. (`dashboard/src/app/dashboard/modules/page.tsx`)
- 🟡 **size**: Large file (751 lines). Consider splitting. (`dashboard/src/app/dashboard/observatory/page.tsx`)
- 🟡 **size**: Large file (2209 lines). Consider splitting. (`dashboard/src/app/dashboard/qwen35/page.tsx`)
- 🟡 **size**: Large file (560 lines). Consider splitting. (`dashboard/src/app/dashboard/synthesizer/page.tsx`)
- 🟡 **size**: Large file (1214 lines). Consider splitting. (`dashboard/src/components/chat/CommandPostWorkspace.tsx`)
- 🟡 **size**: Large file (523 lines). Consider splitting. (`dashboard/src/hooks/useChat.ts`)
- 🟡 **size**: Large file (1093 lines). Consider splitting. (`dashboard/src/lib/controlPlaneShell.test.ts`)
- 🟡 **size**: Large file (578 lines). Consider splitting. (`dashboard/src/lib/controlPlaneShell.ts`)
- 🟡 **size**: Large file (821 lines). Consider splitting. (`dashboard/src/lib/controlPlaneSurfaces.test.ts`)

## Recommended Next Steps
1. Improve documentation. Add docstrings to public functions and classes.
2. Refactor `execute_single_step` in `scripts/allout_autopilot.py` (complexity=95). Extract helper functions.
3. Split large files: api/chat_tools.py, api/module_truth.py, api/routers/chat.py (767+ lines each).
