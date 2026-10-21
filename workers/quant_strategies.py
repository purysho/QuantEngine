"""Pre-registered strategies and the evidence needed before any money is risked.

Two strategy families, fixed in code before results were seen (registered 2026-10-21):

* ``trend``: hold the US stock market only while its trailing excess return over cash is positive,
  optionally scaled to a target volatility (time-series momentum: Moskowitz, Ooi & Pedersen 2012;
  volatility targeting: Moreira & Muir 2017). Traded later as SPY versus cash.
* ``sectors``: hold the K industries with the strongest trailing return, skipping the latest month
  (industry momentum: Moskowitz & Grinblatt 1999), optionally only while the market trend is positive.
  Traded later as US sector ETFs.

Rules common to every backtest: a signal uses closes up to day s; the trade happens at the next close
(s + 1); new weights earn returns from s + 2. Uninvested money earns the risk-free rate. Costs are
charged on turnover. Every parameter variant tried is recorded so the Deflated Sharpe Ratio can
account for the search.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import itertools
import json
import math

import numpy as np

try:
    from . import quant_stats as qs
except ImportError:
    import quant_stats as qs

REGISTERED = "2026-10-21"
TRADING_DAYS = 252
VOL_WINDOW = 63
SKIP = 21

FAMILIES = {
    "trend": {"grid": {"lookback": [126, 189, 252], "target_vol": [None, .10, .15], "rebalance": ["month", "week"]},
              "primary": {"lookback": 252, "target_vol": .15, "rebalance": "month"},
              "benchmark": "Buy and hold the US market"},
    "sectors": {"grid": {"lookback": [126, 252], "top": [2, 3, 4], "trend_filter": [False, True], "rebalance": ["month"]},
                "primary": {"lookback": 252, "top": 3, "trend_filter": False, "rebalance": "month"},
                "benchmark": "Equal-weight all industries"},
}

# Go/no-go gates for moving from backtest (stage 2) to paper trading (stage 3).
# Version 2 (2026-10-21): every gate tests the strategy against simply holding its passive benchmark.
# Version 1 tested excess return over cash, which buy-and-hold itself passes (the equity premium);
# it was replaced after the first run exposed that, a change that can only make passing harder.
GATES_VERSION = 2
GATES = {
    "deflated_sharpe": "Deflated Sharpe Ratio of the primary rule's active return (strategy minus benchmark, after costs) is at least 0.95",
    "newey_west": "Newey–West t-statistic of the primary rule's active return is at least 2",
    "walk_forward": "Walk-forward out-of-sample Sharpe beats the benchmark's Sharpe over the same days",
    "holdout": "Sharpe over the reserved final 10 years (after costs) is at least the benchmark's",
    "robust": "At least 75% of all parameter variants beat the benchmark's Sharpe",
}


def spec_id(family: str, spec: dict) -> str:
    return family + ":" + ",".join(f"{k}={spec[k]}" for k in sorted(spec))


def registration_hash() -> str:
    """Hash of the registered families and gates; reports carry it so later edits are visible."""
    return hashlib.sha256(json.dumps({"families": FAMILIES, "gates": GATES, "gates_version": GATES_VERSION, "registered": REGISTERED,
                                      "skip": SKIP, "vol_window": VOL_WINDOW}, sort_keys=True, default=str).encode()).hexdigest()


def specs(family: str) -> list[dict]:
    grid = FAMILIES[family]["grid"]
    keys = sorted(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*(grid[k] for k in keys))]


def rebalance_days(dates: list[str], rule: str) -> np.ndarray:
    """Boolean mask of signal days: the last trading day of each month, or every fifth day."""
    n = len(dates)
    if rule == "week":
        return np.arange(n) % 5 == 4
    month = np.array([d[:7] for d in dates])
    mask = np.zeros(n, dtype=bool)
    mask[:-1] = month[:-1] != month[1:]
    mask[-1] = True
    return mask


def _trailing_growth(returns: np.ndarray, window: int) -> np.ndarray:
    """Growth over the trailing window ending at each day (NaN until available); 2-D input allowed."""
    log = np.log1p(returns)
    cum = np.cumsum(log, axis=0)
    out = np.full(returns.shape, np.nan)
    out[window:] = cum[window:] - cum[:-window]
    out[window - 1] = cum[window - 1]
    return np.expm1(out)


def target_weights(family: str, spec: dict, market: np.ndarray, rf: np.ndarray, assets: np.ndarray | None = None) -> np.ndarray:
    """Weights wanted at the close of each day from data up to that close (rows: days, columns: assets)."""
    n = len(market)
    lookback = spec["lookback"]
    trend = _trailing_growth(market, lookback) - _trailing_growth(rf, lookback)
    if family == "trend":
        w = np.where(trend > 0, 1.0, 0.0)
        if spec["target_vol"]:
            vol = np.full(n, np.nan)
            sq = np.cumsum(np.r_[0, market]), np.cumsum(np.r_[0, market * market])
            s1 = sq[0][VOL_WINDOW:] - sq[0][:-VOL_WINDOW]
            s2 = sq[1][VOL_WINDOW:] - sq[1][:-VOL_WINDOW]
            vol[VOL_WINDOW - 1:] = np.sqrt(np.maximum(s2 - s1 * s1 / VOL_WINDOW, 0) / (VOL_WINDOW - 1) * TRADING_DAYS)
            w = w * np.minimum(1.0, spec["target_vol"] / np.where(vol > 0, vol, np.nan))
        w[np.isnan(trend)] = np.nan
        return w[:, None]
    if family == "sectors":
        if assets is None:
            raise ValueError("Sector momentum needs asset returns.")
        # Return from t - lookback to t - SKIP: total growth over lookback divided by growth over the skipped month.
        score = (1 + _trailing_growth(assets, lookback)) / (1 + _trailing_growth(assets, SKIP)) - 1
        weights = np.zeros_like(assets)
        valid = ~np.isnan(score).any(axis=1)
        ranks = np.argsort(-np.where(np.isnan(score), -np.inf, score), axis=1)[:, :spec["top"]]
        rows = np.repeat(np.arange(n), spec["top"])
        weights[rows, ranks.ravel()] = 1.0 / spec["top"]
        if spec["trend_filter"]:
            weights[~(trend > 0)] = 0.0
        weights[~valid | np.isnan(trend)] = np.nan
        return weights
    raise ValueError(f"Unknown strategy family: {family}")


def backtest(family: str, spec: dict, dates: list[str], market: np.ndarray, rf: np.ndarray,
             assets: np.ndarray | None = None, cost_bps: float = 10.0) -> dict:
    """Daily net returns with next-close execution, cash at the risk-free rate and costs on turnover."""
    wanted = target_weights(family, spec, market, rf, assets)
    returns = assets if family == "sectors" else market[:, None]
    n, k = returns.shape
    signal = rebalance_days(dates, spec["rebalance"]) & ~np.isnan(wanted).any(axis=1)
    held = np.full((n, k), np.nan)
    current = None
    turnover = np.zeros(n)
    for s in np.flatnonzero(signal):
        if s + 2 >= n:
            break
        new = wanted[s]
        turnover[s + 2] = np.abs(new - (current if current is not None else 0.0)).sum()
        held[s + 2:] = new
        current = new
    start = int(np.flatnonzero(~np.isnan(held[:, 0]))[0])
    w = held[start:]
    gross = (w * returns[start:]).sum(axis=1) + (1 - w.sum(axis=1)) * rf[start:]
    net = gross - turnover[start:] * cost_bps / 1e4
    return {"start": start, "dates": dates[start:], "net": net, "gross": gross, "excess": net - rf[start:],
            "turnover_per_year": float(turnover[start:].sum() / (len(net) / TRADING_DAYS)),
            "exposure": float(w.sum(axis=1).mean()), "weights_last": held[-1].tolist()}


def benchmark_returns(family: str, market: np.ndarray, assets: np.ndarray | None) -> np.ndarray:
    return market if family == "trend" else assets.mean(axis=1)


def walk_forward(family: str, dates: list[str], market, rf, assets, cost_bps: float, first_year: int) -> dict:
    """Each calendar year, pick the variant with the best Sharpe on all earlier data; record next year's returns."""
    runs = {}
    for s in specs(family):
        run = backtest(family, s, dates, market, rf, assets, cost_bps)
        x = run["excess"]
        runs[spec_id(family, s)] = (run, np.array([int(d[:4]) for d in run["dates"]]), np.cumsum(np.r_[0, x]), np.cumsum(np.r_[0, x * x]))
    years = sorted({int(d[:4]) for d in dates if int(d[:4]) >= first_year})
    oos, oos_dates, choices = [], [], []
    for year in years:
        best, best_sharpe = None, -np.inf
        for key, (run, year_of, s1, s2) in runs.items():
            p = int(np.searchsorted(year_of, year))  # Days strictly before this year (prefix sums, no look-ahead).
            if p < TRADING_DAYS * 5:
                continue
            mean = s1[p] / p
            sd = math.sqrt(max(s2[p] / p - mean * mean, 0) * p / (p - 1))
            value = mean / sd * math.sqrt(TRADING_DAYS) if sd > 0 else -np.inf
            if value > best_sharpe:
                best, best_sharpe = key, value
        if best is None:
            continue
        run, year_of = runs[best][0], runs[best][1]
        lo, hi = int(np.searchsorted(year_of, year)), int(np.searchsorted(year_of, year + 1))
        oos.extend(run["excess"][lo:hi]); oos_dates.extend(run["dates"][lo:hi])
        choices.append({"year": str(year), "chosen": best, "in_sample_sharpe": float(best_sharpe)})
    in_sample = float(np.mean([c["in_sample_sharpe"] for c in choices])) if choices else float("nan")
    return {"excess": np.asarray(oos), "dates": oos_dates, "choices": choices, "in_sample_sharpe": in_sample}


def evaluate(family: str, dates: list[str], market: np.ndarray, rf: np.ndarray, assets: np.ndarray | None = None, *,
             cost_bps: float = 10.0, holdout_years: int = 10, first_walk_forward_year: int = 1950, bootstrap_draws: int = 1000) -> dict:
    """Full evidence for one family: every variant, the primary rule, walk-forward, holdout and the gates."""
    family_specs = specs(family)
    bench_all = benchmark_returns(family, market, assets)
    variants = []
    for spec in family_specs:
        run = backtest(family, spec, dates, market, rf, assets, cost_bps)
        active = run["net"] - bench_all[run["start"]:]
        variants.append({"id": spec_id(family, spec), "spec": spec, "sharpe": qs.sharpe(run["excess"]),
                         "benchmark_sharpe": qs.sharpe(bench_all[run["start"]:] - rf[run["start"]:]),
                         "active_per_period": float(active.mean() / active.std(ddof=1)),
                         "annual_return": qs.summary(run["net"])["annual_return"], "max_drawdown": qs.max_drawdown(run["net"]),
                         "turnover_per_year": run["turnover_per_year"]})
    primary_spec = FAMILIES[family]["primary"]
    primary = backtest(family, primary_spec, dates, market, rf, assets, cost_bps)
    excess = primary["excess"]
    trial_sharpes = [v["active_per_period"] for v in variants]
    bench = benchmark_returns(family, market, assets)[primary["start"]:]
    bench_excess = bench - rf[primary["start"]:]
    cutoff = (dt.date.fromisoformat(dates[-1]) - dt.timedelta(days=round(365.25 * holdout_years))).isoformat()
    in_holdout = np.array([d > cutoff for d in primary["dates"]])
    wf = walk_forward(family, dates, market, rf, assets, cost_bps, first_walk_forward_year)
    wf_index = {d: i for i, d in enumerate(primary["dates"])}
    wf_bench = np.array([bench_excess[wf_index[d]] for d in wf["dates"]]) if wf["dates"] else np.array([])
    costs = {str(c): qs.sharpe(backtest(family, primary_spec, dates, market, rf, assets, c)["excess"]) for c in (0, 10, 25, 50)}
    result = {
        "family": family, "benchmark": FAMILIES[family]["benchmark"], "primary": spec_id(family, primary_spec),
        "period": [primary["dates"][0], primary["dates"][-1]], "cost_bps": cost_bps,
        "summary": qs.summary(primary["net"]), "excess_sharpe": qs.sharpe(excess),
        "benchmark_summary": qs.summary(bench), "benchmark_excess_sharpe": qs.sharpe(bench_excess),
        "newey_west_excess": qs.newey_west_mean(excess),
        "newey_west_active": qs.newey_west_mean(primary["net"] - bench),
        "psr_excess": qs.probabilistic_sharpe(excess), "information_ratio": qs.sharpe(primary["net"] - bench),
        "deflated": qs.deflated_sharpe(primary["net"] - bench, trial_sharpes),
        "bootstrap": qs.bootstrap_sharpe(excess, draws=bootstrap_draws),
        "sharpe_vs_benchmark": qs.bootstrap_sharpe_difference(excess, bench_excess, draws=bootstrap_draws),
        "turnover_per_year": primary["turnover_per_year"], "average_exposure": primary["exposure"],
        "cost_sensitivity_sharpe": costs,
        "holdout": {"from": cutoff, "sharpe": qs.sharpe(excess[in_holdout]), "benchmark_sharpe": qs.sharpe(bench_excess[in_holdout]),
                    "pre_holdout_sharpe": qs.sharpe(excess[~in_holdout]), "max_drawdown": qs.max_drawdown(primary["net"][in_holdout]),
                    "benchmark_max_drawdown": qs.max_drawdown(bench[in_holdout])},
        "walk_forward": {"sharpe": qs.sharpe(wf["excess"]) if len(wf["excess"]) > 30 else None,
                         "in_sample_sharpe": wf["in_sample_sharpe"],
                         "benchmark_sharpe": qs.sharpe(wf_bench) if len(wf_bench) > 30 else None,
                         "from": wf["dates"][0] if wf["dates"] else None, "years": len(wf["choices"]),
                         "distinct_choices": len({c["chosen"] for c in wf["choices"]})},
        "variants": variants,
        "spec_curve": {"count": len(variants), "positive_share": float(np.mean([v["sharpe"] > 0 for v in variants])),
                       "beats_benchmark_share": float(np.mean([v["sharpe"] > v["benchmark_sharpe"] for v in variants])),
                       "median_sharpe": float(np.median([v["sharpe"] for v in variants])),
                       "min_sharpe": float(min(v["sharpe"] for v in variants)), "max_sharpe": float(max(v["sharpe"] for v in variants))},
    }
    w = result["walk_forward"]
    result["gates"] = {
        "deflated_sharpe": bool(result["deflated"]["dsr"] >= .95),
        "newey_west": bool(result["newey_west_active"]["t"] >= 2),
        "walk_forward": bool(w["sharpe"] is not None and w["benchmark_sharpe"] is not None and w["sharpe"] > w["benchmark_sharpe"]),
        "holdout": bool(result["holdout"]["sharpe"] >= result["holdout"]["benchmark_sharpe"]),
        "robust": bool(result["spec_curve"]["beats_benchmark_share"] >= .75),
    }
    result["gates_version"] = GATES_VERSION
    result["go_to_paper"] = all(result["gates"].values())
    return result


def latest_signal(family: str, spec: dict, dates: list[str], closes: np.ndarray, symbols: list[str], rf_annual: float = 0.0) -> dict:
    """Target weights for live/paper trading from the traded instruments' own adjusted closes.

    The first column is always the market proxy (SPY): ``trend`` trades it; ``sectors`` uses it only for
    the trend filter and ranks the remaining columns. Same rules as the backtest; the decision is for the next close.
    """
    prices = np.asarray(closes, dtype=np.float64)
    if prices.ndim != 2 or prices.shape[1] != len(symbols) or prices.shape[0] < spec["lookback"] + 30 or (prices <= 0).any():
        raise ValueError("Need positive closes for every symbol covering the lookback plus 30 days.")
    returns = prices[1:] / prices[:-1] - 1
    rf = np.full(len(returns), (1 + rf_annual) ** (1 / TRADING_DAYS) - 1)
    market = returns[:, 0]
    assets = returns[:, 1:] if family == "sectors" else None
    if family == "sectors" and (assets.shape[1] < spec["top"] + 1):
        raise ValueError("Sector momentum needs more sectors than it holds.")
    weights = target_weights(family, spec, market, rf, assets)[-1]
    if np.isnan(weights).any():
        raise ValueError("Not enough history for this rule yet.")
    targets = {symbols[0]: float(weights[0])} if family == "trend" else {s: float(w) for s, w in zip(symbols[1:], weights) if w > 0}
    trend = float(_trailing_growth(market, spec["lookback"])[-1] - _trailing_growth(rf, spec["lookback"])[-1])
    return {"family": family, "spec": spec, "as_of": dates[-1], "targets": targets, "cash": 1 - sum(targets.values()),
            "market_trend": trend, "registration": registration_hash(),
            "note": "Signal from closes up to as_of; the rule trades at the next close."}


def lab_inputs(factors_zip: bytes, industries_zip: bytes):
    """Daily dates, market total return, risk-free rate and 12 industry returns from the French library files."""
    try:
        from . import quant_data as qd
    except ImportError:
        import quant_data as qd
    factors = qd.parse_french(factors_zip)
    industries = qd.parse_french(industries_zip, "Average Value Weighted Returns -- Daily")
    if factors["dates"] != industries["dates"]:
        raise ValueError("Market and industry files cover different dates.")
    market = factors["series"]["Mkt-RF"] + factors["series"]["RF"]
    rf = factors["series"]["RF"]
    assets = np.column_stack([industries["series"][name] for name in industries["series"]])
    keep = np.isfinite(market) & np.isfinite(rf) & np.isfinite(assets).all(axis=1)
    return [d.isoformat() for d, k in zip(factors["dates"], keep) if k], market[keep], rf[keep], assets[keep]


def run_lab(factors_zip: bytes, industries_zip: bytes, progress=None) -> dict:
    dates, market, rf, assets = lab_inputs(factors_zip, industries_zip)
    results = {}
    for i, family in enumerate(FAMILIES):
        if progress:
            progress(f"Testing the {family} strategy family", i / len(FAMILIES))
        results[family] = evaluate(family, dates, market, rf, assets if family == "sectors" else None)
        results[family]["variants"] = sorted(results[family]["variants"], key=lambda v: -v["sharpe"])
    return {"registration": {"date": REGISTERED, "hash": registration_hash(), "gates": GATES, "gates_version": GATES_VERSION,
                             "families": {k: {"primary": v["primary"], "benchmark": v["benchmark"]} for k, v in FAMILIES.items()}},
            "data": {"first": dates[0], "last": dates[-1], "days": len(dates)}, "results": results,
            "go_to_paper": {family: r["go_to_paper"] for family, r in results.items()}}


def paper_signal(family: str, dates: list[str], closes, symbols: list[str], rf_annual: float, since: str | None = None,
                 cost_bps: float = 10.0) -> dict:
    """Today's targets for the traded ETFs plus the rule's simulated daily returns on the same ETFs (tracking benchmark)."""
    spec = FAMILIES[family]["primary"]
    signal = latest_signal(family, spec, dates, closes, symbols, rf_annual)
    prices = np.asarray(closes, dtype=np.float64)
    returns = prices[1:] / prices[:-1] - 1
    rf = np.full(len(returns), (1 + rf_annual) ** (1 / TRADING_DAYS) - 1)
    run = backtest(family, spec, dates[1:], returns[:, 0], rf, returns[:, 1:] if family == "sectors" else None, cost_bps)
    simulated = {d: float(r) for d, r in zip(run["dates"], run["net"]) if since is None or d >= since}
    signal["simulated"] = simulated
    signal["prices"] = {s: float(p) for s, p in zip(symbols, prices[-1])}
    return signal
