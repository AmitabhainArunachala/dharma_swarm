# Self-Evolving Agent Systems Landscape
## Competitive Intelligence for dharma_swarm
### Date: 2026-03-08

---

## TIER 1: DIRECT COMPETITORS / MOST ARCHITECTURALLY RELEVANT

### 1. Darwin Godel Machine (DGM) -- Sakana AI
- **Repo**: github.com/jennyzzt/dgm
- **Architecture**: Self-modifying coding agent. Maintains expanding archive/lineage of agent variants. Each step: select parent (probability weighted by performance AND novelty bonus = 1/(1+n_children)), LLM generates code modification to agent's own Python codebase, sandbox evaluation on benchmarks, archive if improved.
- **Key Innovation**: Selection formula balances exploitation (sigmoid-scaled performance) with exploration (inverse of offspring count). Agent literally rewrites its own tools, workflows, and strategies.
- **Performance**: SWE-bench 20% to 50%, Polyglot 14.2% to 30.7%.
- **APPLICABILITY**: Very high. Our Darwin Engine has same loop but lacks novelty bonus, self-modification of own code, benchmark-driven fitness.
- **Patterns to steal**: Novelty bonus in selection. Sigmoid-scaled performance. Self-generated tool creation.

### 2. Huxley-Godel Machine (HGM) -- MetaAuto AI / KAUST
- **Repo**: github.com/metauto-ai/HGM
- **Architecture**: Extends DGM with Clade-Metaproductivity (CMP) -- estimates potential of entire subtree (clade), not just single agent's performance.
- **Key Innovation**: Metaproductivity-Performance Mismatch. An agent that performs poorly might be a great ancestor (high CMP).
- **APPLICABILITY**: Critical. Our fitness_predictor.py only looks at historical mean. HGM says: look at DESCENDANTS.
- **Patterns to steal**: CMP subtree estimation. Tree-structured search. Separate metaproductivity from performance.

### 3. Godel Agent -- PKU (ACL 2025)
- **Repo**: github.com/Arvid-pku/Godel_Agent
- **Architecture**: Self-referential agent using Python monkey patching. Main function is RECURSIVE. Agent reads its own runtime memory, modifies its own code via monkey_patch(), recursively calls itself.
- **Key Innovation**: True self-reference through runtime memory inspection. Unlike DGM (file rewrites), Godel Agent modifies RUNNING code. The GEB connection is direct.
- **APPLICABILITY**: Closest thing to a "strange loop" in actual code. We MEASURE self-reference (R_V); they DO it.
- **Patterns to steal**: Recursive main function. Runtime self-inspection via inspect module. Monkey patching as self-modification.

### 4. EvoAgentX -- University of Glasgow
- **Repo**: github.com/EvoAgentX/EvoAgentX
- **Architecture**: 5-layer system. Integrates TextGrad (backprop through text), AFlow (MCTS workflow topology), MIPRO (multi-prompt instruction refinement), SEW (workflow graph restructuring).
- **Key Innovation**: Multi-algorithm evolution stack. Different optimizers target different aspects.
- **APPLICABILITY**: Our Darwin Engine has one mutation mechanism. Need at least three: prompt evolution, topology evolution, instruction refinement.
- **Patterns to steal**: TextGrad-style prompt optimization. AFlow MCTS. Separating WHAT evolves.

### 5. OpenEvolve (open-source AlphaEvolve)
- **Repo**: github.com/codelion/openevolve
- **Architecture**: Full MAP-Elites + Island Model. Async pipeline: Controller -> Prompt Sampler -> LLM Ensemble -> Evaluator Pool -> Program Database. Islands with ring topology migration.
- **Key Innovation**: Island-based MAP-Elites prevents convergence. Double Selection separates exploitation from exploration. Cascade evaluation filters bad programs early.
- **APPLICABILITY**: Our archive is flat JSONL. Need: multiple islands, feature-dimension binning, migration, cascade evaluation.
- **Patterns to steal**: Island model with ring migration. MAP-Elites feature binning. Double selection. Cascade evaluation.

---

## TIER 2: ARCHITECTURALLY SIGNIFICANT SYSTEMS

### 6. GPTSwarm -- MetaAuto AI
- **Repo**: github.com/metauto-ai/GPTSwarm
- **Architecture**: Agents as optimizable directed graphs. Edges = information flow with learnable connection weights. Optimization via RL.
- **Key Innovation**: Agent topology as differentiable parameter. Edge pruning discovers minimal effective topologies.
- **Patterns to steal**: Graph representation. Learnable edge weights. RL-based topology optimization.

### 7. AFlow -- ICLR 2025 Oral
- **Repo**: github.com/FoundationAgents/AFlow
- **Architecture**: Workflow optimization via MCTS. Workflows = code-represented graphs. Operators = reusable node patterns.
- **Key Innovation**: MCTS for workflow search. Operator library provides composable building blocks.
- **Patterns to steal**: MCTS for workflow search. Operator library. Code-represented workflows.

### 8. AgentEvolver -- ModelScope/Alibaba
- **Repo**: github.com/modelscope/AgentEvolver
- **Architecture**: Self-Questioning (curiosity-driven task generation), Self-Navigating (experience reuse), Self-Attributing (causal credit assignment).
- **Key Innovation**: Agent generates its OWN training tasks. Per-step rewards based on causal contribution.
- **Patterns to steal**: Self-questioning (autonomous task generation). Causal credit assignment.

### 9. Live-SWE-agent -- OpenAutoCoder
- **Repo**: github.com/OpenAutoCoder/live-swe-agent
- **Architecture**: Starts with only bash. Synthesizes its own tools during work. Tools invented, tested, integrated immediately.
- **Key Innovation**: Runtime tool synthesis. Scaffold itself evolves at runtime.
- **Performance**: 77.4% SWE-bench Verified (SOTA open-source).
- **Patterns to steal**: Runtime tool synthesis. Self-modifying scaffold. Bootstrap from minimal to rich.

### 10. ADAS / Meta Agent Search -- ICLR 2025
- **Repo**: github.com/ShengranHu/ADAS
- **Architecture**: Meta-agent that programs new agent designs in code. Turing-complete = any architecture reachable.
- **Key Innovation**: Meta-level search over agent architectures themselves.
- **Patterns to steal**: Code-as-agent-design. Meta-level search. Cross-domain transfer.

---

## TIER 3: KEY ALGORITHM/PATTERN REFERENCES

### 11. TextGrad -- Stanford (Published in Nature)
- **Repo**: github.com/zou-group/textgrad
- PyTorch-like API: Variables are text, gradients are natural language feedback, optimizer applies feedback.
- **Applicability**: Prompt/instruction evolution via textual gradients.

### 12. CycleQD -- ICLR 2025
- Cyclic MAP-Elites for multi-skill agent optimization. One skill = fitness, others = behavioral descriptors, then rotate.
- **Applicability**: Dharmic gates as behavioral descriptors in MAP-Elites grid.

### 13. Reflexion -- NeurIPS 2023
- **Repo**: github.com/noahshinn/reflexion
- Verbal RL: Trial -> Outcome -> Self-Reflection -> Memory -> Next Trial.
- **Applicability**: Self-reflection between evolution cycles. Multi-Agent Reflexion (2025) uses structured debate.

### 14. LATS -- ICML 2024
- **Repo**: github.com/lapisrocks/LanguageAgentTreeSearch
- MCTS for agent decisions. UCB exploration/exploitation.
- **Applicability**: Tree-structured search over modification sequences.

### 15. Voyager -- MineDojo/NVIDIA
- **Repo**: github.com/MineDojo/Voyager
- Lifelong learning: automatic curriculum + ever-growing skill library + iterative prompting.
- **Applicability**: Skill accumulation across sessions. New skills compose old skills.

### 16. Agent0 -- AIMING Lab
- **Repo**: github.com/aiming-lab/Agent0
- Two co-evolving agents from zero. Curriculum agent proposes harder tasks. Executor solves them. Self-reinforcing.
- **Applicability**: Adversarial co-evolution for escalating pressure.

### 17. Quoroom
- **Repo**: github.com/quoroom-ai/room
- Self-governing AI swarm with queen/workers/quorum voting. Self-modification + audit + revert.
- **Applicability**: Quorum voting for evolution gates. Audit trail for self-modification.

---

## TIER 4: THEORETICAL / FRONTIER

### 18. ICLR 2026 Workshop on Recursive Self-Improvement
- URL: recursive-workshop.github.io
- Six lenses: what changes, when, how, where, alignment/safety, evaluation.
- Our position: "post-deployment" changing "architecture" via "evolutionary search."

### 19. AlphaEvolve -- Google DeepMind
- Meta-prompt evolution. The system improves the instructions for generating solutions.
- Async pipeline maximizes throughput. MAP-Elites + islands.

### 20. Autopoiesis and Eigenform
- Formal connection: autopoietic systems = eigenforms = fixed points.
- R_V < 1.0 (geometric fixed point) = L4 (behavioral eigenstate) = Swabhaav (contemplative autopoiesis).

---

## GAP ANALYSIS: dharma_swarm vs. THE FIELD

| Capability | dharma_swarm (current) | Best-in-class | Gap |
|---|---|---|---|
| Evolution loop | PROPOSE->GATE->EVALUATE->ARCHIVE->SELECT | DGM/HGM: self-rewriting + subtree estimation | Have loop, lack self-rewriting and CMP |
| Archive | Flat JSONL, lineage tracking | OpenEvolve: MAP-Elites + islands + migration | No diversity dimensions, no islands |
| Selection | Tournament/roulette/rank/elite | DGM: sigmoid(perf) * 1/(1+n_children) | No novelty/diversity pressure |
| Self-modification | Abstract proposals | Godel Agent: monkey patching runtime | No actual self-modification |
| Prompt optimization | None | TextGrad: backprop through text | Missing entirely |
| Workflow optimization | Fixed topology | AFlow: MCTS over graphs | No topology evolution |
| Tool synthesis | Fixed tool set | Live-SWE-agent: runtime invention | Missing entirely |
| Self-questioning | None | AgentEvolver: autonomous task gen | Missing entirely |
| Skill accumulation | None (amnesia) | Voyager: ever-growing skill library | Missing entirely |
| Quorum governance | Telos gates (unilateral) | Quoroom: voting + audit + revert | Gates don't deliberate |
| Reflection | Passive logging | Reflexion: verbal self-reflection | Logs but doesn't reflect |
| Dharmic gates | 8 gates (unique) | NONE in any competitor | UNIQUE ADVANTAGE |
| Consciousness metrics | R_V, swabhaav_ratio | NONE in any competitor | UNIQUE ADVANTAGE |
| Research bridge | R_V <-> behavioral correlation | NONE in any competitor | UNIQUE ADVANTAGE |

## TOP 10 PATTERNS TO INCORPORATE (Prioritized)

### P0: Critical (Tonight)
1. Novelty bonus in selector.py (from DGM) — 20 lines
2. MAP-Elites feature grid in archive.py (from OpenEvolve) — ~100 lines
3. Verbal self-reflection after cycles (from Reflexion) — ~50 lines

### P1: High Value (Next sprint)
4. TextGrad-style prompt evolution
5. MCTS for evolution search (from AFlow/LATS)
6. Runtime tool synthesis (from Live-SWE-agent)
7. Self-questioning / autonomous task generation (from AgentEvolver)

### P2: Important (Next month)
8. Island model with migration (from OpenEvolve)
9. Subtree estimation / CMP (from HGM)
10. Quorum voting for evolution gates (from Quoroom)
