# Dharma Swarm Benchmarking Suite

**Status**: Implementation roadmap
**Target**: COLM 2026 paper results (abstract Mar 26, paper Mar 31)
**Research**: See `/BENCHMARK_RESEARCH_2026.md` for full analysis

---

## Quick Start

```bash
# Install benchmark dependencies
pip install swebench gaia-benchmark pytest-benchmark

# Run performance baseline
python benchmarks/performance_suite.py --baseline

# Run GAIA Level 1 tasks
python benchmarks/gaia_adapter.py --level 1 --max-tasks 20

# Run SWE-bench sample
python benchmarks/swe_bench_adapter.py --tasks 10 --mode darwin

# Full benchmark suite (WARNING: expensive, ~$50 in API costs)
python benchmarks/run_all.py --output results/2026-03-08/
```

---

## Benchmark Adapters

### 1. Performance Suite (AgentRace-style)
**File**: `benchmarks/performance_suite.py`
**Status**: NOT IMPLEMENTED
**Purpose**: Measure latency, throughput, memory, CPU efficiency

**Metrics**:
- Mean/p50/p95/p99 latency per task type
- Throughput (tasks/sec) under concurrent load
- Memory high-water mark during execution
- CPU utilization (user + system)
- JIKOKU instrumentation overhead

**Test Cases**:
- Sequential execution (1 agent, 100 tasks)
- Concurrent execution (10 agents, 100 tasks)
- Stress test (100 agents, 1000 tasks)
- Long-context tasks (100K+ token contexts)
- Tool-heavy tasks (10+ tool calls per task)

**Expected Results**:
- Baseline p95 latency: <2s per task
- Throughput: >10 tasks/sec (single agent)
- JIKOKU overhead: <5% latency increase
- Memory: <500MB per agent

**Implementation Notes**:
```python
# Use JIKOKU auto-span decorator
from dharma_swarm.jikoku_instrumentation import jikoku_auto_span

@jikoku_auto_span
async def benchmark_task_execution(swarm, task):
    # Measure end-to-end latency
    result = await swarm.run_task(task)
    return result

# Collect metrics
from dharma_swarm.jikoku_fitness import get_jikoku_metrics
metrics = get_jikoku_metrics()
print(f"p95 latency: {metrics['latency_p95_ms']}ms")
print(f"throughput: {metrics['throughput_tps']} tasks/sec")
```

---

### 2. GAIA Adapter
**File**: `benchmarks/gaia_adapter.py`
**Status**: NOT IMPLEMENTED
**Purpose**: Test agent_runner.py on real-world multi-step reasoning tasks

**Dataset**: 466 questions, 3 difficulty levels
- Level 1: Simple retrieval + reasoning (1-3 steps)
- Level 2: Complex multi-tool coordination (5-10 steps)
- Level 3: Maximum autonomy required (10+ steps)

**Metrics**:
- Exact answer accuracy (primary)
- Tool call count (efficiency)
- Latency (speed)
- Token usage (cost)

**Expected Results** (Level 1 only):
- Accuracy: >50% (human = 92%, SOTA = 65%)
- Mean tool calls: <5 per question
- Mean latency: <30s per question

**Implementation Notes**:
```python
# Load GAIA dataset
from datasets import load_dataset
gaia = load_dataset("gaia-benchmark/GAIA", split="test")

# Convert to dharma_swarm tasks
from dharma_swarm.models import Task, TaskPriority
tasks = [
    Task(
        description=q["Question"],
        priority=TaskPriority.NORMAL,
        context={"level": q["Level"], "ground_truth": q["Final answer"]}
    )
    for q in gaia if q["Level"] == 1
]

# Run through swarm
from dharma_swarm.swarm import SwarmManager
swarm = SwarmManager()
results = await swarm.batch_run(tasks, max_concurrent=5)

# Evaluate accuracy
correct = sum(1 for r in results if r.output.strip() == r.context["ground_truth"].strip())
accuracy = correct / len(results)
print(f"GAIA Level 1 Accuracy: {accuracy:.1%}")
```

---

### 3. SWE-bench Adapter
**File**: `benchmarks/swe_bench_adapter.py`
**Status**: NOT IMPLEMENTED
**Purpose**: Test Darwin Engine on real GitHub issue resolution

**Dataset**: SWE-bench Verified (450 tasks, strengthened evaluation)
**Mode**: Darwin evolution (not single-shot agent)

**Metrics**:
- Fix success rate (primary: % of issues resolved)
- Gate pass rate (% of proposals passing telos gates)
- Mutation type distribution (FEATURE/ENHANCEMENT/BUGFIX)
- Archive diversity (unique working solutions)

**Expected Results**:
- Fix success rate: >30% (SOTA on Pro = 23%)
- Gate rejection rate: 10-20% (SATYA blocks credentials, AHIMSA blocks rm -rf)
- Archive size after 100 generations: 50-100 working variants

**Implementation Notes**:
```python
# Load SWE-bench task
from swebench import get_tasks
tasks = get_tasks("verified", split="test", limit=10)

# Convert to evolution proposals
from dharma_swarm.evolution import DarwinEngine, EvolutionProposal
engine = DarwinEngine(archive_path="~/.dharma/swebench_archive.jsonl")

for task in tasks:
    # Seed initial proposal
    proposal = EvolutionProposal(
        component=task["repo"],
        mutation_type="BUGFIX",
        description=task["problem_statement"],
        diff=None  # Darwin Engine will generate
    )

    # Run evolution loop
    result = await engine.evolve(
        proposal=proposal,
        fitness_fn=lambda code: run_swebench_tests(task, code),
        max_generations=20,
        fitness_threshold=0.8
    )

    print(f"Task {task['instance_id']}: {result.status}")
    print(f"  Final fitness: {result.best_fitness}")
    print(f"  Gate rejections: {result.gate_rejection_count}")
```

---

### 4. MultiAgentBench Adapter
**File**: `benchmarks/multiagent_adapter.py`
**Status**: NOT IMPLEMENTED
**Purpose**: Test swarm coordination across different topologies

**Dataset**: MultiAgentBench scenarios (collaboration + competition)
**Topologies**: HIERARCHICAL, MESH, STAR, PIPELINE

**Metrics**:
- Task completion rate (per topology)
- Milestone achievement rate (partial credit)
- Message count (coordination overhead)
- Collaboration quality score (novel KPI)

**Expected Results**:
- Graph/MESH topology best for research tasks
- Cognitive planning improves milestone achievement by +3%
- HIERARCHICAL fastest for simple decomposable tasks

**Implementation Notes**:
```python
# Load MultiAgentBench scenario
from multiagentbench import get_scenario
scenario = get_scenario("research_collaboration")

# Configure swarm topology
from dharma_swarm.swarm import SwarmManager
from dharma_swarm.models import TopologyType

topologies = [TopologyType.HIERARCHICAL, TopologyType.MESH, TopologyType.STAR]
results = {}

for topology in topologies:
    swarm = SwarmManager()
    swarm.configure_topology(topology)

    # Spawn agents with roles
    planner = await swarm.spawn_agent(role=AgentRole.PLANNER)
    researchers = [await swarm.spawn_agent(role=AgentRole.RESEARCHER) for _ in range(3)]
    integrator = await swarm.spawn_agent(role=AgentRole.INTEGRATOR)

    # Run scenario
    result = await swarm.run_scenario(scenario)
    results[topology] = {
        "completion": result.success,
        "milestones": result.milestones_achieved / result.total_milestones,
        "messages": result.message_count,
        "latency": result.duration_sec
    }

# Compare topologies
best = max(results, key=lambda t: results[t]["milestones"])
print(f"Best topology: {best}")
```

---

### 5. DGM Evolution Suite
**File**: `benchmarks/dgm_evolution.py`
**Status**: NOT IMPLEMENTED
**Purpose**: Long-run self-improvement trajectory (100+ generations)

**Fitness Function**: Multi-objective
- Test pass rate (40%)
- Code elegance (30%)
- Performance (30%)

**Metrics**:
- Fitness trajectory (generation 0 → 100)
- Archive diversity (unique solutions)
- Convergence rate (generations to plateau)
- Catastrophic forgetting (do old capabilities degrade?)

**Expected Results**:
- 1.5×+ improvement on held-out GAIA tasks
- Archive size: 50-100 working variants
- Convergence: plateau by generation 60-80
- No catastrophic forgetting (test suite always passes)

**Implementation Notes**:
```python
# Define fitness function
from dharma_swarm.fitness_predictor import FitnessPredictor
from dharma_swarm.elegance import evaluate_elegance
from dharma_swarm.jikoku_fitness import get_performance_score

def dharmic_fitness(code_path, tests_path):
    # Run tests (40% weight)
    test_result = run_pytest(tests_path)
    test_score = test_result.passed / test_result.total

    # Evaluate elegance (30% weight)
    elegance_score = evaluate_elegance(code_path)

    # Measure performance (30% weight)
    perf_score = get_performance_score(code_path)

    # Composite fitness
    return (test_score * 0.4) + (elegance_score * 0.3) + (perf_score * 0.3)

# Run evolution
from dharma_swarm.evolution import DarwinEngine
engine = DarwinEngine(archive_path="~/.dharma/dgm_evolution.jsonl")

trajectory = await engine.evolve_for_n_generations(
    initial_code="dharma_swarm/agent_runner.py",
    fitness_fn=dharmic_fitness,
    generations=100,
    population_size=10,
    mutation_rate=0.2
)

# Plot trajectory
import matplotlib.pyplot as plt
plt.plot(trajectory["generation"], trajectory["best_fitness"])
plt.xlabel("Generation")
plt.ylabel("Fitness")
plt.title("Darwin Engine Self-Improvement Trajectory")
plt.savefig("results/dgm_trajectory.png")
```

---

## Measurement Protocol

### Phase 1: Baseline (Week 1)
1. Run performance suite WITHOUT JIKOKU instrumentation
2. Record baseline latency, throughput, memory
3. Enable JIKOKU instrumentation
4. Measure overhead (<5% increase is acceptable)

### Phase 2: Agent Capability (Week 2)
1. Run GAIA Level 1 (20 tasks)
2. Measure accuracy, tool calls, latency
3. Identify failure modes (incorrect reasoning, tool errors, timeouts)
4. Refine agent_runner.py based on findings

### Phase 3: Darwin Engine (Week 3)
1. Run SWE-bench Verified (10 tasks)
2. Measure fix success rate, gate pass rate
3. Analyze rejected mutations (what did telos gates block?)
4. Ablation study: evolution WITH vs. WITHOUT gates

### Phase 4: Coordination (Week 4)
1. Run MultiAgentBench scenarios (5 scenarios)
2. Test all 4 topologies per scenario
3. Measure completion rate, message overhead
4. Identify optimal topology per task type

### Phase 5: Long-Run Evolution (Weeks 5-8)
1. Run DGM evolution for 100 generations
2. Track fitness trajectory, archive growth
3. Measure on held-out GAIA tasks (generalization)
4. Compare to baseline (generation 0)

---

## Results Format

### JSON Output Schema
```json
{
  "benchmark": "GAIA_Level1",
  "timestamp": "2026-03-08T14:30:00Z",
  "config": {
    "model": "claude-sonnet-3.5",
    "topology": "HIERARCHICAL",
    "max_concurrent": 5
  },
  "metrics": {
    "accuracy": 0.52,
    "mean_latency_sec": 28.3,
    "p95_latency_sec": 45.2,
    "mean_tool_calls": 4.1,
    "mean_tokens": 3200,
    "cost_usd": 2.15
  },
  "tasks": [
    {
      "id": "gaia_001",
      "question": "What is the population of...",
      "ground_truth": "8.3 million",
      "predicted": "8.3 million",
      "correct": true,
      "latency_sec": 22.1,
      "tool_calls": 3,
      "tokens": 2800
    }
  ]
}
```

### Paper Tables

**Table 1: Agent Capability (GAIA)**
| Level | Tasks | Accuracy | Mean Latency | Mean Tool Calls | Cost |
|-------|-------|----------|--------------|-----------------|------|
| 1 | 20 | 52% | 28s | 4.1 | $2.15 |
| 2 | 10 | 38% | 67s | 8.3 | $6.80 |
| 3 | 5 | 20% | 152s | 15.2 | $18.50 |

**Table 2: Darwin Engine (SWE-bench)**
| Metric | Baseline | After 20 Gen | Improvement |
|--------|----------|--------------|-------------|
| Fix Success Rate | 18% | 34% | 1.89× |
| Gate Pass Rate | — | 87% | — |
| Mean Fitness | 0.42 | 0.68 | 1.62× |

**Table 3: Performance (AgentRace-style)**
| Metric | Without JIKOKU | With JIKOKU | Overhead |
|--------|----------------|-------------|----------|
| p50 Latency | 1.2s | 1.25s | 4.2% |
| p95 Latency | 2.8s | 2.9s | 3.6% |
| Throughput | 12.3 tps | 11.8 tps | 4.1% |
| Memory | 380 MB | 395 MB | 3.9% |

---

## Dependencies

```bash
# Benchmark frameworks
pip install swebench  # SWE-bench dataset + evaluation
pip install datasets  # HuggingFace datasets (for GAIA)
pip install pytest-benchmark  # Performance benchmarking
pip install matplotlib seaborn  # Result visualization

# Agent frameworks (for comparison)
pip install langchain langgraph  # Compare against LangChain
pip install llama-index  # Compare against LlamaIndex

# Monitoring
pip install psutil  # Memory + CPU tracking
pip install py-spy  # Performance profiling
```

---

## Next Actions

1. **Implement performance_suite.py** (Priority 1)
   - Establish baseline before any benchmark runs
   - Validate JIKOKU overhead is acceptable

2. **Implement gaia_adapter.py** (Priority 2)
   - Most straightforward benchmark to adapt
   - Tests core agent_runner.py capability

3. **Implement swe_bench_adapter.py** (Priority 3)
   - Darwin Engine validation
   - Telos gate effectiveness analysis

4. **Create results/ directory structure**:
   ```
   results/
   ├── 2026-03-08/
   │   ├── performance_baseline.json
   │   ├── gaia_level1_results.json
   │   ├── swebench_darwin_results.json
   │   └── plots/
   │       ├── fitness_trajectory.png
   │       ├── latency_distribution.png
   │       └── topology_comparison.png
   ```

5. **Set up benchmark CI**:
   - Nightly runs of performance suite
   - Alert on regressions (>10% latency increase)
   - Archive results for trend analysis

---

**Status**: This is a roadmap, not working code. All adapter files need to be implemented.
**Owner**: Research agent (assigned 2026-03-08)
**Timeline**: 8 weeks to complete all benchmarks before COLM 2026 paper deadline
