"""Does the evolutionary learner actually improve results on real data, out of sample?

Prequential protocol on the CRSP value-weighted US market (Kenneth R. French library):
the population evolves on the 500 trading days before each 2-year block, the champion is
frozen, then scored on that block. Compared with (a) the fixed baseline and (b) the best
single fixed configuration chosen *in hindsight* (an upper bound a static user could not know).
"""
import argparse
import datetime as dt
import time

import numpy as np

from _common import ROOT, write
from workers import quant_data as qd
from workers import quant_evolve as ev

parser = argparse.ArgumentParser()
parser.add_argument("--offline", action="store_true")
args = parser.parse_args()
started = time.perf_counter()
dates, r, meta = qd.us_market_returns(ROOT / ".cache" / "data", offline=args.offline)
first = next(i for i, d in enumerate(dates) if d >= dt.date(1990, 1, 1))
BLOCK, VALIDATION = 500, 500
results, hindsight = {}, {}
memory_path = ROOT / ".cache" / "learning" / "experience.jsonl"
if memory_path.exists():
    memory_path.unlink()  # Reproducible experiment: start without memories, then test warm start below.
memory = ev.Experience(memory_path)
naive = {}
for name, task in (("risk", ev.risk_task(r, p=.01)), ("alpha", ev.alpha_task(r))):
    # v1 (naive): one validation window, no guard. Kept to document what went wrong.
    v1 = ev.prequential(task, len(r), first=first, block=BLOCK, validation=VALIDATION, generations=2, population=10, seed=11)
    naive[name] = {"mean_out_of_sample": v1["mean_out_of_sample"], "share_blocks_beating_baseline": v1["share_blocks_beating_baseline"],
                   "champion_families": {f: sum(c["family"] == f for c in v1["curve"]) for f in {c["family"] for c in v1["curve"]}}}
    # v2: evidence accumulated over six past windows (decay 0.85) and a significance guard against the baseline.
    run = ev.prequential(task, len(r), first=first, block=BLOCK, validation=VALIDATION, generations=2, population=10, seed=11,
                         evidence_windows=6, decay=.85, guard=True)
    for c in run["curve"]:
        c["period"] = f"{dates[c['start']]}..{dates[c['end'] - 1]}"
    memory.remember(name, meta["sha256"], run)
    # Static alternatives evaluated on exactly the same blocks.
    fixed = {}
    candidates = ([{"method": m, "window": 500, "refit_every": 50} for m in task.space["method"]] if name == "risk" else
                  [{**task.baseline, "model": m} for m in ("zero", "mean")] +
                  [{"model": "ridge", "features": 63, "ridge": 100., "hidden": 8, "layers": 1, "l2": 1e-3},
                   {"model": "mlp", "features": 63, "ridge": 100., "hidden": 8, "layers": 1, "l2": 1e-3}])
    for genome in candidates:
        label = ",".join(f"{k}={genome[k]}" for k in (("method", "window") if name == "risk" else ("model", "features")))
        fixed[label] = float(np.mean([task.score(genome, c["start"], c["end"]) for c in run["curve"]]))
    best_label = max(fixed, key=fixed.get)
    first_half = run["curve"][: len(run["curve"]) // 2]; second_half = run["curve"][len(run["curve"]) // 2:]
    results[name] = {**{k: run[k] for k in ("describe", "blocks", "mean_out_of_sample", "mean_baseline",
                                           "share_blocks_beating_baseline", "evaluations", "seconds")},
                     "curve": [{k: c[k] for k in ("period", "family", "genome", "validation_score", "out_of_sample_score", "baseline_score")}
                               for c in run["curve"]],
                     "fixed_configurations_mean_score": fixed, "best_fixed_in_hindsight": {best_label: fixed[best_label]},
                     "learner_minus_best_fixed_in_hindsight": run["mean_out_of_sample"] - fixed[best_label],
                     "champion_family_counts": {f: sum(c["family"] == f for c in run["curve"]) for f in {c["family"] for c in run["curve"]}},
                     "naive_v1": naive[name], "guard_share": run["guard_share"],
                     "excess_vs_baseline_first_half": float(np.mean([c["out_of_sample_score"] - c["baseline_score"] for c in first_half])),
                     "excess_vs_baseline_second_half": float(np.mean([c["out_of_sample_score"] - c["baseline_score"] for c in second_half])),
                     "graph": run["graph"]}

# Warm start: does remembered experience help a fresh run on a different market (the 'Other' industry)?
ind, ind_meta = qd.french("12_Industry_Portfolios_daily", ROOT / ".cache" / "data",
                          section="Average Value Weighted Returns -- Daily", offline=args.offline)
other = ind["series"]["Other"]
other = other[np.isfinite(other)]
o_first = len(other) - 8 * BLOCK
cold = ev.prequential(ev.risk_task(other, p=.01), len(other), first=o_first, block=BLOCK, validation=VALIDATION,
                      generations=1, population=6, seed=5, evidence_windows=6, guard=True)
warm = ev.prequential(ev.risk_task(other, p=.01), len(other), first=o_first, block=BLOCK, validation=VALIDATION,
                      generations=1, population=6, seed=5, evidence_windows=6, guard=True, experience=memory.load("risk", ind_meta["sha256"]))
transfer = {"cold_mean_out_of_sample": cold["mean_out_of_sample"], "warm_mean_out_of_sample": warm["mean_out_of_sample"],
            "cold_first_block": cold["curve"][0]["out_of_sample_score"], "warm_first_block": warm["curve"][0]["out_of_sample_score"],
            "blocks": warm["blocks"], "note": "Same seed and budget (1 generation, 6 genomes); warm start seeds the population with "
                                              "genomes remembered from the US-market run."}
finished = time.perf_counter()
payload = {"purpose": "Measure whether evolutionary model search improves real out-of-sample results over time.",
           "data": {"source": meta["url"], "sha256": meta["sha256"], "first_block": str(dates[first]), "last": str(dates[-1]),
                    "block_days": BLOCK, "validation_days": VALIDATION},
           "tasks": results, "transfer_warm_start": transfer,
           "acceptance": {
               "risk_learner_beats_baseline_on_average": results["risk"]["mean_out_of_sample"] > results["risk"]["mean_baseline"],
               "risk_learner_within_5pct_of_best_fixed_in_hindsight": abs(results["risk"]["learner_minus_best_fixed_in_hindsight"])
                                                                     <= .05 * abs(max(results["risk"]["fixed_configurations_mean_score"].values())),
               "alpha_learner_not_worse_than_mean_forecast": results["alpha"]["mean_out_of_sample"] >= results["alpha"]["mean_baseline"] - .05,
               "warm_start_not_worse_than_cold": transfer["warm_mean_out_of_sample"] >= transfer["cold_mean_out_of_sample"]},
           "interpretation": "A learner is only useful if its frozen, forward-scored choices beat simple fixed choices. "
                             "For next-day returns, an honest result near zero R^2 is expected: daily returns are close to unpredictable."}
path = write("evolution_real", payload, started, finished)
for name, res in results.items():
    print(name, "learner", round(res["mean_out_of_sample"], 4), "baseline", round(res["mean_baseline"], 4),
          "beats baseline share", round(res["share_blocks_beating_baseline"], 2), "best fixed", res["best_fixed_in_hindsight"],
          "families", res["champion_family_counts"], "guard", round(res["guard_share"], 2), "v1", res["naive_v1"], "excess 1st/2nd half", round(res["excess_vs_baseline_first_half"], 4),
          round(res["excess_vs_baseline_second_half"], 4), "evals", res["evaluations"], "s", round(res["seconds"], 1))
print("transfer", transfer)
print(payload["acceptance"], round(finished - started, 1), "s")
