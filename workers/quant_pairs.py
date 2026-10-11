"""Engle–Granger pairs research with formation-only fitting and next-close execution.

Unit-root and cointegration inference follow MacKinnon: critical values from
MacKinnon (2010, Table 2 response surfaces, constant case) and approximate
p-values from MacKinnon (1994). Constants were cross-checked against an
independent implementation; see THIRD_PARTY_NOTICES.md.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
from scipy import stats

# MacKinnon (2010) constant-case response surfaces: tau(T) = b0 + b1/T + b2/T^2 + b3/T^3
# Rows N = 1 (ADF), 2, 3 I(1) series; columns 1%, 5%, 10%.
_TAU_2010_C = np.array([
    [[-3.43035, -6.5393, -16.786, -79.433], [-2.86154, -2.8903, -4.234, -40.040], [-2.56677, -1.5384, -2.809, 0.0]],
    [[-3.89644, -10.9519, -33.527, 0.0], [-3.33613, -6.1101, -6.823, 0.0], [-3.04445, -4.2412, -2.720, 0.0]],
    [[-4.29374, -14.4354, -33.195, 47.433], [-3.74066, -8.5632, -10.852, 27.982], [-3.45218, -6.2143, -3.718, 0.0]],
])
# MacKinnon (1994) constant-case p-value approximations, N = 1..3.
_TAU_MAX_C = [2.74, 0.92, 0.55]
_TAU_MIN_C = [-18.83, -18.86, -23.48]
_TAU_STAR_C = [-1.61, -2.62, -3.13]
_SMALL_P_C = [[2.1659, 1.4412, 0.038269], [2.92, 1.5012, 0.039796], [3.4699, 1.4856, 0.03164]]
_LARGE_P_C = [[1.7339, 0.93202, -0.12745, -0.010368], [2.1945, 0.64695, -0.29198, -0.042377],
              [2.5893, 0.45168, -0.36529, -0.050074]]
TRADING_DAYS = 252


def mackinnon_critical_values(n_series: int = 1, nobs: float = math.inf) -> dict:
    if n_series not in (1, 2, 3):
        raise ValueError("Critical values are provided for 1–3 I(1) series.")
    table = _TAU_2010_C[n_series - 1]
    if math.isinf(nobs):
        values = table[:, 0]
    else:
        powers = np.array([1, 1 / nobs, nobs ** -2, nobs ** -3])
        values = table @ powers
    return {"1%": float(values[0]), "5%": float(values[1]), "10%": float(values[2])}


def mackinnon_p_value(statistic: float, n_series: int = 1) -> float:
    """Approximate asymptotic p-value (MacKinnon 1994), constant case."""
    if n_series not in (1, 2, 3):
        raise ValueError("p-values are provided for 1–3 I(1) series.")
    i = n_series - 1
    if statistic > _TAU_MAX_C[i]:
        return 1.0
    if statistic < _TAU_MIN_C[i]:
        return 0.0
    coefficients = _SMALL_P_C[i] if statistic <= _TAU_STAR_C[i] else _LARGE_P_C[i]
    return float(stats.norm.cdf(sum(c * statistic ** k for k, c in enumerate(coefficients))))


def _ols(y, x):
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ beta
    return beta, resid


def adf(series, *, constant: bool = True, max_lag: int | None = None, criterion: str = "aic") -> dict:
    """Augmented Dickey–Fuller t statistic with AIC/BIC lag choice on a common sample.

    Regression: dy_t = [c] + gamma y_{t-1} + sum_j phi_j dy_{t-j} + e_t; H0: gamma = 0.
    """
    if criterion not in ("aic", "bic"):
        raise ValueError("Lag criterion must be 'aic' or 'bic'.")
    y = np.asarray(series, dtype=np.float64)
    if y.ndim != 1 or len(y) < 20 or not np.isfinite(y).all():
        raise ValueError("ADF needs at least 20 finite observations.")
    n = len(y)
    deterministic = 1 if constant else 0
    if max_lag is None:
        max_lag = int(math.ceil(12 * (n / 100) ** .25))  # Schwert (1989).
    max_lag = max(0, min(max_lag, n // 2 - deterministic - 1))
    dy = np.diff(y)

    def design(lags, trim):
        rows = len(dy) - trim
        columns = [y[trim:-1]] + [dy[trim - j:len(dy) - j] for j in range(1, lags + 1)]
        if constant:
            columns.append(np.ones(rows))
        return dy[trim:], np.column_stack(columns)

    best_lag, best_aic = 0, math.inf
    for lags in range(max_lag + 1):
        target, x = design(lags, max_lag)
        _, resid = _ols(target, x)
        ssr = float(resid @ resid)
        penalty = 2 if criterion == "aic" else math.log(len(target))
        aic = len(target) * math.log(max(ssr, 1e-300) / len(target)) + penalty * x.shape[1]
        if aic < best_aic - 1e-12:
            best_lag, best_aic = lags, aic
    target, x = design(best_lag, best_lag)
    beta, resid = _ols(target, x)
    dof = len(target) - x.shape[1]
    sigma2 = float(resid @ resid) / dof
    covariance = sigma2 * np.linalg.pinv(x.T @ x)
    statistic = float(beta[0] / math.sqrt(covariance[0, 0])) if covariance[0, 0] > 0 else -math.inf
    return {"statistic": statistic, "lags": best_lag, "nobs": len(target), "gamma": float(beta[0])}


def adf_test(series, *, max_lag: int | None = None, criterion: str = "aic") -> dict:
    """ADF with constant, MacKinnon p-value and finite-sample critical values."""
    result = adf(series, constant=True, max_lag=max_lag, criterion=criterion)
    critical = mackinnon_critical_values(1, result["nobs"])
    return {**result, "p_value": mackinnon_p_value(result["statistic"], 1), "critical_values": critical,
            "rejects_unit_root_5pct": result["statistic"] < critical["5%"]}


def engle_granger(y, x, *, max_lag: int | None = None, criterion: str = "aic") -> dict:
    """Engle–Granger two-step test of y on x (with constant); H0: no cointegration."""
    a = np.asarray(y, dtype=np.float64)
    b = np.asarray(x, dtype=np.float64)
    if a.shape != b.shape or a.ndim != 1 or len(a) < 30 or not (np.isfinite(a).all() and np.isfinite(b).all()):
        raise ValueError("Engle–Granger needs two equal-length finite series of at least 30 observations.")
    design = np.column_stack([np.ones(len(b)), b])
    beta, resid = _ols(a, design)
    total = float(((a - a.mean()) ** 2).sum())
    if total <= 0 or float(resid @ resid) / total < 1e-12:
        raise ValueError("Series are (almost) perfectly collinear; the test is not informative.")
    # Residual ADF has no constant: OLS residuals already have zero mean.
    result = adf(resid, constant=False, max_lag=max_lag, criterion=criterion)
    critical = mackinnon_critical_values(2, len(a) - 1)
    return {"statistic": result["statistic"], "lags": result["lags"], "lag_criterion": criterion, "nobs": len(a),
            "p_value": mackinnon_p_value(result["statistic"], 2), "critical_values": critical,
            "intercept": float(beta[0]), "hedge_ratio": float(beta[1]),
            "residual_std": float(resid.std(ddof=2)), "half_life": half_life(resid),
            "rejects_5pct": result["statistic"] < critical["5%"]}


def half_life(spread) -> float | None:
    """Mean-reversion half-life from ds_t = a + b s_{t-1}; None when b >= 0."""
    s = np.asarray(spread, dtype=np.float64)
    beta, _ = _ols(np.diff(s), np.column_stack([np.ones(len(s) - 1), s[:-1]]))
    b = float(beta[1])
    if b >= 0 or b <= -1:
        return None
    return float(-math.log(2) / math.log(1 + b))


def holm(p_values, alpha: float = .05) -> list[bool]:
    """Holm–Bonferroni step-down family-wise error control."""
    order = np.argsort(p_values, kind="stable")
    m = len(p_values)
    reject = [False] * m
    for rank, index in enumerate(order):
        if p_values[index] <= alpha / (m - rank):
            reject[index] = True
        else:
            break
    return reject


def select_pairs(log_prices, names, *, alpha: float = .05, criterion: str = "bic") -> dict:
    """Test every ordered pair on formation data only; control family-wise error with Holm."""
    p = np.asarray(log_prices, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != len(names) or not 2 <= p.shape[1] <= 32:
        raise ValueError("Pair selection needs a rows x 2–32 matrix of formation log prices.")
    integrated = []
    for j, name in enumerate(names):
        level, change = adf_test(p[:, j]), adf_test(np.diff(p[:, j]))
        integrated.append({"asset": name, "level_p_value": level["p_value"], "difference_p_value": change["p_value"],
                           "consistent_with_i1": level["p_value"] > .05 and change["p_value"] <= .05})
    tests = []
    for i, j in itertools.permutations(range(len(names)), 2):
        if not (integrated[i]["consistent_with_i1"] and integrated[j]["consistent_with_i1"]):
            continue
        try:
            result = engle_granger(p[:, i], p[:, j], criterion=criterion)
        except ValueError as exc:
            tests.append({"y": names[i], "x": names[j], "error": str(exc), "p_value": 1.0})
            continue
        tests.append({"y": names[i], "x": names[j], **result})
    decisions = holm([t["p_value"] for t in tests], alpha) if tests else []
    for test, keep in zip(tests, decisions):
        test["selected"] = keep
    return {"integration": integrated, "tests": tests, "tests_run": len(tests),
            "selected": [t for t in tests if t["selected"]],
            "policy": f"Both legs must look I(1) (level ADF p > 0.05, difference ADF p <= 0.05); "
                      f"ordered Engle–Granger tests ({criterion.upper()} lags) with Holm family-wise error {alpha:.0%}. "
                      "BIC is the default because AIC lag search over-rejected (about 7% at nominal 5%) on independent walks."}


def pairs_backtest(price_y, price_x, *, formation: int = 252, entry_z: float = 2.0, exit_z: float = .5,
                   stop_z: float = 4.0, cost_bps: float = 5.0, borrow_bps: float = 50.0,
                   criterion: str = "bic") -> dict:
    """Trade a formation-fitted log spread with share-based legs.

    Hedge ratio, spread mean and spread volatility use only the first ``formation``
    closes. A z-score observed at close t changes holdings at close t+1. Each
    position is sized to unit gross notional at entry and then held in shares
    (no implicit daily rebalancing). Costs apply to traded notional; short
    notional pays an annual borrow fee daily; open positions are liquidated with
    costs at the final close.
    """
    a = np.asarray(price_y, dtype=np.float64)
    b = np.asarray(price_x, dtype=np.float64)
    if a.shape != b.shape or a.ndim != 1 or not (np.isfinite(a).all() and np.isfinite(b).all()) or (a <= 0).any() or (b <= 0).any():
        raise ValueError("Pair prices must be equal-length positive finite series.")
    if isinstance(formation, bool) or not isinstance(formation, int) or not 30 <= formation <= len(a) - 3:
        raise ValueError("Formation must be at least 30 closes and leave at least three trading closes.")
    if not 0 <= exit_z < entry_z < stop_z <= 20:
        raise ValueError("Require 0 <= exit z < entry z < stop z <= 20.")
    if not 0 <= cost_bps <= 500 or not 0 <= borrow_bps <= 10_000:
        raise ValueError("Cost must be 0–500 bps per traded unit and borrow 0–10,000 bps per year.")
    la, lb = np.log(a), np.log(b)
    test = engle_granger(la[:formation], lb[:formation], criterion=criterion)
    beta, intercept = test["hedge_ratio"], test["intercept"]
    formation_spread = la[:formation] - intercept - beta * lb[:formation]
    mu, sigma = float(formation_spread.mean()), float(formation_spread.std(ddof=1))
    z = (la - intercept - beta * lb - mu) / sigma
    cost, borrow = cost_bps / 10_000, borrow_bps / 10_000 / TRADING_DAYS
    cash, shares = 1.0, np.zeros(2)
    state = 0          # Desired spread position decided at the previous close: +1 long, -1 short.
    blocked = 0        # After a stop, wait for |z| to return inside the entry band.
    equity, trades, costs_paid, borrow_paid, days_in = [1.0], [], 0.0, 0.0, 0
    for t in range(formation, len(a)):
        prices = np.array([a[t], b[t]])
        if t > formation:
            # Execute the decision from close t-1 at close t.
            if desired != state:
                value = cash + shares @ prices
                if desired == 0:
                    target = np.zeros(2)
                else:
                    gross = 1 + abs(beta)
                    target = np.array([desired / gross, -desired * beta / gross]) * value / prices
                traded = float(np.abs(target - shares) @ prices)
                fee = traded * cost
                cash -= (target - shares) @ prices + fee
                costs_paid += fee
                trades.append({"signal_close": t - 1, "execution_close": t, "position": int(desired),
                               "z_at_signal": float(z[t - 1]), "traded_notional": traded, "cost": fee})
                shares, state = target, desired
            short_notional = float(-np.minimum(shares, 0) @ prices)
            fee = short_notional * borrow
            cash -= fee
            borrow_paid += fee
            equity.append(cash + shares @ prices)
            days_in += int(state != 0)
        # Decide at close t using z observed at close t.
        zt = z[t]
        desired = state
        if blocked and abs(zt) < entry_z:
            blocked = 0
        if state != 0 and (abs(zt) >= stop_z):
            desired, blocked = 0, 1
        elif state != 0 and ((state > 0 and zt >= -exit_z) or (state < 0 and zt <= exit_z)):
            desired = 0
        elif state == 0 and not blocked and abs(zt) < stop_z:
            if zt >= entry_z:
                desired = -1
            elif zt <= -entry_z:
                desired = 1
    if shares.any():
        prices = np.array([a[-1], b[-1]])
        traded = float(np.abs(shares) @ prices)
        fee = traded * cost
        cash += shares @ prices - fee
        costs_paid += fee
        trades.append({"signal_close": len(a) - 1, "execution_close": len(a) - 1, "position": 0,
                       "z_at_signal": float(z[-1]), "traded_notional": traded, "cost": fee, "liquidation": True})
        shares = np.zeros(2)
        equity[-1] = cash
    curve = np.asarray(equity)
    returns = curve[1:] / curve[:-1] - 1
    vol = float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS)) if len(returns) > 1 else 0.0
    peaks = np.maximum.accumulate(curve)
    return {"formation_test": test, "hedge_ratio": beta, "spread_mean": mu, "spread_std": sigma,
            "z": z[formation:].tolist(), "equity": curve.tolist(), "trades": trades,
            "round_trips": sum(1 for t in trades if t["position"] == 0),
            "total_return": float(curve[-1] - 1), "volatility": vol,
            "sharpe": float(returns.mean() * TRADING_DAYS / vol) if vol > 1e-12 else 0.0,
            "max_drawdown": float((curve / peaks - 1).min()), "costs_paid": costs_paid, "borrow_paid": borrow_paid,
            "time_in_market": days_in / max(len(returns), 1),
            "baseline_cash_return": 0.0,
            "timing": "z at close t decides; holdings change at close t+1; first P&L from t+1 to t+2.",
            "assumptions": ["Hedge ratio, spread mean and volatility are frozen from the formation window.",
                            "Close prices are executable; no queueing, partial fills, recalls or locate failures.",
                            "Short proceeds earn zero interest; borrow fee charged daily on short notional.",
                            "Positions held in shares between trades, so the hedge ratio drifts with prices."]}
