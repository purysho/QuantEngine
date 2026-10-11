"""Engle–Granger size/power and the cost of trading spurious pairs. Synthetic data only."""
import time

import numpy as np

from _common import array_hash, write
from workers import quant_pairs as qp

REPS, N, FORMATION = 1000, 500, 250
started = time.perf_counter()


def walk(rng, n):
    return 4 + np.cumsum(rng.normal(0, .01, n))


def coint_pair(rng, n, phi):
    x = walk(rng, n)
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = phi * s[t - 1] + rng.normal(0, .01)
    return .5 + .8 * x + s, x


size = {c: {"1%": 0, "5%": 0, "10%": 0} for c in ("aic", "bic")}
fixed_lag_size = 0
adf_size = 0
p_null = []
for rep in range(REPS):
    rng = np.random.default_rng(10_000 + rep)
    y, x = walk(rng, FORMATION), walk(rng, FORMATION)
    for criterion in ("aic", "bic"):
        r = qp.engle_granger(y, x, criterion=criterion)
        if criterion == "bic":
            p_null.append(r["p_value"])
        for level, crit in r["critical_values"].items():
            size[criterion][level] += r["statistic"] < crit
    fixed_lag_size += qp.engle_granger(y, x, max_lag=0)["rejects_5pct"]
    adf_size += qp.adf_test(walk(rng, FORMATION))["rejects_unit_root_5pct"]
power = {}
for phi in (.8, .9, .95, .98):
    hits = 0
    for rep in range(REPS // 4):
        y, x = coint_pair(np.random.default_rng(20_000 + rep), FORMATION, phi)
        hits += qp.engle_granger(y, x, criterion="bic")["rejects_5pct"]
    power[str(phi)] = hits / (REPS // 4)

# Trading: true pairs vs spurious pairs that passed the formation test by chance.
def trade(kind, seeds):
    results = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        if kind == "cointegrated":
            ly, lx = coint_pair(rng, N, .9)
        else:
            ly, lx = walk(rng, N), walk(rng, N)
        if not qp.engle_granger(ly[:FORMATION], lx[:FORMATION], criterion="bic")["rejects_5pct"]:
            continue
        bt = qp.pairs_backtest(np.exp(ly), np.exp(lx), formation=FORMATION, cost_bps=5, borrow_bps=50)
        results.append({"seed": seed, "total_return": bt["total_return"], "sharpe": bt["sharpe"],
                        "round_trips": bt["round_trips"], "costs": bt["costs_paid"] + bt["borrow_paid"],
                        "max_drawdown": bt["max_drawdown"]})
    r = np.array([row["total_return"] for row in results])
    return {"selected_pairs": len(results),
            "mean_total_return": float(r.mean()) if len(r) else None,
            "median_total_return": float(np.median(r)) if len(r) else None,
            "share_profitable": float(np.mean(r > 0)) if len(r) else None,
            "mean_round_trips": float(np.mean([row["round_trips"] for row in results])) if results else None,
            "mean_costs": float(np.mean([row["costs"] for row in results])) if results else None,
            "worst_drawdown": float(min(row["max_drawdown"] for row in results)) if results else None}

true_pairs = trade("cointegrated", range(30_000, 30_200))
spurious = trade("independent", range(40_000, 42_000))
sample = coint_pair(np.random.default_rng(30_000), N, .9)
finished = time.perf_counter()
p_null = np.array(p_null)
payload = {
    "purpose": "Validate Engle–Granger size and power, and measure out-of-sample trading of true vs spurious pairs.",
    "data": {"kind": "synthetic log prices, daily vol 1%", "formation": FORMATION, "total_closes": N,
             "first_true_pair_sha256": array_hash(*sample)},
    "size_independent_random_walks": {"replications": REPS,
                                      "rejection_rate_by_lag_criterion": {c: {k: v / REPS for k, v in row.items()} for c, row in size.items()},
                                      "rejection_rate_fixed_lag_0_5pct": fixed_lag_size / REPS,
                                      "single_series_adf_rejection_5pct": adf_size / REPS,
                                      "share_p_below_0.05": float(np.mean(p_null < .05))},
    "power_by_spread_ar": {"replications_each": REPS // 4, "rejection_rate_5pct": power},
    "trading_after_formation_test": {"costs": "5 bps per traded notional, 50 bps/yr borrow",
                                     "true_cointegrated_ar0.9": true_pairs,
                                     "spurious_independent_walks": spurious},
    "acceptance": {
        "bic_size_5pct_within_binomial_band": abs(size["bic"]["5%"] / REPS - .05) <= 3 * (.05 * .95 / REPS) ** .5,
        "aic_size_5pct_within_binomial_band": abs(size["aic"]["5%"] / REPS - .05) <= 3 * (.05 * .95 / REPS) ** .5,
        "adf_size_5pct_within_binomial_band": abs(adf_size / REPS - .05) <= 3 * (.05 * .95 / REPS) ** .5,
        "power_increases_with_mean_reversion": power["0.8"] >= power["0.9"] >= power["0.95"] >= power["0.98"],
        "true_pairs_outperform_spurious": (true_pairs["mean_total_return"] or 0) > (spurious["mean_total_return"] or 0),
    },
    "interpretation": "AIC lag search is reported as a known over-rejection, not a pass. Finite-sample size checks the MacKinnon response surfaces. Spurious pairs are the realistic failure mode when many pairs are screened.",
}
path = write("pairs_cointegration", payload, started, finished)
print(path.read_text())
