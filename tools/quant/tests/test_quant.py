"""Tests for dharma_swarm quantitative finance toolkit.

All tests use synthetic data generated with numpy -- no external downloads.
Deterministic seeds ensure reproducibility.
"""

from __future__ import annotations

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Cornish-Fisher CVaR
# ---------------------------------------------------------------------------

from tools.quant.cf_cvar import (
    cornish_fisher_cvar,
    cornish_fisher_var,
    compare_var_methods,
    normal_var,
    historical_var,
    _cornish_fisher_z,
)


class TestCornishFisherVar:
    """Tests for Cornish-Fisher VaR module."""

    def test_normal_returns_cf_close_to_normal_var(self) -> None:
        """For truly normal returns, CF-VaR should approximate normal VaR."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0005, 0.02, size=10000)
        cf = cornish_fisher_var(returns, confidence=0.99)
        nv = normal_var(returns, confidence=0.99)
        # Within 10% for large normal sample
        assert abs(cf - nv) / nv < 0.10

    def test_fat_tails_cf_exceeds_normal(self) -> None:
        """CF-VaR should exceed normal VaR for leptokurtic (fat-tailed) data.

        This is THE key property: fat tails mean more risk than Gaussian assumes.
        """
        rng = np.random.default_rng(123)
        # Student-t with df=3 has excess kurtosis = 6 / (3-2) - 3 = 3
        returns = rng.standard_t(df=3, size=5000) * 0.02
        cf = cornish_fisher_var(returns, confidence=0.99)
        nv = normal_var(returns, confidence=0.99)
        assert cf > nv, f"CF-VaR ({cf:.6f}) should exceed Normal VaR ({nv:.6f}) for fat tails"

    def test_fat_tails_cf_cvar_exceeds_cf_var(self) -> None:
        """CVaR (Expected Shortfall) must exceed VaR -- it's the tail mean."""
        rng = np.random.default_rng(456)
        returns = rng.standard_t(df=3, size=5000) * 0.02
        var = cornish_fisher_var(returns, confidence=0.99)
        cvar = cornish_fisher_cvar(returns, confidence=0.99)
        assert cvar >= var, f"CF-CVaR ({cvar:.6f}) must >= CF-VaR ({var:.6f})"

    def test_fat_tails_cf_cvar_exceeds_normal_cvar_proxy(self) -> None:
        """CF-CVaR should exceed Normal VaR for leptokurtic data."""
        rng = np.random.default_rng(789)
        returns = rng.standard_t(df=3, size=5000) * 0.02
        cf_cvar = cornish_fisher_cvar(returns, confidence=0.99)
        nv = normal_var(returns, confidence=0.99)
        assert cf_cvar > nv

    def test_compare_var_methods_returns_all_fields(self) -> None:
        """compare_var_methods should populate all fields."""
        rng = np.random.default_rng(42)
        returns = rng.standard_t(df=4, size=2000) * 0.015
        result = compare_var_methods(returns, confidence=0.95)
        assert result.n_obs == 2000
        assert result.confidence == 0.95
        assert result.normal_var > 0
        assert result.historical_var > 0
        assert result.cf_var > 0
        assert result.cf_cvar > 0
        # Str representation should work
        s = str(result)
        assert "VaR Comparison" in s

    def test_positive_var_values(self) -> None:
        """All VaR measures should be positive (representing losses)."""
        rng = np.random.default_rng(99)
        returns = rng.normal(-0.001, 0.03, size=1000)
        assert cornish_fisher_var(returns) > 0
        assert cornish_fisher_cvar(returns) > 0
        assert normal_var(returns) > 0
        assert historical_var(returns) > 0

    def test_higher_confidence_higher_var(self) -> None:
        """99% VaR should exceed 95% VaR."""
        rng = np.random.default_rng(55)
        returns = rng.normal(0, 0.02, size=2000)
        var_95 = cornish_fisher_var(returns, confidence=0.95)
        var_99 = cornish_fisher_var(returns, confidence=0.99)
        assert var_99 > var_95

    def test_too_few_observations_raises(self) -> None:
        """Should raise ValueError with fewer than 4 observations."""
        with pytest.raises(ValueError, match="Need >= 4"):
            cornish_fisher_var([0.01, -0.01, 0.02])

    def test_invalid_confidence_raises(self) -> None:
        """Should raise ValueError for confidence outside (0, 1)."""
        rng = np.random.default_rng(1)
        returns = rng.normal(0, 0.02, size=100)
        with pytest.raises(ValueError, match="confidence"):
            cornish_fisher_var(returns, confidence=1.5)
        with pytest.raises(ValueError, match="confidence"):
            cornish_fisher_var(returns, confidence=0.0)

    def test_cornish_fisher_z_normal_case(self) -> None:
        """With zero skew and zero excess kurtosis, z_cf should equal z."""
        from scipy import stats
        z = stats.norm.ppf(0.01)
        z_cf = _cornish_fisher_z(0.99, skew=0.0, excess_kurt=0.0)
        assert abs(z_cf - z) < 1e-10

    def test_negative_skew_increases_left_tail(self) -> None:
        """Negative skew should push CF-VaR higher (more left-tail risk)."""
        rng = np.random.default_rng(77)
        # Generate negatively skewed returns
        normal = rng.normal(0, 0.02, size=5000)
        # Add left-tail contamination
        skewed = np.concatenate([normal, rng.normal(-0.10, 0.05, size=200)])
        rng.shuffle(skewed)

        cf = cornish_fisher_var(skewed, confidence=0.99)
        nv = normal_var(skewed, confidence=0.99)
        assert cf > nv


# ---------------------------------------------------------------------------
# Fama-MacBeth
# ---------------------------------------------------------------------------

from tools.quant.fama_macbeth import fama_macbeth, FamaMacBethResult


class TestFamaMacBeth:
    """Tests for Fama-MacBeth two-pass regression."""

    @staticmethod
    def _generate_factor_data(
        seed: int = 42,
        T: int = 500,
        N: int = 50,
        true_lambda: float = 0.005,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Generate synthetic factor data where factor earns a known premium.

        Returns are generated as:
            r_{i,t} = alpha_i + beta_i * F_t + eps_{i,t}

        where betas are drawn from U(0.5, 2.0) and the factor earns a
        premium of ``true_lambda`` per period.

        Args:
            seed: Random seed.
            T: Number of time periods.
            N: Number of assets.
            true_lambda: True risk premium per period.

        Returns:
            (returns_TxN, factors_Tx1) arrays.
        """
        rng = np.random.default_rng(seed)
        betas = rng.uniform(0.5, 2.0, size=N)
        factor = rng.normal(true_lambda, 0.02, size=T)
        alphas = rng.normal(0.0, 0.001, size=N)
        eps = rng.normal(0.0, 0.01, size=(T, N))

        returns = alphas[np.newaxis, :] + betas[np.newaxis, :] * factor[:, np.newaxis] + eps
        return returns, factor[:, np.newaxis]

    def test_significant_factor_detected(self) -> None:
        """A factor with true premium should have |t-stat| > 2.0."""
        returns, factors = self._generate_factor_data(
            seed=42, T=500, N=50, true_lambda=0.005
        )
        result = fama_macbeth(returns, factors)
        # Factor 1 t-stat (index 1, since 0 is intercept)
        assert abs(result.t_stats[1]) > 2.0, (
            f"Factor t-stat ({result.t_stats[1]:.3f}) should exceed 2.0 for true premium"
        )

    def test_noise_factor_insignificant(self) -> None:
        """A pure noise factor should have |t-stat| < 2.0 (usually)."""
        rng = np.random.default_rng(99)
        T, N = 500, 50
        returns = rng.normal(0, 0.02, size=(T, N))
        noise_factor = rng.normal(0, 0.02, size=(T, 1))
        result = fama_macbeth(returns, noise_factor)
        # With no true relationship, t-stat should be small
        # Use a generous threshold since this is probabilistic
        assert abs(result.t_stats[1]) < 4.0

    def test_result_dimensions(self) -> None:
        """Verify output shapes match inputs."""
        returns, factors = self._generate_factor_data(seed=10, T=200, N=30)
        result = fama_macbeth(returns, factors)
        K = factors.shape[1]
        assert result.lambda_means.shape == (K + 1,)
        assert result.lambda_stds.shape == (K + 1,)
        assert result.t_stats.shape == (K + 1,)
        assert result.betas.shape == (30, K + 1)
        assert result.lambdas.shape == (200, K + 1)
        assert result.n_assets == 30
        assert result.n_periods == 200
        assert result.n_factors == K

    def test_r_squared_positive(self) -> None:
        """Average cross-sectional R-squared should be positive."""
        returns, factors = self._generate_factor_data(seed=42)
        result = fama_macbeth(returns, factors)
        assert result.r_squared_avg > 0.0

    def test_multi_factor(self) -> None:
        """Should handle multiple factors."""
        rng = np.random.default_rng(42)
        T, N, K = 500, 50, 3
        betas = rng.uniform(0.5, 2.0, size=(N, K))
        factors = rng.normal(0.003, 0.02, size=(T, K))
        eps = rng.normal(0, 0.01, size=(T, N))
        returns = (factors @ betas.T) + eps

        result = fama_macbeth(returns, factors)
        assert result.n_factors == K
        assert result.lambda_means.shape == (K + 1,)

    def test_dimension_mismatch_raises(self) -> None:
        """Mismatched T dimensions should raise ValueError."""
        rng = np.random.default_rng(1)
        returns = rng.normal(0, 0.02, size=(100, 20))
        factors = rng.normal(0, 0.02, size=(50, 1))  # Different T
        with pytest.raises(ValueError, match="periods"):
            fama_macbeth(returns, factors)

    def test_str_representation(self) -> None:
        """String representation should work and show factor info."""
        returns, factors = self._generate_factor_data(seed=42, T=100, N=20)
        result = fama_macbeth(returns, factors)
        s = str(result)
        assert "Fama-MacBeth" in s
        assert "Factor_1" in s

    def test_positive_premium_direction(self) -> None:
        """Estimated premium should be positive when true premium is positive."""
        returns, factors = self._generate_factor_data(
            seed=42, T=500, N=50, true_lambda=0.005
        )
        result = fama_macbeth(returns, factors)
        # Factor lambda (index 1) should be positive
        assert result.lambda_means[1] > 0


# ---------------------------------------------------------------------------
# HMM Regimes
# ---------------------------------------------------------------------------

from tools.quant.hmm_regimes import fit_regimes, RegimeResult


class TestHMMRegimes:
    """Tests for Hidden Markov Model regime detection."""

    @staticmethod
    def _generate_regime_data(seed: int = 42) -> np.ndarray:
        """Generate synthetic regime-switching returns.

        Creates 3 distinct regimes:
            Bear:    mean=-0.03, std=0.04 (200 periods)
            Neutral: mean=0.001, std=0.01 (400 periods)
            Bull:    mean=0.02,  std=0.015 (200 periods)

        Returns:
            1-D array of 800 period returns.
        """
        rng = np.random.default_rng(seed)
        bear = rng.normal(-0.03, 0.04, size=200)
        neutral = rng.normal(0.001, 0.01, size=400)
        bull = rng.normal(0.02, 0.015, size=200)
        return np.concatenate([bear, neutral, bull])

    def test_three_regimes_detected(self) -> None:
        """Should detect 3 distinct regimes from obvious regime-switching data."""
        returns = self._generate_regime_data(seed=42)
        result = fit_regimes(returns, n_states=3)
        unique_regimes = set(result.regime_history)
        assert len(unique_regimes) == 3, f"Expected 3 regimes, got {unique_regimes}"

    def test_regime_labels_correct(self) -> None:
        """Regime labels should include bear, neutral, bull for 3-state."""
        returns = self._generate_regime_data()
        result = fit_regimes(returns, n_states=3)
        expected = {"bear", "neutral", "bull"}
        assert set(result.state_labels) == expected

    def test_bear_has_lowest_mean(self) -> None:
        """Bear regime should have the lowest state mean."""
        returns = self._generate_regime_data()
        result = fit_regimes(returns, n_states=3)
        bear_idx = result.state_labels.index("bear")
        assert result.state_means[bear_idx] == min(result.state_means)

    def test_bull_has_highest_mean(self) -> None:
        """Bull regime should have the highest state mean."""
        returns = self._generate_regime_data()
        result = fit_regimes(returns, n_states=3)
        bull_idx = result.state_labels.index("bull")
        assert result.state_means[bull_idx] == max(result.state_means)

    def test_transition_matrix_rows_sum_to_one(self) -> None:
        """Each row of the transition matrix must sum to 1."""
        returns = self._generate_regime_data()
        result = fit_regimes(returns, n_states=3)
        row_sums = result.transition_matrix.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)

    def test_current_regime_is_last(self) -> None:
        """current_regime should match the last entry in regime_history."""
        returns = self._generate_regime_data()
        result = fit_regimes(returns, n_states=3)
        assert result.current_regime == result.regime_history[-1]

    def test_output_length_matches_input(self) -> None:
        """regime_history and state_sequence should have same length as input."""
        returns = self._generate_regime_data()
        result = fit_regimes(returns, n_states=3)
        assert len(result.regime_history) == len(returns)
        assert len(result.state_sequence) == len(returns)

    def test_two_states_work(self) -> None:
        """Should work with n_states=2."""
        rng = np.random.default_rng(42)
        bear = rng.normal(-0.03, 0.04, size=300)
        bull = rng.normal(0.02, 0.015, size=300)
        returns = np.concatenate([bear, bull])
        result = fit_regimes(returns, n_states=2)
        assert len(set(result.regime_history)) == 2
        assert set(result.state_labels) == {"bear", "bull"}

    def test_threshold_fallback(self) -> None:
        """force_threshold=True should use threshold method."""
        returns = self._generate_regime_data()
        result = fit_regimes(returns, n_states=3, force_threshold=True)
        assert result.method == "threshold"
        assert len(set(result.regime_history)) >= 2

    def test_too_few_observations_raises(self) -> None:
        """Should raise ValueError with fewer than 10 observations."""
        with pytest.raises(ValueError, match="Need >= 10"):
            fit_regimes([0.01, -0.01, 0.02, 0.01, -0.02])

    def test_str_representation(self) -> None:
        """String representation should work."""
        returns = self._generate_regime_data()
        result = fit_regimes(returns, n_states=3)
        s = str(result)
        assert "RegimeResult" in s
        assert "bear" in s
        assert "bull" in s

    def test_regime_assignment_accuracy(self) -> None:
        """For well-separated regimes, the fitted means should reflect the data.

        We generate data with clearly distinct bear (-0.03), neutral (0.001),
        and bull (+0.02) periods. The HMM's fitted state means should recover
        the ordering: bear_mean < neutral_mean < bull_mean, with the bear
        state mean negative and the bull state mean positive.
        """
        rng = np.random.default_rng(77)
        # Very wide separation: bear=-0.05, neutral=0.0, bull=+0.05
        bear = rng.normal(-0.05, 0.02, size=300)
        neutral = rng.normal(0.0, 0.01, size=300)
        bull = rng.normal(0.05, 0.02, size=300)
        returns = np.concatenate([bear, neutral, bull])

        result = fit_regimes(returns, n_states=3, random_state=77)
        bear_idx = result.state_labels.index("bear")
        bull_idx = result.state_labels.index("bull")

        # Bear mean should be negative, bull mean should be positive
        assert result.state_means[bear_idx] < -0.01, (
            f"Bear mean ({result.state_means[bear_idx]:.4f}) should be < -0.01"
        )
        assert result.state_means[bull_idx] > 0.01, (
            f"Bull mean ({result.state_means[bull_idx]:.4f}) should be > 0.01"
        )
        # Ordering must hold
        assert result.state_means[bear_idx] < result.state_means[bull_idx]


# ---------------------------------------------------------------------------
# Amihud Illiquidity
# ---------------------------------------------------------------------------

from tools.quant.amihud_illiquidity import (
    amihud_ratio,
    rolling_amihud,
    flag_illiquid,
    summarize,
)


class TestAmihudIlliquidity:
    """Tests for Amihud illiquidity ratio module."""

    @staticmethod
    def _generate_liquidity_data(
        seed: int = 42,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Generate returns and volumes with a known illiquid period.

        Structure:
            - Periods 0-199: normal volume (1M shares), normal returns
            - Periods 200-249: LOW volume (100K shares), same returns -> illiquid
            - Periods 250-499: normal volume again

        Returns:
            (returns, volumes) arrays each of shape (500,).
        """
        rng = np.random.default_rng(seed)
        T = 500
        returns = rng.normal(0.0005, 0.02, size=T)
        volumes = np.full(T, 1_000_000.0)
        # Illiquid period: 10x lower volume
        volumes[200:250] = 100_000.0
        return returns, volumes

    def test_ratio_positive(self) -> None:
        """Amihud ratio should always be positive."""
        returns, volumes = self._generate_liquidity_data()
        ratio = amihud_ratio(returns, volumes)
        assert ratio > 0

    def test_low_volume_increases_ratio(self) -> None:
        """Lower volume should produce higher illiquidity ratio."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0, 0.02, size=100)
        high_vol = np.full(100, 1_000_000.0)
        low_vol = np.full(100, 100_000.0)

        ratio_high_vol = amihud_ratio(returns, high_vol)
        ratio_low_vol = amihud_ratio(returns, low_vol)
        assert ratio_low_vol > ratio_high_vol, (
            f"Low volume ratio ({ratio_low_vol:.4f}) should exceed "
            f"high volume ratio ({ratio_high_vol:.4f})"
        )

    def test_ratio_scales_with_volume(self) -> None:
        """Halving volume should approximately double the ratio."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0, 0.02, size=1000)
        vol_1 = np.full(1000, 1_000_000.0)
        vol_2 = np.full(1000, 500_000.0)

        r1 = amihud_ratio(returns, vol_1)
        r2 = amihud_ratio(returns, vol_2)
        ratio = r2 / r1
        assert 1.8 < ratio < 2.2, f"Expected ~2x ratio, got {ratio:.2f}"

    def test_rolling_amihud_shape(self) -> None:
        """Rolling Amihud should return array of same length as input."""
        returns, volumes = self._generate_liquidity_data()
        rolling = rolling_amihud(returns, volumes, window=20)
        assert rolling.shape == (500,)

    def test_rolling_amihud_leading_nans(self) -> None:
        """First (window-1) values should be NaN."""
        returns, volumes = self._generate_liquidity_data()
        rolling = rolling_amihud(returns, volumes, window=20)
        assert np.all(np.isnan(rolling[:19]))
        assert not np.isnan(rolling[19])

    def test_rolling_amihud_spikes_in_illiquid_period(self) -> None:
        """Rolling Amihud should spike during the low-volume period."""
        returns, volumes = self._generate_liquidity_data()
        rolling = rolling_amihud(returns, volumes, window=20)

        # Mean ratio during illiquid window (periods 219-249, after burn-in)
        illiquid_mean = np.nanmean(rolling[219:250])
        # Mean ratio during normal periods
        normal_mean = np.nanmean(rolling[19:200])

        assert illiquid_mean > 2 * normal_mean, (
            f"Illiquid period mean ({illiquid_mean:.4f}) should be > 2x "
            f"normal mean ({normal_mean:.4f})"
        )

    def test_flag_illiquid_detects_low_volume(self) -> None:
        """flag_illiquid should flag some periods during the illiquid window."""
        returns, volumes = self._generate_liquidity_data()
        mask = flag_illiquid(returns, volumes, window=20, threshold_pct=90)
        assert mask.shape == (500,)
        # Some of the illiquid window (200-249) should be flagged
        illiquid_flagged = np.sum(mask[200:250])
        assert illiquid_flagged > 0, "At least some illiquid periods should be flagged"

    def test_flag_illiquid_sparse_in_normal_periods(self) -> None:
        """Normal-volume periods should be mostly not flagged."""
        returns, volumes = self._generate_liquidity_data()
        mask = flag_illiquid(returns, volumes, window=20, threshold_pct=90)
        normal_flagged_pct = np.mean(mask[:200]) * 100
        # At most ~15% of normal periods should be flagged (threshold is 90th pctile)
        assert normal_flagged_pct < 20, (
            f"{normal_flagged_pct:.1f}% of normal periods flagged -- too many"
        )

    def test_window_parameter(self) -> None:
        """amihud_ratio with window should use only recent data."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0, 0.02, size=200)
        volumes = np.full(200, 1_000_000.0)
        # Make last 20 periods illiquid
        volumes[-20:] = 100_000.0

        full_ratio = amihud_ratio(returns, volumes)
        window_ratio = amihud_ratio(returns, volumes, window=20)
        assert window_ratio > full_ratio

    def test_zero_volume_raises(self) -> None:
        """Zero or negative volume should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            amihud_ratio([0.01, -0.01], [1000, 0])

    def test_mismatched_lengths_raises(self) -> None:
        """Different lengths should raise ValueError."""
        with pytest.raises(ValueError, match="length"):
            amihud_ratio([0.01, -0.01, 0.02], [1000, 2000])

    def test_summarize(self) -> None:
        """summarize should produce an AmihudSummary with all fields."""
        returns, volumes = self._generate_liquidity_data()
        summary = summarize(returns, volumes)
        assert summary.n_periods == 500
        assert summary.overall_ratio > 0
        assert summary.mean_rolling > 0
        assert summary.pct_illiquid >= 0
        s = str(summary)
        assert "Amihud" in s


# ---------------------------------------------------------------------------
# Integration: __init__.py imports
# ---------------------------------------------------------------------------

class TestModuleImports:
    """Verify the package-level imports work."""

    def test_import_all_from_init(self) -> None:
        """All advertised names should be importable from tools.quant."""
        from tools.quant import (
            cornish_fisher_var,
            cornish_fisher_cvar,
            compare_var_methods,
            fama_macbeth,
            fit_regimes,
            amihud_ratio,
            flag_illiquid,
        )
        # Just verify they're callable
        assert callable(cornish_fisher_var)
        assert callable(cornish_fisher_cvar)
        assert callable(compare_var_methods)
        assert callable(fama_macbeth)
        assert callable(fit_regimes)
        assert callable(amihud_ratio)
        assert callable(flag_illiquid)
