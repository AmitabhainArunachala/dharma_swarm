# Show HN: 6 AI Agents Trade Stocks, Publish Every Prediction Score (Including Misses)

Dharmic Quant is an open experiment: six LLM agents analyze macro data, SEC filings, and market signals to generate probabilistic predictions — and we Brier-score every single one publicly, including the misses.

## Technical Stack

**Orchestration:** dharma_swarm, our async multi-agent system. 103K lines of Python, 4,300+ tests. Runs as a daemon with stigmergy-based coordination (agents leave pheromone marks rather than direct messaging).

**Agents:** Six specialists on OpenRouter — Kimi-K2.5 (macro regime), DeepSeek-V3 (fundamentals/filings), Nemotron-70B (quant signals), GLM-5 (pipelines), plus a risk sentinel and opportunity scout. They analyze independently, then synthesize. Dissents are published alongside consensus.

**Models:** HMM for regime detection (bull/bear/sideways). GARCH for volatility estimation. Half-Kelly for position sizing — deliberately betting half what the math recommends because edge estimates are always overconfident.

**Data:** FRED API (macro), Finnhub (market data + SEC filings), CoinGecko (crypto). Just publicly available information.

**Scoring:** Brier scores on every prediction. Running calibration curves. Published before resolution, scored after. The publishing pipeline requires logging before execution.

## Why "Dharmic"

Three constraints enforced in code, not guidelines:

- **SATYA:** All predictions published with probabilities before outcomes. No selective reporting.
- **AHIMSA:** Max 5% position size. Hard limit in sizing code.
- **REVERSIBILITY:** Every position requires stop loss at entry. No hold-and-hope.

These are `if` statements that run before trades, not a code of conduct.

## What We Don't Claim

We are not beating the market. Paper trading with $100K simulated capital. No live track record. Brier scores are preliminary and need months before they're statistically meaningful.

We're testing whether radical transparency creates useful accountability, not asserting AI agents are better than humans.

## FAQ

**"Isn't this just a chatbot calling an API?"**
The agents run HMM regime detection, parse 10-K filings structurally, compute quantitative features from price/volume data. SENTINEL runs correlation and concentration checks to veto signals. It's more pipeline than chatbot.

**"Why publish misses?"**
Self-reported hedge fund performance is unfalsifiable. Publishing misses makes the track record auditable. If calibration is good (predicting 70% events that happen 70% of the time), misses are expected and informative.

**"Paper trading isn't real."**
Correct. Slippage, liquidity, and execution risk are real. Paper trading proves the system works mechanically. It doesn't prove it makes money. We're clear about the gap.

**"What's the edge?"**
Unknown. That's an empirical question. The hypothesis is multi-model synthesis with regime awareness produces better-calibrated probabilities. We're testing it, not asserting it.

**"Solo founder?"**
Yes. dharma_swarm handles orchestration, scheduling, memory, and evolution autonomously. I built the infrastructure and set the constraints. The agents do the daily analysis.

---

Dashboard: [link to SwarmLens]
Substack: [link to newsletter]
GitHub: github.com/shakti-saraswati/dharma_swarm
