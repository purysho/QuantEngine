"""Out-of-sample VaR exception backtests (Kupiec 1995; Christoffersen 1998).

A forecast for day t uses only returns before t. An exception is a realised
return below minus the VaR forecast. Tests:

* Kupiec proportion of failures: H0 exception rate = p, LR ~ chi2(1).
* Christoffersen independence: H0 exceptions are not clustered (first-order
  Markov), LR ~ chi2(1).
* Conditional coverage = sum of both, LR ~ chi2(2).
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats

METHODS = ("historical", "gaussian", "student_t")


def _xlogy(x, y):
    return 0.0 if x == 0 else x * math.log(y)


def kupiec_christoffersen(exceptions, p: float) -> dict:
    hits = np.asarray(exceptions, dtype=bool)
    n, x = len(hits), int(hits.sum())
    if n < 2 or not 0 < p < 1:
        raise ValueError("Need at least two forecasts and 0 < p < 1.")
    rate = x / n
    lr_pof = -2 * (_xlogy(n - x, 1 - p) + _xlogy(x, p) - _xlogy(n - x, 1 - rate) - _xlogy(x, rate))
    prev, curr = hits[:-1], hits[1:]
    n00, n01 = int(np.sum(~prev & ~curr)), int(np.sum(~prev & curr))
    n10, n11 = int(np.sum(prev & ~curr)), int(np.sum(prev & curr))
    pi0 = n01 / (n00 + n01) if n00 + n01 else 0.0
    pi1 = n11 / (n10 + n11) if n10 + n11 else 0.0
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)
    lr_ind = -2 * (_xlogy(n00 + n10, 1 - pi) + _xlogy(n01 + n11, pi)
                   - _xlogy(n00, 1 - pi0) - _xlogy(n01, pi0) - _xlogy(n10, 1 - pi1) - _xlogy(n11, pi1))
    lr_ind = max(lr_ind, 0.0)
    lr_pof = max(lr_pof, 0.0)
    return {"forecasts": n, "exceptions": x, "expected_exceptions": n * p, "exception_rate": rate,
            "kupiec_lr": lr_pof, "kupiec_p_value": float(stats.chi2.sf(lr_pof, 1)),
            "independence_lr": lr_ind, "independence_p_value": float(stats.chi2.sf(lr_ind, 1)),
            "conditional_coverage_lr": lr_pof + lr_ind,
            "conditional_coverage_p_value": float(stats.chi2.sf(lr_pof + lr_ind, 2)),
            "transitions": {"n00": n00, "n01": n01, "n10": n10, "n11": n11}}


def rolling_var(returns, *, window: int = 250, p: float = .01, method: str = "historical",
                refit_every: int = 1) -> np.ndarray:
    """One-day VaR forecasts (signed loss) for days window..n-1 from the prior window only.

    ``refit_every`` > 1 runs the full Student-t MLE only every k days. Between refits,
    degrees of freedom are held and location/scale are moment-matched daily
    (mean, sd * sqrt((df - 2) / df)) when df > 2. No step uses future data.
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.ndim != 1 or not np.isfinite(r).all():
        raise ValueError("Returns must be a finite one-dimensional array.")
    if isinstance(window, bool) or not isinstance(window, int) or not 30 <= window < len(r):
        raise ValueError("Window must be an integer of at least 30 and shorter than the sample.")
    if method not in METHODS:
        raise ValueError(f"Method must be one of {METHODS}.")
    if isinstance(refit_every, bool) or not isinstance(refit_every, int) or not 1 <= refit_every <= 250:
        raise ValueError("refit_every must be an integer from 1 to 250.")
    df = None
    forecasts = np.empty(len(r) - window)
    for i, t in enumerate(range(window, len(r))):
        past = r[t - window:t]  # Day t's own return is never visible to its forecast.
        if method == "historical":
            x = np.sort(past)
            forecasts[i] = -x[max(1, math.ceil(p * window - 1e-9)) - 1]
        elif method == "gaussian":
            forecasts[i] = -(past.mean() + past.std(ddof=1) * stats.norm.ppf(p))
        else:
            if df is None or i % refit_every == 0:
                df, loc, scale = stats.t.fit(past)
                df = min(df, 1_000.0)
            elif df > 2:
                loc, scale = past.mean(), past.std(ddof=1) * math.sqrt((df - 2) / df)
            forecasts[i] = -(loc + scale * stats.t.ppf(p, df))
    return forecasts


def backtest_var(returns, *, window: int = 250, p: float = .01, method: str = "historical",
                 refit_every: int = 1) -> dict:
    r = np.asarray(returns, dtype=np.float64)
    forecasts = rolling_var(r, window=window, p=p, method=method, refit_every=refit_every)
    realised = r[window:]
    exceptions = realised < -forecasts
    return {"method": method, "window": window, "tail_probability": p, "refit_every": refit_every,
            **kupiec_christoffersen(exceptions, p),
            "exception_indices": (np.flatnonzero(exceptions) + window).tolist(),
            "mean_forecast": float(forecasts.mean())}
