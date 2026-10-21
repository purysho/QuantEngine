"""Statistics for judging whether a backtest's profit is real.

* Newey–West (HAC) standard error of a mean return: daily strategy returns are autocorrelated,
  so the naive t-statistic overstates confidence.
* Probabilistic and Deflated Sharpe Ratio (Bailey & López de Prado, 2012 and 2014): the
  probability that the true Sharpe ratio exceeds a benchmark, allowing for skew, fat tails,
  sample length and, for the deflated version, how many strategy variants were tried.
* Stationary block bootstrap confidence interval for the Sharpe ratio (Politis & Romano, 1994).
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats

EULER_GAMMA = 0.5772156649015329
PERIODS_PER_YEAR = 252


def _clean(returns) -> np.ndarray:
    r = np.asarray(returns, dtype=np.float64)
    if r.ndim != 1 or len(r) < 30 or not np.isfinite(r).all():
        raise ValueError("Need at least 30 finite periodic returns.")
    return r


def newey_west_lags(n: int) -> int:
    """Automatic lag length floor(4 (n/100)^(2/9)) (Newey & West, 1994)."""
    return int(math.floor(4 * (n / 100.0) ** (2.0 / 9.0)))


def newey_west_mean(returns, lags: int | None = None) -> dict:
    """Mean, HAC standard error (Bartlett kernel) and t-statistic of the mean."""
    r = _clean(returns)
    n = len(r)
    lags = newey_west_lags(n) if lags is None else int(lags)
    e = r - r.mean()
    variance = float(e @ e) / n
    for lag in range(1, lags + 1):
        weight = 1 - lag / (lags + 1)
        variance += 2 * weight * float(e[lag:] @ e[:-lag]) / n
    se = math.sqrt(max(variance, 0.0) / n)
    naive = float(r.std(ddof=1)) / math.sqrt(n)
    return {"mean": float(r.mean()), "se": se, "t": float(r.mean() / se) if se > 0 else float("nan"),
            "naive_se": naive, "lags": lags, "n": n}


def sharpe(returns, periods: int = PERIODS_PER_YEAR) -> float:
    r = _clean(returns)
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(periods)) if sd > 0 else float("nan")


def probabilistic_sharpe(returns, benchmark: float = 0.0) -> float:
    """P(true per-period Sharpe > benchmark) given skew and kurtosis of the sample (PSR)."""
    r = _clean(returns)
    sd = r.std(ddof=1)
    if sd == 0:
        return float("nan")
    sr = r.mean() / sd
    skew = float(stats.skew(r))
    kurt = float(stats.kurtosis(r, fisher=False))
    denominator = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    if denominator <= 0:
        return float("nan")
    return float(stats.norm.cdf((sr - benchmark) * math.sqrt(len(r) - 1) / math.sqrt(denominator)))


def expected_max_sharpe(trial_sharpes, n_trials: int | None = None) -> float:
    """Expected maximum per-period Sharpe among N unskilled trials with the observed dispersion."""
    values = np.asarray(trial_sharpes, dtype=np.float64)
    n = len(values) if n_trials is None else int(n_trials)
    if n < 2:
        return 0.0
    sd = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    return sd * ((1 - EULER_GAMMA) * stats.norm.ppf(1 - 1 / n) + EULER_GAMMA * stats.norm.ppf(1 - 1 / (n * math.e)))


def deflated_sharpe(returns, trial_sharpes, n_trials: int | None = None) -> dict:
    """Deflated Sharpe Ratio: PSR against the Sharpe a lucky best-of-N search would show by chance.

    ``trial_sharpes`` are the per-period (not annualised) Sharpe ratios of every variant tried.
    """
    threshold = expected_max_sharpe(trial_sharpes, n_trials)
    return {"dsr": probabilistic_sharpe(returns, threshold), "threshold_per_period": threshold,
            "threshold_annual": threshold * math.sqrt(PERIODS_PER_YEAR),
            "trials": int(n_trials or len(trial_sharpes))}


def bootstrap_sharpe(returns, *, block: int = 21, draws: int = 2000, seed: int = 7, periods: int = PERIODS_PER_YEAR) -> dict:
    """Stationary block bootstrap 90% and 95% intervals for the annualised Sharpe ratio."""
    r = _clean(returns)
    n = len(r)
    rng = np.random.default_rng(seed)
    positions = np.arange(n)
    out = np.empty(draws)
    for d in range(draws):
        # Geometric block lengths: a new block starts with probability 1/block; inside a block the index advances by one.
        restart = rng.random(n) < 1.0 / block
        restart[0] = True
        starts = rng.integers(0, n, n)
        last = np.maximum.accumulate(np.where(restart, positions, 0))
        sample = r[(starts[last] + positions - last) % n]
        sd = sample.std(ddof=1)
        out[d] = sample.mean() / sd * math.sqrt(periods) if sd > 0 else 0.0
    return {"sharpe": sharpe(r, periods), "ci90": [float(np.quantile(out, .05)), float(np.quantile(out, .95))],
            "ci95": [float(np.quantile(out, .025)), float(np.quantile(out, .975))],
            "p_sharpe_le_0": float(np.mean(out <= 0)), "block": block, "draws": draws, "seed": seed}


def bootstrap_sharpe_difference(a, b, *, block: int = 21, draws: int = 1000, seed: int = 11, periods: int = PERIODS_PER_YEAR) -> dict:
    """Paired stationary bootstrap of Sharpe(a) - Sharpe(b): the same resampled days for both series."""
    x, y = _clean(a), _clean(b)
    if len(x) != len(y):
        raise ValueError("Series must cover the same days.")
    n = len(x)
    rng = np.random.default_rng(seed)
    positions = np.arange(n)
    out = np.empty(draws)
    for d in range(draws):
        restart = rng.random(n) < 1.0 / block
        restart[0] = True
        starts = rng.integers(0, n, n)
        last = np.maximum.accumulate(np.where(restart, positions, 0))
        index = (starts[last] + positions - last) % n
        sx, sy = x[index], y[index]
        out[d] = (sx.mean() / sx.std(ddof=1) - sy.mean() / sy.std(ddof=1)) * math.sqrt(periods)
    return {"difference": sharpe(x, periods) - sharpe(y, periods), "ci95": [float(np.quantile(out, .025)), float(np.quantile(out, .975))],
            "p_better": float(np.mean(out > 0)), "draws": draws, "block": block, "seed": seed}


def max_drawdown(returns) -> float:
    wealth = np.cumprod(1 + np.asarray(returns, dtype=np.float64))
    peak = np.maximum.accumulate(wealth)
    return float((wealth / peak - 1).min())


def summary(returns, periods: int = PERIODS_PER_YEAR) -> dict:
    r = _clean(returns)
    years = len(r) / periods
    growth = float(np.prod(1 + r))
    return {"annual_return": growth ** (1 / years) - 1 if growth > 0 else -1.0,
            "annual_volatility": float(r.std(ddof=1) * math.sqrt(periods)),
            "sharpe": sharpe(r, periods), "max_drawdown": max_drawdown(r), "years": years,
            "skew": float(stats.skew(r)), "kurtosis": float(stats.kurtosis(r, fisher=False))}
