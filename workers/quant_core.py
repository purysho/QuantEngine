"""Independent numerical research engine. No brokerage or order interfaces."""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.optimize import minimize

TRADING_DAYS = 252
MIN_OBSERVATIONS = 40
MAX_ASSETS = 64
MAX_ROWS = 100_000


def price_returns(prices: np.ndarray) -> np.ndarray:
    p = np.asarray(prices, dtype=np.float64)
    if p.ndim != 2 or p.shape[0] < 2 or not 1 <= p.shape[1] <= MAX_ASSETS:
        raise ValueError("Prices must contain at least two rows and 1–64 assets.")
    if not np.isfinite(p).all() or (p <= 0).any():
        raise ValueError("All prices must be positive finite numbers; missing prices are not filled.")
    returns = p[1:] / p[:-1] - 1
    if not np.isfinite(returns).all():
        raise ValueError("Price ratios overflow; check the source data.")
    return returns


def load_prices(path: str | Path, minimum: int = MIN_OBSERVATIONS):
    """Wide CSV: date,A,B,... . Reject unsorted dates rather than silently sorting."""
    content = Path(path).read_text(encoding="utf-8-sig")
    return parse_prices(content, minimum=minimum)


def parse_prices(content: str, minimum: int = MIN_OBSERVATIONS):
    reader = csv.reader(io.StringIO(content))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV is empty.") from exc
    if not 2 <= len(header) <= MAX_ASSETS + 1 or header[0].strip().lower() != "date":
        raise ValueError("CSV header must be date followed by 1–64 asset names.")
    assets = [value.strip() for value in header[1:]]
    if any(not x or len(x) > 40 for x in assets) or len(set(assets)) != len(assets):
        raise ValueError("Asset names must be unique, nonempty and at most 40 characters.")
    dates, rows = [], []
    for line, row in enumerate(reader, start=2):
        if not row or all(not cell.strip() for cell in row):
            raise ValueError(f"CSV row {line} is blank.")
        if len(row) != len(header):
            raise ValueError(f"CSV row {line} has a missing or extra column.")
        date = row[0].strip()
        try:
            parsed = dt.date.fromisoformat(date)
            if parsed.isoformat() != date:
                raise ValueError()
        except ValueError as exc:
            raise ValueError(f"CSV row {line}: date must be YYYY-MM-DD.") from exc
        if dates and date <= dates[-1]:
            raise ValueError("Dates must be unique and strictly increasing.")
        try:
            values = [float(x) for x in row[1:]]
        except ValueError as exc:
            raise ValueError(f"CSV row {line} contains a missing or invalid price.") from exc
        if not all(math.isfinite(x) and x > 0 for x in values):
            raise ValueError(f"CSV row {line} contains a nonpositive or nonfinite price.")
        dates.append(date)
        rows.append(values)
        if len(rows) > MAX_ROWS:
            raise ValueError(f"CSV exceeds {MAX_ROWS:,} rows.")
    if len(rows) < minimum:
        raise ValueError(f"At least {minimum} dated price observations are required.")
    return dates, assets, np.asarray(rows, dtype=np.float64)


def minimum_variance(covariance: np.ndarray) -> np.ndarray:
    """Long-only fully invested minimum-variance weights, via constrained SLSQP."""
    cov = np.atleast_2d(np.asarray(covariance, dtype=np.float64))
    if cov.shape[0] != cov.shape[1] or not np.isfinite(cov).all() or not len(cov):
        raise ValueError("Covariance must be a finite square matrix.")
    if not np.allclose(cov, cov.T, atol=1e-10) or np.linalg.eigvalsh(cov).min() < -1e-9:
        raise ValueError("Covariance must be symmetric and positive semidefinite.")
    n = len(cov)
    scale = max(float(np.max(np.diag(cov))), 1e-16)
    if scale == 1e-16:
        return np.full(n, 1 / n)
    normalized = cov / scale
    result = minimize(
        lambda w: float(w @ normalized @ w), np.full(n, 1 / n),
        jac=lambda w: 2 * normalized @ w,
        method="SLSQP", bounds=[(0.0, 1.0)] * n,
        constraints={"type": "eq", "fun": lambda w: float(w.sum() - 1),
                     "jac": lambda w: np.ones(n)},
        options={"ftol": 1e-12, "maxiter": 500},
    )
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError(f"Portfolio optimization did not converge: {result.message}")
    weights = np.clip(result.x, 0, 1)
    return weights / weights.sum()


def simulate_risk(returns: np.ndarray, weights: np.ndarray, *, paths: int = 50_000,
                  horizon: int = 20, seed: int = 17,
                  progress: Callable[[str, float], None] | None = None) -> dict:
    r = np.asarray(returns, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    if r.ndim != 2 or len(r) < 2 or w.shape != (r.shape[1],) or not np.isfinite(r).all():
        raise ValueError("Simulation requires finite returns and one weight per asset.")
    if not np.isfinite(w).all() or (w < 0).any() or not np.isclose(w.sum(), 1):
        raise ValueError("Simulation weights must be nonnegative and sum to one.")
    if isinstance(paths, bool) or not isinstance(paths, int) or not 1_000 <= paths <= 1_000_000:
        raise ValueError("Paths must be an integer between 1,000 and 1,000,000.")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 252:
        raise ValueError("Horizon must be an integer between 1 and 252 observations.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be an integer between 0 and 4,294,967,295.")
    daily = r @ w
    mean = float(daily.mean()) * horizon
    sigma = float(daily.std(ddof=1)) * math.sqrt(horizon)
    if sigma < 1e-15:
        sigma = 0.0
    rng = np.random.default_rng(seed)
    samples = np.empty(paths, dtype=np.float64)  # At most 8 MB at the path cap.
    for start in range(0, paths, 8192):
        end = min(start + 8192, paths)
        samples[start:end] = rng.normal(mean, sigma, end - start)
        if progress:
            progress("Simulating Gaussian risk", end / paths)
    quantiles = np.quantile(samples, [.01, .05, .5, .95, .99])
    q05 = float(quantiles[1])
    tail = samples[samples <= q05]
    counts, edges = np.histogram(samples, bins=40)
    return {
        "paths": paths, "horizon": horizon, "seed": seed,
        "var95": -q05, "es95": -float(tail.mean()),
        "p01": float(quantiles[0]), "p05": q05, "median": float(quantiles[2]),
        "p95": float(quantiles[3]), "p99": float(quantiles[4]),
        "mean": float(samples.mean()), "standard_deviation": float(samples.std(ddof=1)),
        "loss_probability": float(np.mean(samples < 0)),
        "histogram": [{"low": float(edges[i]), "high": float(edges[i+1]),
                       "count": int(counts[i])} for i in range(len(counts))],
        "model": "Gaussian cumulative arithmetic return",
        "assumptions": ["Historical mean and sample variance are fixed over the horizon.",
                        "Independent identically distributed observation returns; no serial correlation.",
                        "Gaussian tails and arithmetic aggregation can understate crisis losses; returns may be below −100%.",
                        "No future-price forecast, currency conversion, financing, or execution model."],
        "max_sample_memory_bytes": paths * 8,
    }


def _performance(net: list[float] | np.ndarray, gross=None) -> dict:
    r = np.asarray(net, dtype=np.float64)
    equity = np.cumprod(1 + r)
    total = float(equity[-1] - 1) if len(r) else 0.0
    peaks = np.maximum.accumulate(np.r_[1.0, equity])
    drawdown = np.r_[1.0, equity] / peaks - 1
    vol = float(r.std(ddof=1)) * math.sqrt(TRADING_DAYS) if len(r) > 1 else 0.0
    sharpe = float(r.mean() * TRADING_DAYS / vol) if vol > 1e-15 else 0.0
    annual = float(equity[-1] ** (TRADING_DAYS / len(r)) - 1) if len(r) and equity[-1] > 0 else 0.0
    result = {"total_return": total, "annualized_return": annual,
              "volatility": vol, "sharpe": sharpe,
              "max_drawdown": float(drawdown.min()), "observations": len(r)}
    if gross is not None:
        result["gross_total_return"] = float(np.prod(1 + np.asarray(gross)) - 1)
    return result


def bootstrap_risk(returns: np.ndarray, weights: np.ndarray, *, paths: int = 50_000,
                   horizon: int = 20, seed: int = 17, block_size: int = 5,
                   progress: Callable[[str, float], None] | None = None) -> dict:
    """Circular block bootstrap: preserve local empirical dependence within blocks."""
    r = np.asarray(returns, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    if r.ndim != 2 or len(r) < 2 or w.shape != (r.shape[1],) or not np.isfinite(r).all():
        raise ValueError("Bootstrap requires finite returns and one weight per asset.")
    if not np.isfinite(w).all() or (w < 0).any() or not np.isclose(w.sum(), 1):
        raise ValueError("Bootstrap weights must be nonnegative and sum to one.")
    if not isinstance(paths, int) or not 1_000 <= paths <= 1_000_000 or not isinstance(horizon, int) or not 1 <= horizon <= 252:
        raise ValueError("Bootstrap paths must be 1,000–1,000,000 and horizon 1–252.")
    if not isinstance(block_size, int) or not 1 <= block_size <= min(63, len(r)):
        raise ValueError("Bootstrap block size must be 1–63 and fit the dataset.")
    if not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Bootstrap seed is outside the supported range.")
    daily = r @ w
    rng = np.random.default_rng(seed)
    samples = np.empty(paths)
    block_count = math.ceil(horizon / block_size)
    batch_size = min(4096, max(1, 1_000_000 // (block_count * block_size)))
    offsets = np.arange(block_size)[None, None, :]
    for start in range(0, paths, batch_size):
        end = min(start + batch_size, paths)
        starts = rng.integers(0, len(daily), size=(end - start, block_count, 1))
        indices = (starts + offsets) % len(daily)
        samples[start:end] = daily[indices].reshape(end - start, -1)[:, :horizon].sum(axis=1)
        if progress:
            progress("Resampling empirical blocks", end / paths)
    q05, median, q95 = np.quantile(samples, [.05, .5, .95])
    counts, edges = np.histogram(samples, bins=40)
    return {"paths": paths, "horizon": horizon, "seed": seed, "block_size": block_size,
            "var95": -float(q05), "es95": -float(samples[samples <= q05].mean()),
            "median": float(median), "p95": float(q95), "loss_probability": float(np.mean(samples < 0)),
            "model": "Circular historical block bootstrap, cumulative arithmetic return",
            "max_batch_bytes": int(batch_size * block_count * block_size * 8),
            "histogram": [{"low": float(edges[i]), "high": float(edges[i+1]), "count": int(counts[i])}
                          for i in range(len(counts))],
            "assumptions": ["Historical blocks recur; within-block dependence is preserved, cross-block dependence is not.",
                            "Circular wrapping joins the last and first historical observation.",
                            "No unobserved crisis, changing regime, compounded return or forward forecast is modeled."]}


def walk_forward(prices: np.ndarray, *, lookback: int = 20, rebalance: int = 5,
                 cost_bps: float = 10.0) -> dict:
    """Trailing positive momentum, inverse-vol weights; trades before the next return."""
    returns = price_returns(prices)
    if not isinstance(lookback, int) or not 5 <= lookback < len(returns) - 1:
        raise ValueError("Lookback must be 5 or more and leave at least two evaluation observations.")
    if not isinstance(rebalance, int) or not 1 <= rebalance <= 63:
        raise ValueError("Rebalance must be 1–63 observations.")
    if not math.isfinite(cost_bps) or not 0 <= cost_bps <= 500:
        raise ValueError("Transaction cost must be 0–500 basis points per traded unit.")
    n = returns.shape[1]
    weights = np.zeros(n)
    equal_weights = np.zeros(n)
    net, gross, equal_net, costs, turnover, decisions = [], [], [], [], [], []
    for t in range(lookback, len(returns)):
        fee = equal_fee = 0.0
        if (t - lookback) % rebalance == 0:
            past = returns[t - lookback:t]  # Current/future return is never visible.
            momentum = np.prod(1 + past, axis=0) - 1
            selected = np.argsort(-momentum, kind="stable")[:max(1, math.ceil(n / 2))]
            selected = selected[momentum[selected] > 0]
            target = np.zeros(n)
            if len(selected):
                inverse_vol = 1 / np.maximum(past[:, selected].std(axis=0, ddof=1), 1e-8)
                target[selected] = inverse_vol / inverse_vol.sum()
            # L1 traded risky notional includes entry/exit; cash is the residual.
            traded = float(np.abs(target - weights).sum())
            fee = traded * cost_bps / 10_000
            equal_target = np.full(n, 1 / n)
            equal_fee = float(np.abs(equal_target - equal_weights).sum()) * cost_bps / 10_000
            weights, equal_weights = target, equal_target
            turnover.append(traded)
            decisions.append({"return_index": t, "last_observed_price_index": t,
                              "weights": weights.tolist(), "cash_weight": float(1 - weights.sum()),
                              "turnover": traded, "cost_fraction": fee})
        daily = returns[t]
        raw = float(weights @ daily)
        equal_raw = float(equal_weights @ daily)
        gross.append(raw)
        net.append((1 - fee) * (1 + raw) - 1)
        equal_net.append((1 - equal_fee) * (1 + equal_raw) - 1)
        costs.append(fee)
        # Holdings drift between scheduled rebalances, including residual cash.
        weights = weights * (1 + daily) / (1 + raw)
        equal_weights = equal_weights * (1 + daily) / (1 + equal_raw)
    result = _performance(net, gross)
    result.update({"net_returns": net, "gross_returns": gross, "cost_fractions": costs,
                   "cost_bps": cost_bps, "lookback": lookback, "rebalance": rebalance,
                   "turnover": float(sum(turnover)), "decisions": decisions,
                   "strategy": "Trailing positive momentum with inverse-volatility weights",
                   "baselines": {"equal_weight": {**_performance(equal_net), "net_returns": equal_net},
                                 "cash": {**_performance(np.zeros(len(net))), "net_returns": [0.0] * len(net)}}})
    return result


def example_prices():
    """Deterministic synthetic prices. Asset names intentionally never mimic tickers."""
    rng = np.random.default_rng(2048)
    covariance = np.array([[.00012, .000045, .000018, -.000008],
                           [.000045, .00020, .00003, 0],
                           [.000018, .00003, .000055, .00001],
                           [-.000008, 0, .00001, .000035]])
    shocks = rng.multivariate_normal([.00035, .00025, .00012, .00005], covariance, 503)
    shocks[180:190] -= [.018, .025, .006, -.003]
    prices = 100 * np.vstack([np.ones(4), np.cumprod(1 + shocks, axis=0)])
    dates, date = [], dt.date(2024, 1, 2)
    while len(dates) < len(prices):
        if date.weekday() < 5:
            dates.append(date.isoformat())
        date += dt.timedelta(days=1)
    return dates, ["Sample Growth", "Sample Cyclical", "Sample Defensive", "Sample Reserve"], prices


def analyse(dates, assets, prices, *, paths: int = 50_000, horizon: int = 20,
            seed: int = 17, lookback: int = 20, rebalance: int = 5,
            cost_bps: float = 10, shrinkage: float = .10,
            progress: Callable[[str, float], None] | None = None) -> dict:
    p = np.asarray(prices, dtype=np.float64)
    returns = price_returns(p)
    if len(dates) != len(p) or len(assets) != p.shape[1] or len(p) < MIN_OBSERVATIONS:
        raise ValueError(f"Dataset must have matching dates/assets and at least {MIN_OBSERVATIONS} observations.")
    if not math.isfinite(shrinkage) or not 0 <= shrinkage <= 1:
        raise ValueError("Diagonal shrinkage must be between zero and one.")
    if progress:
        progress("Estimating covariance and optimizing", 0.0)
    cov = np.atleast_2d(np.cov(returns, rowvar=False, ddof=1))
    shrunk = (1 - shrinkage) * cov + shrinkage * np.diag(np.diag(cov))
    weights = minimum_variance(shrunk)
    std = np.sqrt(np.maximum(np.diag(cov), 0))
    denominator = np.outer(std, std)
    correlation = np.divide(cov, denominator, out=np.zeros_like(cov), where=denominator > 1e-16)
    np.fill_diagonal(correlation, 1)
    risk = simulate_risk(returns, weights, paths=paths, horizon=horizon, seed=seed, progress=progress)
    bootstrap = bootstrap_risk(returns, weights, paths=paths, horizon=horizon, seed=seed, progress=progress)
    if progress:
        progress("Running chronological backtest", .95)
    backtest = walk_forward(p, lookback=lookback, rebalance=rebalance, cost_bps=cost_bps)
    net = np.cumprod(1 + np.asarray(backtest["net_returns"]))
    gross = np.cumprod(1 + np.asarray(backtest["gross_returns"]))
    equal = np.cumprod(1 + np.asarray(backtest["baselines"]["equal_weight"]["net_returns"]))
    curve_dates = dates[lookback + 1:]
    curve = [{"date": dates[lookback], "strategy": 1.0, "gross": 1.0, "equal_weight": 1.0, "cash": 1.0}]
    curve.extend({"date": date, "strategy": float(net[i]), "gross": float(gross[i]),
                  "equal_weight": float(equal[i]), "cash": 1.0} for i, date in enumerate(curve_dates))
    weighted_returns = returns @ weights
    worst = int(np.argmin(weighted_returns))
    sensitivity = []
    for comparison_lookback in sorted(set([10, 20, 40, 60, lookback])):
        if comparison_lookback >= len(returns) - 1:
            continue
        variant = backtest if comparison_lookback == lookback else walk_forward(
            p, lookback=comparison_lookback, rebalance=rebalance, cost_bps=cost_bps)
        sensitivity.append({"lookback": comparison_lookback, "total_return": variant["total_return"],
                            "sharpe": variant["sharpe"], "max_drawdown": variant["max_drawdown"],
                            "equal_weight_return": variant["baselines"]["equal_weight"]["total_return"],
                            "observations": variant["observations"]})
    report = {
        "schema_version": 1, "engine_version": "0.1.0",
        "observations": len(p), "return_observations": len(returns), "assets": list(assets),
        "date_range": {"start": dates[0], "end": dates[-1]},
        "parameters": {"paths": paths, "horizon": horizon, "seed": seed, "lookback": lookback,
                       "rebalance": rebalance, "cost_bps": cost_bps, "shrinkage": shrinkage,
                       "annualization": TRADING_DAYS},
        "weights": {name: float(weights[i]) for i, name in enumerate(assets)},
        "annualized_volatility": float(math.sqrt(max(0, weights @ cov @ weights) * TRADING_DAYS)),
        "annualized_mean_return": float(weighted_returns.mean() * TRADING_DAYS),
        "covariance": (cov * TRADING_DAYS).tolist(), "shrunk_covariance": (shrunk * TRADING_DAYS).tolist(),
        "correlation": correlation.tolist(), "shrinkage": shrinkage,
        "monte_carlo": risk, "bootstrap": bootstrap, "sensitivity": sensitivity,
        "backtest": backtest, "curve": curve,
        "stress": [{"name": "Worst observed portfolio day", "date": dates[worst + 1],
                    "return": float(weighted_returns[worst]), "kind": "historical"},
                   {"name": "All assets −10%", "return": -.10, "kind": "hypothetical"},
                   *[{"name": f"{asset} −20%; others flat", "return": float(-.2 * weights[i]),
                      "kind": "hypothetical"} for i, asset in enumerate(assets)]],
        "methodology": ["Simple observation-to-observation returns; no missing-data imputation.",
                        "Sample covariance; configurable diagonal shrinkage; long-only SLSQP portfolio optimization.",
                        "Risk uses optimized static weights. Backtest separately tests trailing positive momentum/inverse volatility.",
                        "Backtest observes only prior returns; holdings drift, then rebalance before the next return.",
                        "Transaction costs apply to L1 traded risky notional, including initial entry. Cash yields zero.",
                        "252 observations per year; use equally spaced trading-day price observations.",
                        "Sensitivity variants have different warm-up windows and overlapping evaluation data; comparisons are descriptive, not independent evidence for selecting a winning parameter.",
                        "Historical research with no dividends, splits, taxes, slippage, survivorship corrections or trade execution."],
    }
    if progress:
        progress("Numerical analysis complete", 1.0)
    return report
