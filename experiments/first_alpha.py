"""First alpha experiment: does a chronological ridge model beat explicit baselines?

Synthetic data only. It validates the mechanism (power on a known weak signal,
false-positive behaviour on null data, rejection of a leaked feature); it is not
evidence of market alpha.
"""
import time

import numpy as np

from _common import array_hash, write
from workers.quant_validation import chronological_ridge

N, FEATURES, SEEDS = 1000, 5, 200
SETTINGS = dict(initial_train=200, test_size=100, final_holdout=200, alphas=(.1, 1., 10., 100., 1000.))


def scenario(seed, kind):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(N, FEATURES))
    clock = np.arange(N)
    if kind == "null":
        y, ends = rng.normal(size=N), clock + 1
    elif kind == "weak_signal":
        y, ends = .15 * x[:, 0] + rng.normal(size=N), clock + 1  # True R^2 ~ 2.2%.
    elif kind == "overlapping_5":
        shocks = rng.normal(size=N + 5)
        shocks[1:N + 1] += .3 * x[:, 0]  # Feature predicts the first of five future shocks.
        y = np.array([shocks[i + 1:i + 6].sum() for i in range(N)])
        ends = clock + 5
    else:
        raise ValueError(kind)
    return x, y, clock, ends


def summarise(values):
    v = np.asarray(values)
    return {"mean": float(v.mean()), "median": float(np.median(v)), "p05": float(np.quantile(v, .05)),
            "p95": float(np.quantile(v, .95)), "share_positive": float(np.mean(v > 0))}


started = time.perf_counter()
results, hashes = {}, []
for kind in ("null", "weak_signal", "overlapping_5"):
    r2, hits, alphas = [], [], []
    for seed in range(SEEDS):
        x, y, available, ends = scenario(seed, kind)
        if seed == 0:
            hashes.append({"scenario": kind, "seed": 0, "sha256": array_hash(x, y, available, ends)})
        out = chronological_ridge(x, y, feature_available=available, label_end=ends, **SETTINGS)
        r2.append(out["holdout"]["oos_r2_vs_mean"])
        hits.append(out["holdout"]["hit_rate"])
        alphas.append(out["selected_alpha"])
    results[kind] = {"seeds": SEEDS, "holdout_oos_r2_vs_mean": summarise(r2), "holdout_hit_rate": summarise(hits),
                     "selected_alpha_counts": {str(a): alphas.count(a) for a in SETTINGS["alphas"]}}

# Negative control: the next label itself as a feature, with an honest availability clock.
x, y, clock, ends = scenario(0, "null")
leaked = np.column_stack([x, y])
try:
    chronological_ridge(leaked, y, feature_available=ends, label_end=ends, **SETTINGS)
    leak = {"rejected": False}
except ValueError as exc:
    leak = {"rejected": True, "message": str(exc)}
# Counterfactual: the same leak with a falsified clock shows what the check prevents.
fake = chronological_ridge(leaked, y, feature_available=clock, label_end=ends, **SETTINGS)
leak["if_clock_were_falsified_oos_r2"] = fake["holdout"]["oos_r2_vs_mean"]

finished = time.perf_counter()
null_p95 = results["null"]["holdout_oos_r2_vs_mean"]["p95"]
payload = {
    "purpose": "Mechanism validation for chronological ridge alpha with purged labels and a frozen holdout.",
    "data": {"rows": N, "features": FEATURES, "seeds": list(range(SEEDS)), "settings": SETTINGS,
             "first_seed_hashes": hashes, "kind": "synthetic Gaussian; not market data"},
    "scenarios": results,
    "leak_control": leak,
    "acceptance": {
        "null_does_not_systematically_beat_mean": results["null"]["holdout_oos_r2_vs_mean"]["mean"] <= 0.0,
        "weak_signal_median_above_null_p95": results["weak_signal"]["holdout_oos_r2_vs_mean"]["median"] > null_p95,
        "overlapping_signal_beats_mean_in_most_seeds": results["overlapping_5"]["holdout_oos_r2_vs_mean"]["share_positive"] > .5,
        "leaked_feature_rejected": leak["rejected"],
    },
    "interpretation": "Synthetic results check timing, selection and power. They say nothing about real-market predictability.",
}
path = write("first_alpha", payload, started, finished)
print(path.read_text())
