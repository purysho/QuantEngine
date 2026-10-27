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
    # Registered 2026-10-22, before any run on real data (see REGISTERED_EXTRA and the git history).
    # Buffett lesson: hold the most profitable companies patiently (Novy-Marx 2013; Frazzini, Kabiller & Pedersen 2018).
    "quality": {"grid": {"portfolio": ["Hi 10", "Hi 20", "Hi 30"], "rebalance": ["month"]},
                "primary": {"portfolio": "Hi 30", "rebalance": "month"},
                "benchmark": "Buy and hold the US market"},
    # Medallion lesson, retail version: combine several weakly related return sources (trend-timed market,
    # sector momentum, quality, 10-year Treasuries), balance them by risk, then size the whole portfolio to a
    # volatility target with at most modest borrowing, paying a realistic margin rate.
    "ensemble": {"specs": [{"weighting": w, "target_vol": v, "leverage_cap": c, "rebalance": "month"}
                           for w in ("equal", "inverse_vol") for v, c in ((None, 1.0), (.10, 1.0), (.10, 1.5), (.15, 1.0), (.15, 1.5))],
                 "primary": {"weighting": "inverse_vol", "target_vol": .15, "leverage_cap": 1.5, "rebalance": "month"},
                 "benchmark": "Buy and hold the US market"},
    # Registered 2026-10-27, before any run on real data (see REGISTERED_MULTIFACTOR and the git history).
    # Quality, value and momentum, held together: each has a long published record (Novy-Marx 2013; Fama & French
    # 1992; Jegadeesh & Titman 1993) and value and momentum tend to do well at different times (Asness, Moskowitz &
    # Pedersen 2013), so the blend should beat the market more steadily than any one of them. Long-only, no borrowing.
    "multifactor": {"grid": {"cut": ["Hi 30", "Hi 20", "Hi 10"], "weighting": ["equal", "inverse_vol"], "rebalance": ["month"]},
                    "primary": {"cut": "Hi 30", "weighting": "equal", "rebalance": "month"},
                    "benchmark": "Buy and hold the US market"},
}
REGISTERED_EXTRA = "2026-10-22"  # quality and ensemble
REGISTERED_MULTIFACTOR = "2026-10-27"
BORROW_SPREAD = 0.025  # Annual margin cost above the risk-free rate on any borrowed amount (registered with the families).
QUALITY_COLUMNS = ["Hi 10", "Hi 20", "Hi 30"]
# Asset layout for quality/ensemble backtests: market, 12 industries, quality (Hi 10, Hi 20, Hi 30), 10-year Treasury.
ENSEMBLE_QUALITY = 13 + QUALITY_COLUMNS.index("Hi 30")
ENSEMBLE_BONDS = 16
LAB_LAYOUT = {"sectors": slice(1, 13), "quality": ENSEMBLE_QUALITY, "bonds": ENSEMBLE_BONDS}
# Multi-factor sleeves (value-weighted Ken French portfolios, US): profitability = Portfolios_Formed_on_OP,
# value = Portfolios_Formed_on_BE-ME (book-to-market), momentum = 10_Portfolios_Prior_12_2 (return from 12 to
# 2 months ago). "Hi 30" for momentum is the average of the top three deciles, "Hi 20" of the top two, "Hi 10" the
# top decile. In the full lab matrix value sits in columns 17-19 and momentum in 20-22 (Hi 10, Hi 20, Hi 30).
MOMENTUM_CUTS = {"Hi 10": ["Hi PRIOR"], "Hi 20": ["PRIOR 9", "Hi PRIOR"], "Hi 30": ["PRIOR 8", "PRIOR 9", "Hi PRIOR"]}
MULTIFACTOR_COLUMNS = {cut: [13 + i, 17 + i, 20 + i] for i, cut in enumerate(QUALITY_COLUMNS)}

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
                                      "registered_extra": REGISTERED_EXTRA, "registered_multifactor": REGISTERED_MULTIFACTOR,
                                      "momentum_cuts": MOMENTUM_CUTS, "borrow_spread": BORROW_SPREAD,
                                      "skip": SKIP, "vol_window": VOL_WINDOW}, sort_keys=True, default=str).encode()).hexdigest()


def specs(family: str) -> list[dict]:
    if "specs" in FAMILIES[family]:
        return [dict(s) for s in FAMILIES[family]["specs"]]
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


def target_weights(family: str, spec: dict, market: np.ndarray, rf: np.ndarray, assets: np.ndarray | None = None,
                   dates: list[str] | None = None, layout: dict | None = None) -> np.ndarray:
    """Weights wanted at the close of each day from data up to that close (rows: days, columns: assets)."""
    n = len(market)
    lookback = spec.get("lookback", 252)  # The ensemble's trend sleeve uses the registered 12-month trend.
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
    if family == "quality":
        weights = np.zeros_like(assets)
        weights[:, (layout or {}).get("quality", 13 + QUALITY_COLUMNS.index(spec["portfolio"]))] = 1.0
        return weights
    if family == "multifactor":
        # Three sleeves (profitability, value, momentum): equal thirds, or weights inversely proportional to each
        # sleeve's volatility over the last 63 days. Fully invested, never borrowed.
        columns = (layout or {}).get("sleeves") or MULTIFACTOR_COLUMNS[spec["cut"]]
        sleeves = assets[:, columns]
        weights = np.zeros_like(assets)
        if spec["weighting"] == "equal":
            weights[:, columns] = 1 / len(columns)
            return weights
        s1, s2 = (np.cumsum(np.vstack([np.zeros(len(columns)), x]), axis=0) for x in (sleeves, sleeves * sleeves))
        a, b = s1[VOL_WINDOW:] - s1[:-VOL_WINDOW], s2[VOL_WINDOW:] - s2[:-VOL_WINDOW]
        vol = np.full(sleeves.shape, np.nan)
        vol[VOL_WINDOW - 1:] = np.sqrt(np.maximum(b - a * a / VOL_WINDOW, 0) / (VOL_WINDOW - 1))
        inverse = 1 / np.where(vol > 0, vol, np.nan)
        weights[:, columns] = inverse / inverse.sum(axis=1, keepdims=True)
        weights[np.isnan(inverse).any(axis=1)] = np.nan
        return weights
    if family == "ensemble":
        if dates is None or len(dates) != len(market):
            raise ValueError("The ensemble needs dates to find month-ends.")
        return _ensemble_weights(spec, assets, trend, rebalance_days(dates, spec["rebalance"]), layout or LAB_LAYOUT)
    raise ValueError(f"Unknown strategy family: {family}")


def _ensemble_weights(spec: dict, assets, trend, signal_days: np.ndarray, layout: dict) -> np.ndarray:
    """Four sleeves balanced by risk, then scaled to the volatility target. Computed on month-ends only."""
    n, k = assets.shape
    weights = np.full((n, k), np.nan)
    sectors = layout["sectors"]
    sector_scores = (1 + _trailing_growth(assets[:, sectors], 252)) / (1 + _trailing_growth(assets[:, sectors], SKIP)) - 1
    for s in np.flatnonzero(signal_days):
        if s < 252 or np.isnan(trend[s]) or np.isnan(sector_scores[s]).any():
            continue
        window = assets[s - VOL_WINDOW + 1:s + 1]
        sleeves = []
        trend_sleeve = np.zeros(k); trend_sleeve[0] = 1.0
        sector_sleeve = np.zeros(k); sector_sleeve[sectors.start + np.argsort(-sector_scores[s])[:3]] = 1 / 3
        quality_sleeve = np.zeros(k); quality_sleeve[layout["quality"]] = 1.0
        bond_sleeve = np.zeros(k); bond_sleeve[layout["bonds"]] = 1.0
        for sleeve in (trend_sleeve, sector_sleeve, quality_sleeve, bond_sleeve):
            sleeves.append((sleeve, float(np.std(window @ sleeve, ddof=1) * math.sqrt(TRADING_DAYS))))
        raw = np.array([1 / v if spec["weighting"] == "inverse_vol" else 1.0 for _, v in sleeves])
        sleeve_weights = raw / raw.sum()
        # The trend sleeve holds the market only while its trend is positive; otherwise its share sits in cash.
        combined = sum(w * (sl if i or trend[s] > 0 else np.zeros(k)) for i, ((sl, _), w) in enumerate(zip(sleeves, sleeve_weights)))
        if spec["target_vol"]:
            vol = float(np.sqrt(combined @ np.cov(window, rowvar=False) @ combined) * math.sqrt(TRADING_DAYS))
            combined = combined * (min(spec["leverage_cap"], spec["target_vol"] / vol) if vol > 0 else 1.0)
        weights[s] = combined
    return weights



def backtest(family: str, spec: dict, dates: list[str], market: np.ndarray, rf: np.ndarray,
             assets: np.ndarray | None = None, cost_bps: float = 10.0, layout: dict | None = None) -> dict:
    """Daily net returns with next-close execution, cash at the risk-free rate and costs on turnover."""
    wanted = target_weights(family, spec, market, rf, assets, dates, layout)
    returns = market[:, None] if family == "trend" else assets
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
    borrowed = np.maximum(w.sum(axis=1) - 1, 0)  # Borrowing pays the risk-free rate (above) plus the margin spread.
    net = gross - turnover[start:] * cost_bps / 1e4 - borrowed * BORROW_SPREAD / TRADING_DAYS
    return {"start": start, "dates": dates[start:], "net": net, "gross": gross, "excess": net - rf[start:],
            "turnover_per_year": float(turnover[start:].sum() / (len(net) / TRADING_DAYS)),
            "exposure": float(w.sum(axis=1).mean()), "max_exposure": float(w.sum(axis=1).max()), "weights_last": held[-1].tolist()}


def benchmark_returns(family: str, market: np.ndarray, assets: np.ndarray | None) -> np.ndarray:
    return assets.mean(axis=1) if family == "sectors" else market


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
             cost_bps: float = 10.0, holdout_years: int = 10, first_walk_forward_year: int = 1950, bootstrap_draws: int = 1000,
             n_trials: int | None = None) -> dict:
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
        "deflated": qs.deflated_sharpe(primary["net"] - bench, trial_sharpes, n_trials),
        "bootstrap": qs.bootstrap_sharpe(excess, draws=bootstrap_draws),
        "sharpe_vs_benchmark": qs.bootstrap_sharpe_difference(excess, bench_excess, draws=bootstrap_draws),
        "turnover_per_year": primary["turnover_per_year"], "average_exposure": primary["exposure"],
        "max_exposure": primary["max_exposure"],
        # Annual return if the strategy were scaled (up or down) to the benchmark's volatility: the fair "more return" comparison.
        "return_at_benchmark_risk": float(np.mean(rf[primary["start"]:]) * TRADING_DAYS + qs.sharpe(excess) * qs.summary(bench)["annual_volatility"]),
        "benchmark_return_arithmetic": float(np.mean(bench) * TRADING_DAYS),
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
    if assets is not None and assets.shape[1] > ENSEMBLE_BONDS:
        mix = (.6 * market + .4 * assets[:, ENSEMBLE_BONDS])[primary["start"]:]
        result["reference_60_40"] = {"summary": qs.summary(mix), "excess_sharpe": qs.sharpe(mix - rf[primary["start"]:])}
    result["go_to_paper"] = all(result["gates"].values())
    return result


# Traded instruments for each family. The first column is always SPY (market and trend filter).
PAPER_UNIVERSE = {
    "trend": ["SPY"],
    "sectors": ["SPY", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC"],
    "quality": ["SPY", "QUAL"],
    "ensemble": ["SPY", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "XLRE", "XLC", "QUAL", "IEF"],
    # iShares MSCI USA factor ETFs (2013 onwards) stand in for the three Ken French sleeves; their index rules
    # differ, so paper trading measures how closely the tradable version follows the researched one.
    "multifactor": ["SPY", "QUAL", "VLUE", "MTUM"],
}
PAPER_LAYOUT = {"quality": {"quality": 1}, "ensemble": {"sectors": slice(1, 12), "quality": 12, "bonds": 13},
                "multifactor": {"sleeves": [1, 2, 3]}}


def latest_signal(family: str, spec: dict, dates: list[str], closes: np.ndarray, symbols: list[str], rf_annual: float = 0.0) -> dict:
    """Target weights for live/paper trading from the traded instruments' own adjusted closes.

    The first column is always the market proxy (SPY): ``trend`` trades it; ``sectors`` uses it only for the
    trend filter and ranks the other columns; ``quality`` holds QUAL; ``ensemble`` uses SPY, the sector ETFs,
    QUAL and IEF in the PAPER_UNIVERSE order; ``multifactor`` holds QUAL, VLUE and MTUM. Same rules as the backtest; the decision is for the next close.
    """
    prices = np.asarray(closes, dtype=np.float64)
    if prices.ndim != 2 or prices.shape[1] != len(symbols) or prices.shape[0] < spec.get("lookback", 252) + 30 or (prices <= 0).any():
        raise ValueError("Need positive closes for every symbol covering the lookback plus 30 days.")
    if family in PAPER_UNIVERSE and family != "sectors" and symbols != PAPER_UNIVERSE[family]:
        raise ValueError(f"The {family} signal expects these symbols in order: {', '.join(PAPER_UNIVERSE[family])}.")
    returns = prices[1:] / prices[:-1] - 1
    rf = np.full(len(returns), (1 + rf_annual) ** (1 / TRADING_DAYS) - 1)
    market = returns[:, 0]
    if family == "sectors":
        assets = returns[:, 1:]
        if assets.shape[1] < spec["top"] + 1:
            raise ValueError("Sector momentum needs more sectors than it holds.")
    else:
        assets = returns if family in ("quality", "ensemble", "multifactor") else None
    signal_dates = dates[1:]
    weights = target_weights(family, spec, market, rf, assets, signal_dates, PAPER_LAYOUT.get(family))
    if family == "ensemble":
        # The ensemble decides on month-ends only; between them it keeps the latest month-end targets.
        decided = np.flatnonzero(~np.isnan(weights).any(axis=1))
        if not len(decided):
            raise ValueError("Not enough history for this rule yet.")
        weights = weights[decided[-1]]
    else:
        weights = weights[-1]
    if np.isnan(weights).any():
        raise ValueError("Not enough history for this rule yet.")
    columns = symbols[1:] if family == "sectors" else symbols
    targets = {symbols[0]: float(weights[0])} if family == "trend" else {s: float(w) for s, w in zip(columns, weights) if w > 1e-9}
    trend = float(_trailing_growth(market, spec.get("lookback", 252))[-1] - _trailing_growth(rf, spec.get("lookback", 252))[-1])
    return {"family": family, "spec": spec, "as_of": dates[-1], "targets": targets, "cash": 1 - sum(targets.values()),
            "gross_exposure": float(sum(targets.values())), "market_trend": trend, "registration": registration_hash(),
            "note": "Signal from closes up to as_of; the rule trades at the next close."}


def treasury_returns(trading_dates: list[str], fred_dates: list[str], yields) -> np.ndarray:
    """Daily total return of a 10-year par Treasury from FRED DGS10 (percent), repriced each day at the new yield.

    Buy a par bond (coupon = yesterday's yield, 10 years, semiannual) at price 1, earn a day of coupon, and
    revalue at today's yield. Missing yields carry the last value (return = coupon only). A standard
    approximation of a constant-maturity bond index; IEF (7-10 years) is the traded counterpart.
    """
    level = dict(zip(fred_dates, yields))
    out = np.full(len(trading_dates), np.nan)
    last = None
    for i, d in enumerate(trading_dates):
        y = level.get(d)
        current = y / 100 if y is not None and np.isfinite(y) else last
        if last is not None and current is not None:
            c, h = last, current / 2
            price = (c / 2) * (1 - (1 + h) ** -20) / h + (1 + h) ** -20 if h > 0 else 1.0
            out[i] = price - 1 + c / TRADING_DAYS
        last = current
    return out


def lab_inputs(factors_zip: bytes, industries_zip: bytes, op_zip: bytes | None = None, dgs10_csv: bytes | None = None,
               bm_zip: bytes | None = None, momentum_zip: bytes | None = None) -> dict:
    """Daily inputs. ``main`` covers 1926 onwards (trend, sectors); ``full`` adds quality and Treasuries from mid-1963,
    and value and momentum portfolios (columns 17-22) when those files are given."""
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
    dates = [d.isoformat() for d, k in zip(factors["dates"], keep) if k]
    out = {"main": (dates, market[keep], rf[keep], assets[keep]), "full": None}
    if op_zip is not None and dgs10_csv is not None:
        op = qd.parse_french(op_zip, "Average Value Weighted Returns -- Daily")
        fred = qd.parse_fred(dgs10_csv)
        op_index = {d.isoformat(): i for i, d in enumerate(op["dates"])}
        rows = [i for i, d in enumerate(dates) if d in op_index]
        full_dates = [dates[i] for i in rows]
        if bm_zip is not None and momentum_zip is not None:
            bm = qd.parse_french(bm_zip, "Average Value Weighted Returns -- Daily")
            mom = qd.parse_french(momentum_zip, "Average Value Weighted Returns -- Daily")
            bm_index = {d.isoformat(): i for i, d in enumerate(bm["dates"])}
            mom_index = {d.isoformat(): i for i, d in enumerate(mom["dates"])}
            rows = [i for i in rows if dates[i] in bm_index and dates[i] in mom_index]
            full_dates = [dates[i] for i in rows]
        quality = np.column_stack([op["series"][c][[op_index[d] for d in full_dates]] for c in QUALITY_COLUMNS])
        bonds = treasury_returns(full_dates, [d.isoformat() for d in fred["dates"]], fred["series"]["DGS10"])
        m, r, a = market[keep][rows], rf[keep][rows], assets[keep][rows]
        parts = [m, a, quality, bonds]
        if bm_zip is not None and momentum_zip is not None:
            parts.append(np.column_stack([bm["series"][c][[bm_index[d] for d in full_dates]] for c in QUALITY_COLUMNS]))
            parts.append(np.column_stack([np.mean([mom["series"][c][[mom_index[d] for d in full_dates]] for c in MOMENTUM_CUTS[cut]], axis=0)
                                          for cut in QUALITY_COLUMNS]))
        matrix = np.column_stack(parts)
        ok = np.isfinite(matrix).all(axis=1)
        out["full"] = ([d for d, k in zip(full_dates, ok) if k], m[ok], r[ok], matrix[ok])
    return out


def run_lab(factors_zip: bytes, industries_zip: bytes, op_zip: bytes | None = None, dgs10_csv: bytes | None = None,
            bm_zip: bytes | None = None, momentum_zip: bytes | None = None, progress=None) -> dict:
    inputs = lab_inputs(factors_zip, industries_zip, op_zip, dgs10_csv, bm_zip, momentum_zip)
    full = inputs["full"]
    families = [f for f in FAMILIES if f in ("trend", "sectors") or (full is not None and (f != "multifactor" or full[3].shape[1] > 20))]
    total_trials = sum(len(specs(f)) for f in families)
    results = {}
    for i, family in enumerate(families):
        if progress:
            progress(f"Testing the {family} strategy family", i / len(families))
        dates, market, rf, assets = inputs["main"] if family in ("trend", "sectors") else inputs["full"]
        # Families registered later are deflated by every variant tried so far, across all families.
        results[family] = evaluate(family, dates, market, rf, assets if family != "trend" else None,
                                   n_trials=total_trials if family in ("quality", "ensemble", "multifactor") else None)
        results[family]["variants"] = sorted(results[family]["variants"], key=lambda v: -v["sharpe"])
    first, last = inputs["main"][0][0], inputs["main"][0][-1]
    return {"registration": {"date": REGISTERED, "extra": REGISTERED_EXTRA, "multifactor": REGISTERED_MULTIFACTOR,
                             "hash": registration_hash(), "gates": GATES,
                             "gates_version": GATES_VERSION, "borrow_spread": BORROW_SPREAD, "total_trials": total_trials,
                             "families": {k: {"primary": v["primary"], "benchmark": v["benchmark"]} for k, v in FAMILIES.items()}},
            "data": {"first": first, "last": last, "days": len(inputs["main"][0]),
                     "full_first": inputs["full"][0][0] if inputs["full"] else None},
            "results": results, "go_to_paper": {family: r["go_to_paper"] for family, r in results.items()}}


def paper_signal(family: str, dates: list[str], closes, symbols: list[str], rf_annual: float, since: str | None = None,
                 cost_bps: float = 10.0) -> dict:
    """Today's targets for the traded ETFs plus the rule's simulated daily returns on the same ETFs (tracking benchmark)."""
    spec = FAMILIES[family]["primary"]
    signal = latest_signal(family, spec, dates, closes, symbols, rf_annual)
    prices = np.asarray(closes, dtype=np.float64)
    returns = prices[1:] / prices[:-1] - 1
    rf = np.full(len(returns), (1 + rf_annual) ** (1 / TRADING_DAYS) - 1)
    assets = returns[:, 1:] if family == "sectors" else returns if family in ("quality", "ensemble", "multifactor") else None
    run = backtest(family, spec, dates[1:], returns[:, 0], rf, assets, cost_bps, PAPER_LAYOUT.get(family))
    simulated = {d: float(r) for d, r in zip(run["dates"], run["net"]) if since is None or d >= since}
    signal["simulated"] = simulated
    signal["market_returns"] = {d: float(r) for d, r in zip(dates[1:], returns[:, 0]) if since is None or d >= since}
    signal["prices"] = {s: float(p) for s, p in zip(symbols, prices[-1])}
    return signal


def etf_check(family: str, dates: list[str], closes, symbols: list[str], rf_annual: float, cost_bps: float = 10.0) -> dict:
    """The primary rule replayed on the ETFs it would really hold, against holding SPY, over the same days.

    This is the tradable version of the research: the ETFs' own index rules and fees are in their prices, so the
    gap to the Ken French results shows how much of the researched edge a real account could have kept.
    Cash earns a constant ``rf_annual`` (today's rate), a simplification for this check only.
    """
    spec = FAMILIES[family]["primary"]
    if symbols != PAPER_UNIVERSE[family]:
        raise ValueError(f"The {family} check expects these symbols in order: {', '.join(PAPER_UNIVERSE[family])}.")
    prices = np.asarray(closes, dtype=np.float64)
    if prices.ndim != 2 or prices.shape[1] != len(symbols) or prices.shape[0] < 300 or (prices <= 0).any():
        raise ValueError("Need positive closes for every symbol covering at least 300 days.")
    returns = prices[1:] / prices[:-1] - 1
    rf = np.full(len(returns), (1 + rf_annual) ** (1 / TRADING_DAYS) - 1)
    assets = returns[:, 1:] if family == "sectors" else returns if family != "trend" else None
    run = backtest(family, spec, dates[1:], returns[:, 0], rf, assets, cost_bps, PAPER_LAYOUT.get(family))
    rule, spy = run["net"], returns[run["start"]:, 0]
    days = run["dates"]

    def stats(r):
        summary = qs.summary(r)
        return {"annual_return": summary["annual_return"], "annual_volatility": summary["annual_volatility"],
                "sharpe": qs.sharpe(r - rf[run["start"]:]), "max_drawdown": qs.max_drawdown(r), "growth_of_10000": float(10000 * np.prod(1 + r))}

    years = {}
    for year in sorted({d[:4] for d in days}):
        mask = np.array([d[:4] == year for d in days])
        years[year] = {"rule": float(np.prod(1 + rule[mask]) - 1), "spy": float(np.prod(1 + spy[mask]) - 1), "days": int(mask.sum())}
    active = rule - spy
    return {"family": family, "primary": spec_id(family, spec), "symbols": symbols, "from": days[0], "to": days[-1], "days": len(days),
            "rule": stats(rule), "spy": stats(spy), "years": years, "newey_west_active": qs.newey_west_mean(active),
            "beat_spy_years": sum(1 for y in years.values() if y["days"] > 200 and y["rule"] > y["spy"]),
            "full_years": sum(1 for y in years.values() if y["days"] > 200), "rf_annual": rf_annual, "cost_bps": cost_bps,
            "note": "ETF prices include each fund's fees and index rules; cash earns today's rate throughout."}

