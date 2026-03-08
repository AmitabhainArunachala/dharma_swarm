# Real-World Agent Benchmarks for Dharma Swarm (2026 Research)

**Research Date**: 2026-03-08
**Purpose**: Identify state-of-the-art benchmarks adaptable to dharma_swarm's self-evolving, multi-agent architecture

---

## Executive Summary

Five benchmark categories are highly relevant to dharma_swarm:

1. **SWE-bench** → Code evolution capability (Darwin Engine testing)
2. **GAIA** → Multi-step reasoning + tool use (agent_runner validation)
3. **MultiAgentBench** → Coordination protocols (swarm topology testing)
4. **AgentRace** → Performance optimization (JIKOKU-style metrics)
5. **Darwin Gödel Machine** → Self-improvement benchmarking (evolution archive validation)

**Key Finding**: dharma_swarm's architecture (evolution.py, swarm.py, agent_runner.py) maps well to these benchmarks. The Darwin Engine could be tested against SWE-bench-style self-modification tasks, while swarm coordination could be evaluated using MultiAgentBench protocols.

---

## 1. SWE-bench: Software Engineering Agent Benchmark

### What It Tests
- **Core Capability**: Autonomous code modification to resolve real GitHub issues
- **Domains**: 12 open-source Python repositories
- **Task Structure**: Real GitHub issues → agent proposes fix → automated validation
- **Variants**:
  - SWE-bench (812 tasks)
  - SWE-bench Verified (450 tasks, strengthened evaluation)
  - SWE-bench Pro (long-horizon tasks)
  - SWE-EVO (autonomous software evolution, not just single-issue repair)

### How Success is Measured
- **Primary Metric**: % of issues correctly resolved (automated test suite passes)
- **Evaluation**: Stateful comparison of repository state vs. expected outcome
- **Secondary Metrics**:
  - Token usage
  - Number of tool calls
  - Time to resolution

### Success Rates (2026)
| Model/System | Success Rate | Benchmark |
|--------------|--------------|-----------|
| GPT-5, Opus 4.1 | 23% | SWE-bench Pro |
| State-of-the-art | 70%+ | SWE-bench Verified |
| SWE-EVO improvements | 20.0% → 50.0% | SWE-bench (via self-modification) |

### Hard Tasks
- **Long-horizon refactoring**: Multi-file changes with cascading dependencies
- **Cross-module changes**: Requires understanding entire codebase architecture
- **Breaking API changes**: Must update all downstream callers
- **Edge case handling**: Obscure bugs requiring deep domain knowledge

### Dharma Swarm Adaptation
**Map to Darwin Engine**:
- Each SWE-bench issue = evolution proposal
- Gate check → telos_gates.py validation
- Code modification → diff_applier.py
- Testing → sandbox.py execution
- Fitness evaluation → test pass rate + elegance.py score
- Archive results → archive.py storage

**Relevance Score**: ⭐⭐⭐⭐⭐
Direct alignment with dharma_swarm's self-modification architecture. The Darwin Engine (evolution.py) could be benchmarked by giving it SWE-bench tasks and measuring:
- Proposal quality (before gating)
- Gate pass rate (dharmic alignment)
- Fix success rate (after evolution)
- Archive diversity (mutation exploration)

---

## 2. GAIA: General AI Assistants Benchmark

### What It Tests
- **Core Capability**: Real-world question answering requiring multi-step reasoning
- **Fundamental Abilities**:
  - Multi-modality handling (text, images, PDFs)
  - Web browsing and navigation
  - Tool use proficiency
  - Long-context reasoning (5-10 steps for Level 2, 10+ for Level 3)
- **Task Structure**: 466 questions with unambiguous answers, organized into difficulty levels

### How Success is Measured
- **Primary Metric**: Exact answer accuracy (0/1 scoring)
- **Difficulty Levels**:
  - Level 1: Simple retrieval + reasoning (1-3 steps)
  - Level 2: Complex multi-tool coordination (5-10 steps)
  - Level 3: Highly challenging, maximum autonomy required (10+ steps)
- **Evaluation**: Human-verifiable ground truth answers retained for leaderboard

### Success Rates (2026)
| System | Accuracy | Notes |
|--------|----------|-------|
| Human respondents | 92% | Baseline capability |
| GPT-4 + plugins (2023) | 15% | Early baseline |
| H2O.ai h2oGPTe | 65% | Current SOTA (2026 leaderboard) |
| Google (best) | 49% | |
| Microsoft (best) | 38% | |

### Hard Tasks
- **Multi-domain reasoning**: Combining web search + document analysis + calculation
- **Long dependency chains**: Step N depends on correct completion of steps 1 through N-1
- **Ambiguity resolution**: Clarifying underspecified questions through inference
- **Tool orchestration**: Selecting correct tool sequence from 10+ available tools

### Dharma Swarm Adaptation
**Map to Agent Runner**:
- GAIA question → Task object in swarm.py
- Multi-step reasoning → agent_runner.py orchestration loop
- Tool use → providers.py multi-model routing
- Context management → context.py 5-layer system
- Memory across steps → memory.py StrangeLoopMemory

**Test Protocol**:
1. Load GAIA questions into task_board.py
2. Assign to agents via swarm.spawn_agent()
3. Track tool calls, context switches, memory retrievals
4. Measure accuracy + token efficiency + latency

**Relevance Score**: ⭐⭐⭐⭐⭐
Perfect match for dharma_swarm's agent_runner.py. Tests real-world task completion with the exact capabilities dharma_swarm provides: multi-provider LLM routing, tool use, memory, and multi-step reasoning.

---

## 3. MultiAgentBench: Coordination & Collaboration Benchmark

### What It Tests
- **Core Capability**: Multi-agent collaboration AND competition in interactive scenarios
- **Coordination Protocols**:
  - Star topology (central coordinator)
  - Chain topology (sequential handoffs)
  - Tree topology (hierarchical delegation)
  - Graph topology (peer-to-peer mesh)
- **Strategies Evaluated**:
  - Group discussion (consensus building)
  - Cognitive planning (shared mental models)
  - Competitive negotiation
  - Resource allocation under constraints

### How Success is Measured
- **Primary Metrics**:
  - Task completion rate (binary success/fail)
  - Milestone achievement rate (partial credit for progress)
  - Collaboration quality score (novel KPI measuring coordination efficiency)
- **Protocol Performance**: Measured separately for each topology type
- **Strategy Effectiveness**: Improvement delta vs. baseline (e.g., cognitive planning +3% milestone achievement)

### Success Rates (2026)
| Model/Configuration | Task Score | Notes |
|---------------------|------------|-------|
| gpt-4o-mini | Highest avg | Best overall performer |
| Graph topology | Best | Outperforms star/chain/tree in research scenarios |
| Cognitive planning | +3% | Milestone achievement improvement over baseline |

### Hard Tasks
- **Conflicting objectives**: Agents with competing goals must negotiate
- **Information asymmetry**: Agents hold partial information, must share strategically
- **Dynamic replanning**: Task requirements change mid-execution
- **Scalability**: Performance degrades with >5 agents in complex topologies

### Dharma Swarm Adaptation
**Map to Swarm Topology**:
- MultiAgentBench scenarios → swarm_state.topology configuration
- Coordination protocols → models.py TopologyType enum
- Message passing → message_bus.py inter-agent messaging
- Milestone tracking → task_board.py subtask decomposition
- Agent roles → models.py AgentRole (planner, coder, researcher, tester, integrator)

**Test Protocol**:
1. Implement MultiAgentBench scenarios as swarm tasks
2. Vary topology: HIERARCHICAL, MESH, STAR, PIPELINE
3. Measure:
   - Task completion rate per topology
   - Message count (coordination overhead)
   - Latency (critical path length)
   - Role specialization effectiveness

**Relevance Score**: ⭐⭐⭐⭐
Strong alignment with dharma_swarm's multi-agent architecture. The swarm.py coordinator and message_bus.py are designed for exactly this type of coordination. Testing would validate topology choices and reveal optimal agent counts per task type.

---

## 4. AgentRace: Performance & Efficiency Benchmark

### What It Tests
- **Core Capability**: Runtime performance, scalability, and efficiency of agent frameworks
- **Metrics Measured**:
  - **Latency**: Time to first token, total response time
  - **Throughput**: Tokens/sec across many concurrent requests
  - **Tool invocation latency**: Time to call external tools
  - **Communication overhead**: Message passing cost in multi-agent systems
  - **Memory efficiency**: RAM usage during execution
  - **CPU efficiency**: Compute resource utilization

### How Success is Measured
- **Composite Score**: Weighted average
  - Latency: 27.8%
  - Throughput: 33.3%
  - Memory: 22.2%
  - CPU: 16.7%
- **Controlled Comparisons**: Same tasks across different frameworks
- **Scalability Tests**: Performance degradation as load increases

### Success Rates (2026)
| Framework | Performance | Notes |
|-----------|-------------|-------|
| AutoAgents (Rust) | Baseline +25% | Beats avg Python framework on latency |
| AutoAgents vs. LangGraph | +43.7% | Specific head-to-head comparison |
| Caching optimization | 41× improvement | Tool-call latency: 2,485ms → 0.01ms |
| Batching + Pipelining | Significant gains | Maximizes throughput |

**Target Metrics (Production)**:
- Voice AI latency: <500ms (customers hang up 40% more at >1sec)
- Tool-call latency (cached): <10ms
- First-token latency: <300ms (Mistral Large 2512 benchmark)

### Hard Tasks
- **Concurrent request handling**: 100+ simultaneous agents without degradation
- **Cold-start optimization**: Minimize first-run overhead
- **Memory-bounded execution**: Operate under strict RAM limits (e.g., 2GB)
- **Long-context throughput**: Maintain tokens/sec with 100K+ context windows

### Dharma Swarm Adaptation
**Map to JIKOKU Instrumentation**:
- AgentRace metrics → jikoku_instrumentation.py @jikoku_auto_span decorator
- Throughput testing → Stress test swarm.spawn_agent() concurrency
- Latency profiling → Measure agent_runner.py execution time per task
- Memory tracking → Monitor memory.py StrangeLoopMemory database size
- Tool-call latency → providers.py model switching overhead

**Test Protocol**:
1. Instrument all critical paths with JIKOKU spans
2. Run 100 concurrent tasks through swarm
3. Measure:
   - Mean/p50/p95/p99 latency per task
   - Throughput (tasks/sec)
   - Memory high-water mark
   - CPU utilization
4. Identify bottlenecks → feed into Darwin Engine for optimization proposals

**Relevance Score**: ⭐⭐⭐⭐⭐
CRITICAL for dharma_swarm validation. The JIKOKU instrumentation is already in place (jikoku_instrumentation.py, jikoku_fitness.py). AgentRace-style benchmarking would:
- Validate JIKOKU's overhead is acceptable (<5%)
- Identify performance regressions during evolution
- Provide fitness signal for Darwin Engine (faster code = higher fitness)
- Enable COLM 2026 paper performance claims

---

## 5. Darwin Gödel Machine: Self-Improvement Benchmark

### What It Tests
- **Core Capability**: Autonomous self-modification and empirical validation
- **Evolution Mechanics**:
  - Code self-modification (rewriting own implementation)
  - Archive growth (accumulating improved variants)
  - Open-ended exploration (discovering novel solutions)
  - Recursive cascade (improvements enable further improvements)
- **Validation**: Each modification tested on external coding benchmarks

### How Success is Measured
- **Primary Metric**: Improvement trajectory on target benchmarks
  - SWE-bench: 20.0% → 50.0% (2.5× improvement)
  - Polyglot: 14.2% → 30.7% (2.16× improvement)
- **Secondary Metrics**:
  - Archive diversity (number of distinct working variants)
  - Mutation novelty (how different are new versions)
  - Convergence rate (iterations to reach performance plateau)
- **Theoretical Framework**: "What evolves, how it evolves, when it evolves"

### Success Rates (2026)
| System | Initial | Final | Improvement |
|--------|---------|-------|-------------|
| DGM on SWE-bench | 20.0% | 50.0% | 2.5× |
| DGM on Polyglot | 14.2% | 30.7% | 2.16× |

**Key Insight**: The agent-tool boundary blurs in self-modification. The agent IS the tool, creating recursive self-improvement loops.

### Hard Tasks
- **Stability under self-modification**: Avoid breaking core functionality
- **Exploration-exploitation trade-off**: When to refine vs. explore radically new approaches
- **Generalization across benchmarks**: Improvements on SWE-bench don't degrade Polyglot performance
- **Catastrophic forgetting**: Retain capabilities learned in earlier generations

### Dharma Swarm Adaptation
**Map to Darwin Engine**:
- DGM self-modification → evolution.py PROPOSE → GATE → EVALUATE → ARCHIVE → SELECT cycle
- Archive growth → archive.py EvolutionArchive with lineage tracking
- Empirical validation → sandbox.py code execution + test running
- Fitness evaluation → fitness_predictor.py + elegance.py + metrics.py
- Parent selection → selector.py (tournament, roulette, rank, elite)

**Test Protocol**:
1. Seed Darwin Engine with dharma_swarm codebase as initial population
2. Define fitness function: (test_pass_rate × 0.4) + (elegance × 0.3) + (performance × 0.3)
3. Run evolution loop for 100 generations
4. Track:
   - Archive size and diversity
   - Best fitness per generation
   - Mutation type distribution (FEATURE vs. ENHANCEMENT vs. BUGFIX)
   - Telos gate rejection rate (ensure dharmic alignment preserved)
5. Compare final population performance vs. initial on external benchmarks (e.g., GAIA subset)

**Relevance Score**: ⭐⭐⭐⭐⭐
PERFECT CONCEPTUAL MATCH. Dharma swarm's Darwin Engine (evolution.py) is philosophically aligned with the Darwin Gödel Machine. Key difference: dharma_swarm adds dharmic gates (telos_gates.py) to ensure self-modifications remain ethically aligned. This is a novel contribution vs. pure Darwinian evolution.

**Paper Contribution**: "Dharmic Darwin Engine: Self-Improvement Under Ethical Constraints"
- Show that telos gates don't prohibitively slow evolution
- Demonstrate that SATYA gate prevents credential leaks during self-modification
- Prove that AHIMSA gate blocks harmful mutations while allowing beneficial ones
- Measure fitness trajectory with/without gates (control experiment)

---

## Synthesis: Benchmark Suite for Dharma Swarm

### Recommended Test Battery

| Benchmark | Tests | Metric | Target |
|-----------|-------|--------|--------|
| **SWE-bench Lite** | Darwin Engine code evolution | Fix success rate | >30% (vs. 23% SOTA on Pro) |
| **GAIA Level 2** | Agent runner multi-step reasoning | Exact answer accuracy | >50% (vs. 65% SOTA) |
| **MultiAgentBench** | Swarm coordination topologies | Task completion + collab quality | Graph topology best for research tasks |
| **AgentRace** | JIKOKU performance profiling | Latency/throughput composite | <5% overhead from instrumentation |
| **DGM-style Evolution** | Self-improvement trajectory | Fitness growth over 100 generations | 1.5×+ improvement on held-out tasks |

### Implementation Priority

1. **AgentRace** (Week 1) — Validate JIKOKU, establish baseline performance
2. **GAIA** (Week 2) — Stress test agent_runner.py, find coordination bugs
3. **SWE-bench** (Week 3) — Darwin Engine validation, telos gate effectiveness
4. **MultiAgentBench** (Week 4) — Topology optimization, message bus efficiency
5. **DGM Evolution** (Weeks 5-8) — Long-run self-improvement, paper results

### Paper Positioning (COLM 2026)

**Title**: "Dharma Swarm: Self-Improving Multi-Agent Systems Under Ethical Constraints"

**Contributions**:
1. **Architecture**: Darwin Engine with dharmic gates (AHIMSA, SATYA, SVABHAAVA, etc.)
2. **Benchmarks**: GAIA (agent capability), SWE-bench (self-modification), AgentRace (efficiency)
3. **Key Result**: Self-improvement WITHOUT sacrificing ethical alignment (telos gates preserve Jagat Kalyan)
4. **Novel Metric**: "Dharmic fitness" = (task_performance × ethics_score) — both must be high

**Differentiation**:
- vs. DGM: Adds ethical constraints, shows they don't block evolution
- vs. SWE-agent: Multi-agent coordination, not single-agent coding
- vs. AutoGPT/BabyAGI: Rigorous benchmarking, not just demos
- vs. LangChain/LangGraph: Performance-optimized (JIKOKU), self-evolving

---

## Additional Benchmarks Considered (Not Top 5)

### WebArena
- **What**: Realistic web navigation (e-commerce, forums, CMS)
- **Current SOTA**: 61.7% (IBM CUGA, 2026)
- **Why Not Top 5**: Dharma swarm is not primarily web-focused; would require significant browser integration
- **Potential Future Work**: If agent_runner.py adds Playwright/Selenium integration

### TAU-bench (τ-bench)
- **What**: Tool-agent-user interaction in customer service domains (retail, telecom)
- **Current SOTA**: GPT-4o <50% success, pass^8 <25% (inconsistency metric)
- **Why Not Top 5**: Narrow domain (customer service), less relevant to research/code tasks
- **Potential Use**: If dharma_swarm targets conversational agents

### AgentBench (Original)
- **What**: 8 environments (OS, database, knowledge graph, card game, puzzles, web shopping, etc.)
- **Why Not Top 5**: Superseded by more focused benchmarks (GAIA for reasoning, SWE-bench for code)
- **Value**: Broad coverage, but less depth than specialized benchmarks

---

## Next Steps

1. **Download benchmark datasets**:
   - SWE-bench Verified (450 tasks): https://github.com/SWE-bench/SWE-bench
   - GAIA (466 questions): https://huggingface.co/gaia-benchmark
   - MultiAgentBench: https://github.com/multiagentbench
   - AgentRace: https://github.com/agentrace (adapt metrics to JIKOKU)

2. **Implement adapters**:
   - `benchmarks/swe_bench_adapter.py` → Convert GitHub issues to evolution proposals
   - `benchmarks/gaia_adapter.py` → Load questions into task_board.py
   - `benchmarks/multiagent_adapter.py` → Configure swarm topologies per scenario
   - `benchmarks/performance_suite.py` → JIKOKU-instrumented stress tests

3. **Baseline measurements** (before evolution):
   - Run GAIA Level 1 tasks → measure accuracy, latency, tool calls
   - Run AgentRace performance suite → establish p50/p95/p99 latency
   - Run 10 SWE-bench tasks manually → measure fix success rate

4. **Evolution experiments**:
   - Darwin Engine self-improvement on SWE-bench subset
   - Track archive growth, fitness trajectory, gate rejection rate
   - Ablation study: evolution WITH vs. WITHOUT telos gates

5. **Paper draft** (by Mar 26):
   - Results tables from all benchmarks
   - Dharmic fitness definition and validation
   - Performance overhead analysis (JIKOKU instrumentation cost)
   - Qualitative analysis of rejected mutations (what did gates block?)

---

## References

### SWE-bench
- [OpenAI: Introducing SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/)
- [SWE-agent GitHub](https://github.com/SWE-agent/SWE-agent)
- [SWE-bench Official Site](https://www.swebench.com/)
- [SWE-EVO: Benchmarking Coding Agents](https://www.arxiv.org/pdf/2512.18470)
- [SWE-Bench Pro](https://arxiv.org/html/2509.16941v1)

### GAIA
- [GAIA: Meta AI Research](https://ai.meta.com/research/publications/gaia-a-benchmark-for-general-ai-assistants/)
- [GAIA on arXiv](https://arxiv.org/abs/2311.12983)
- [GAIA Leaderboard](https://hal.cs.princeton.edu/gaia)
- [GAIA Benchmark 2026 Overview](https://www.chatbench.org/gaia-benchmark-for-autonomous-ai-agents/)

### MultiAgentBench
- [MultiAgentBench on arXiv](https://arxiv.org/abs/2503.01935)
- [ACL Anthology Entry](https://aclanthology.org/2025.acl-long.421/)
- [WMAC 2026 Workshop](https://multiagents.org/2026/)

### AgentRace & Performance
- [AgentRace on OpenReview](https://openreview.net/forum?id=eUuxWAQA5F)
- [LLM Latency Benchmarks 2026](https://research.aimultiple.com/llm-latency-benchmark/)
- [AI Performance Engineering 2025-2026](https://medium.com/@robi.tomar72/ai-performance-engineering-2025-2026-edition-latency-throughput-cost-optimization-142eec0daece)
- [AutoAgents Benchmarking](https://dev.to/saivishwak/benchmarking-ai-agent-frameworks-in-2026-autoagents-rust-vs-langchain-langgraph-llamaindex-338f)

### Darwin Gödel Machine
- [Darwin Gödel Machine on OpenReview](https://openreview.net/forum?id=pUpzQZTvGY)
- [DGM on arXiv](https://arxiv.org/abs/2505.22954)
- [Sakana AI: DGM Announcement](https://sakana.ai/dgm/)
- [Survey: Self-Evolving Agents](https://github.com/EvoAgentX/Awesome-Self-Evolving-Agents)
- [Self-Evolving Agents Survey](https://arxiv.org/html/2507.21046v4)

### WebArena
- [WebArena Official Site](https://webarena.dev/)
- [WebArena Verified GitHub](https://github.com/ServiceNow/webarena-verified)
- [BrowserArena](https://arxiv.org/html/2510.02418v2)

### TAU-bench
- [τ-bench by Sierra](https://sierra.ai/blog/benchmarking-ai-agents)
- [τ-bench on arXiv](https://arxiv.org/abs/2406.12045)
- [τ²-bench Extension](https://toloka.ai/blog/tau-bench-extension-benchmarking-policy-aware-agents-in-realistic-settings/)
- [Automated Hallucination Correction](https://cleanlab.ai/blog/tau-bench/)

### AgentBench
- [AgentBench on arXiv](https://arxiv.org/abs/2308.03688)
- [AgentBench GitHub](https://github.com/THUDM/AgentBench)
- [AI Agent Benchmarks Overview](https://www.evidentlyai.com/blog/ai-agent-benchmarks)

---

**End of Benchmark Research Report**
*Compiled by dharma_swarm research agent, 2026-03-08*
*For COLM 2026 paper submission (abstract Mar 26, paper Mar 31)*
