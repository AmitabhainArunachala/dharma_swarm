# Repo X-Ray: dharma_swarm
*Generated 2026-03-13T15:07:21 UTC*

## Overview
- **Path**: `/Users/dhyana/dharma_swarm`
- **Files analyzed**: 446
- **Total lines**: 152,785 (128,909 non-blank)
- **Languages**: config: 726 files (0 lines) | docs: 603 files (0 lines) | python: 441 files (152,079 lines) | javascript: 5 files (706 lines)

## Architecture
### Top Modules
- **dharma_swarm**: 205 files, 88,438 lines, 556 classes, 3045 functions — Contains 0 classes, 11 functions
- **tests**: 194 files, 51,425 lines, 378 classes, 3508 functions — Contains 2 classes, 20 functions
- **scripts**: 38 files, 11,670 lines, 8 classes, 277 functions — Contains 0 classes, 1 functions
- **.claude**: 5 files, 706 lines, 0 classes, 0 functions
- **(root)**: 1 files, 351 lines, 0 classes, 4 functions — Contains 0 classes, 4 functions
- **hooks**: 1 files, 183 lines, 0 classes, 2 functions — Contains 0 classes, 2 functions
- **spinouts**: 2 files, 12 lines, 0 classes, 1 functions — Contains 0 classes, 0 functions

### Module Connections
- `tests` → `dharma_swarm`
- `scripts` → `dharma_swarm`

## Code Quality Signals
**Overall Grade: C** (score: 0.53)

- **Test ratio**: 81% (199 test files)
- **Docstring coverage**: 42%
- **Naming conventions**: 100%
- **Type annotation rate**: 31%
- **Avg complexity per file**: 48.1

## Complexity Hotspots
Functions with the highest cyclomatic complexity:

- `execute_single_step` in `scripts/strange_loop.py:1007` — complexity=95, 304 lines
- `execute_single_step` in `scripts/allout_autopilot.py:698` — complexity=95, 304 lines
- `analyze_repo` in `dharma_swarm/xray.py:424` — complexity=87, 312 lines
- `_handle_command` in `dharma_swarm/tui_legacy.py:807` — complexity=78, 278 lines
- `_dispatch_async` in `dharma_swarm/tui/app.py:1953` — complexity=77, 349 lines
- `cmd_swarm` in `dharma_swarm/dgc_cli.py:1174` — complexity=72, 275 lines
- `build_darwin_status_text` in `dharma_swarm/tui_helpers.py:292` — complexity=68, 243 lines
- `check` in `dharma_swarm/telos_gates.py:148` — complexity=61, 260 lines
- `on_provider_runner_agent_event` in `dharma_swarm/tui/app.py:1117` — complexity=57, 176 lines
- `execute_pending_tasks` in `dharma_swarm/thinkodynamic_director.py:3614` — complexity=48, 196 lines

## Largest Files
- `dharma_swarm/dgc_cli.py` — 4,591 lines (complexity=592)
- `dharma_swarm/thinkodynamic_director.py` — 4,175 lines (complexity=712)
- `dharma_swarm/evolution.py` — 2,392 lines (complexity=260)
- `dharma_swarm/tui/app.py` — 2,233 lines (complexity=509)
- `tests/test_evolution.py` — 1,732 lines (complexity=330)
- `dharma_swarm/runtime_state.py` — 1,636 lines (complexity=181)
- `dharma_swarm/orchestrator.py` — 1,620 lines (complexity=256)

## External Dependencies
74 external packages: `adapters, aiofiles, aiosqlite, anthropic, app, artifacts, base, btw, child_process, chunker, claude, codex, commands, conversation_memory, croniter, crypto, data_flywheel, dharma_dark, ecosystem_map, engine`
*...and 54 more*

## Internal Coupling
Files with the most internal imports:

- `dharma_swarm/dgc_cli.py` imports 52 internal modules
- `dharma_swarm/swarm.py` imports 36 internal modules
- `dharma_swarm/evolution.py` imports 25 internal modules
- `tests/test_godel_claw_e2e.py` imports 14 internal modules
- `tests/test_integration.py` imports 13 internal modules
- `dharma_swarm/pulse.py` imports 12 internal modules
- `dharma_swarm/dse_integration.py` imports 12 internal modules

## Risk Flags
- 🟡 **size**: Large file (596 lines). Consider splitting. (`tests/test_monitor.py`)
- 🟡 **size**: Large file (523 lines). Consider splitting. (`tests/test_semantic_evolution.py`)
- 🟡 **size**: Large file (1056 lines). Consider splitting. (`tests/test_thinkodynamic_director.py`)
- 🟡 **size**: Large file (893 lines). Consider splitting. (`tests/test_gaia.py`)
- 🟡 **size**: Large file (750 lines). Consider splitting. (`tests/test_orchestrator.py`)
- 🟡 **size**: Large file (1472 lines). Consider splitting. (`tests/test_dgc_cli.py`)
- 🟡 **size**: Large file (951 lines). Consider splitting. (`tests/test_ouroboros.py`)
- 🟡 **size**: Large file (714 lines). Consider splitting. (`tests/test_integration.py`)
- 🟡 **size**: Large file (1732 lines). Consider splitting. (`tests/test_evolution.py`)
- 🟡 **size**: Large file (614 lines). Consider splitting. (`tests/test_bridge.py`)
- 🟡 **size**: Large file (1268 lines). Consider splitting. (`tests/test_dse_integration.py`)
- 🟡 **size**: Large file (507 lines). Consider splitting. (`tests/tui/test_app_plan_mode.py`)
- 🟡 **size**: Large file (1601 lines). Consider splitting. (`scripts/strange_loop.py`)
- 🟡 **size**: Large file (1267 lines). Consider splitting. (`scripts/allout_autopilot.py`)
- 🟡 **size**: Large file (518 lines). Consider splitting. (`scripts/psmv_hyperfile_bootstrap.py`)

## Recommended Next Steps
1. Improve documentation. Add docstrings to public functions and classes.
2. Refactor `execute_single_step` in `scripts/strange_loop.py` (complexity=95). Extract helper functions.
3. Split large files: tests/test_monitor.py, tests/test_semantic_evolution.py, tests/test_thinkodynamic_director.py (596+ lines each).
