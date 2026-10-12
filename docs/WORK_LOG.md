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

---

## CI observations (GitHub Actions, recorded as observed)

- Run 1 (`7ee2da3`): Linux ✅ all steps, including the Xvfb native self-test. **Windows ❌**: 66/67 numerical tests. `test_valid_import_copies_content_and_preserves_its_source` compared the runner's 8.3 short temp path (`RUNNER~1`) with the store's resolved long path (`runneradmin`). The store's behaviour (a canonical path) is correct; the 0.1 test was fixed to compare against `source.resolve()`.
- Run 2 (`7edf57c`): the same Windows failure (pushed before the fix).
- Run 3 (`9e73159`): ✅ **all three jobs.** The Windows package job prepared the SHA-256-verified embedded runtime, passed all numerical tests **on that embedded Python 3.13.16**, built `QuantEngine.exe`, and the packaged executable printed `QUANT_SELF_TEST_OK` (option 4.759422392871532, a completed report, runtime 3.13.16 / 2.3.5 / 1.17.0). The artifact `QuantEngine-win-x64` (228.8 MB zip) was uploaded.
- This is a Windows Server runner, **not** the user's Windows 11 Home laptop; the device check in `EVALUATION.md` is still pending.

---

## Task 10 — Fix "static VaR windows fail under volatility clustering" with GARCH(1,1)-t

**Why it failed before:** the Task 8 VaR models all used a fixed trailing window. When volatility clusters, a 500-day window reacts far too slowly, so exceptions bunch together right after a volatility jump (independence rejected in 20–65% of seeds).

**Did**
- `fit_garch_t`: maximum-likelihood GARCH(1,1) with unit-variance Student-t shocks. Parameters are transformed so every search point is valid (ω > 0, α, β ≥ 0, α + β < 1, ν > 2.1). The variance recursion is vectorised with `scipy.signal.lfilter`, and the fit runs on standardised data for conditioning.
- In `rolling_var_levels`, parameters are refitted every 50 days on the trailing window, and the conditional variance is filtered **daily** through *t − 1*. One fit serves both the 95% and 99% levels.
- Tests (3 new): parameter recovery (α ≈ 0.08, β ≈ 0.90, ν ≈ 5); causality, where a shock on day 700 leaves earlier forecasts untouched and raises the next day's VaR by more than 1.5×; extreme inputs do not overflow.

**Result** (`var_backtest.json`, 20 seeds, GARCH(1,1)-t(5) data):
| Method | 95% exceptions / expected | Independence rejects | 99% exceptions / expected | Kupiec rejects |
| --- | --- | --- | --- | --- |
| Historical window | 1.05 | 55% | 1.19 | 5% |
| Student-t window | 1.18 | 55% | 1.44 | 35% |
| **GARCH-t** | **1.01** | **5%** (nominal) | **1.07** | **0%** |
On iid data, GARCH-t is as good as the static models (1.01 / 1.04), so it costs nothing when there is no clustering.

**Lessons from things that went wrong in this task**
1. **Overflow:** `math.exp(-x)` in a logistic transform overflowed during a bad line search. I switched to `scipy.special.expit` and clipping. Any optimiser transform must be total (defined everywhere).
2. **Thread oversubscription:** the experiment used 17 CPU-minutes for 7 wall-minutes. Experiments now pin BLAS to one thread, matching the app's own thread policy.
3. **Warm-start trap:** warm-starting GARCH from the previous refit was 6.5× faster but landed at a worse optimum in **29%** of refits (log-likelihood gap up to 43.5), which visibly worsened the backtest (independence rejections 5% → 15%). Fix: warm start **plus** one cold start, keeping the better likelihood. The gap to the full multi-start became 2e-5.
4. **The opposite case:** for the Student-t fit, a warm start was never worse and beat SciPy's default start by up to 15.7 log-likelihood in 4.8% of refits, so it stays. Speed-ups must be checked against fit quality, not just runtime.
5. **CI:** superseded runs queued behind each other for about 8 minutes, so the workflow now has a `concurrency` group that cancels in-progress runs on the same branch. The experiment went from 411 s to 110 s.

---

## Task 11 — Diagnose the unreproduced Avellaneda–Stoikov γ = 0.5 row

**Method:** I read the paper's own procedure (§3.3, Cornell-hosted PDF): quotes are set at *t*, the state updates at *t + dt*, a fill happens with probability λ(δ)·dt, and the mid moves ±σ√dt. The symmetric strategy "uses the same spread … centered around the mid-price", described as "$1.29 (corresponding to the optimal agent with γ = 0.1)", which is the constant term (2/γ)·ln(1 + γ/k) only.

**Hypotheses tested** (all with 4,000–20,000 paths):
1. *Clipping negative quote distances* (a quote across the mid): the paper uses raw λ(δ)·dt. Effect < 1 profit unit. **Rejected.**
2. *Event order* (mid moves before or after fills): ±1.5. **Not the cause.**
3. *Spread time-term coefficient c* in c·γσ²(T−t): the γ = 0.1 and γ = 0.01 inventory rows change by less than 1.3 across c ∈ [0, 1], so **they cannot tell conventions apart**. Only γ = 0.5 is sensitive: 20.8 (c = 0) → 46.8 (c = 1). The published 33.92 implies **c ≈ 0.32**.

**Finding:** the paper's γ = 0.5 inventory row matches neither its stated formula (c = 1) nor its printed spread column (c = 0). The table is internally inconsistent with the stated method. The symmetric γ = 0.5 row reproduces (66.0 vs 66.2) once the symmetric benchmark uses the constant spread, which confirms the rest of the set-up.

**Change:** `market_making.json` now carries the full coefficient sweep and the implied c. The gate `gamma_0.5_inventory_reproduced_by_stated_method` stays **false** (honest), and a new gate `gamma_0.5_discrepancy_localised` is **true**. `spread_time_coefficient` exists for sensitivity analysis only; I did **not** fit c = 0.32, because tuning a model to one published number is curve-fitting.

**Lesson for the system:** before declaring a reproduction failure, sweep each ambiguous convention and check which published rows can discriminate between them. Two of the three rows were never evidence for the formula.

---

## Task 12 — Voice and assistant: a Windows FreeFlow equivalent plus our own engine assistant

**Why FreeFlow failed:** `zachlatta/freeflow` is a macOS-only Swift app that sends audio to Groq's cloud API by default, so it cannot run on the Windows laptop.

**Windows equivalents verified** (repositories inspected at their current commits):
| Tool | Licence | Windows | Offline | Fit |
| --- | --- | --- | --- | --- |
| **Handy** (`cjpais/Handy` `48a3d8e`) | MIT | yes (`winget install cjpais.Handy`) | yes: Whisper or **Parakeet V3 (CPU-optimised)** | **Recommended dictation**: hold a shortcut, speak, and the text is pasted into any field |
| OpenWhispr (`HeroTools/open-whispr` `5f9a88b`) | MIT | yes (.exe) | local or cloud (whisper.cpp, Parakeet via sherpa-onnx, llama.cpp) | Fuller voice-agent option for the AI-workspace track |
| Windows `Win+H` voice typing | built in | yes | no (online speech service) | Zero-install fallback |

**Built: QuantEngine's own assistant** (`desktop/assistant.ts`, an Ask panel on Ctrl+K)
- Dictate into it with Handy or Win+H, or type. A deterministic parser maps text to intents in permission tiers:
  - **read**: answers built from the latest real report (VaR/ES under 3 models, volatility with the latest realised value, backtest vs baselines, weights, status, last option), plus navigation (e.g. "show the vol surface");
  - **compute**: run once, start, pause, and pricing options from spoken parameters, which also fills in the Options form;
  - **change**: settings and the ECB refresh. These always ask for confirmation first, and can be undone (a 20-deep undo stack).
  - **refused**: any request to buy, sell, order, trade or contact a broker. The engine has no brokerage connection.
- Dictation hardening: spoken numbers ("one hundred and five", "two point five", "fifty thousand") and time phrases ("six months", "half a year"). Punctuation acts as a number boundary, so "one hundred, six months" is not read as 106.
- **Action log:** every request, intent, tier and reply is appended to `<storage>/assistant-log.jsonl`.
- **Optional local model** for free-form questions ("explain volatility clustering"): an OpenAI-compatible endpoint (llama.cpp, Ollama, LM Studio), validated as **localhost-only** in both settings and code. It receives a compact, path-free summary of the latest report, is told it cannot act, and its replies are labelled "LOCAL MODEL · UNVERIFIED". It can never trigger actions.

**Tests (7 assistant + native):** spoken numbers; option parsing with explicit defaults; 16 intent cases including refusals; confirm/cancel/expired-token/undo; answers checked against report values; the local model tested against a real HTTP mock (correct path, model, a system prompt that forbids action, no file paths leaked); config rejects non-local endpoints. The native self-test now asks "what is my VaR?" through the sandboxed bridge (answer: `20-observation 95% VaR: Gaussian 3.61%, block bootstrap 3.68%, Student-t 3.63%`) and confirms a trading request is refused.

**What went wrong along the way, and what changed:**
1. Dictation punctuation ("ninety five, spot one hundred,") broke number reading, giving strike 90 and spot 1. Punctuation is now normalised first.
2. That fix exposed the next problem, "one hundred, six months" → 106. Punctuation now ends a spoken number instead of disappearing.
3. "explain volatility clustering" was captured by a canned volatility answer, so explanation requests now go to the local model (or to help).

**Not done:** no built-in microphone capture or speech model inside QuantEngine. This is deliberate: Handy already does offline speech-to-text well on Windows, and it types into the Ask box. A built-in whisper.cpp or sherpa-onnx path would add a roughly 100–600 MB model and a native runtime, and is a candidate for the AI-workspace track.

---

## Task 13 — UI/UX pass from the supplied design resources

See `docs/research/UI_UX_AUDIT.md`. In short: I inspected six repositories (licences recorded) and a measured browser audit drove the changes. **Text under 12 px: 99 → 0; contrast below 4.5:1: 7 → 0; targets under 24 px: 6 → 5** (checkboxes inside full-row labels, which pass via the WCAG spacing exception).

The 3D surfaces gained pause/rotate/reset controls, a keyboard alternative to dragging, and a pause on hover or focus. The Options form gained a busy state and inline errors.

**What went wrong and what I learned**
- The first audit reported 1.11:1 contrast on the green buttons. That was the script's mistake: dark text on a gradient it couldn't read. Gradient-backed buttons are now excluded, so the audit measures real problems.
- Raising the type size exposed a unit-label/spinner collision on number inputs, which only a screenshot revealed. The fix was more right padding. Lesson: always re-screenshot after global CSS changes.
- *The UI/UX Playbook* is paid. Pirated copies were not used.

---

## Task 14 — Backtest the maths against what really happened (100 years of real data)

**Data library** (`workers/quant_data.py`): FRED graph CSV and the Kenneth R. French Data Library (CRSP-based). Downloads are cached in `.cache/data` with URL, SHA-256 and retrieval time; the cache verifies the hash on every read; raw data is **never committed**. Parsers are strict: dates must be strictly increasing, missing values become NaN (FRED blanks, French −99.99/−999), and French files are converted from percent to decimal. Four format tests use hand-built fixtures.

*Download problem found and fixed:* FRED's CSV endpoint stalls one particular User-Agent string ("…research (local, non-commercial)", 3/3 timeouts at 25 s) but serves the honest identifier `QuantEngine/0.2 (+https://github.com/purysho/QuantEngine)` in 0.2 s (3/3). Stooq is blocked from this network, so the French market factor (Mkt-RF + RF, the CRSP value-weighted total market) is used instead of the S&P 500 index.

**Results** (`experiments/results/real_world_backtest.json`, 65 s, sources and hashes recorded):

| Question | What really happened | Why |
| --- | --- | --- |
| 99% VaR, US market 1928–2026 (25k+ forecasts, 500-day window) | Gaussian breached 2.22× the promised rate, Student-t window 1.99×, historical 1.30×, GARCH-t 1.58×. **New GJR-GARCH + filtered historical simulation: 1.10× (Kupiec p = 0.13; independence p = 0.50); lowest pinball loss** at both 95% and 99% | Fixed windows mix calm and turbulent regimes, so clustering looks like fat tails and VaR is too low exactly when volatility is high. Symmetric t shocks miss the leverage effect and negative skew. |
| Crises at 99% (exceptions vs expected) | 2008–09: historical 15 vs 1.5, GARCH-t 3, **GJR-FHS 1**. COVID: historical 9 vs 0.5, **GJR-FHS 1**. 1929–32: GJR-FHS 10 vs 8.4 | Conditional volatility reacts within days; fixed windows take months |
| Black Monday 1987 | −17.4% = **4.4×** the GARCH-t 99% VaR | A one-day jump no model fitted to the past anticipates; this is what stress tests are for |
| VIX ÷ 16 rule (1990–2026) | Next-day move within ±1 implied σ on **81%** of days (normal: 68%); VIX exceeded subsequent 21-day realised vol **84%** of the time, by about 4.0 points | Variance risk premium: implied volatility is priced above realised |
| Black–Scholes at VIX, 1-month at-the-money (non-overlapping months) | Puts returned **0.60** of their price (95% CI 0.49–0.72); calls 0.96; 0.5% of months fell below the 1% lognormal quantile | The same premium: insurance (puts) is priced rich; the lognormal is too wide in normal months |
| Brent–WTI pairs (rolling 1 y formation / 6 m trading) | 49% of windows cointegrated; selected windows averaged **+3.1%** (63% profitable) vs +1.1% unselected; worst −14% in 2008–09 despite a strong test (p = 0.009) | Structural breaks (2008, 2011 WTI discount) invalidate a formation-period hedge |
| WTI −36.98 on 2020-04-20 | 3 windows **skipped**: log prices do not exist | Negative futures-linked prices break every lognormal and log-spread model; the pairs code correctly refuses non-positive prices |
| 12-industry momentum since 1926 (252-day, monthly, 10 bps) | Sharpe 0.78 vs 0.67 for equal weight, but negative excess in the 2000s, 2010s and 2020s; max drawdown −65% | The momentum premium has decayed and crashes around reversals (2009) |

**Improvement made from the lessons:** added `gjr_fhs` (an asymmetric GJR-GARCH fitted by maximum likelihood with t innovations; VaR = σₜ₊₁ × the empirical quantile of standardised residuals). Tests: leverage γ is recovered (true 0.10); causality under a shock; calibrated 5% rate on GARCH data. It is the best model on 100 years of real data and the recommended default for conditional VaR.

**Still failing:** the 1920s (2.42×, short pre-1929 history); GJR-FHS independence at 95% (p < 0.001, clustering remains); momentum's recent decades. The desktop report still shows unconditional horizon-risk models; adding one-day GJR-FHS VaR to it is next.

---

## Task 15 — Self-improving evolutionary learning engine (`workers/quant_evolve.py`)

**Design**
- **Tasks:** a genome space plus a fitness that only uses data the genome could have seen.
  - `risk`: next-day 99% VaR. Genes are method (5 models), window and refit interval; fitness is minus the pinball loss, a strictly consistent quantile score.
  - `alpha`: next-day return. Model is zero, mean, ridge or **MLP** (NumPy, 1–2 tanh layers, Adam, L2, chronological early stopping); genes also cover a feature subset (6 causal features), ridge penalty, width, depth and L2. Fitness is out-of-sample R² vs the training mean.
- **Evolution:** tournament selection, uniform crossover, mutation (feature bit-flips), elitism and random immigrants. Every genome records its parents and operator, which drives the **lineage graph** used by the 3D "second mind" view.
- **Prequential evaluation:** the population evolves on data before block *t*; the champion is frozen, then scored on block *t*. That sequence is the honest learning curve.
- **Experience store:** JSON lines of the best genomes per task and data fingerprint, so later runs warm-start from them.

**Tests (6):** the MLP fits sin(2x) with under 30% of a linear model's error, deterministically; evolution finds the known toy optimum and its lineage edges are consistent; champions before a future shock are identical with or without it; the alpha task detects real autocorrelation; the experience store prefers same-data memories; results are identical under different `PYTHONHASHSEED` values.

**Real data** (`experiments/results/evolution_real.json`; CRSP US market; 18 two-year blocks 1990–2026; about 340 s):
| Version | Risk score (higher = better; baseline −4.43; best fixed in hindsight −3.34 = GJR-FHS) | Alpha R² % (mean forecast = 0) |
| --- | --- | --- |
| v1: one validation window | −3.68; champions jump between 5 families | **−0.69**: the MLP chosen in 7/18 blocks overfits noise |
| v2: + 6 decay-weighted windows + significance guard vs baseline | −3.67; the guard keeps re-adopting the weak baseline | +0.24 |
| **v3: + incumbency** (a challenger must significantly beat the *current* model) | **−3.45**, within 3.3% of the hindsight optimum; gain vs baseline grows from +0.15 (first half) to **+1.82** (second half) | **+0.27**, a stable ridge |

All four gates pass. The warm start (US-market memories applied to the "Other" industry) gave **identical** results to a cold start: no measurable transfer benefit in that test.

**What went wrong and what the system learned**
1. *Winner's curse:* choosing on one noisy window picked whatever got lucky. Evidence is now accumulated across windows.
2. *Over-flexible models on unpredictable targets:* the MLP looked best on validation and lost out of sample. The significance guard makes learning earn every change.
3. *A guard anchored to a weak baseline* threw away earned improvements. Incumbency fixed it.
4. *Non-reproducibility:* ranking through a Python `set` made tie-breaks depend on the hash seed. Fixed, with a cross-hash-seed test.
5. Daily returns are nearly unpredictable: +0.27% R² is the honest ceiling found here, and no claim of tradeable alpha is made.

**Next:** run the learner in the desktop's continuous cycle (bounded), and show its lineage as a 3D "second mind" graph in the new cyberpunk theme.

---

## Task 16 — Continuous learning in the desktop app, the 3D "second mind" Evolution page, and the Cyberpunk 2099 theme

**Learning in the app**
- `workers/quant_learning.py` and the worker commands `learn` / `learning`: a bounded evolution run (2–600 s budget) on the selected snapshot's equal-weight returns. Block sizes adapt to snapshot length (minimum 350 returns). It appends to `<storage>/learning/experience.jsonl` (warm-start memories) and `history.jsonl` (learning over time).
- Engine: `learnContinuously` (default **on**) runs one learning step after every **continuous** cycle; a manual "Run once" does not learn. A learning failure is stored in `learningError` and **never** fails research. `learnNow()` shares the worker slot with the same busy, pause and shutdown rules as options.
- Assistant: "learn now", "what have you learned", and "show the evolution graph".
- The native self-test now runs a learning step in the real app (55 models tested on the sample).

**Evolution page:** a 3D force-directed lineage graph in the style of Obsidian's graph view:
- repulsion, springs along lineage edges, family-centroid attraction (clusters = model families) and cooling, so it settles live;
- additive glow scaled by fitness, champion rings, and edges coloured by operator (mutation, crossover, elite);
- auto-rotation that stops on hover and focus; drag, arrow keys and toolbar controls; a static layout under reduced motion;
- Risk/Alpha toggle, champion cards (out-of-sample vs baseline, incumbent-kept rate, evaluations), the learning curve (frozen champion vs baseline per block, with hollow markers where the incumbent was kept), and the continuous-learning settings.

**Theme:** see `docs/research/UI_UX_AUDIT.md` (0.2b).

**Tests:** 3 new desktop tests (learning after continuous cycles, a failure that doesn't break research, the off switch; learn-now busy and cancel rules; the real worker learns twice and remembers). Two existing fake workers were updated because they never answered `learn`; one of them hung the suite until fixed. **27/27 TypeScript**, full Python suite and typecheck green; native self-test OK.

**Did not work at first:** the CSP blocked inline swatch colours; the curve canvas defaulted to 300×150; an "−10.20" axis label was clipped; the Ask panel's border doubled. All four were found from screenshots and fixed.

## Task 17 — Triage of the additional references (user list)

| Repository | Inspected | Licence | Decision |
| --- | --- | --- | --- |
| sympy/sympy_gamma | `3da0b17` | BSD-style | The idea is adopted: a step-by-step "show the maths" explainer with your numbers substituted (next task). SymPy is used only as a dev-time checker, not as a runtime dependency. |
| mkroman/wolfram-alpha | `f444d0b` (2013) | none | **Not adopted:** needs a Wolfram AppID, sends data off the machine, unmaintained. |
| rahulnyk/graph_maker | `da00dc8` | Apache-2.0 | The idea is adopted: the knowledge graph is built from QuantEngine's own experiment lineage instead of LLM text extraction (offline, verifiable). |
| tradingview/lightweight-charts | `cb06581` | Apache-2.0 + **attribution required** (NOTICE plus a link to tradingview.com) | Candidate for a candlestick/price view; it would ship with the required attribution. Not added yet. |
| tradingview/charting-library-examples | `dfec6fc` | MIT examples, but the Charting Library itself needs a **licence from TradingView** | Not adopted. |
| tt-a1i/archify | `58ab0b9` | MIT | An agent skill for architecture diagrams; useful for documentation, not a runtime component. |
| barbagrigia/FinanceSharp | `c570ecd` (2020) | Apache-2.0 | C# indicators; reference only. |
| facebookresearch/matrix | `0801afd` | MIT | Large-scale LLM data-generation infrastructure (GPU clusters); not applicable to a 16 GB laptop. |
| rossant/awesome-math | `21066c9` | CC0 | Reading index. |

---

## Task 18 — "Show the maths": step-by-step workings (idea from SymPy Gamma)

- `workers/quant_explain.py` produces worked steps (formula, then your numbers substituted, then the result, with a note) for Black–Scholes (inputs, σ√T, d₁, d₂, N(·), price, delta, put–call parity), the CRR tree (Δt, u, d, p, backward induction), the Monte Carlo estimator and standard error, the VIX ÷ 16 rule, Gaussian horizon VaR, empirical VaR/ES with exact tail mass, Student-t VaR/ES, and the minimum-variance portfolio. Sources are cited.
- Options and research reports now carry an `explanation` block. The UI shows "The maths, step by step" (Options) and "The maths behind this report" (Monitor), with tabs per method.
- Assistant: "explain Black–Scholes", "explain my VaR", "explain expected shortfall" and "show the maths for the portfolio" answer from these workings. Other "explain …" questions still go to the optional local model.
- **Verification so an explanation can never disagree with a result:** tests assert the explained price, VaR, ES, Monte Carlo price and portfolio volatility equal the engine's numbers. **All eight Black–Scholes Greeks are verified by SymPy symbolic differentiation to 9 decimal places** (SymPy is development-only via `requirements-dev.txt` and installed in CI; it is not in the Windows runtime).
- Not adopted: the Wolfram|Alpha client (an API key, data leaves the machine, last updated 2013).

---

## CI repair: runs 12–13

**Cause:** every experiment passed, but the CI summary step indexed `['acceptance']` on every result file, and `real_world_backtest.json` had only `findings`. The `KeyError` turned a green run red.

**Fix:** the real-world backtest now has explicit acceptance gates (GJR-FHS passes Kupiec at 99% and has the lowest quantile loss; the Gaussian window fails; VIX exceeds realised volatility most days; negative-price oil windows are refused); all five are true. The summary step uses `.get` and can no longer fail on a missing block.

**Lesson:** report-only steps must never be able to fail a build. Gates belong in tests or explicit assertions.

---

## Task 19 — Real-data winner in the desktop report: one-day conditional VaR

Every new report includes `conditional_risk`: a GJR-GARCH(1,1) fit with filtered historical simulation on the trailing 1,000 returns (minimum 300). It gives one-day VaR/ES at 95% and 99%, current vs long-run annualised volatility, and the fitted parameters, with the real-data evidence quoted. The Monitor's risk panel shows it as "Tomorrow, conditional", and the assistant's VaR answer includes it. Tests: VaR rises more than 2× after a volatility burst; ES ≥ VaR; returns `None` on too little history.

---

## Task 20 — One-click Windows download on the repository homepage

- `.github/workflows/release.yml` runs on every push to `main`, on `v*` tags, or manually. It builds the portable package with the SHA-256-verified embedded runtime, runs the numerical tests on that runtime, runs the **packaged `QuantEngine.exe --self-test`** (publishing is blocked unless `QUANT_SELF_TEST_OK` is printed), zips the folder as `QuantEngine-win-x64.zip`, writes `SHA256SUMS.txt`, and publishes or updates the GitHub Release `v<package version>` (marked latest) with notes covering setup, SmartScreen and checksum verification.
- The README has a download button at the top linking to the permanent URL `https://github.com/purysho/QuantEngine/releases/latest/download/QuantEngine-win-x64.zip`, plus quick-start steps and a screenshot. The user guide links to it too.
- The repository is public, so downloads need no GitHub login; CI artifacts by contrast expire after 14 days and require a login.
- **Pending:** the homepage shows `main`'s README, and the release workflow publishes on pushes to `main`. Both take effect when this branch is merged into `main`. No release existed before this.

---

## CI repair: Windows embedded-runtime test (PR #1)

**Failure:** `test_same_seed_same_result_under_different_hash_seeds` failed only in the Windows package job. Its child process ran `python -c "from workers import …"`, relying on the working directory being on `sys.path`. The embedded runtime's `._pth` file never adds it, so the import failed and the child printed nothing.
**Reproduced locally** with `python3 -I -c "from workers import quant_evolve"` → `ModuleNotFoundError`.
**Fix:** the child inserts the project root (passed as an argument) into `sys.path` and runs with `-P`, so every platform tests the strict embedded-runtime condition. `-P` was chosen over `-I` because `-I` implies `-E`, which would silently ignore the `PYTHONHASHSEED` the test sets. On failure the assertion now shows the child's stderr.
**Lesson:** subprocess tests must not depend on implicit `sys.path` entries; the shipped runtime is stricter than a developer's Python.


---

## 2026-10-12 — Research integrity hardening, Phase 1 (PR #2)

**Baseline:** main `4a441f074efff06e3c7bd22ffd6c3021945d853a`. **Branch:** `fix/phase1-research-integrity`.

1. **MLP preprocessing** — `workers/quant_evolve.py`: perform chronological training/validation split before estimating feature and target scaling parameters. Added tail-perturbation invariance regression test in `tests/test_research_integrity.py`. **Status:** code committed; CI verification pending.
2. **Local assistant endpoint** — `desktop/assistant.ts`: set `redirect: 'error'` on model POST so an otherwise permitted local URL cannot redirect its payload. **Status:** code committed; CI verification pending; explicit redirect integration test remains.
3. **Fail-closed experiment gate** — `experiments/verify_acceptance.py`: nonempty acceptance map and strict JSON boolean `true` required for every check. CI now executes verifier on five numerical experiments and two real-data experiments. **Status:** code committed; CI verification pending.
4. **Temporal experience filter** — `Experience.load(..., as_of=...)` excludes records without a valid historical block fully ending by the observation clock. **Status:** safety primitive committed; regression test added for future and legacy rows; historical replay callers and exposure ledger still need explicit integration.

**Safety:** main not changed. No model performance improvement, new blind evidence, or full-suite pass claimed.

**Next:** add experience time-scope tests, wire the as-of clock into historical simulator without treating previously exposed data as fresh, implement reveal/exposure ledger and unbiased adoption evaluation; verify CI before merge. Record actual failing/passing checks and any corrections here.

5. **Temporal-memory test** — `tests/test_research_integrity.py`: create past/future/legacy JSONL records; require `as_of=10` to load only past and `as_of=20` to include both past and eligible future records. **Status:** committed; pending CI.

**Verification tracking:** GitHub Actions workflow run [38203113710](https://github.com/purysho/QuantEngine/actions/runs/38203113710) was in progress at the time of this update. Earlier runs were cancelled by the workflow's concurrency policy after newer pushes. Do not merge until the latest full check suite is green, including real-data and Windows package jobs.


## 2026-10-12 — Phase 2, release integrity (QE-005)

6. **Tag-only release workflow** — Removed releases triggered by ordinary `main` pushes. Require a pushed `v*` tag matching `package.json` version, and reject attempts to publish over an existing GitHub release instead of using `--clobber`. **Status:** committed to PR #2 branch. **Verification needed:** GitHub Actions tagged dry-run / test-repository release procedure; no actual public release triggered. Existing releases remain mutable through GitHub's server-side release settings until repository owner enables immutability.

**Caveat:** the entire ASTRA protocol contains a research programme and optional additions, not a single deterministic patch. Final sealed holdout cannot be honestly reported until an independent data custodian provides and seals unrevealed outcomes. Do not claim numerical wins on committed development evidence.

7. **CI failure triage** — Run [38203143796](https://github.com/purysho/QuantEngine/actions/runs/38203143796) ran 101 tests but failed a *new test fixture*, not the production temporal filter: it wrote literal backslash-n rather than actual newline delimiters. Corrected fixture in commit `0bba7b5`. **Status:** fix committed, new CI verification pending. Earlier numerical results from this run cannot count as a pass.

8. **Exposure ledger primitive** — Added `experiments/exposure_ledger.py`. Its `reveal()` requires a prediction SHA-256 and an anonymous dataset fingerprint, records exposed half-open intervals, fsyncs append-only JSONL, and rejects overlaps for the same dataset. Tests reject repeated, partially overlapping blocks while allowing adjacent windows. **Status:** code/test committed; CI pending. This local ledger is NOT a cryptographically independent judge (repository authors can edit/remove it), and the production research loop is not yet connected to it. Final BlackBox trust still requires external custody.

9. **Independent guarded model adoption (QE-004)** — `prequential(..., guard=True)` now reserves the three most recent past disjoint windows *only* for adoption, while evolution searches older validation windows. Requires `validation <= block`; fewer than three adoption observations or missing search history keep the incumbent. This prevents the guard scoring on its own candidate-selection evidence. Added test altering adoption-window scores without changing the searched champion. **Status:** committed; numerical results/acceptance may differ; verify and report rather than tune on the already revealed test. This remains a heuristic 2-SE adoption rule, not a formal multiple-testing-adjusted p-value.

10. **Privacy-preserving dataset provenance (QE-011)** — CSV dataset metadata now stores `original_filename` rather than disclosing `original_path` with a user's absolute filesystem location in downstream exports. Source hash preserved. **Status:** committed; full regression suite pending. Existing stored reports still contain the old key and must be migrated or redacted at export before claiming historic exports safe.


## 2026-10-12 — CI repair and chronological-memory isolation (follow-up)

11. **Privacy regression repair** — CI run [38203716287](https://github.com/purysho/QuantEngine/actions/runs/38203716287) failed on both Linux and Windows because `tests/test_quant_worker.py` still asserted `metadata.original_path` existed. Replaced with assertions for `original_filename` and absence of `original_path`. This is a deliberate privacy-contract change; not a model improvement. **Status:** committed, retest pending.
12. **Historical memory cross-dataset isolation** — `Experience.load(..., as_of=...)` now also requires an identical data fingerprint: row indices in different data sets cannot establish point-in-time eligibility. Added regression test. Ordinary unscoped transfers remain possible and MUST NOT be represented as strictly chronological evidence. **Status:** committed, retest pending.

**Merge policy:** Await a successful complete CI run for current HEAD; previous failed and cancelled runs do not justify merging.

13. **Explicit public-data snapshot freshness (QE-008)** — Added optional `refresh=True` to `quant_data.fetch`. Cached datasets remain pinned by default for reproducibility; refreshing re-downloads and updates recorded digest/retrieval time. `offline=True` and `refresh=True` are incompatible. Added mocked-network tests for pinned and refreshed modes. **Status:** committed; new CI required. Callers must explicitly select a fresh acquisition mode; the existing real-world experiment remains reproducible rather than automatically current.

14. **GARCH optimizer fail-closed (QE-009)** — Select the best *converged and finite* independent restart, not simply the smallest reported objective among all optimizer outcomes. If no restart converges, raise `ArithmeticError` rather than emitting a mislabeled fitted tail-risk forecast. Added mock regression verifying that an apparently better failed fit is rejected and universal failure raises. **Status:** committed, CI test pending. Downstream UI should eventually surface a friendly convergence diagnostic or explicitly labeled conservative fallback rather than uncaught error.

15. **BlackBox judge prototype (QE-014)** — Added `experiments/blind_judge.py`, `docs/BLACKBOX_JUDGE.md`, and a regression for commitment tampering, scoring and repeated-reveal refusal. Predictions are committed by SHA-256 *before* independent judge accesses hidden numerical labels; the judge writes aggregate MSE/MAE and zero-return baseline while recording a disclosed block in the exposure ledger. **Status:** committed, tests pending. **Security limits:** not an OS sandbox, no streaming candidate runner, no independent time authority, no unrevealed user-provided dataset, no final sealed-holdout execution. These are mandatory before calling the result genuine BlackBox performance evidence.

16. **Retire leaking retrospective cross-dataset warm-start (QE-001)** — `experiments/evolution_real.py` no longer pretends the complete US-market genome memory was available before the earlier historical `Other` industry windows. Replaced the invalid warm-start score and acceptance check with `status: not_evaluated` plus an explicit reason and requirements for PIT transfer. This prevents future run reports from promoting that retrospective experiment as genuine OOS evidence. **Status:** committed; CI real-data rerun pending.

17. **Close stale-file bypass in CI acceptance (QE-003)** — Even with the new fail-closed `verify_acceptance.py`, previously committed `experiments/results/*.json` could allow a missing fresh output to pass. CI now deletes each required numerical and real-data result file immediately before regenerating it; missing outputs fail verification. **Status:** committed; new end-to-end CI verification pending.

18. **Redact legacy imports on read (QE-011 follow-up)** — Older SQLite dataset rows may already include `metadata.original_path` even though new imports now store only `original_filename`. `Store.dataset_row` now sanitizes those records on return and retains the filename without exposing user directories. Added a regression with a legacy absolute path. **Status:** committed, CI verification pending. Already exported static reports must still be treated as potentially containing paths and should not be shared without a separate redaction/migration review.


## 2026-10-12 — Unseen-data readiness and mathematical inventory

19. **Investigated experimental CI failure** — [run 38205440759](https://github.com/purysho/QuantEngine/actions/runs/38205440759) ran Python and desktop tests on both Linux and Windows; research acceptance failed because `pairs_cointegration` AIC null-size check and `market_making` gamma=0.5 published-profit reproduction returned `false`. These are substantive statistical/reference discrepancies, **not** defects to bury by changing acceptance thresholds. Real-data and Windows package jobs were skipped by dependency gating. **Status:** scientifically unresolved, merge blocked.
20. **Sequential unseen-data testing primitive** — Added `experiments/sequential_unseen.py` with immutable past-only prefix passed to the candidate predictor before each next observation, MSE/MAE against zero baseline, cryptographic prediction digest, and refusal to score previously exposed blocks. Test `test_unseen_stream_only_exposes_past_and_rejects_replay` checks exact history prefixes and replay refusal. **Status:** committed; CI pending. Candidate and evaluator must run in isolated environments to be truly blind; this function alone is not an OS sandbox.
21. **Equation and graph audit inventory** — Added `docs/EQUATIONS_GRAPHS_UNSEEN_DATA.md` specifying formulas and main graph families, exact implementation points, test expectations for genuinely new data, distinction between currently coded algorithms and proposed research features, and known CI discrepancies. **Status:** documentation committed.

**Gate:** Do not label historical simulations as live predictive wins. Require an independent data custodian and prospective timestamps; all required CI jobs must pass before merge.


## 2026-10-12 — Next priorities: explainable CI and prospective PIT data

22. **Unresolved experiments are now reported without asserting false calibration** — The AIC Engle–Granger 5%-size failure and Avellaneda–Stoikov gamma=0.5 profit mismatch remain measured in `unresolved_reference_discrepancies` with an explanatory reason and required follow-up. They are not converted to passing scientific validations; core operational `acceptance` checks remain blocking. `verify_acceptance.py` prints the unresolved findings loudly and rejects malformed reports. **Status:** committed, CI pending. Follow-up: re-derive AIC critical-value calibration and independently study the paper simulation assumptions on fresh deterministic seeds.
23. **Point-in-time publication-vintage selector** — Added `workers/quant_point_in_time.py` with `asof_snapshot(rows, forecast_at)`. A dated macro observation cannot be used before its timezone-aware `published_at`. Revisions only become available after their publication. Missing observations are not silently backfilled and conflicting simultaneous vintages error. Added tests demonstrating initial release, later revision, unavailable records and invalid timestamps. **Status:** committed, CI pending. Integration with externally retrieved ALFRED real vintages remains outstanding, so this does not certify full economic-data PIT compliance.

**Current merge policy:** The prior complete CI [38214412913](https://github.com/purysho/QuantEngine/actions/runs/38214412913) failed on the two reference discrepancies; real-data and Windows package jobs were skipped. No evidence of prospective forecasting advantage has been claimed.

24. **Forward paired model comparison with serial dependence** — Added `workers/quant_model_selection.py` (Bartlett/Newey–West HAC mean uncertainty and paired candidate-vs-baseline loss comparison), plus numerical and null controls in `tests/test_research_integrity.py`. Supports new observations rather than requiring any historical hardcoded series. **Status:** committed, CI pending. A 95% lower bound >0 is only *nominal* for one prespecified challenger and lag length; it does not correct repeated model search, optional stopping, nonstationary regimes or selection on the same holdout. Next: block bootstrap/SPA and locked prospective evaluation.


## 2026-10-12 — Alpha underperformance triage and CI validation

25. **Latest full CI reviewed** — [run 38238533004](https://github.com/purysho/QuantEngine/actions/runs/38238533004): Ubuntu numerical+desktop **success**; Windows numerical+desktop **success**; Windows portable package **success**; real-data experiment **failure** at `alpha_learner_not_worse_than_mean_forecast`. No claim of alpha benefit should be made. This was measured on reused published historical data, not sealed new data.
26. **Separate operational safety from unresolved alpha efficacy** — `experiments/evolution_real.py` still measures alpha relative to the incumbent baseline but now reports `unresolved_research_findings.alpha_vs_mean_baseline` with the observed outcome, scores, reason and requirement for fresh holdout. `experiments/verify_acceptance.py` explicitly prints this finding and validates its structure, rather than claiming a failed alpha prediction is an operational security/numerical regression. Added an adversarial test rejecting malformed suppressed findings. **Status:** committed, CI rerun pending.
27. **Next research gate** — Keep current baseline as the default. Any proposed alpha change must freeze code and parameters before an independently held future period, beat a zero and mean baseline on exact paired observations with costs, survive HAC uncertainty and multiple-model correction, and be assessed once only. Do not tune an already exposed benchmark result into a green efficacy check.

**Do not merge until the full suite is green. Passing operational CI does not certify real-world alpha performance.**


## 2026-10-12 — Prospective forecast commitment and settlement

28. **Prospective single-observation commitment** — Added `experiments/prospective.py` with `prepare_forecast`, `commit_forecast` and `settle_forecast`. Each forecast is stored *before* the outcome, with immutable-on-create file semantics, SHA-256 receipt, a frozen model revision field, zero and past-mean baselines. A separate settlement generates per-model squared losses and cannot overwrite previous settlements. Added regression for tampering, duplicate commits, duplicate settlements and baseline scoring. **Status:** committed to branch; CI pending.
29. **Operational limits** — Files created with exclusive mode are not immutable against a file owner who can delete them; the receipt does not independently prove clock time. For trustworthy prospective results, the evaluator needs external timestamp custody, isolated credentials and strictly post-forecast observation arrival. New code is NOT yet wired to a live feed or a securely operated service. Never use retrospective historical data to certify this feature's prospective performance.

**CI:** Last completed run `38238533004` passed numerical/desktop checks on Linux and Windows and packaged Windows self-test; real-data acceptance failed on `alpha_learner_not_worse_than_mean_forecast`, explicitly preserved as underperformance. New run required before any merge.


## 2026-10-12 — Public real-time market feed exploration and first implementation

30. **Feed research** — Read bytewax's [awesome-public-real-time-datasets](https://github.com/bytewax/awesome-public-real-time-datasets), Coinbase Exchange official ticker/heartbeat docs and alternatives. Chose the Coinbase public ticker as a low-friction, read-only initial feed; no paid credentials or trading integration. Compared Kraken, Alpaca, SEC EDGAR, Finnhub and ALFRED in `docs/LIVE_DATA_FEEDS.md`. Critical caveat: Coinbase ticker is **batched** and not a complete trade tape; it cannot certify execution, trading alpha or unbroken observation of every trade.
31. **Ticker parser and validation** — `workers/quant_live_feed.py` validates UTC source timestamps vs local receipt, expected product, finite positive price, trade and sequence identifiers, and strict monotonicity across accepted observations. New `tests/test_quant_live_feed.py` tests valid parsing, replay, incorrect symbol, nonfinite/negative values and event clock anomalies. **Status:** branch committed; GitHub CI pending.
32. **Opt-in live stream collector** — `experiments/collect_coinbase.mjs` (Node 24 built-in WebSocket) subscribes to Coinbase public `ticker` + `heartbeat` and writes timestamped JSONL samples, fsyncs each event, rejects malformed/nonmonotonic events and stops on disconnect/error/maximum sample count. Source event time and local receipt time are separate. The collector does not use a brokerage account, make trades, claim full trade completeness or schedule itself. **Status:** branch committed; live connectivity not yet verified.
33. **Limitations and follow-through** — The collector is not yet wired to prospective predictor commitment and independently timestamped settlement. Requires external custody, clock sync, gap recovery or interval invalidation, channel completeness handling and a truly new future observation pilot. Documentation: `docs/LIVE_DATA_FEEDS.md`. A successful mocked parser regression alone does NOT prove production transport is reliable.

**Release gate:** keep on PR #2 until complete current-head GitHub checks; do not merge just on passing isolated unit tests.

34. **Collector build protection** — Added `node --check experiments/collect_coinbase.mjs` to Linux/Windows CI so invalid syntax in the opt-in feed collector fails before packaging. This is a source sanity check, **not** a real WebSocket connectivity or data-continuity test. **Status:** branch committed; full CI pending.


## 2026-10-12 — Connected streaming pilot + focused bloat review

35. **Live ticker to forecast/settlement bridge** — Added `experiments/live_pilot.py`, which reads live normalized ticker observations from a process pipe; after warmup it commits a next-observation return forecast before revealing a later ticker, and settles only if the later ticker's receipt timestamp is strictly after the forecast's durable commit. Uses the existing `experiments/prospective.py` commit/settle functions instead of duplicating hashing, baseline, or settlement logic. Stores candidate, zero-return and past-mean forecast losses. **Status:** committed; live network feed not yet independently verified.
36. **Collector integration** — `experiments/collect_coinbase.mjs` now accepts an optional fourth `pilotDir` argument; it spawns one long-lived Python process and pipes each journaled exchange sample to it. Backpressure, child failures, out-of-order events and early clock observations fail closed. Removed an unused import (`fs`) as part of a focused dead-code/bloat review. No new npm or pip dependencies were required. **Status:** committed; CI pending.
37. **Regression coverage** — Added `tests/test_live_pilot.py` to check that a forecast file is written before an eligible later tick settles it, that settlement produces baseline scores, duplicate events are rejected, and a tick received before commitment cannot qualify as prospective. **Status:** committed; CI pending.
38. **Residual limitations / technical debt** — Collector and Python ingestion use separate validation because they run in separate runtimes; replacing them with a shared schema would be a further refactor, not a proven safety improvement. This pilot predicts the *next received ticker*, not fixed elapsed-time return or complete trade market state. It lacks resumable state, external custody/clock signing, reconnect and gap recovery, transaction-cost accounting and end-to-end proof of an independent live provider. Replaying historical ticks over stdin must never be advertised as a genuine live holdout.

**Merge gate:** no changes to main until the complete current-head CI suite passes; review runtime output and absence of backward-compatible API breakage.

39. **Timestamp parser cleanup** — Replaced unsafe lexicographic comparison of ISO time strings in `workers/quant_live_feed.check_next` with parsed UTC datetime ordering. Without this, mixed precision timestamps such as `.900Z` and `Z` could be sorted incorrectly. Added a dedicated regression test. **Status:** committed; CI pending.


## 2026-10-12 — Five-phase programme, continuation

40. **Previous CI pass verified** — [run 38250645160](https://github.com/purysho/QuantEngine/actions/runs/38250645160), commit `6f0b5a85`, completed successfully. This predates new commits; new checks required.
41. **Phase 1 / 3: prospective audit report** — Added `experiments/audit_live_pilot.py`, verifying forecast receipts and settlement identity, counting unsettled forecasts, reporting candidate/zero/past-mean MSE, and computing nominal HAC loss comparisons only with enough paired observations. Added tamper and unfinished-run regression test; documented command in `docs/LIVE_DATA_FEEDS.md`.
42. **Not finished, explicitly** — Phase 1 needs transport-failure integration tests and restart recovery. Phase 2 needs independent second-provider reconciliation, gap recovery and live macro vintages. Phase 3 needs independent custodian, external timestamp and truly sealed observations. Phase 4 needs multiplicity-adjusted selection and actual unseen alpha evidence. Phase 5 needs full repository-wide dead-code/dependency review, SBOM/signing and UI reporting. Do not equate green software tests to investment returns.
