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
    "acceptance": {
        "inventory_strategy_lowers_profit_std_every_gamma": all(
            next(r for r in reproduction if r["gamma"] == g and r["strategy"] == "inventory")["ours"]["profit_std"] <
            next(r for r in reproduction if r["gamma"] == g and r["strategy"] == "symmetric")["ours"]["profit_std"] for g in PAPER),
        "gamma_0.1_and_0.01_profits_within_3pct": all(abs(v) < .03 for k, v in gaps.items() if not k.startswith("0.5/")),
        "gamma_0.5_inventory_reproduced": abs(gaps["0.5/inventory"]) < .03,
        "frictions_reduce_inventory_strategy_profit": ablation[-1]["inventory"]["profit_mean"] < ablation[0]["inventory"]["profit_mean"],
    },
    "interpretation": "Stylised Poisson-fill model; useful for comparing quoting rules under stated frictions, not for forecasting venue P&L.",
}
path = write("market_making", payload, started, finished)
print(path.read_text())
