# Abstraction Layer Audit — 2026-03-18

> Classifying every major module as COMMODITY, DIFFERENTIATOR, or APPLICATION
> per the Structured Prompts Leverage Playbook (Prompt #1).

**Total Codebase**: 228 Python files, ~120K lines of code

---

## Summary

```
DIFFERENTIATOR (Dharmic Genome)         ~16.5K lines   14%
COMMODITY (Infrastructure)               ~21K lines   17%
APPLICATION (Revenue Products)           ~32K lines   27%
EXPERIMENTAL/SUPPORT (misc)              ~50K lines   42%
```

---

## DIFFERENTIATOR — The Dharmic Genome (NO Replacements)

These modules embody principles from the 10 pillars. They are the moat.

| Module | Lines | Pillar Ground | Status |
|--------|-------|--------------|--------|
| dharma_kernel.py | 396 | Dada Bhagwan, Hofstadter, Aurobindo, Levin | SHIPPING |
| dharma_corpus.py | 416 | Dada Bhagwan, Bateson | SHIPPING |
| ontology.py | 1,645 | Palantir + Deacon + Friston | SHIPPING |
| telos_gates.py | 629 | Dada Bhagwan, Akram Vignan | SHIPPING |
| guardrails.py | 575 | Ashby, Beer, Friston | SHIPPING |
| logic_layer.py | 819 | Palantir AIP + Deacon | SHIPPING |
| cascade.py | 485 | Kauffman, Hofstadter (F(S)=S) | SHIPPING |
| decision_ontology.py | 470 | Friston, Varela | SHIPPING |
| identity.py | 358 | Beer VSM S5, Hofstadter | SHIPPING |
| zeitgeist.py | 300 | Beer VSM S4, Levin | SHIPPING |
| lineage.py | 462 | Palantir + Bateson | SHIPPING |
| traces.py | 187 | Bateson, Jain karma | SHIPPING |
| evolution.py | 2,675 | Kauffman, Friston, Deacon | SHIPPING |
| semantic_evolution/ | 4,220 | Friston prediction error | SHIPPING |
| context.py suite | 2,719 | Varela, Friston, Deacon | SHIPPING |
| rv.py + system_rv.py | 655 | Empirical core (R_V) | SHIPPING |
| pramana.py | 480 | Jain epistemology | SHIPPING |
| catalytic_graph.py | 395 | Kauffman autocatalytic sets | SHIPPING |
| info_geometry.py | 665 | Friston information geometry | SHIPPING |
| jikoku_*.py | ~1,128 | Witness time (Bateson) | SHIPPING |
| **NEW: persistent_memory.py** | 320 | Varela, Ashby, Dada Bhagwan (nirjara) | SHIPPING |
| **NEW: research_scout.py** | 310 | Friston, Kauffman, Ashby | SHIPPING |
| **NEW: media_memory.py** | 370 | Varela, Ashby, Kauffman | SHIPPING |
| **NEW: sandbox_policy.py** | 360 | Beer, Dada Bhagwan, Ashby, Varela | SHIPPING |

**Investment priority**: evolution.py, ontology.py, rv.py, semantic_evolution/, telos_gates.py

---

## COMMODITY — Replaceable Infrastructure

| Module | Lines | COTS Replacement | Effort |
|--------|-------|-----------------|--------|
| providers.py | 1,629 | LiteLLM | 3 weeks |
| runtime_state.py | 1,776 | Postgres + SQLAlchemy | 3 weeks |
| message_bus.py | 605 | NATS or RabbitMQ | 2 weeks |
| agent_runner.py | 1,521 | LangChain Agents | 2 weeks |
| task_board.py + workflow.py | 996 | Celery + Dagster | 2 weeks |
| monitor.py + metrics.py + pulse.py | 1,609 | OpenTelemetry | 2 weeks |
| swarmlens_app.py | 1,544 | Streamlit or Reflex | 2-3 weeks |
| agent_registry.py | 939 | LangChain Agent registry | 1-2 weeks |
| experiment_memory.py | 297 | MLflow / W&B | 1-2 weeks |

**Total commodity replacement**: ~16-20 engineer weeks to shed ~10K lines of maintenance

---

## APPLICATION — Revenue Products

### GINKO (Quant Trading) — ~12.5K lines, SHIPPING
First complete AI trading system grounded in dharmic principles.
**Thinnest path to revenue: 4-6 weeks to first live signals.**

### TELOS_AI (Agent OS) — ~8K lines, SHIPPING
Autonomous agent orchestration with provable safety.
**Enterprise governance market. 6-8 weeks to SaaS pilot.**

### AUTORESEARCH (Research Automation) — ~5K lines, SHIPPING
AI-driven research loop with R_V paper already submission-ready.
**2-3 months to first publications.**

---

## Thinnest Path to First Revenue

**Pursue GINKO + AUTORESEARCH in parallel:**
1. GINKO → immediate cash flow ($60K ARR target with 10 users @ $500/mo)
2. AUTORESEARCH → credibility + narrative (publications, then consulting)

---

## VSM Gaps (from CLAUDE.md Section VII)

| Gap | Effort | Priority |
|-----|--------|----------|
| S3↔S4 Channel | 2 weeks | Medium |
| Sporadic S3* | 1 week | Medium |
| Algedonic Signal | **CLOSED by sandbox_policy.py** | Done |
| Agent-Internal S1-S5 | 2 weeks | Medium |
| Variety Expansion Protocol | 1 week | Medium |

**Note**: VSM Gap #3 (Algedonic Signal) is now closed by the new
`sandbox_policy.py` module, which routes critical violations directly
to Dhyana (S5) via the `AlgedonicAlert` channel.

---

## Recommendation

The differentiator IS the moat. Double down on:
1. Evolution engine (darwin engine, fitness, self-improvement)
2. Ontology (Palantir pattern, the coordination bus)
3. R_V measurement (empirical core, the proof)
4. Telos gates (safety expansion to 26 axioms)

Replace commodity infrastructure to free effort for APPLICATION and SHIPPING.
The gap is not technical. The gap is shipping.
