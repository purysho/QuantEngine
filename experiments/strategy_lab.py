"""Stage 2 evidence for the pre-registered strategies on 100 years of US data (Ken French library).

Run: python experiments/strategy_lab.py [--offline]
Writes experiments/results/strategy_lab.json. Gates decide whether a strategy may move to paper trading.
"""
from __future__ import annotations

import argparse
import time

import numpy as np

from _common import ROOT, array_hash, write
from workers import quant_data as qd
from workers import quant_strategies as st

parser = argparse.ArgumentParser()
parser.add_argument("--offline", action="store_true")
args = parser.parse_args()
started = time.perf_counter()
cache = ROOT / ".cache" / "data"

factors, factors_meta = qd.french("F-F_Research_Data_Factors_daily", cache, offline=args.offline)
industries, industries_meta = qd.french("12_Industry_Portfolios_daily", cache, section="Average Value Weighted Returns -- Daily", offline=args.offline)
if factors["dates"] != industries["dates"]:
    raise SystemExit("Market and industry files cover different dates.")
market = factors["series"]["Mkt-RF"] + factors["series"]["RF"]
rf = factors["series"]["RF"]
assets = np.column_stack([industries["series"][name] for name in industries["series"]])
keep = np.isfinite(market) & np.isfinite(rf) & np.isfinite(assets).all(axis=1)
dates = [d.isoformat() for d, k in zip(factors["dates"], keep) if k]
market, rf, assets = market[keep], rf[keep], assets[keep]

families = {name: st.evaluate(name, dates, market, rf, assets if name == "sectors" else None) for name in st.FAMILIES}
for result in families.values():  # Keep the JSON small: variant lists are summarised by the spec curve.
    result["variants"] = sorted(result["variants"], key=lambda v: -v["sharpe"])

finished = time.perf_counter()
payload = {
    "registration": {"date": st.REGISTERED, "hash": st.registration_hash(), "families": st.FAMILIES, "gates": st.GATES,
                     "gates_version": st.GATES_VERSION,
                     "gates_history": "Version 1 compared returns with cash; buy-and-hold passes that, so version 2 compares with the benchmark."},
    "data": {"source": "Kenneth R. French Data Library: Mkt-RF + RF and 12 value-weighted industries (daily)",
             "first": dates[0], "last": dates[-1], "days": len(dates), "sha256": array_hash(market, rf, assets),
             "files": [factors_meta["sha256"], industries_meta["sha256"]]},
    "contamination_note": ("Industry momentum on this data was already examined in Task 16 (real_world_backtest), and trend-following "
                           "is widely published, so the reserved final decade is not a pristine holdout. The only clean "
                           "out-of-sample test is forward paper trading (stage 3)."),
    "results": families,
    "acceptance": {f"{name}_go_to_paper": result["go_to_paper"] for name, result in families.items()},
}
path = write("strategy_lab", payload, started, finished)
for name, result in families.items():
    print(name, "go" if result["go_to_paper"] else "no-go", result["gates"])
    print("  Sharpe %.2f vs bench %.2f | IR %.2f  DSR(active) %.3f  NW t(active) %.2f | WF %.2f vs %.2f | holdout %.2f vs %.2f | beats bench %.0f%% of variants | MDD %.1f%% vs %.1f%%" % (
        result["excess_sharpe"], result["benchmark_excess_sharpe"], result["information_ratio"], result["deflated"]["dsr"], result["newey_west_active"]["t"],
        result["walk_forward"]["sharpe"], result["walk_forward"]["benchmark_sharpe"], result["holdout"]["sharpe"], result["holdout"]["benchmark_sharpe"],
        100 * result["spec_curve"]["beats_benchmark_share"], 100 * result["summary"]["max_drawdown"], 100 * result["benchmark_summary"]["max_drawdown"]))
    print("  P(Sharpe beats benchmark) %.2f, difference CI95 %s" % (result["sharpe_vs_benchmark"]["p_better"], [round(x, 2) for x in result["sharpe_vs_benchmark"]["ci95"]]))
print(path)
