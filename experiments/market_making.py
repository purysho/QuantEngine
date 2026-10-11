"""Avellaneda–Stoikov reproduction and friction ablation. Synthetic only."""
import time

from _common import write
from workers import quant_lob as lob

PAPER = {  # Avellaneda & Stoikov (2008), Tables 1–3: spread, profit, std(profit), mean q, std q.
    .1: {"inventory": (1.29, 62.94, 5.89, .08, 2.80), "symmetric": (1.29, 67.21, 13.43, .01, 8.66)},
    .01: {"inventory": (1.33, 66.78, 8.76, -.02, 4.70), "symmetric": (1.33, 67.36, 13.40, -.31, 8.65)},
    .5: {"inventory": (1.15, 33.92, 4.72, -.02, 1.88), "symmetric": (1.15, 66.20, 14.53, .25, 9.06)},
}
started = time.perf_counter()
reproduction = []
for gamma, rows in PAPER.items():
    result = lob.compare({"gamma": gamma, "paths": 20_000, "seed": 11, "spread_time_term": False})
    for strategy, paper in rows.items():
        r = result[strategy]
        reproduction.append({"gamma": gamma, "strategy": strategy,
                             "paper": dict(zip(("spread", "profit", "profit_std", "q_mean", "q_std"), paper)),
                             "ours": {"spread": r["initial_spread"], "profit": r["profit_mean"], "profit_se": r["profit_standard_error"],
                                      "profit_std": r["profit_std"], "q_mean": r["final_inventory_mean"], "q_std": r["final_inventory_std"]},
                             "profit_relative_gap": r["profit_mean"] / paper[1] - 1})

# Localise the gamma = 0.5 discrepancy: which spread time-term coefficient c reproduces each row?
# The symmetric benchmark is quoted with the constant spread (c = 0), as the paper states.
sweep = []
for c in (0.0, .25, .5, .75, 1.0):
    row = {"coefficient": c}
    for gamma in PAPER:
        r = lob.simulate({"gamma": gamma, "paths": 20_000, "seed": 11, "strategy": "inventory",
                          "spread_time_term": c > 0, "spread_time_coefficient": c or 1.0})
        row[str(gamma)] = r["profit_mean"]
    sweep.append(row)
target = PAPER[.5]["inventory"][1]
xs, ys = [r["coefficient"] for r in sweep], [r["0.5"] for r in sweep]
implied = next((xs[i] + (target - ys[i]) * (xs[i + 1] - xs[i]) / (ys[i + 1] - ys[i])
                for i in range(len(xs) - 1) if min(ys[i], ys[i + 1]) <= target <= max(ys[i], ys[i + 1])), None)

base = {"mode": "realistic", "paths": 5000, "seed": 21, "gamma": .1, "spread_time_term": True}
steps = [("clean realistic mode", {}),
         ("+ queue ahead (mean 3 units)", {"queue_depth": 3.0}),
         ("+ random order sizes (mean 2) / quote size 2", {"mean_order_size": 2.0, "quote_size": 2}),
         ("+ 3-step quote latency", {"latency_steps": 3}),
         ("+ 0.05 tick", {"tick": .05}),
         ("+ adverse move 0.05 after fills", {"adverse_move": .05}),
         ("+ maker 0.5 bp, taker 2 bp", {"maker_fee_bps": .5, "taker_fee_bps": 2.0}),
         ("+ inventory limit 10", {"inventory_limit": 10})]
ablation, current = [], dict(base)
for label, change in steps:
    current.update(change)
    result = lob.compare(current)
    ablation.append({"step": label, **{s: {k: result[s][k] for k in ("profit_mean", "profit_std", "final_inventory_std",
                                                                     "fills_mean", "fees_mean", "max_abs_inventory_mean")}
                                         for s in ("inventory", "symmetric")}})
finished = time.perf_counter()
gaps = {f'{r["gamma"]}/{r["strategy"]}': r["profit_relative_gap"] for r in reproduction}
payload = {
    "purpose": "Reproduce Avellaneda–Stoikov (2008) and measure how execution frictions change market-making P&L.",
    "paper_settings": {"mid": 100, "horizon": 1, "sigma": 2, "dt": .005, "k": 1.5, "A": 140, "paper_paths": 1000,
                       "our_paths": 20_000, "spread_time_term": False,
                       "note": "Published table spreads equal (2/gamma) ln(1 + gamma/k); the time term is omitted to match them."},
    "reproduction": reproduction,
    "friction_ablation": {"base": base, "rows": ablation},
    "gamma_0.5_diagnosis": {
        "spread_time_coefficient_sweep_inventory_profit": sweep,
        "implied_coefficient_for_published_33.92": implied,
        "finding": "Rows gamma=0.1 and 0.01 are insensitive to the spread convention; only gamma=0.5 discriminates. "
                   "The published 33.92 implies an effective time-term coefficient near the value above, matching neither the "
                   "paper's stated formula (c=1) nor its printed constant spread (c=0). The table is not reproducible from the "
                   "stated method; it is reported, not fitted.",
        "paper_procedure_source": "Avellaneda & Stoikov, section 3.3, people.orie.cornell.edu/sfs33/LimitOrderBook.pdf"},
    "acceptance": {
        "inventory_strategy_lowers_profit_std_every_gamma": all(
            next(r for r in reproduction if r["gamma"] == g and r["strategy"] == "inventory")["ours"]["profit_std"] <
            next(r for r in reproduction if r["gamma"] == g and r["strategy"] == "symmetric")["ours"]["profit_std"] for g in PAPER),
        "gamma_0.1_and_0.01_profits_within_3pct": all(abs(v) < .03 for k, v in gaps.items() if not k.startswith("0.5/")),
        "gamma_0.5_inventory_reproduced_by_stated_method": abs(gaps["0.5/inventory"]) < .03,
        "gamma_0.5_discrepancy_localised": implied is not None and all(
            abs(sweep[-1][g] - sweep[0][g]) < 2 for g in ("0.1", "0.01")),
        "frictions_reduce_inventory_strategy_profit": ablation[-1]["inventory"]["profit_mean"] < ablation[0]["inventory"]["profit_mean"],
    },
    "interpretation": "Stylised Poisson-fill model; useful for comparing quoting rules under stated frictions, not for forecasting venue P&L.",
}
path = write("market_making", payload, started, finished)
print(path.read_text())
