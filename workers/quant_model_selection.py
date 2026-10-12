"""Dependence-aware paired model comparison for locked forward blocks.

This is a predeclared *single comparison* diagnostic. It does not adjust for
trying multiple candidate models or searching over bandwidths on holdout data.
"""
from __future__ import annotations

import math
import numpy as np


def newey_west_mean(values, *, lags: int) -> dict:
    """Bartlett HAC uncertainty for a mean under weakly dependent observations.

    long-run variance = gamma_0 + 2 sum_{k=1}^L (1-k/(L+1)) gamma_k;
    standard error = sqrt(max(LRV,0)/n).
    """
    x = np.asarray(values, dtype=np.float64)
    if x.ndim != 1 or len(x) < 3 or not np.isfinite(x).all():
        raise ValueError("Need at least three finite, one-dimensional observations.")
    if type(lags) is not int or not 0 <= lags < len(x):
        raise ValueError("lags must be an integer from 0 through n-1.")
    n = len(x)
    mu = float(x.mean())
    residual = x - mu
    long_run = float(np.dot(residual, residual)/n)
    for lag in range(1, lags + 1):
        autocov = float(np.dot(residual[lag:], residual[:-lag])/n)
        long_run += 2 * (1 - lag/(lags+1)) * autocov
    se = math.sqrt(max(long_run, 0.0)/n)
    return {"n": n, "mean": mu, "lags": lags,
            "long_run_variance": max(long_run, 0.0),
            "standard_error": se, "lower_95": mu-1.96*se,
            "upper_95": mu+1.96*se}


def paired_loss_comparison(candidate_losses, baseline_losses, *, lags: int) -> dict:
    """Positive mean advantage means candidate has lower realized loss.

    Candidate must be frozen before any of these outcomes are disclosed.
    Do not estimate parameters or choose lags using these withheld losses.
    """
    a = np.asarray(candidate_losses, dtype=np.float64)
    b = np.asarray(baseline_losses, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("Paired losses must match exactly.")
    result = newey_west_mean(b-a, lags=lags)
    result["candidate_better_at_nominal_95"] = bool(result["lower_95"] > 0 and result["standard_error"] > 0)
    result["caution"] = "Nominal, single prespecified comparison; no search/multiplicity correction."
    return result
