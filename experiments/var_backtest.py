"""Rolling VaR exception backtests on iid and volatility-clustered fat-tailed returns. Synthetic only."""
import math
import time

import numpy as np

from _common import array_hash, write
from workers.quant_varbacktest import METHODS, backtest_var, rolling_var_levels

N, WINDOW = 3000, 500


def garch_t(seed, n=N, omega=2e-6, alpha=.08, beta=.9, df=5):
    rng = np.random.default_rng(seed)
    z = rng.standard_t(df, n) / math.sqrt(df / (df - 2))  # Unit-variance t shocks.
    r, var = np.empty(n), omega / (1 - alpha - beta)
    for t in range(n):
        r[t] = math.sqrt(var) * z[t]
        var = omega + alpha * r[t] ** 2 + beta * var
    return r


SEEDS = 20
started = time.perf_counter()
makers = {"iid_student_t5": lambda seed: np.random.default_rng(seed).standard_t(5, N) * .01 / math.sqrt(5 / 3),
          "garch11_t5": lambda seed: garch_t(seed)}
rows, hashes = [], {}
for name, make in makers.items():
    stats_by = {}
    for seed in range(SEEDS):
        r = make(1000 + seed)
        if seed == 0:
            hashes[name] = array_hash(r)
        for method in METHODS:
            levels = rolling_var_levels(r, window=WINDOW, levels=(.05, .01), method=method, refit_every=50)
            for p in (.05, .01):
                result = backtest_var(r, window=WINDOW, p=p, method=method, forecasts=levels[p])
                acc = stats_by.setdefault((p, method), {"ratio": [], "kupiec": 0, "independence": 0})
                acc["ratio"].append(result["exceptions"] / result["expected_exceptions"])
                acc["kupiec"] += result["kupiec_p_value"] < .05
                acc["independence"] += result["independence_p_value"] < .05
    for (p, method), acc in stats_by.items():
        rows.append({"series": name, "p": p, "method": method, "seeds": SEEDS,
                     "mean_exception_ratio": float(np.mean(acc["ratio"])),
                     "kupiec_rejection_rate": acc["kupiec"] / SEEDS,
                     "independence_rejection_rate": acc["independence"] / SEEDS})
finished = time.perf_counter()
get = lambda s, p, m: next(r for r in rows if r["series"] == s and r["p"] == p and r["method"] == m)
payload = {
    "purpose": "Do rolling-window VaR models deliver the promised exception rate, and are exceptions independent?",
    "data": {"days": N, "window": WINDOW, "seeds": SEEDS, "first_seed_hashes": hashes,
             "garch": "omega 2e-6, alpha .08, beta .90, unit-variance t(5) shocks", "student_t_refit_every": 50},
    "results": rows,
    "acceptance": {
        "gaussian_99_underestimates_on_fat_tails": get("iid_student_t5", .01, "gaussian")["mean_exception_ratio"] > 1.2,
        "student_t_99_calibrated_on_iid_t": abs(get("iid_student_t5", .01, "student_t")["mean_exception_ratio"] - 1) < .15,
        "garch_t_calibrated_under_clustering_99": abs(get("garch11_t5", .01, "garch_t")["mean_exception_ratio"] - 1) < .2,
        "garch_t_fewer_independence_rejections_than_static_95": get("garch11_t5", .05, "garch_t")["independence_rejection_rate"]
                                                               < min(get("garch11_t5", .05, m)["independence_rejection_rate"] for m in ("historical", "gaussian", "student_t")),
        "clustering_raises_independence_rejections": get("garch11_t5", .05, "historical")["independence_rejection_rate"]
                                                     > get("iid_student_t5", .05, "historical")["independence_rejection_rate"],
    },
    "interpretation": "Rejection rates over seeds show power and size; one seed is not evidence. Static windows react slowly to volatility clustering; the conditional GARCH(1,1)-t forecast is the remedy tested here.",
}
path = write("var_backtest", payload, started, finished)
print(path.read_text())
