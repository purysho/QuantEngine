# QuantEngine work log

One entry per task: what was done, what worked, what did not, and what comes next.
Every number quoted here comes from a command that was actually run in the recorded environment.
Environment for this session: Linux container, Python 3.13.16 with NumPy 2.3.5 and SciPy 1.17.0, Node 22. The Windows 11 laptop has **not** been tested in this session.

---

## Task 0 — Restore baseline and confirm GitHub state (2026-10-11)

**Did**
- Confirmed the restored 0.1.0 source is on `main` and `claude/lucid-bell-sitnae` at `5a59d84` in `purysho/QuantEngine`.
- Installed pinned `numpy==2.3.5`, `scipy==1.17.0` and `npm ci`.
- Re-ran the baseline: 18/18 Python tests, 12/12 TypeScript tests, `tsc --noEmit` clean.

**Worked:** Baseline reproduced exactly.

**Did not work / limits:** The three books (*Crisis Engineering*, *The Infinity Machine*, *AI for Good*) are not present as full texts in the repository or attachments. Nothing here claims to summarise their contents beyond publisher descriptions recorded in `docs/research/`.

**Next:** Execute the 0.2 plan in `docs/superpowers/plans/2026-10-11-research-release.md`.

---

## Task 1 — Causal timing and tail accounting

**Did**
- `empirical_tail(samples, p)`: VaR is minus the lower empirical inverse-CDF quantile. ES is minus the mean of exactly `p` probability mass, including the fractional boundary observation and ties. Floating-point `n·p`, such as `0.05·100 = 5.000000000000001`, is snapped before `ceil`/`floor`.
- Gaussian and bootstrap risk now use it at 95% and 99%, and record `quantile_method`.
- `walk_forward`: a signal formed after close *s* executes at close *s+1*. The first held return runs from *s+1* to *s+2*. Each decision records `signal_price_index`, `execution_price_index` and `first_return_interval`. Costs are paid at the execution close. Equal-weight uses the same start and cost convention. Curve dates start at the execution close.
- `student_t_risk`: maximum-likelihood Student-t daily returns, simulated over the horizon (a sum of t variables is not itself t, so there is no √h scaling). It adds a closed-form one-day t VaR/ES, sample skew and excess kurtosis.
- `hill_tail_index`: Pareto tail index of daily losses, reported for several *k* values because the estimate is sensitive to *k*.
- Reports now carry `schema_version: 2` and `engine_version: "0.2.0"`. Version 1 report keys are unchanged, so old reports still load.

**Tests added:** fractional-tail fixture `[−10, −1, 0, 2]` at 37.5% gives ES = 7 and VaR = 1; tied tails; the 5%-of-100 rounding case; invalid probabilities; a toy path proving no trade at the signal close; cost timing; curve alignment; Student-t heavier than Gaussian on t(3) data; Hill recovery of α = 3 within ±0.3.

**Worked:** 25/25 Python tests. The existing prefix-invariance test (future price changes leave earlier returns unchanged) still passes under the delayed execution.

**Did not work / caveats:** Student-t fitting is iid with no volatility clustering (no GARCH). The Hill estimate on about 500 daily observations is noisy, so treat it as a diagnostic.

**Next:** Options mathematics (Task 2).

---

## Task 2 — Options mathematics and volatility surface

**Did** (`workers/quant_options.py`)
- Black–Scholes–Merton with a continuous dividend yield. Greeks are delta, gamma, vega (per 1.00 and per point), theta (per year and per calendar day), rho (per 1.00 and per 1%), vanna and volga. Expired and zero-volatility contracts use the discounted deterministic forward payoff with the correct theta.
- CRR binomial trees, European and American, vectorised in NumPy and capped at 5,000 steps. A tree whose risk-neutral probability falls outside (0, 1) is rejected rather than silently mispriced.
- Risk-neutral Monte Carlo with antithetic pairs. Standard error is computed from independent pair means, because paths within a pair are correlated.
- Implied volatility by Brent root-finding. Quotes at or outside the no-arbitrage bounds are rejected with the bound in the message.
- `implied_move`: the "VIX/16" rule, made precise. √252 ≈ 15.87, so VIX/16 is a one-sigma daily move; the expected absolute move is only √(2/π) ≈ 0.80σ, and a move stays inside ±1σ only 68% of the time.
- `volatility_surface`: implied volatility per quote, puts converted to calls via parity, vertical and butterfly checks in strike, a calendar check in total variance at equal forward log-moneyness, and per-expiry raw SVI fits (Gatheral) including a Roger Lee wing check.
- `options_report`: one validated parameter object returns a cross-checked report (analytic, tree, Monte Carlo, parity gap, optional implied volatility).

**Evidence:** `experiments/options_reference.py` writes `experiments/results/options_reference.json`.
- Published references match: Hull call 4.7594 and put 0.8086 (published 4.76 and 0.81); Haug generalized-BSM put 4.0870; Merton (1973) put 2.4648; Hull American put 4.49 on a 5-step tree and ≈4.283 on 500 steps.
- CRR European error falls as O(1/N): −0.197 at 10 steps, −0.0040 at 500 and −0.0004 at 5,000.
- Monte Carlo standard error falls by about 3.13–3.21× per 10× paths (theory: √10 ≈ 3.16). Every estimate is within 3 standard errors of the analytic price.

**Tests:** 17 in `tests/test_quant_options.py`. They cover the references, parity across rates/dividends, every Greek against central finite differences, expiry and zero volatility, invalid input, tree convergence and American dominance, Monte Carlo reproducibility and error bound, an implied-volatility round trip from 5% to 250%, impossible quotes, the rule of 16, SVI recovery (RMSE < 1e-6), and calendar and butterfly detection.

**Did not work / caveats:** SVI slices are fitted independently, so the surface is not guaranteed arbitrage-free as a whole (no SSVI or joint fit). There are no discrete dividends and no live chain. American implied volatility is not inverted.

**Next:** Chronological ridge alpha experiment (Task 3).
