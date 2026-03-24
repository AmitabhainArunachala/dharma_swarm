# dharma_swarm Quantitative Finance Toolkit

Four modules addressing critical gaps that most quant systems ignore: fat-tailed risk, factor significance testing, regime awareness, and liquidity constraints.

Location: `~/dharma_swarm/tools/quant/`

## Modules

### 1. `cf_cvar.py` -- Cornish-Fisher CVaR

**What**: Corrects standard VaR/CVaR for fat tails using skewness and kurtosis.

**When to use**: Every time you compute risk. Standard VaR assumes normal returns. Real returns have fat tails (excess kurtosis > 0) and negative skew. Ignoring this underestimates tail risk by 20-50%.

**Math**:

The Cornish-Fisher expansion adjusts the Gaussian quantile z:

```
z_cf = z + (z^2 - 1) * S / 6
         + (z^3 - 3z) * K / 24
         - (2z^3 - 5z) * S^2 / 36
```

where S = skewness, K = excess kurtosis, z = Phi^{-1}(1 - alpha).

VaR_CF = -(mu + sigma * z_cf)

CVaR_CF = mean of all returns below -VaR_CF.

**Example**:

```python
from tools.quant.cf_cvar import cornish_fisher_var, cornish_fisher_cvar, compare_var_methods
import numpy as np

returns = np.random.default_rng(42).standard_t(df=4, size=1000) * 0.02
print(compare_var_methods(returns, confidence=0.99))
# Shows Normal VaR vs Historical VaR vs CF VaR vs CF CVaR side by side
```

### 2. `fama_macbeth.py` -- Fama-MacBeth Cross-Sectional Regression

**What**: Two-pass regression testing whether a factor earns a statistically significant risk premium across assets.

**When to use**: Before trading any factor. If |t-stat| < 2.0, the factor does not earn a significant premium and your strategy is chasing noise.

**Math**:

Pass 1 (time-series, per asset i):
```
r_{i,t} = alpha_i + beta_i * F_t + eps_{i,t}
```

Pass 2 (cross-section, per period t):
```
r_{i,t} = lambda_{0,t} + lambda_{1,t} * beta_i + eta_{i,t}
```

Result: lambda_bar = (1/T) * sum(lambda_t), tested with Newey-West HAC standard errors.

**Example**:

```python
from tools.quant.fama_macbeth import fama_macbeth
import numpy as np

rng = np.random.default_rng(42)
T, N = 500, 50
betas = rng.uniform(0.5, 2.0, size=N)
factor = rng.normal(0.005, 0.02, size=(T, 1))
returns = betas[None, :] * factor + rng.normal(0, 0.01, size=(T, N))

result = fama_macbeth(returns, factor)
print(result)  # Shows lambda, t-stat, significance
```

### 3. `hmm_regimes.py` -- Hidden Markov Model Market Regimes

**What**: Detects bull/bear/neutral regimes from return series without manual labels.

**When to use**: Before any strategy that assumes stationary parameters. Markets switch regimes. A momentum strategy that works in bull markets bleeds in bear markets. This module tells you which regime you are in.

**Math**:

Gaussian HMM with K states:
```
P(r_t | state_t = k) = N(mu_k, sigma_k^2)
P(state_t = k | state_{t-1} = j) = A_{j,k}
```

Inference via Baum-Welch (EM). State decoding via Viterbi algorithm. States auto-labeled by ascending mean return.

Falls back to threshold-based detection (mean +/- 0.5*std boundaries) if hmmlearn is not installed.

**Example**:

```python
from tools.quant.hmm_regimes import fit_regimes
import numpy as np

rng = np.random.default_rng(42)
bear = rng.normal(-0.03, 0.04, size=200)
bull = rng.normal(0.02, 0.015, size=200)
returns = np.concatenate([bear, rng.normal(0, 0.01, size=400), bull])

result = fit_regimes(returns, n_states=3)
print(result.current_regime)      # 'bull', 'bear', or 'neutral'
print(result.transition_matrix)   # State transition probabilities
```

### 4. `amihud_illiquidity.py` -- Amihud Illiquidity Ratio

**What**: Measures price impact per unit volume. Detects illiquid periods where backtest results are unreliable.

**When to use**: Before trusting any backtest. Most backtests assume infinite liquidity. Amihud's ratio flags periods where large price moves per unit volume indicate that your simulated fills would never happen in production.

**Math**:

```
ILLIQ = (10^6 / T) * sum_{t=1}^{T} |r_t| / volume_t
```

High ILLIQ = illiquid (large price impact). Low ILLIQ = liquid.

Rolling version computes ILLIQ over a trailing window for time-series monitoring.

**Example**:

```python
from tools.quant.amihud_illiquidity import amihud_ratio, flag_illiquid, rolling_amihud
import numpy as np

rng = np.random.default_rng(42)
returns = rng.normal(0, 0.02, size=500)
volumes = np.full(500, 1_000_000.0)
volumes[200:250] = 100_000.0  # Illiquid period

ratio = amihud_ratio(returns, volumes, window=20)
illiquid_mask = flag_illiquid(returns, volumes, threshold_pct=90)
rolling = rolling_amihud(returns, volumes, window=20)
```

## Dependencies

- **numpy** (required)
- **scipy** (required for cf_cvar and fama_macbeth)
- **hmmlearn** (optional, for hmm_regimes; graceful fallback to threshold method)

## Testing

```bash
cd ~/dharma_swarm
python3 -m pytest tools/quant/tests/test_quant.py -q --tb=short
```

## Shakti Trading Integration

These modules are designed to feed into the dharma_swarm trading system (ginko). Integration points:

- **cf_cvar**: Wire into position sizing. Replace normal VaR with CF-VaR for realistic risk budgets. When excess kurtosis > 1.0, CF-VaR can be 30-50% higher than normal VaR -- meaning you should hold 30-50% smaller positions than Gaussian risk says.

- **fama_macbeth**: Validate any alpha signal before it enters the strategy pipeline. A factor with |t-stat| < 2.0 after Newey-West correction is noise. Run this monthly on your factor zoo to prune dead signals.

- **hmm_regimes**: Feed current regime into strategy selection. Bull regime -> trend following. Bear regime -> mean reversion or cash. Neutral -> reduced position sizes. The transition matrix gives you regime persistence probabilities for forward-looking allocation.

- **amihud_illiquidity**: Gate all backtest results through illiquidity filtering. If Amihud ratio during a backtest period exceeds the 90th percentile of the full history, those returns are suspect. Flag them and rerun with realistic slippage assumptions.

The Four Shaktis mapping:
- **Kriya Shakti** (action): amihud -- can you actually execute this trade?
- **Jnana Shakti** (knowledge): fama_macbeth -- is this factor real?
- **Iccha Shakti** (will): hmm_regimes -- what environment are you in?
- **Para Shakti** (transcendent): cf_cvar -- what is your true risk?
