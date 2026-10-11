"""Independent numerical research engine. No brokerage or order interfaces."""
from __future__ import annotations

import csv
import datetime as dt
import io
import math
from pathlib import Path
from typing import Callable

import numpy as np
from scipy import stats
from scipy.optimize import minimize

try:
    from . import quant_explain as explain
except ImportError:
    import quant_explain as explain

TRADING_DAYS = 252
MIN_OBSERVATIONS = 40
MAX_ASSETS = 64
MAX_ROWS = 100_000


ENGINE_VERSION = "0.2.0"
SCHEMA_VERSION = 2
QUANTILE_METHOD = "lower empirical inverse CDF: smallest sample x with F_n(x) >= p"


def empirical_tail(samples, tail_probability: float = .05) -> dict:
    """Signed-loss VaR/ES with exact empirical probability mass.

    VaR is minus the lower inverse-CDF quantile. ES is minus the mean of the
    lowest ``p`` probability mass: whole observations below the boundary plus
    the fractional share of the boundary observation, so ties and n*p that is
    not an integer are handled exactly. Negative values mean the whole tail is
    a gain.
    """
    x = np.sort(np.asarray(samples, dtype=np.float64).ravel())
    if not len(x) or not np.isfinite(x).all():
        raise ValueError("Tail samples must be a nonempty finite array.")
    if isinstance(tail_probability, bool) or not isinstance(tail_probability, (int, float)) \
            or not math.isfinite(tail_probability) or not 0 < tail_probability <= 1:
        raise ValueError("Tail probability must be in (0, 1].")
    n = len(x)
    mass = tail_probability * n
    # Guard 0.05 * 100 = 5.000000000000001 style rounding before ceil/floor.
    rounded = round(mass)
    if abs(mass - rounded) <= 1e-9 * max(1.0, mass):
        mass = float(rounded)
    k = max(1, math.ceil(mass))
    whole = math.floor(mass)
    tail_sum = float(x[:whole].sum()) + (mass - whole) * float(x[whole]) if whole < n else float(x.sum())
    return {"var": -float(x[k - 1]), "expected_shortfall": -tail_sum / mass,
            "tail_probability": float(tail_probability), "observations": n,
            "quantile_method": QUANTILE_METHOD}


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
    tail95, tail99 = empirical_tail(samples, .05), empirical_tail(samples, .01)
    counts, edges = np.histogram(samples, bins=40)
    return {
        "paths": paths, "horizon": horizon, "seed": seed,
        "var95": tail95["var"], "es95": tail95["expected_shortfall"],
        "var99": tail99["var"], "es99": tail99["expected_shortfall"],
        "quantile_method": QUANTILE_METHOD,
        "p01": float(quantiles[0]), "p05": float(quantiles[1]), "median": float(quantiles[2]),
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


def _check_simulation(paths, horizon, seed):
    if isinstance(paths, bool) or not isinstance(paths, int) or not 1_000 <= paths <= 1_000_000:
        raise ValueError("Paths must be an integer between 1,000 and 1,000,000.")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 252:
        raise ValueError("Horizon must be an integer between 1 and 252 observations.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be an integer between 0 and 4,294,967,295.")


def hill_tail_index(losses, k: int | None = None) -> dict:
    """Hill estimator of the Pareto tail index alpha for positive losses.

    alpha = 1 / mean(log(L_(i) / L_(k+1))), i = 1..k over the largest losses.
    Smaller alpha means a heavier tail; alpha <= 2 implies infinite variance and
    alpha <= 4 an undefined kurtosis. The estimate is sensitive to k, so several
    k values are reported.
    """
    x = np.sort(np.asarray(losses, dtype=np.float64).ravel())[::-1]
    x = x[np.isfinite(x) & (x > 0)]
    if len(x) < 12:
        return {"alpha": None, "k": 0, "by_k": [], "positive_losses": int(len(x)),
                "note": "Fewer than 12 positive losses; no tail-index estimate."}
    def estimate(count):
        return float(1 / np.mean(np.log(x[:count] / x[count])))
    k = k or max(5, int(.10 * len(x)))
    k = min(k, len(x) - 1)
    candidates = sorted({c for c in (5, 10, 20, 40, int(.05 * len(x)), k, int(.2 * len(x))) if 5 <= c < len(x)})
    return {"alpha": estimate(k), "k": k, "positive_losses": int(len(x)),
            "by_k": [{"k": c, "alpha": estimate(c)} for c in candidates],
            "note": "Hill estimator on positive daily losses; assumes a Pareto-type tail above the k-th largest loss."}


def student_t_risk(returns: np.ndarray, weights: np.ndarray, *, paths: int = 50_000,
                   horizon: int = 20, seed: int = 17,
                   progress: Callable[[str, float], None] | None = None) -> dict:
    """Maximum-likelihood Student-t daily returns, iid and summed over the horizon."""
    r = np.asarray(returns, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    if r.ndim != 2 or len(r) < 2 or w.shape != (r.shape[1],) or not np.isfinite(r).all():
        raise ValueError("Student-t risk requires finite returns and one weight per asset.")
    if not np.isfinite(w).all() or (w < 0).any() or not np.isclose(w.sum(), 1):
        raise ValueError("Student-t weights must be nonnegative and sum to one.")
    _check_simulation(paths, horizon, seed)
    daily = r @ w
    centred = daily - daily.mean()
    sd = float(daily.std(ddof=1))
    if sd < 1e-15:
        df, loc, scale = math.inf, float(daily.mean()), 0.0
    else:
        df, loc, scale = (float(v) for v in stats.t.fit(daily))
        df = min(df, 1_000.0)
    rng = np.random.default_rng(seed)
    samples = np.empty(paths)
    batch = max(1, 1_000_000 // horizon)
    for start in range(0, paths, batch):
        end = min(start + batch, paths)
        if scale == 0:
            samples[start:end] = loc * horizon
        else:
            samples[start:end] = (loc + scale * rng.standard_t(df, size=(end - start, horizon))).sum(axis=1)
        if progress:
            progress("Simulating Student-t risk", end / paths)
    tail95, tail99 = empirical_tail(samples, .05), empirical_tail(samples, .01)
    one_day = {}
    if scale > 0:
        for level in (.05, .01):
            q = stats.t.ppf(level, df)
            # Closed-form ES of a location-scale t: E[T | T <= q] = -(df + q^2)/(df - 1) * pdf(q)/level.
            es = -(loc - scale * (df + q * q) / (df - 1) * stats.t.pdf(q, df) / level) if df > 1 else math.inf
            one_day[f"var{int(round((1 - level) * 100))}"] = -(loc + scale * q)
            one_day[f"es{int(round((1 - level) * 100))}"] = es if math.isfinite(es) else None
    excess_kurtosis = float(stats.kurtosis(daily, bias=False)) if sd >= 1e-15 and len(daily) > 3 else 0.0
    return {"paths": paths, "horizon": horizon, "seed": seed,
            "degrees_of_freedom": df if math.isfinite(df) else None, "location": loc, "scale": scale,
            "var95": tail95["var"], "es95": tail95["expected_shortfall"],
            "var99": tail99["var"], "es99": tail99["expected_shortfall"],
            "one_day_analytic": one_day, "quantile_method": QUANTILE_METHOD,
            "loss_probability": float(np.mean(samples < 0)),
            "sample_skewness": float(stats.skew(daily, bias=False)) if sd >= 1e-15 and len(daily) > 2 else 0.0,
            "sample_excess_kurtosis": excess_kurtosis,
            "hill": hill_tail_index(-centred),
            "model": "Maximum-likelihood Student-t daily return, iid, summed arithmetically",
            "assumptions": ["Daily returns are iid Student-t with fitted degrees of freedom, location and scale.",
                            "Fat tails are modeled; volatility clustering, skew and regime change are not.",
                            "The sum of t variables is not t; horizon risk is simulated rather than scaled by sqrt(horizon).",
                            "Degrees of freedom at or below 2 imply infinite variance; at or below 1 the mean and ES are undefined."]}


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
    median, q95 = np.quantile(samples, [.5, .95])
    tail95, tail99 = empirical_tail(samples, .05), empirical_tail(samples, .01)
    counts, edges = np.histogram(samples, bins=40)
    return {"paths": paths, "horizon": horizon, "seed": seed, "block_size": block_size,
            "var95": tail95["var"], "es95": tail95["expected_shortfall"],
            "var99": tail99["var"], "es99": tail99["expected_shortfall"],
            "quantile_method": QUANTILE_METHOD,
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
    """Trailing positive momentum, inverse-vol weights, executed at the next close.

    Close-only timing: a signal formed from prices through close s is first
    executable at close s + 1, and that position first earns the return from
    close s + 1 to close s + 2. Return index t is the move from price t to t + 1.
    """
    returns = price_returns(prices)
    if isinstance(lookback, bool) or not isinstance(lookback, int) or not 5 <= lookback < len(returns) - 2:
        raise ValueError("Lookback must be 5 or more and leave at least two evaluation observations after the one-close execution delay.")
    if isinstance(rebalance, bool) or not isinstance(rebalance, int) or not 1 <= rebalance <= 63:
        raise ValueError("Rebalance must be 1–63 observations.")
    if not isinstance(cost_bps, (int, float)) or isinstance(cost_bps, bool) or not math.isfinite(cost_bps) or not 0 <= cost_bps <= 500:
        raise ValueError("Transaction cost must be 0–500 basis points per traded unit.")
    n = returns.shape[1]
    weights = np.zeros(n)
    equal_weights = np.zeros(n)
    net, gross, equal_net, costs, turnover, decisions = [], [], [], [], [], []
    first = lookback + 1  # First return index that can carry an executed position.
    for t in range(first, len(returns)):
        fee = equal_fee = 0.0
        if (t - first) % rebalance == 0:
            signal_close = t - 1
            past = returns[signal_close - lookback:signal_close]  # Uses prices through close t − 1 only.
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
            decisions.append({"signal_price_index": signal_close, "execution_price_index": t,
                              "return_index": t, "first_return_interval": [t, t + 1],
                              "last_observed_price_index": signal_close,
                              "weights": weights.tolist(), "cash_weight": float(1 - weights.sum()),
                              "turnover": traded, "cost_fraction": fee})
        daily = returns[t]
        raw = float(weights @ daily)
        equal_raw = float(equal_weights @ daily)
        gross.append(raw)
        # Costs are paid at the execution close, before the first held return.
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
                   "timing": {"execution_delay_closes": 1, "first_execution_price_index": first,
                              "convention": "Signal after close s; trade at close s+1; first earns close s+1 to s+2."},
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


def realised_vol_surface(dates, daily_returns, *, max_dates: int = 240) -> dict:
    """Annualised trailing realised volatility by lookback window and date.

    Value [i][j] uses only returns that ended on or before ``dates[j]``: the
    window ``windows[i]`` returns immediately before that close. Dates are
    subsampled evenly to at most ``max_dates`` columns for display.
    """
    r = np.asarray(daily_returns, dtype=np.float64)
    if r.ndim != 1 or len(r) < 12 or len(dates) != len(r) + 1:
        raise ValueError("Realised-volatility surface needs one date per price and at least 12 returns.")
    windows = [w for w in (5, 10, 15, 20, 30, 40, 50, 60, 80, 100, 120, 160, 200, 250) if w <= len(r) // 2]
    if len(windows) < 2:
        raise ValueError("Too few returns for a volatility surface.")
    c1 = np.r_[0.0, np.cumsum(r)]
    c2 = np.r_[0.0, np.cumsum(r * r)]
    first = windows[-1]
    ends = np.arange(first, len(r) + 1)  # Number of returns observed; price index of that close.
    if len(ends) > max_dates:
        ends = np.unique(np.linspace(first, len(r), max_dates).round().astype(int))
    values = []
    for w in windows:
        total = c1[ends] - c1[ends - w]
        squares = c2[ends] - c2[ends - w]
        variance = np.maximum((squares - total * total / w) / (w - 1), 0.0)
        values.append((np.sqrt(variance * TRADING_DAYS)).tolist())
    return {"windows": windows, "dates": [dates[int(e)] for e in ends], "values": values,
            "units": "annualised volatility (decimal)", "basis": "optimised portfolio daily returns",
            "construction": "Trailing sample standard deviation over each lookback, sqrt(252) annualisation; no future returns."}


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
    student = student_t_risk(returns, weights, paths=paths, horizon=horizon, seed=seed, progress=progress)
    if progress:
        progress("Running chronological backtest", .95)
    backtest = walk_forward(p, lookback=lookback, rebalance=rebalance, cost_bps=cost_bps)
    net = np.cumprod(1 + np.asarray(backtest["net_returns"]))
    gross = np.cumprod(1 + np.asarray(backtest["gross_returns"]))
    equal = np.cumprod(1 + np.asarray(backtest["baselines"]["equal_weight"]["net_returns"]))
    first = backtest["timing"]["first_execution_price_index"]
    curve_dates = dates[first + 1:]  # Each held return ends one close after it starts.
    curve = [{"date": dates[first], "strategy": 1.0, "gross": 1.0, "equal_weight": 1.0, "cash": 1.0}]
    curve.extend({"date": date, "strategy": float(net[i]), "gross": float(gross[i]),
                  "equal_weight": float(equal[i]), "cash": 1.0} for i, date in enumerate(curve_dates))
    weighted_returns = returns @ weights
    worst = int(np.argmin(weighted_returns))
    sensitivity = []
    for comparison_lookback in sorted(set([10, 20, 40, 60, lookback])):
        if comparison_lookback >= len(returns) - 2:
            continue
        variant = backtest if comparison_lookback == lookback else walk_forward(
            p, lookback=comparison_lookback, rebalance=rebalance, cost_bps=cost_bps)
        sensitivity.append({"lookback": comparison_lookback, "total_return": variant["total_return"],
                            "sharpe": variant["sharpe"], "max_drawdown": variant["max_drawdown"],
                            "equal_weight_return": variant["baselines"]["equal_weight"]["total_return"],
                            "observations": variant["observations"]})
    report = {
        "schema_version": SCHEMA_VERSION, "engine_version": ENGINE_VERSION,
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
        "monte_carlo": risk, "bootstrap": bootstrap, "student_t": student, "sensitivity": sensitivity,
        "volatility_surface": realised_vol_surface(dates, weighted_returns),
        "explanation": {
            "gaussian_var": explain.gaussian_horizon_steps(float(weighted_returns.mean()), float(weighted_returns.std(ddof=1)), horizon),
            "empirical_tail_daily": explain.tail_steps(weighted_returns, .05),
            "student_t": explain.student_t_steps(student["degrees_of_freedom"], student["location"], student["scale"], .01)
                         if student["degrees_of_freedom"] and student["scale"] > 0 else [],
            "minimum_variance": explain.minimum_variance_steps(shrunk * TRADING_DAYS, weights),
            "sources": [explain.SOURCES["var"], explain.SOURCES["student_t"], explain.SOURCES["min_variance"]]},
        "backtest": backtest, "curve": curve,
        "stress": [{"name": "Worst observed portfolio day", "date": dates[worst + 1],
                    "return": float(weighted_returns[worst]), "kind": "historical"},
                   {"name": "All assets −10%", "return": -.10, "kind": "hypothetical"},
                   *[{"name": f"{asset} −20%; others flat", "return": float(-.2 * weights[i]),
                      "kind": "hypothetical"} for i, asset in enumerate(assets)]],
        "methodology": ["Simple observation-to-observation returns; no missing-data imputation.",
                        "Sample covariance; configurable diagonal shrinkage; long-only SLSQP portfolio optimization.",
                        "Risk uses optimized static weights. Backtest separately tests trailing positive momentum/inverse volatility.",
                        "Backtest signals use closes through s and execute at close s+1; the first held return is s+1 to s+2.",
                        "VaR/ES use the lower empirical inverse CDF and exact tail probability mass, including ties and a fractional boundary observation.",
                        "Risk is compared under Gaussian, historical block bootstrap and fitted Student-t daily returns, with a Hill tail-index diagnostic.",
                        "Transaction costs apply to L1 traded risky notional, including initial entry. Cash yields zero.",
                        "252 observations per year; use equally spaced trading-day price observations.",
                        "Sensitivity variants have different warm-up windows and overlapping evaluation data; comparisons are descriptive, not independent evidence for selecting a winning parameter.",
                        "Historical research with no dividends, splits, taxes, slippage, survivorship corrections or trade execution."],
    }
    if progress:
        progress("Numerical analysis complete", 1.0)
    return report
