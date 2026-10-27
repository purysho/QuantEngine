"""Stage 2 evidence for the pre-registered strategies on 100 years of US data (Ken French library).

Run: python experiments/strategy_lab.py [--offline]
Writes experiments/results/strategy_lab.json. Gates decide whether a strategy may move to paper trading.
"""
from __future__ import annotations

import argparse
import time

from _common import ROOT, write
from workers import quant_data as qd
from workers import quant_strategies as st

parser = argparse.ArgumentParser()
parser.add_argument("--offline", action="store_true")
args = parser.parse_args()
started = time.perf_counter()
cache = ROOT / ".cache" / "data"

raw = {}
for name, kind in (("F-F_Research_Data_Factors_daily", "french"), ("12_Industry_Portfolios_daily", "french"),
                   ("Portfolios_Formed_on_OP_Daily", "french"), ("DGS10", "fred"),
                   ("Portfolios_Formed_on_BE-ME_Daily", "french"), ("10_Portfolios_Prior_12_2_Daily", "french")):
    raw[name] = (qd.fetch(qd.FRENCH_URL.format(name=name), cache, f"french-{name}", offline=args.offline) if kind == "french"
                 else qd.fred_long(name, cache, offline=args.offline))
lab = st.run_lab(*(raw[n][0] for n in ("F-F_Research_Data_Factors_daily", "12_Industry_Portfolios_daily", "Portfolios_Formed_on_OP_Daily", "DGS10",
                                       "Portfolios_Formed_on_BE-ME_Daily", "10_Portfolios_Prior_12_2_Daily")))
families = lab["results"]

finished = time.perf_counter()
payload = {
    "registration": {**lab["registration"], "families": st.FAMILIES,
                     "gates_history": "Version 1 compared returns with cash; buy-and-hold passes that, so version 2 compares with the benchmark."},
    "data": {"source": "Kenneth R. French Data Library (market, risk-free rate, 12 industries, portfolios on operating profitability, "
                       "book-to-market and prior 12-2 month return) "
                       "and FRED DGS10 (10-year Treasury yield, converted to daily par-bond returns)",
             **lab["data"], "files": {n: raw[n][1]["sha256"] for n in raw}},
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
    print("  P(Sharpe beats benchmark) %.2f, difference CI95 %s | annual %.1f%% vs %.1f%% | at benchmark risk %.1f%% | max exposure %.2f" % (
        result["sharpe_vs_benchmark"]["p_better"], [round(x, 2) for x in result["sharpe_vs_benchmark"]["ci95"]],
        100 * result["summary"]["annual_return"], 100 * result["benchmark_summary"]["annual_return"], 100 * result["return_at_benchmark_risk"], result["max_exposure"]))
print(path)
