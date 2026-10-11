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

**Did not work / limits:** The three books (*Crisis Engineering*, *The Infinity Machine*, *AI for Good*) are not present as full texts in the repository or attachments. Nothing here summarises their contents; see `docs/research/RESEARCH_INDEX.md` for how they are treated. (Correction: an earlier draft of this entry said publisher descriptions were recorded in `docs/research/`; they were not.)

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

---

## Task 3 — Chronological ridge alpha experiment

**Did** (`workers/quant_validation.py`)
- `chronological_ridge` takes explicit information clocks. `feature_available[i] ≤ i` (otherwise rejected as a leaked feature before any fitting) and `label_end[i] > i` (otherwise rejected as an incomplete label).
- Purged training: every fit uses only rows whose labels completed **strictly before** the evaluation start, as in López de Prado. Overlapping multi-step labels are handled.
- Features are standardised on each training set only. The ridge intercept (target mean) is not penalised.
- The penalty is chosen on inner chronological blocks before the final holdout. The holdout is scored once with a frozen model.
- Every candidate and its per-block predictions are recorded in the ledger.
- Scores: MSE; zero forecast (cash) and training-mean baselines; Campbell–Thompson out-of-sample R² against the mean; hit rate; sign-position mean.

**Tests (7):** known linear coefficients recovered within 0.12; a leaked feature is rejected with its row named; bad labels, ragged arrays, NaNs and float clocks are rejected; purging under 5-step overlap (training rows = s − 5); holdout perturbation by 1000× leaves selection, ledger and fitted model identical; future perturbation leaves earlier block predictions unchanged; all candidates are logged.

**Evidence:** `experiments/first_alpha.py` writes `experiments/results/first_alpha.json` (200 seeds × 3 scenarios, 1,000 rows, about 3.4 s).
| Scenario | Holdout OOS R² vs mean (median) | Beats mean | Notes |
| --- | --- | --- | --- |
| Null | −0.0004 (p95 0.0066) | 44.5% | Selects maximum shrinkage (α = 1000) in 197/200 seeds |
| Weak signal (true R² ≈ 2.2%) | 0.0167 | 85% | Median exceeds the null p95 |
| Overlapping 5-step labels | 0.0097 | 78.5% | Purged |
| Leaked label as feature | **Rejected** | — | With a falsified clock, the OOS R² would have been 0.99999998 |

**Worked:** All four acceptance gates passed.

**Did not work / caveats:** Synthetic Gaussian data only, so this is mechanism validation and not market alpha. There are no nonlinear models yet (trees or gradient boosting would be the next candidates, with the same clock protocol). There is no embargo after the test block, which is unnecessary here because we only ever train on the past.

**Next:** Pairs trading with cointegration (from the deferred list), then desktop integration.

---

## Task 4 — Pairs trading with cointegration (previously deferred)

**Did** (`workers/quant_pairs.py`, no new runtime dependency)
- ADF with Schwert maximum lag and AIC/BIC lag choice on a common sample, refitted at the chosen lag.
- MacKinnon (2010) finite-sample critical values and MacKinnon (1994) approximate p-values for N = 1–3 series.
- Engle–Granger two-step test: OLS with constant, then residual ADF with no constant and N = 2 critical values. Returns the hedge ratio and the AR(1) half-life of mean reversion. Collinear series are rejected.
- `select_pairs`: both legs must look I(1) (level not rejected, difference rejected). All ordered pairs are tested, with Holm–Bonferroni family-wise error control.
- `pairs_backtest`: hedge ratio, spread mean and spread volatility are fitted on the formation window only. The z-score at close *t* trades at close *t+1*. Legs are held in shares (no implicit daily rebalancing). Costs apply to traded notional, a daily borrow fee applies to short notional, there is a stop-loss with re-entry blocking, and positions are force-liquidated at the end with costs.

**Cross-check:** Against statsmodels 0.14 in a scratch venv (not a project dependency), 60 seeds give identical AIC lags, statistics within 2.5e-13, p-values within 7e-14, and identical critical values at T = 50, 250, 1,000 and ∞.

**Tests (10):** published MacKinnon values, the response-surface formula, ADF on a walk vs its differences, EG power and hedge ratio, the collinear/short guard, Holm step-down, selection of a planted pair from noise, formation-only prefix invariance, no trade at the signal close, and costs/borrow/liquidation.

**Evidence:** `experiments/pairs_cointegration.py` writes `experiments/results/pairs_cointegration.json` (about 12 s).
- Size at nominal 5% on 1,000 independent random walks (n = 250): **AIC lags 7.1% (fails the 3σ binomial band)**, BIC 6.3% (passes), fixed lag 0 6.1%, single-series ADF 5.9%.
- Power at 5% by spread AR coefficient: 0.8 → 100%, 0.9 → 85%, 0.95 → 31%, 0.98 → 8%. Slow mean reversion is hard to detect in one year.
- Trading after passing the formation test, with 5 bps costs and 50 bps/yr borrow: true pairs (176 selected) had a median return of **+8.4%** and 97% were profitable. Spurious pairs (102 of 2,000 independent pairs passed by chance) had a median of **−0.75%**, 43% profitable, and a worst drawdown of −15.6%.

**Did not work / caveats**
- AIC lag search over-rejects. This was found by the experiment, not assumed. I switched pair screening to BIC; raw `engle_granger` keeps AIC so it stays comparable with statsmodels.
- The hedge ratio is static. There is no Kalman or rolling re-estimation, and no Johansen test for more than two legs.
- Close-price fills only. The synthetic results show the mechanism, not real-market profitability.

**Next:** LOB market-making simulator, then desktop integration and CI.

---

## Task 5 — Limit-order-book market-making simulator (previously deferred)

**Did** (`workers/quant_lob.py`)
- Avellaneda–Stoikov (2008): reservation price `s − qγσ²(T−t)` and optimal spread `γσ²(T−t) + (2/γ)ln(1+γ/k)`. Fills are Poisson with intensity `A·e^{−kδ}`. Inventory-aware and symmetric strategies are compared on identical random numbers, with a no-quote baseline of 0.
- Event order: quotes are set, then the mid moves, then orders arrive against the **new** mid. Fills therefore carry the latest move, which is the conservative choice.
- `realistic` mode adds FIFO queue position (exponential queue ahead at each new price; an unchanged price keeps priority), negative-binomial market-order sizes with partial fills, quote latency in steps (quotes use a stale mid), tick rounding, maker/taker fees, adverse post-fill mid moves, a hard inventory limit, and a costed terminal exit (cross half the spread plus taker fee).

**Tests (6):** closed-form quotes; inventory strategy has lower inventory and profit std than symmetric for γ ∈ {0.01, 0.1, 0.5}; reproduction of the paper's γ = 0.1 row (2% tolerance including the paper's own sampling error); reproducibility and validation; the inventory limit is never breached; frictions lower profit and fills.

**Evidence:** `experiments/market_making.py` writes `experiments/results/market_making.json` (20,000 paths per row, about 6 s).
| γ / strategy | Paper profit | Ours | Gap | Paper q std | Ours |
| --- | --- | --- | --- | --- | --- |
| 0.1 inventory | 62.94 | 62.15 | −1.3% | 2.80 | 2.96 |
| 0.1 symmetric | 67.21 | 67.08 | −0.2% | 8.66 | 8.98 |
| 0.01 inventory | 66.78 | 66.88 | +0.2% | 4.70 | 5.29 |
| 0.01 symmetric | 67.36 | 67.21 | −0.2% | 8.65 | 8.90 |
| **0.5 inventory** | **33.92** | **20.78** | **−39%** | 1.88 | 1.97 |
| 0.5 symmetric | 66.20 | 66.04 | −0.2% | 9.06 | 9.30 |

Friction ablation (γ = 0.1, inventory strategy, mean profit / fills): clean 54.1 / 87; adding queue-ahead (mean 3) gives 9.3 / 27; random sizes with quote size 2 gives 28.7; latency 26.4; tick 26.7; adverse selection 25.4; fees 25.1; inventory limit 25.1. The symmetric strategy's profit std rises from 13.1 to 17.1 under adverse selection, while the inventory strategy stays at about 6.7.

**Did not work / caveats**
- **The paper's γ = 0.5 inventory row is not reproduced.** I tried four variants (spread with/without the time term × mid moving before/after fills). None gives 33.92: they give about 21 or about 47. The paper's discretisation is ambiguous. I recorded this as a failed acceptance gate instead of tuning parameters to fit it.
- The printed table spreads equal `(2/γ)ln(1+γ/k)`, so the reproduction omits the time term. The default (`spread_time_term=True`) follows the paper's formula.
- This is a reduced-form book with no historical order-book data, no hidden liquidity and no venue rules.

**Next:** Desktop integration (Options page, worker command), CI, and a research index.

---

## Task 6 — Desktop integration (Options page, Student-t risk, version 0.2.0)

Scope note from the user: focus only on the **Quant** half (not the AI desktop or OS work). Target is the Windows 11 Home laptop (Core 5 210H, 16 GB RAM, integrated Intel graphics, data on `D:`). CPU-only, at most two BLAS threads, one queued worker.

**Did**
- Worker command `options` returns an options report without writing price snapshots or research history.
- `Engine.calculateOptions` uses the same single worker slot. It rejects while busy, while settings are saving, or during pause. A waiting continuous cycle is postponed and then rescheduled. Pause kills the worker and reports "Option calculation cancelled". Shutdown drains it.
- Main process: a `calculate-options` IPC command with a shape check; Python does the authoritative range validation. Option state is sent only when it changes.
- Preload: `window.quant.calculateOptions`.
- Renderer: a new **Options** page with contract inputs (percent inputs converted to decimals) and cross-checked prices (analytic / CRR European / CRR American / Monte Carlo ± SE / counterpart and parity gap / implied volatility). It shows Greeks with explicit units, and implied moves with the precise "VIX/16" explanation. All text is HTML-escaped.
- The risk comparison now shows Gaussian / block bootstrap / Student-t at 95% and 99%, plus t degrees of freedom and the Hill index. Schema 1 reports still render (missing columns are hidden).
- The native `--self-test` now also prices Hull's reference contract through the sandboxed preload bridge.
- Tests use `QUANT_PYTHON`, otherwise `python` on Windows and `python3` elsewhere (Python tests use `sys.executable`).
- Version bumped to 0.2.0 (package, sidebar, ECB User-Agent).

**Tests added:** 4 desktop (no overlap with research, pause cancels and releases the slot, waiting cycle resumes, real worker prices without history); 1 renderer (real worker reports render the Options page, Student-t and 99% rows; provenance HTML is escaped); 2 Python worker (options command leaves no history and rejects unknown fields; schema-2 reports include Student-t and one-close timing).

**Results (Linux host, Python 3.13.16 / NumPy 2.3.5 / SciPy 1.17.0):** 67/67 Python, 17/17 TypeScript, `tsc` clean, build clean. The native Electron self-test under Xvfb printed `QUANT_SELF_TEST_OK` with `option: 4.759422392871532` and a completed 5,000-path report.

**Did not work / caveats:** A visual review of the new page in a real window has not been done. The Electron self-test ran on Linux under Xvfb, **not on Windows**. Pairs, market-making and alpha experiments are available as Python modules and scripts but do not have desktop pages yet.

**Next:** CI (Linux and Windows), a research index, and a screenshot review.

---

## Task 7 — CI, packaging and visual review

**Did**
- `.github/workflows/ci.yml` runs on Linux and Windows: typecheck, numerical tests, desktop tests, build, all four experiments (printing their acceptance gates), and the native Electron self-test under Xvfb on Linux. A separate `windows-package` job prepares the SHA-256 verified embedded Python 3.13.16/NumPy/SciPy, runs the numerical tests **on that embedded runtime**, builds `QuantEngine.exe`, runs `--self-test` on the packaged executable, and uploads the portable folder as an artifact.
- `packaging/test-python.mjs` is a cross-platform test launcher (`QUANT_PYTHON`, otherwise `python` on Windows and `python3` elsewhere). It uses `-t .` because embedded `._pth` runtimes don't put the working directory on `sys.path`; `tests/__init__.py` was added for that.
- **Packaging bug fixed:** `.cache/` (runtime wheels and, here, the Electron zip) was being copied into `resources/app`; it is now excluded, which took the build from 751 MB to 543 MB. `.github/` is excluded too.
- `ELECTRON_ZIP_DIR` lets offline or proxied builds use a checksum-verified Electron zip. Here the zip's SHA-256 `eee30dc8…665c` matched Electron's published `SHASUMS256.txt`.
- Visual review in headless Chromium with a stub bridge and real worker output: the Options and Monitor pages render with no page errors. Fixed two labels: "95% / 99% tail loss", and Call/Put instead of "European call", since American prices are shown too.

**Results:** The Windows x64 portable folder was cross-built on Linux (543 MB: Electron EXE 235 MB, embedded runtime 174 MB). Locally: 67/67 Python, 17/17 TypeScript, typecheck and build clean, Linux native self-test OK.

**Did not work / caveats**
- Electron's own download inside `@electron/packager` failed in this container's network path (an undici assertion), hence the `ELECTRON_ZIP_DIR` route. CI on GitHub should download normally.
- The packaged `QuantEngine.exe` was **not executed** here (no Windows). The CI `windows-package` job is the first real execution, and its result is recorded below once observed.
- An honest observation, not a bug: with next-close execution, the sample momentum strategy on the synthetic dataset is −13.7% net (Sharpe −0.46), worse than equal weight. 0.1 traded at the signal close.

**Next:** Observe CI, write the research index (resource coverage), and update the README/build plan.

---

## Task 8 — VaR exception backtests (research step 1 from the index)

**Did** (`workers/quant_varbacktest.py`)
- Kupiec proportion-of-failures, Christoffersen independence (first-order Markov) and conditional-coverage likelihood-ratio tests with χ² p-values.
- `rolling_var`: one-day historical / Gaussian / Student-t VaR, where each forecast uses only the previous `window` returns. The Student-t MLE is refitted every `refit_every` days, with moment-matched location/scale in between; this cut test time from 75 s to 3.4 s without using future data.

**Tests (5):** a hand-derived Kupiec LR (5 exceptions in 250 at 1% gives 1.9569; exactly-on-target gives 0); clustered exceptions fail independence while passing Kupiec; a shock on day 300 cannot change forecasts for days ≤ 300; Gaussian fails and Student-t passes on t(3) data; validation.

**Evidence:** `experiments/var_backtest.py` writes `experiments/results/var_backtest.json` (20 seeds × 3,000 days, window 500, about 206 s).
| Series | p | Method | Exceptions / expected | Kupiec rejects | Independence rejects |
| --- | --- | --- | --- | --- | --- |
| iid t(5) | 1% | Gaussian | **1.58** | **70%** | 5% |
| iid t(5) | 1% | Student-t | 1.08 | 0% | 5% |
| iid t(5) | 1% | Historical | 1.04 | 0% | 5% |
| GARCH(1,1)-t(5) | 5% | Historical | 1.05 | 5% | **55%** |
| GARCH(1,1)-t(5) | 1% | Gaussian | 1.87 | 100% | 35% |
| GARCH(1,1)-t(5) | 5% | Student-t | 1.31 | 85% | 65% |

**What worked / what didn't**
- The first single-seed run was inconclusive: Gaussian 99% was *not* rejected (p = 0.058) despite 35 vs 25 exceptions, and the independence test flagged an iid series (p = 0.014). I replaced it with rejection rates over 20 seeds instead of reporting one lucky or unlucky draw.
- Under volatility clustering, no static-window model is acceptable: exceptions bunch together. The fix is a conditional volatility model (GARCH-t), which is the next risk step.
- The runtime is long because of Student-t refits; it is acceptable for CI but not for an interactive page.

**Next:** Live 3D volatility-surface visual (user request), then GARCH-t.

---

## Task 9 — Live 3D volatility surfaces (user request: "look like 3D volatility surfaces, moving because it's live")

**Did**
- `realised_vol_surface` (Python): annualised trailing realised volatility of the optimised portfolio by lookback (5–250 days) × date. It uses cumulative sums, is subsampled to at most 240 dates, and is causal: value *(w, t)* uses only the *w* returns ending at close *t*. It is added to every new report as `volatility_surface`.
- `ssvi_surface` (Python): an SSVI power-law implied-volatility surface (Gatheral & Jacquier 2014) around the contract's volatility, with user skew ρ and curvature η. It reports whether the sufficient no-arbitrage conditions `γ ≤ ½, η(1+|ρ|) ≤ 2` hold. It is labelled as a **model** surface; no market quotes are implied.
- Renderer: a self-contained 3D surface engine on canvas 2D (no WebGL, suitable for integrated graphics) with:
  - depth-sorted lit quads, a wireframe and dotted back walls;
  - axes auto-placed on the leftmost corner, with camera auto-fit over the rotation range in use;
  - slow auto-rotation, drag to rotate (double-click resumes) and hover readouts of exact values;
  - an animation throttled to about 30 fps that stops when the page or tab is hidden or not selected, and is static under `prefers-reduced-motion`.
- **Monitor → "Vol surface 3D" tab:** the surface scrolls through the dataset's history ("Replaying history · through <date>"), holds on the latest data, then replays. Each new research cycle swaps in the new data.
- **Options page:** an implied-volatility surface panel with ρ/η inputs. It morphs smoothly (700 ms ease) whenever a new calculation arrives.
- Colour: the dataviz guidance rules out rainbow (jet) maps, so the surface uses a sequential navy → teal → mint → amber ramp with lightness increasing with value. Height also encodes value, and colour is normalised to the 2nd–98th percentile so a few spikes don't flatten it.

**Tests:** realised surface equals direct `std(ddof=1)·√252` to 1e-10 and is unchanged by future shocks; report surface is bounded. SSVI ATM equals the contract vol exactly; re-pricing the SSVI surface through Black–Scholes passes the independent butterfly/calendar checks; negative ρ gives put skew; out-of-bound parameters are flagged. Renderer: options surface, arbitrage note and 3D tab render without errors.

**Results:** 67+ Python tests, 17/17 TypeScript, Linux native self-test OK. Headless Chromium screenshots (`docs/screenshots/surface-*.png`) show no page errors.

**What didn't work at first:**
- The first render clipped the surface and put the z-axis in mid-air; a camera auto-fit over the active azimuth range fixed it.
- Short-dated SSVI wings dominated the colour range at T = 1/12; the default grid is now 0.1–2 years and ±0.5 log-moneyness.
- Monthly date ticks repeated; full dates with fewer ticks fixed it.
- The renderer unit-test stubs needed `parentElement`, so the chart wrapper now has its own id.

**Not done / caveats:** No market-quote import for a *market* implied surface yet; `volatility_surface()` already supports quotes, but there is no CSV/UI path. The surface visual has not been checked on the Windows laptop's integrated GPU; the canvas draw is about 1,000 quads per frame.

**Voice AI request (logged for the AI track, not built here):** `zachlatta/freeflow` (`20674709`, MIT) is a **macOS-only** Swift dictation app that sends audio to Groq's cloud API by default, so it does not run on the Windows 11 laptop. A Windows-local equivalent would combine CPU speech-to-text (e.g. whisper.cpp base/small), a small local LLM, and a permission-controlled action service with logs and undo, as discussed earlier. QuantEngine could expose read-only "ask the engine" endpoints (latest report, run options) for that assistant to call.
