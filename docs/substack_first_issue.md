# We Publish Every Miss: Introducing Dharmic Quant

Most hedge funds hide their losses. We Brier-score every prediction and publish them all — including the misses. Here's why that changes everything.

---

## The Problem Nobody Talks About

Hedge funds are black boxes by design. Performance is self-reported. Backtests are curve-fit to historical data until they look spectacular, then marketed as "proven strategies." When a fund blows up, investors discover the actual risk profile was nothing like what was described.

Survivorship bias compounds the problem. The funds that blew up don't publish postmortems — they disappear. The ones that remain look like geniuses by default. The entire industry optimizes for the appearance of competence rather than actual, measurable epistemic accuracy.

We think that's broken. So we built something different.

## What Dharmic Quant Actually Is

Six AI agents. Real data feeds. Every prediction timestamped, probability-scored, and published before resolution. Every outcome tracked. Every miss visible.

The agents:

| Agent | Model | Role |
|-------|-------|------|
| **KIMI** | Kimi K2.5 | Macro oracle. Reads FRED data, detects regime shifts via HMM. |
| **DEEPSEEK** | DeepSeek V3 | Quant architect. SEC filing analysis, quantitative signals. |
| **NEMOTRON** | Nemotron 70B | Intelligence synthesizer. Resolves conflicts, produces consensus. |
| **GLM** | GLM-5 Plus | Pipeline smith. Data flows, signal integrity, report generation. |
| **SENTINEL** | DeepSeek V3 | Risk warden. Doesn't generate signals — vetoes them. AHIMSA enforcer. |
| **SCOUT** | Kimi K2.5 | Alpha hunter. Finds mispriced assets, unusual patterns. |

They run on OpenRouter through dharma_swarm, our 103K-line multi-agent orchestrator with 4,300+ tests. No proprietary black box.

## How a Signal Becomes a Prediction

Raw data flows from three sources: FRED (macro), Finnhub (equities + SEC), CoinGecko (crypto).

1. **Regime Detection**: KIMI runs HMM classification — is the environment bull, bear, or sideways? GARCH estimates volatility clustering. This sets context for everything downstream.

2. **Multi-Agent Analysis**: DEEPSEEK and NEMOTRON analyze fundamentals and quantitative signals independently. GLM reads the narrative layer. SCOUT flags anomalies.

3. **Synthesis**: Agreements get weighted higher. Disagreements get flagged explicitly — we publish the dissents, not just the consensus.

4. **Risk Gates**: SENTINEL applies position limits. Half-Kelly sizing — deliberately betting half of what the math says is optimal, because edge estimates are always overconfident.

5. **Prediction**: An explicit probability, position size, stop loss, and timestamp. Published before the outcome is known.

After resolution, we Brier-score it. A Brier score measures probabilistic prediction accuracy: 0.0 is perfect, 0.25 is coin-flip useless. We publish the running score. Always.

## The Three Gates

This is where "Dharmic" means something beyond branding. Three constraints enforced in code:

**SATYA (Truth):** The report generation pipeline cannot produce output if any prediction scores are filtered out. Cherry-picking is architecturally impossible.

**AHIMSA (Non-harm):** No single position exceeds 5% of portfolio value. Hard limit in the position-sizing code, not a guideline that gets waived when conviction is high.

**REVERSIBILITY:** Every position has a stop loss at entry. No exceptions. The system will not execute a trade without a defined exit.

These aren't aspirational principles. They're `if` statements. They run before every trade, and they cannot be overridden without changing the source code.

## Current Predictions (Paper Trading)

We're paper trading with a $100,000 simulated portfolio. This is not real money. We have not proven anything yet. Here's what the system is tracking:

- **SPY 30-day direction (bullish):** 62% probability. KIMI sees risk-on regime, DEEPSEEK notes strong earnings. Dissent: GLM reads tariff narrative as headwind.

- **BTC holds above $78K through March:** 58% probability. SCOUT notes institutional flow patterns. Low conviction — barely above baseline.

- **10Y yield rises above 4.5% by April:** 71% probability. KIMI most confident. DEEPSEEK sees fiscal deficit supporting higher rates. No significant dissent.

These will be scored. If we're wrong, you'll see it. That's the point.

## What We're Honest About

We have no live track record. Paper trading proves the system works mechanically — it does not prove it makes money. The Brier scores are preliminary. We need months of data before they mean anything statistically.

We're not claiming AI agents are better than human traders. We're claiming that radical transparency creates accountability that the industry currently lacks.

## What Comes Next

- **Daily intelligence reports** with predictions and updated Brier scores
- **Weekly analysis** on what agents got right and wrong
- **Monthly performance reviews** with full statistical breakdowns
- **SEC filing analysis** through the agent pipeline

Every subscriber sees the same data. The entire point is that accountability requires an audience.

Subscribe to find out if we're good or not.

---

*Dharmic Quant is a research project by Dhyana (John Shrader), built on dharma_swarm. Paper trading only. Not financial advice. The whole point is that we tell you when we're wrong.*
