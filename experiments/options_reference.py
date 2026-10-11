"""Options reference prices, tree convergence and Monte Carlo error scaling."""
import math
import time

from _common import write
from workers import quant_options as opt

started = time.perf_counter()
references = [
    {"source": "Hull, S=42 K=40 r=10% sigma=20% T=0.5 call", "published": 4.76, "args": (42, 40, .5, .1, .2, 0, "call")},
    {"source": "Hull, same contract put", "published": .81, "args": (42, 40, .5, .1, .2, 0, "put")},
    {"source": "Haug generalized BSM put S=75 K=70 T=0.5 r=10% q=5% sigma=35%", "published": 4.0870, "args": (75, 70, .5, .1, .35, .05, "put")},
    {"source": "Haug Merton (1973) put S=100 K=95 T=0.5 r=10% q=5% sigma=20%", "published": 2.4648, "args": (100, 95, .5, .1, .2, .05, "put")},
]
for row in references:
    row["computed"] = opt.black_scholes(*row["args"])["price"]
    row["absolute_difference"] = abs(row["computed"] - row["published"])
    row["args"] = list(row["args"])

exact = opt.black_scholes(100, 100, 1, .05, .2)["price"]
tree = [{"steps": n, "price": (p := opt.crr_price(100, 100, 1, .05, .2, steps=n)), "error": p - exact}
        for n in (10, 50, 100, 250, 500, 1000, 2500, 5000)]
american = [{"steps": n, "price": opt.crr_price(50, 50, 5 / 12, .1, .4, kind="put", steps=n, american=True)}
            for n in (5, 30, 50, 100, 500, 2000)]
mc = []
for paths in (2_000, 20_000, 200_000, 2_000_000):
    value = opt.monte_carlo_price(100, 100, 1, .05, .2, paths=paths, seed=17)
    mc.append({"paths": paths, "price": value["price"], "standard_error": value["standard_error"],
               "error": value["price"] - exact,
               "error_in_standard_errors": (value["price"] - exact) / value["standard_error"]})
ratios = [mc[i]["standard_error"] / mc[i + 1]["standard_error"] for i in range(len(mc) - 1)]

finished = time.perf_counter()
path = write("options_reference", {
    "purpose": "Verify analytic prices against published examples; measure tree convergence and Monte Carlo sampling error.",
    "published_references": references,
    "european_tree_convergence": {"contract": "S=K=100, T=1, r=5%, sigma=20% call", "black_scholes": exact, "rows": tree},
    "american_put_tree": {"contract": "Hull S=K=50, r=10%, sigma=40%, T=5/12 put; published 5-step 4.49, converged ~4.28", "rows": american},
    "monte_carlo": {"rows": mc, "standard_error_ratio_per_10x_paths": ratios, "expected_ratio": math.sqrt(10)},
    "acceptance": {
        "references_within_rounding": all(r["absolute_difference"] <= (.005 if r["published"] in (4.76, .81) else 5e-5) for r in references),
        "tree_error_below_1e-3_at_5000_steps": abs(tree[-1]["error"]) < 1e-3,
        "mc_within_three_standard_errors": all(abs(r["error_in_standard_errors"]) < 3 for r in mc),
    },
}, started, finished)
print(path.read_text())
