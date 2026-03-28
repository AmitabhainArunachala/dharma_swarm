"""dharma_swarm Quantitative Finance Toolkit.

Four modules for risk, alpha testing, regime detection, and liquidity.

Modules:
    cf_cvar: Cornish-Fisher adjusted VaR and CVaR for fat-tailed returns.
    fama_macbeth: Two-pass cross-sectional regression for factor risk premia.
    hmm_regimes: Hidden Markov Model market regime detection.
    amihud_illiquidity: Amihud illiquidity ratio and illiquid period flagging.
"""

from tools.quant.cf_cvar import (
    cornish_fisher_cvar,
    cornish_fisher_var,
    compare_var_methods,
)
from tools.quant.fama_macbeth import fama_macbeth
from tools.quant.hmm_regimes import fit_regimes
from tools.quant.amihud_illiquidity import amihud_ratio, flag_illiquid

__all__ = [
    "cornish_fisher_var",
    "cornish_fisher_cvar",
    "compare_var_methods",
    "fama_macbeth",
    "fit_regimes",
    "amihud_ratio",
    "flag_illiquid",
]
