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
from scipy import optimize, signal, special, stats

METHODS = ("historical", "gaussian", "student_t", "garch_t", "gjr_fhs")


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


def _garch_variance(r, omega, alpha, beta, initial, gamma=0.0):
    """sigma2_t = omega + (alpha + gamma 1[r_{t-1} < 0]) r_{t-1}^2 + beta sigma2_{t-1} (GJR when gamma > 0).

    Returns sigma2 for t = 0..n, where index n is the one-step-ahead forecast.
    """
    shock = (alpha + gamma * (r < 0)) * r * r
    drive = omega + np.r_[0.0, shock]
    drive[0] = initial
    return signal.lfilter([1.0], [1.0, -beta], drive)


def fit_garch_t(returns, start: dict | None = None, asymmetric: bool = False) -> dict:
    """Maximum-likelihood GARCH(1,1) (or GJR-GARCH when ``asymmetric``) with unit-variance t innovations.

    Constraints: omega > 0; alpha, beta, gamma >= 0; alpha + beta + gamma / 2 < 1; nu > 2.1.
    GJR adds gamma for negative shocks: equity volatility rises more after losses (leverage effect).
    """
    r = np.asarray(returns, dtype=np.float64)
    if r.ndim != 1 or len(r) < 100 or not np.isfinite(r).all():
        raise ValueError("GARCH needs at least 100 finite returns.")
    mu0, var0 = float(r.mean()), float(r.var())
    if var0 <= 0:
        raise ValueError("Returns have zero variance.")
    scale = math.sqrt(var0)
    z = (r - mu0) / scale  # Fit on standardised data for conditioning; rescale afterwards.

    def unpack(x):
        x = np.clip(x, -30, 30)  # Unconstrained search space; transforms keep every parameter valid.
        omega = math.exp(x[0])
        persistence = float(special.expit(x[1])) * .9999
        nu = 2.1 + math.exp(min(x[3], 6.0))
        if asymmetric:
            w = np.exp(np.r_[x[2], x[5], 0.0] - max(x[2], x[5], 0.0))
            w /= w.sum()
            return omega, persistence * w[0], persistence * w[2], nu, x[4], 2 * persistence * w[1]
        share = float(special.expit(x[2]))
        return omega, persistence * share, persistence * (1 - share), nu, x[4], 0.0

    def negative_log_likelihood(x):
        omega, alpha, beta, nu, mu, gamma = unpack(x)
        e = z - mu
        s2 = _garch_variance(e, omega, alpha, beta, 1.0, gamma)[:-1]
        if not np.isfinite(s2).all() or (s2 <= 0).any():
            return 1e12
        c = math.lgamma((nu + 1) / 2) - math.lgamma(nu / 2) - .5 * math.log(math.pi * (nu - 2))
        ll = c - .5 * np.log(s2) - (nu + 1) / 2 * np.log1p(e * e / (s2 * (nu - 2)))
        return -float(ll.sum())

    starts = [[math.log(.05), 2.5, -2.0, math.log(6), 0.0], [math.log(.1), 1.5, -1.0, math.log(10), 0.0]]
    if asymmetric:
        starts = [x + [-2.0] for x in starts]
    if start and start.get("_x") is not None:
        # A warm start alone stopped at a worse optimum in 29% of rolling refits (LL gap up to 43),
        # so it is always paired with a cold start and the better likelihood wins.
        starts = [start["_x"], starts[0]]
    best = None
    for x0 in starts:
        result = optimize.minimize(negative_log_likelihood, x0, method="L-BFGS-B")
        if best is None or result.fun < best.fun:
            best = result
    omega, alpha, beta, nu, mu, gamma = unpack(best.x)
    return {"_x": [float(v) for v in best.x], "gamma": gamma, "asymmetric": asymmetric,"omega": omega * var0, "alpha": alpha, "beta": beta, "nu": nu, "mu": mu0 + mu * scale,
            "persistence": alpha + beta + gamma / 2, "log_likelihood": -best.fun - len(r) * math.log(scale),
            "converged": bool(best.success)}


def garch_filter(returns, params) -> np.ndarray:
    """Conditional variances for every return in the window plus the one-step-ahead forecast."""
    r = np.asarray(returns, dtype=np.float64) - params["mu"]
    return _garch_variance(r, params["omega"], params["alpha"], params["beta"], float(r.var()), params.get("gamma", 0.0))


def garch_forecast_variance(returns, params) -> float:
    """One-step-ahead conditional variance after the last return, filtered from the sample variance."""
    return float(garch_filter(returns, params)[-1])


def rolling_var_levels(returns, *, window: int = 250, levels=(.01,), method: str = "historical",
                       refit_every: int = 1) -> dict:
    """One-day VaR forecasts (signed loss) for days window..n-1 from the prior window only.

    One model fit serves every tail level. ``refit_every`` > 1 runs the full Student-t
    or GARCH MLE only every k days; in between, Student-t location/scale are
    moment-matched and the GARCH variance is filtered daily. No step uses future data.
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
    levels = tuple(float(p) for p in levels)
    if not levels or not all(0 < p < 1 for p in levels):
        raise ValueError("Tail levels must be in (0, 1).")
    forecasts = {p: np.empty(len(r) - window) for p in levels}
    normal_q = {p: stats.norm.ppf(p) for p in levels}
    df = garch = None
    t_q = {}
    for i, t in enumerate(range(window, len(r))):
        past = r[t - window:t]  # Day t's own return is never visible to its forecast.
        if method == "historical":
            x = np.sort(past)
            for p in levels:
                forecasts[p][i] = -x[max(1, math.ceil(p * window - 1e-9)) - 1]
        elif method == "gaussian":
            mean, sd = past.mean(), past.std(ddof=1)
            for p in levels:
                forecasts[p][i] = -(mean + sd * normal_q[p])
        elif method == "garch_t":
            if garch is None or i % refit_every == 0:
                garch = fit_garch_t(past, start=garch)
                t_q = {p: stats.t.ppf(p, garch["nu"]) * math.sqrt((garch["nu"] - 2) / garch["nu"]) for p in levels}
            sigma = math.sqrt(garch_forecast_variance(past, garch))
            for p in levels:
                forecasts[p][i] = -(garch["mu"] + sigma * t_q[p])
        elif method == "gjr_fhs":
            # Filtered historical simulation: GJR-GARCH volatility times the empirical quantile of
            # standardised window residuals, so skew and tail shape come from data, not an assumed t.
            if garch is None or i % refit_every == 0:
                garch = fit_garch_t(past, start=garch, asymmetric=True)
            s2 = garch_filter(past, garch)
            standardised = np.sort((past - garch["mu"]) / np.sqrt(s2[:-1]))
            sigma = math.sqrt(s2[-1])
            for p in levels:
                k = max(1, math.ceil(p * window - 1e-9))
                forecasts[p][i] = -(garch["mu"] + sigma * standardised[k - 1])
        else:
            if df is None or i % refit_every == 0:
                df, loc, scale = stats.t.fit(past, *(() if df is None else (df,)),
                                             **({} if df is None else {"loc": loc, "scale": scale}))
                df = min(df, 1_000.0)
                t_q = {p: stats.t.ppf(p, df) for p in levels}
            elif df > 2:
                loc, scale = past.mean(), past.std(ddof=1) * math.sqrt((df - 2) / df)
            for p in levels:
                forecasts[p][i] = -(loc + scale * t_q[p])
    return forecasts


def rolling_var(returns, *, window: int = 250, p: float = .01, method: str = "historical",
                refit_every: int = 1) -> np.ndarray:
    return rolling_var_levels(returns, window=window, levels=(p,), method=method, refit_every=refit_every)[float(p)]


def backtest_var(returns, *, window: int = 250, p: float = .01, method: str = "historical",
                 refit_every: int = 1, forecasts=None) -> dict:
    r = np.asarray(returns, dtype=np.float64)
    if forecasts is None:
        forecasts = rolling_var(r, window=window, p=p, method=method, refit_every=refit_every)
    realised = r[window:]
    exceptions = realised < -forecasts
    return {"method": method, "window": window, "tail_probability": p, "refit_every": refit_every,
            **kupiec_christoffersen(exceptions, p),
            "exception_indices": (np.flatnonzero(exceptions) + window).tolist(),
            "mean_forecast": float(forecasts.mean())}
