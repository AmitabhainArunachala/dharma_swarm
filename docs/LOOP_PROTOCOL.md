# Loop Protocol -- Overnight Autonomous Iteration

## When to Use Overnight Loops vs. One-Shot Tasks

**Use a loop** when:
- The outcome is defined by a convergence criterion, not a fixed action
- Each iteration produces measurable progress toward a threshold
- The work benefits from accumulation (more seeds, more coverage, tighter bounds)
- You want to wake up and see a result, not babysit a process

**Use a one-shot task** when:
- The work is deterministic (run a script, deploy a config)
- There is no iteration -- the action either succeeds or fails
- The output does not improve with repeated attempts

## Anatomy of a Loop Template

Every loop template in `tools/loop_templates/` follows the same structure:

### 1. Module Docstring

States the convergence criterion, max iterations, and expected time per iteration.
This is the contract -- anyone reading the docstring knows when the loop stops.

### 2. LoopConfig Dataclass

```python
@dataclass
class LoopConfig:
    max_iterations: int = 50
    convergence_threshold: float = 0.1
    timeout_per_iteration: float = 300.0
    log_dir: Path = field(default_factory=lambda: OVERNIGHT_DIR)
```

All tuning knobs live here. No magic numbers buried in the loop body.
Every config has a `to_dict()` method for serialization.

### 3. IterationResult Dataclass

```python
@dataclass
class IterationResult:
    iteration: int
    converged: bool
    elapsed_seconds: float
    timestamp: str = ""
```

Each iteration produces one result. The loop returns the full list.
Results also have `to_dict()` for JSONL logging.

### 4. Convergence Check

The loop defines a clear boolean condition:
- `std(values) < threshold` (R_V optimization)
- `all gates covered` (gate coverage)
- `waste_ratio < 0.05` (conductor efficiency)

When the condition is met, the loop logs "converged" and exits.

### 5. Async `run()` Function

```python
async def run(
    config: LoopConfig | None = None,
    shutdown_event: asyncio.Event | None = None,
) -> list[IterationResult]:
```

Signature is always the same. Optional config, optional shutdown event,
returns iteration results. The async signature allows:
- Non-blocking I/O within iterations
- Integration with the orchestrate_live event loop
- Graceful shutdown via the event

### 6. JSONL Logging

Every iteration appends to `~/.dharma/overnight/<loop_name>.jsonl`:
- `loop_start` event with full config
- `iteration` event with full IterationResult
- `loop_end` event with summary

Format: one JSON object per line. Read with:
```bash
cat ~/.dharma/overnight/rv_optimization.jsonl | python3 -m json.tool --json-lines
```

### 7. Graceful Shutdown

Every loop checks `shutdown_event.is_set()` between iterations.
Signal handlers (SIGINT, SIGTERM) set the event.
The loop finishes the current iteration, logs a summary, and exits.

## Safety Bounds

Every loop template enforces:

| Bound | Purpose | Typical Value |
|-------|---------|---------------|
| `max_iterations` | Hard ceiling on loop count | 20-50 |
| `timeout_per_iteration` | Kill hung measurements | 60-300s |
| `convergence_threshold` | Stop condition | Problem-specific |
| Graceful shutdown | SIGINT/SIGTERM handler | Always present |

Additional constraints for production overnight runs:
- **No unbounded retries.** A failed measurement counts toward max_iterations.
- **No file growth bombs.** JSONL logs are append-only, one line per iteration.
  50 iterations at ~500 bytes each = ~25KB per run.
- **No runaway processes.** The loop is a single async coroutine. It does not
  spawn background processes that outlive it.
- **No silent failures.** Every exception is logged. The summary always written,
  even on early exit.

## How to Create a New Loop Template

1. Copy an existing template (rv_pipeline_optimization.py is a good starting point).

2. Define your convergence criterion in the module docstring.

3. Create a `LoopConfig` with your tuning knobs.

4. Create an `IterationResult` with your per-iteration metrics.

5. Implement `async def run()` with the standard signature.

6. Add JSONL logging to `~/.dharma/overnight/<your_loop>.jsonl`.

7. Add graceful shutdown via `shutdown_event`.

8. Add `__main__` block for direct execution.

9. Verify the import works:
   ```bash
   cd ~/dharma_swarm
   python3 -c "from tools.loop_templates.your_loop import LoopConfig; print('OK')"
   ```

Template checklist:
- [ ] Docstring with convergence criterion, max iterations, time estimate
- [ ] LoopConfig dataclass with to_dict()
- [ ] IterationResult dataclass with to_dict()
- [ ] async run() with standard signature
- [ ] JSONL logging (start, iteration, end events)
- [ ] Graceful shutdown
- [ ] __main__ entry point
- [ ] No hardcoded paths (use Path.home() / ".dharma" / ...)

## How to Run

### Direct execution

```bash
cd ~/dharma_swarm
python3 -m tools.loop_templates.rv_pipeline_optimization
python3 -m tools.loop_templates.telos_gate_coverage
python3 -m tools.loop_templates.conductor_efficiency
```

### From Python

```python
import asyncio
from tools.loop_templates.rv_pipeline_optimization import LoopConfig, run

config = LoopConfig(max_iterations=10, convergence_threshold=0.05)
results = asyncio.run(run(config=config))
```

### With custom measurement backend (R_V example)

```python
from geometric_lens.metrics import compute_rv  # real GPU pipeline

async def real_rv_measurement(seed: int) -> dict[str, float]:
    return await compute_rv(seed=seed, model="mistral-7b")

results = asyncio.run(run(measure_fn=real_rv_measurement))
```

### With graceful shutdown

```python
import asyncio, signal

shutdown = asyncio.Event()
signal.signal(signal.SIGINT, lambda *_: shutdown.set())

results = asyncio.run(run(shutdown_event=shutdown))
```

## Integration with orchestrate_live.py

Loop templates can be registered as additional loops in the live orchestrator.
The integration is optional -- loops run fine standalone.

To register a loop:

```python
# In orchestrate_live.py, add alongside existing loops:
async def run_overnight_loop(shutdown_event: asyncio.Event) -> None:
    from tools.loop_templates.rv_pipeline_optimization import LoopConfig, run
    config = LoopConfig(max_iterations=50)
    await run(config=config, shutdown_event=shutdown_event)
```

Then add it to the task group in the main orchestrator coroutine.
The loop shares the same shutdown_event as all other orchestrator loops,
so `dgc down` stops everything cleanly.

## Existing Templates

| Template | Convergence | Max Iter | Log File |
|----------|-------------|----------|----------|
| `rv_pipeline_optimization` | std(Cohen_d) < 0.1 | 50 | rv_optimization.jsonl |
| `telos_gate_coverage` | 11/11 gates covered | 20 | gate_coverage.jsonl |
| `conductor_efficiency` | waste_ratio < 0.05 | 30 | conductor_efficiency.jsonl |

## Reading Results

```bash
# Last iteration of any loop:
tail -2 ~/.dharma/overnight/rv_optimization.jsonl | python3 -m json.tool

# All iterations as a table:
python3 -c "
import json
with open('$HOME/.dharma/overnight/conductor_efficiency.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r.get('event') == 'iteration':
            print(f\"iter={r['iteration']:2d}  interval={r['wake_interval_tested']:6.1f}s  waste={r['waste_ratio']:.4f}\")
"
```
