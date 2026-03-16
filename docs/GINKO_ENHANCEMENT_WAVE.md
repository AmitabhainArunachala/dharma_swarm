# Dharmic Quant — Enhancement Wave (Post-Build)

**Created**: 2026-03-17
**Purpose**: Execute after 25-agent build completes. Each enhancement is a self-contained agent spec.
**Runner**: `python3 -m dharma_swarm.ginko_audit --enhancements` for latest ranked list.

## Execution Strategy

Three tiers, executed in order. Each tier is a parallel agent wave.

### Tier 1: Critical Fixes (4 agents, 30 min)

Must run before anything else. Fix what the build got wrong.

| # | Agent Type | Enhancement | Target File | Effort |
|---|-----------|-------------|-------------|--------|
| 1 | fintech-engineer | Real AHIMSA Position Gate | ginko_paper_trade.py | trivial |
| 2 | python-pro | API Key Validator | ginko_data.py | trivial |
| 3 | python-pro | Fix pyproject.toml deps | pyproject.toml | trivial |
| 4 | security-engineer | Dashboard Bearer Auth | swarmlens_app.py | small |

**Agent 1 spec**: Add `_check_ahimsa_limit(quantity, price)` to PaperPortfolio.open_position(). If `(quantity * price) / portfolio_value > 0.05`, raise ValueError with "AHIMSA: position exceeds 5% limit". Log via `logger.warning()`. Also verify stop_loss is required (REVERSIBILITY gate).

**Agent 2 spec**: Add `validate_api_keys() -> dict[str, bool]` to ginko_data.py. Check env vars: OPENROUTER_API_KEY, FRED_API_KEY, FINNHUB_API_KEY, OLLAMA_API_KEY. Print status table on import. Return availability dict. Modify `pull_all_data()` to skip unavailable sources gracefully instead of crashing.

**Agent 3 spec**: Read pyproject.toml, add to `[project.dependencies]`: `fastapi>=0.104`, `uvicorn>=0.24`, `numpy>=1.24`. Add to `[project.optional-dependencies]` under `[ginko]`: `hmmlearn>=0.3`, `arch>=6.0`, `yfinance>=0.2`. Verify `pip install -e .` works after edit.

**Agent 4 spec**: Add FastAPI middleware to swarmlens_app.py. Read `DASHBOARD_API_KEY` from env. All `/api/*` routes require `Authorization: Bearer {key}`. Exempt: `/fund`, `/api/waitlist`, `/api/waitlist/count`. Return `{"error": "unauthorized"}` with 401 on failure. If `DASHBOARD_API_KEY` not set, all routes open (dev mode).

---

### Tier 2: Alpha Multiplication (5 agents, 2-3 hours)

The differentiation layer. What makes this 100-1000x better.

| # | Agent Type | Enhancement | Target File | Impact |
|---|-----------|-------------|-------------|--------|
| 5 | fintech-engineer | Backtesting Engine | ginko_backtest.py (NEW) | 100x |
| 6 | fintech-engineer | Portfolio Risk (VaR) | ginko_risk.py (NEW) | 100x |
| 7 | fintech-engineer | Darwin Prompt Tournament | ginko_agents.py (EDIT) | 1000x |
| 8 | fintech-engineer | Multi-Timeframe Signals | ginko_signals.py (EDIT) | 100x |
| 9 | fintech-engineer | Performance Attribution | ginko_attribution.py (NEW) | 100x |

**Agent 5 spec**: Build `ginko_backtest.py`. Install `yfinance`. Download 3 years daily OHLCV for S&P 500 components. For each trading day: run `generate_signal_report()` → simulate paper trades → track equity curve. Compute: annualized return, Sharpe, max drawdown, win rate, Calmar ratio. Compare vs SPY buy-and-hold. Output: `~/.dharma/ginko/backtest/report.json` with equity curve array. Add `dgc ginko backtest` CLI command.

**Agent 6 spec**: Build `ginko_risk.py`. Functions: `compute_correlation_matrix(positions, price_history_30d) -> np.ndarray`, `compute_var(portfolio_value, daily_returns, confidence=0.95) -> float`, `compute_cvar(portfolio_value, daily_returns, confidence=0.95) -> float`, `check_sector_exposure(positions, sector_map, max_pct=0.30) -> list[str]`. Wire into `ginko_orchestrator.action_full_cycle()` as pre-trade risk gate. If VaR > 5% of portfolio, reduce all position sizes by 50%.

**Agent 7 spec**: Wire `evolution.py` DarwinEngine to ginko agent prompts. Add to `agent_registry.py`: `prompt_generation: int = 0`, `prompt_variants: list[str]`, `prompt_fitness: dict[str, float]`. Monthly cycle: rank agents by Brier score, top 2 keep prompts, bottom 2 get LLM-mutated prompts (call Ollama Cloud: "Improve this trading analysis prompt based on these Brier scores: {scores}"). Save variant history. Add `dgc ginko evolve` CLI.

**Agent 8 spec**: Extend `ginko_signals.py`. Add `TimeFrame` enum (DAILY, WEEKLY, MONTHLY). Modify `generate_signal_report()` to accept `timeframe: TimeFrame = TimeFrame.DAILY`. Add `generate_multi_timeframe_report(price_data, regime) -> SignalReport` that computes signals on all 3 timeframes. Confirmation logic: all 3 align → confidence += 0.25. Conflict → confidence -= 0.20, add "timeframe divergence" to reason. DO NOT break existing tests.

**Agent 9 spec**: Build `ginko_attribution.py`. For each closed trade in `trades.jsonl`, trace: signal_source (technical/SEC/sentiment), agent_name (who generated the signal), regime_at_entry (bull/bear/sideways). Aggregate: `pnl_by_agent: dict[str, float]`, `pnl_by_signal_type: dict[str, float]`, `pnl_by_regime: dict[str, float]`. Add `/api/attribution` endpoint to swarmlens_app.py. Add "Attribution" tab with tables.

---

### Tier 3: Ecosystem Integration (3 agents, 1-2 hours)

Wire into the broader dharma_swarm ecosystem.

| # | Agent Type | Enhancement | Target File | Impact |
|---|-----------|-------------|-------------|--------|
| 10 | python-pro | Cost Budget + Kill Switch | agent_registry.py (EDIT) | 10x |
| 11 | python-pro | Prediction Webhooks | ginko_brier.py (EDIT) | 10x |
| 12 | fintech-engineer | Sentiment Pipeline | ginko_sentiment.py (NEW) | 100x |

**Agent 10 spec**: Add to `AgentRegistry`: `daily_budget_usd: float = 5.0`, `weekly_budget_usd: float = 25.0`. Before each `agent_task()` call, sum today's cost from `task_log.jsonl`. If over 80%: log warning. If over 100%: return `{"error": "budget_exceeded", "budget": daily_budget_usd, "spent": spent}` instead of making LLM call. Add `dgc ginko budget` CLI showing spend vs limits.

**Agent 11 spec**: Add `webhook_notify(prediction, outcome, brier_score)` to `ginko_brier.py`. Read `GINKO_WEBHOOK_URL` from env. If set, POST JSON to it: `{prediction, outcome, brier_score, running_brier, timestamp}`. Also append to `~/.dharma/ginko/resolved_notifications.jsonl`. Call from `auto_resolve_predictions()` after each resolution.

**Agent 12 spec**: Build `ginko_sentiment.py`. Use httpx to call X API v2 (if `X_BEARER_TOKEN` set): search `{ticker} lang:en -is:retweet`, last 24h, extract text. Compute naive sentiment: count positive/negative financial keywords (rally, crash, bullish, bearish, moon, dump). Score -1.0 to +1.0. `SentimentSignal` dataclass: ticker, score, tweet_count, sample_tweets. Add `incorporate_sentiment_signals()` to `ginko_signals.py` with 10% weight. Fall back gracefully if no X API key.

---

## Verification After Enhancement Wave

```bash
# After Tier 1
python3 -m pytest tests/test_ginko_*.py -v              # All pass
python3 -m dharma_swarm.ginko_audit                      # Zero FAIL on FC-01, FC-04, GAP-01, GAP-02

# After Tier 2
python3 -m dharma_swarm.ginko_backtest                   # Backtest report generated
dgc ginko evolve                                         # Prompt tournament runs
python3 -m dharma_swarm.ginko_audit --enhancements       # Top items marked DONE

# After Tier 3
dgc ginko budget                                         # Shows spend tracking
python3 -m dharma_swarm.ginko_audit                      # All GAPs resolved
```

## What This Gets You

**Without enhancement wave**: A working signal pipeline + paper trading + dashboard. Good demo.

**With enhancement wave**:
- **Backtested**: 3 years of historical validation. Sharpe, drawdown, win rate all computed.
- **Risk-managed**: VaR, correlation, sector exposure. Portfolio-level protection.
- **Self-evolving**: Darwin Engine mutates agent prompts monthly based on Brier scores.
- **Multi-timeframe**: Daily/weekly/monthly signal confirmation.
- **Attributed**: Know exactly which agent/signal/regime generates alpha.
- **Budget-controlled**: Hard limits prevent runaway LLM costs.
- **Authenticated**: Dashboard locked behind API key.
- **Sentiment-aware**: Social signal input when available.

This is the difference between "interesting project" and "fundable hedge fund."
