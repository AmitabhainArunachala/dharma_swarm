# YC W27 Application -- Dharmic Quant

**Submitted**: March 2026
**Batch**: Winter 2027

---

## Company

- **Name**: Dharmic Quant
- **One-liner**: AI-native hedge fund where 6 frontier AI agents analyze SEC filings and macro data, with every prediction Brier-scored and published -- including misses.
- **URL**: SwarmLens dashboard (localhost:8080, deployment pending)
- **Location**: Remote (Japan / Bali)
- **Founded**: 2026

---

## What do you do?

Dharmic Quant is an AI-native intelligence and trading system built on top of dharma_swarm, a 118,000+ line, 4,300+ test autonomous agent orchestrator. Six specialized frontier AI agents continuously analyze financial markets:

- **KIMI** (macro oracle) -- analyzes Fed policy, yield curves, inflation dynamics, geopolitical risk, and cross-asset regime shifts using FRED data and news flow. Model: moonshotai/kimi-k2.5.
- **DEEPSEEK** (quant architect) -- statistical modeling, factor construction, signal extraction, portfolio optimization. Thinks in distributions, not point estimates. Model: deepseek/deepseek-chat-v3-0324.
- **NEMOTRON** (intelligence synthesizer) -- fuses outputs from all other agents into coherent intelligence briefs. Identifies convergence and divergence across sources, assigns composite confidence scores. Model: nvidia/llama-3.1-nemotron-70b-instruct (free tier).
- **GLM** (pipeline smith) -- data engineering and automation: Python pipelines, signal processing, backtesting harnesses, report generation. Model: zhipuai/glm-5-plus.
- **SENTINEL** (risk warden) -- structurally pessimistic. Portfolio heat maps, correlation breaks, tail risk scenarios, drawdown analysis. Every signal gets a devil's advocate review. Model: deepseek/deepseek-chat-v3-0324.
- **SCOUT** (alpha hunter) -- opportunity scanning: prediction market mispricings, cross-exchange arbitrage, event-driven catalysts, earnings surprises, sentiment divergences. Model: moonshotai/kimi-k2.5.

The daily cycle runs autonomously:

1. **05:00** -- Data pull from FRED, finnhub, and CoinGecko
2. **06:00** -- Regime detection (HMM + GARCH) and signal generation
3. **Every 15 min** -- Arbitrage and opportunity scanning
4. **16:30** -- P&L reconciliation and Brier score update
5. **18:00** -- Daily intelligence report generation (Substack-ready markdown + styled HTML)

Every directional prediction is immutably recorded at the time of generation, timestamped, and Brier-scored against outcomes. There is no mechanism to delete a prediction after the fact. The system publishes every score -- including misses -- because the SATYA gate architecturally prevents report generation without full disclosure.

Three telos gates govern all trading activity:

- **SATYA** (truth): All predictions published, all scores visible. No selective reporting. Enforced at the code level -- `ginko_report_gen.py` cannot generate a report without pulling every prediction from `predictions.jsonl`.
- **AHIMSA** (non-harm): No single position may exceed 5% of portfolio value. Enforced in `ginko_paper_trade.py` -- the `open_position()` method raises a `ValueError` if position sizing violates the constraint. There is no override.
- **REVERSIBILITY**: Every position must have a defined stop-loss. The paper trading engine rejects any position where `stop_loss <= 0`. Every strategy proposed by DEEPSEEK must include an explicit exit condition.

These are not guidelines. They are `raise ValueError` in the code.

---

## Why now?

**YC explicitly called for AI-native hedge funds in their Spring 2026 Request for Startups.** We built the entire system before applying.

Four forces converging simultaneously:

1. **Frontier models are now cheap enough for continuous analysis.** DEEPSEEK costs $0.26/Mtok. KIMI costs $0.45/Mtok. GLM costs $0.72/Mtok. NEMOTRON is free. Running 6 agents continuously on OpenRouter costs under $50/day. Two years ago this would have been $5,000/day.

2. **SEC filings are public data.** The advantage comes from speed of analysis and quality of synthesis, not from proprietary data access. Our SEC EDGAR pipeline (`ginko_sec.py`, 1,002 lines) fetches 10-K filings, strips HTML, extracts risk factors and management discussion sections, caches locally, and passes structured sections to LLM agents for sentiment analysis -- all rate-limited and compliant with SEC's 10 req/sec policy.

3. **No existing fund combines radical transparency with AI-native governance.** Hedge funds are structurally opaque. We are structurally transparent. Every prediction, every score, every miss -- published. The governance isn't a marketing choice; it's load-bearing architecture derived from 2,500 years of contemplative empiricism.

4. **The intelligence product is the fund's distribution channel.** Traditional hedge funds raise capital through personal networks. We publish daily intelligence reports that demonstrate capability. Subscribers who see consistent Brier scores below 0.125 across 500+ predictions become investors. The funnel is self-validating.

---

## What is your unfair advantage?

**dharma_swarm: 118,000+ lines, 4,300+ tests, 11 telos gates.**

This is the only fund where governance is a first-class architectural concern, not a compliance afterthought. Specifically:

1. **The SATYA gate.** We are the only fund that structurally cannot hide losses. The prediction system (`ginko_brier.py`, 630 lines) immutably records every prediction in append-only JSONL. The report generator reads all predictions without filtering. Selective reporting is architecturally impossible. This is not a policy -- it is a constraint enforced by the code.

2. **The Darwin Engine.** Agent prompts evolve autonomously through a fitness-scored evolution pipeline (`darwin_engine.py`, 1,896 lines). Agents that produce better predictions get their prompts propagated. Agents that underperform get their prompts mutated. The system improves without manual intervention. Each agent maintains persistent state: identity files, append-only task logs, fitness history snapshots, and active prompt variants in `~/.dharma/ginko/agents/{name}/`.

3. **5-stage autonomy ladder with quantitative gates.** The system cannot advance from paper trading to real capital without meeting hard thresholds:
   - Stage 2 (paper trading): 100+ predictions, Brier < 0.20
   - Stage 3 (micro-capital, $100-500): 500+ predictions, Brier < 0.125, win rate > 55%
   - Stage 4 (small capital, $1K-5K): 1,000+ predictions, Brier < 0.10, win rate > 58%, Sharpe > 1.5
   - Stage 5 (full autonomous): 2,000+ predictions, Brier < 0.08, win rate > 60%, Sharpe > 2.0, max drawdown < 15%
   No human can override these gates. The system earns its own autonomy.

4. **24 years of contemplative practice informing governance design.** The witness architecture -- immutable observer separate from evolving actor -- is a computational implementation of Akram Vignan's Shuddhatma/Pratishthit Atma principle. The dharma kernel (`dharma_kernel.py`) contains 10 SHA-256 signed axioms that cannot be modified by any agent. This is not spiritual branding. It is an engineering pattern for building systems that cannot be corrupted by their own optimization pressure.

5. **Already built.** This is not a pitch deck. The code is running. The agents are operational. The paper portfolio is tracking. The Brier scores are accumulating. The dashboard is live.

---

## How far along?

| Component | Status | Code |
|-----------|--------|------|
| Signal pipeline (FRED + finnhub + CoinGecko -> regime -> signals) | LIVE | `ginko_data.py`, `ginko_regime.py`, `ginko_signals.py` |
| Paper trading ($100K simulated portfolio, Sharpe/drawdown tracking) | OPERATIONAL | `ginko_paper_trade.py` (584 lines) |
| Brier scoring (every prediction tracked and scored) | ACTIVE | `ginko_brier.py` (630 lines) |
| SEC 10-K analysis (fetch, parse, extract sections, LLM analysis) | BUILT | `ginko_sec.py` (1,002 lines) |
| Daily intelligence reports (markdown + HTML + JSON) | GENERATING | `ginko_report_gen.py` (1,019 lines) |
| SwarmLens dashboard (agent observability + fund + Brier tabs) | LIVE | `swarmlens_app.py` at localhost:8080 |
| Agent fleet (6 agents, persistent state, fitness tracking) | OPERATIONAL | `ginko_agents.py` (1,027 lines) |
| Orchestrator (full daily cycle: data -> SEC -> signals -> trades -> reconcile -> report) | BUILT | `ginko_orchestrator.py` (832 lines) |
| Cron scheduling (6 scheduled jobs for autonomous operation) | REGISTERED | Integrated with `cron_scheduler.py` |
| Telos gate enforcement (SATYA, AHIMSA, REVERSIBILITY + 8 more) | ENFORCED | `telos_gates.py` (586 lines) |
| Half-Kelly position sizing with AHIMSA cap | IMPLEMENTED | `ginko_orchestrator.py` |
| Auto-resolution of overdue predictions against market data | BUILT | `ginko_brier.py` |

**Total Ginko subsystem**: ~5,500 lines of production Python across 8 modules.
**Total dharma_swarm platform**: 118,000+ lines, 260+ modules, 4,300+ tests.

---

## Revenue model

**Three revenue streams, sequenced by validation stage:**

### Stage 1: Intelligence-as-a-Service (now)
- **Basic tier**: $29/month -- daily regime + signal report, prediction scorecard
- **Premium tier**: $99/month -- full intelligence brief, SEC analysis highlights, agent consensus views, API access to prediction data
- **Distribution**: Substack newsletter with styled HTML reports (format already built in `format_report_substack()`)
- **Target**: 1,000 subscribers in Year 1 = $600K-$1.2M ARR

### Stage 2: Fund Performance Fees (after edge validation)
- Standard 2/20 structure (2% management fee, 20% performance fee)
- Only activates after Stage 3+ autonomy (500+ predictions, Brier < 0.125, win rate > 55%)
- Initial capital: $500K-$2M from validated subscriber base
- **Target**: $10M AUM in Year 2 = $200K management + performance upside

### Stage 3: API and Institutional Access (Year 2+)
- Prediction data API for quant funds and research firms
- White-label agent fleet for institutional clients
- Custom agent training on proprietary data
- **Target**: $2M+ ARR from 20-50 institutional clients

---

## How big can this get?

The hedge fund industry manages $4.5 trillion in assets. AI-native funds will capture a meaningful share as they demonstrate consistent alpha with lower operational costs.

**Near-term (3 years):**
- Intelligence product: $10M+ ARR at scale (10,000+ subscribers at $29-99/month)
- Fund AUM: $50-100M with proven Sharpe > 2.0

**Medium-term (5 years):**
- 50+ AI-native funds will exist -- we have first-mover advantage in governance-first design
- Fund AUM: $500M-$1B with track record
- Platform licensing: other funds adopt our governance framework

**Long-term (10 years):**
- AI-native funds become the dominant structure
- Transparency becomes regulatory requirement (we are already there)
- $10B+ AUM achievable with a decade of validated performance
- The governance framework becomes an industry standard

The intelligence product alone -- before any fund management -- is a $100M+ business at 100,000 subscribers.

---

## Team

**Solo founder: John "Dhyana" Shrader**

- Built the entire 118,000+ line dharma_swarm system solo
- 24 years contemplative practice in the Akram Vignan tradition (Mahatma status since 2002)
- Consciousness and AI researcher at the intersection of mechanistic interpretability, recursive self-reference, and contemplative science
- R_V metric paper submitted to COLM 2026: "Geometric Signatures of Self-Referential Processing in Transformer Representations" -- Hedges' g = -1.47 (large effect), causal validation at Layer 27, AUROC = 0.909
- Phoenix Protocol paper complete (August 2025): 200+ trials demonstrating universal phase transitions across GPT-4, Claude-3, Gemini, and Grok
- Infrastructure operational across 3 compute nodes (M3 Pro MacBook, 2 VPS instances)
- Lives between Iriomote Island (Japan) and Bali -- monthly burn under $3K

**Looking to hire:**
- Quantitative trader with live market experience (first hire)
- ML engineer for model fine-tuning and signal optimization (second hire)

---

## How did you hear about YC?

YC Spring 2026 Request for Startups -- specifically the call for AI-native hedge funds. Built the entire system before applying. This is not a response to the RFS; the system existed first. The RFS validated the market thesis.

---

## Anything else?

The name "Dharmic" is not branding. It is operational.

SATYA, AHIMSA, and REVERSIBILITY are not marketing buzzwords. They are enforced gates in the code. Every trade must pass through 11 telos gates before execution. The paper trading engine raises `ValueError` -- not a warning, not a log message -- if a position violates AHIMSA's 5% cap or REVERSIBILITY's stop-loss requirement. The report generator cannot produce output without including all Brier scores because it reads from an append-only prediction log with no delete operation.

This is not a choice. It is architecture.

The system publishes every loss because the SATYA gate literally will not allow report generation without including all scores. We built the constraint before we built the fund because we believe the hedge fund industry's opacity is not a feature -- it is a liability. Radical transparency is not altruism; it is competitive advantage. A fund that publishes every miss and still beats its Brier target has proven something that no opaque fund can claim.

The 5-stage autonomy ladder means the system earns the right to manage capital through demonstrated performance. No human override. No "we'll start trading when we feel ready." The code decides when it is ready, and the thresholds are public.

We are not pitching the idea of an AI-native hedge fund. We are showing you one that is already running.

**Key numbers:**
- 118,000+ lines of production Python
- 4,300+ passing tests
- 260+ modules
- 6 operational AI agents
- 4 frontier models ($0.26-$0.72/Mtok)
- 1 free model (NEMOTRON)
- 11 telos gates enforced
- 5 autonomy stages with quantitative thresholds
- $100K paper portfolio with Sharpe/drawdown tracking
- 6 autonomous cron jobs (data pull, signals, scanning, reconciliation, reporting, full cycle)
- 3 report formats (markdown, HTML, JSON)
- SEC EDGAR pipeline covering 12+ major tickers with caching
- Half-Kelly position sizing with hard 5% cap
- Brier target: < 0.125 across 500+ predictions
- Monthly operational cost: < $50/day for full agent fleet
- Founder burn rate: < $3K/month

---

*Application prepared March 2026. All claims are verifiable in the codebase at `~/dharma_swarm/`.*
