# Validation, pairs trading, execution, and CPU ML research

Research checked on **11 October 2026**. This document records primary-source findings and proposed implementation acceptance contracts. It does not record implemented features, completed experiments, measured resource use, or profitable out-of-sample results.

The repository currently declares NumPy and SciPy in `requirements.txt`. Statsmodels, scikit-learn, HftBacktest, and Stable Baselines3 below are reference implementations or documentation sources, not dependencies added by this research. Before implementation, choose explicit package versions and API parameters; the online `stable` documentation can change independently of this repository.

## 1. Main implementation direction

Establish causality, accounting, and reproducibility before broad model searches. First deliver a pairs experiment with chronological selection and simple CPU prediction baselines. Use Avellaneda–Stoikov as an inventory-aware market-making benchmark, supported by a separately verified execution simulator. Add RL only after those components supply a meaningful comparison.

Treat these as different outputs:

1. Numerical/statistical correctness.
2. Predictive evaluation on future observations.
3. Trading evaluation under declared execution and cost assumptions.
4. Selection-bias diagnostics for the research process.

A positive result in one category does not establish the others.

## 2. Engle–Granger and MacKinnon statistics

Official statsmodels documentation specifies that `coint` implements the augmented Engle–Granger two-step test, assumes I(1) input variables, and has the null hypothesis **no cointegration**. The first-stage cointegrating regression includes the declared deterministic terms. Its p-value is MacKinnon's approximate asymptotic value; critical values depend on observation count and response-surface approximations. Near-perfect collinearity can yield `t = -inf` and `p = 0`. The documented implementation assumes no missing observations or time gaps. [S1]

The ordinary ADF null is a unit root. Failure to reject does not prove a unit root. ADF statistics do not have an ordinary standard-normal null distribution. In particular, the ordinary ADF p-value is not interchangeable with the fitted-residual cointegration distribution. Retain the test identity, deterministic terms, lag choice, sample length, statistic, p-value, and critical values. [S2, S3, S4]

Cointegration is a statistical relationship under assumptions, not a probability of profitable mean reversion. Correlation is not a cointegration test. Testing levels and first differences can supply diagnostics for I(1), but finite-sample nonrejection is not a conclusive classification. Select a regression direction in advance; if both directions are searched, record both in the research ledger.

### Statistical acceptance contract

- Compare ordinary finite inputs against the selected statsmodels version, with explicit `trend`, `maxlag`, and `autolag`, rather than relying on changing defaults.
- Include independent random walks and a constructed pair `y_t = a + b x_t + u_t`, where `x_t` is I(1) and `u_t` is stationary. Include stationary inputs to exercise the method's stated assumptions.
- Add cases for constant series, too few observations, duplicate dates, nonfinite values, missing rows, identical series, and nearly collinear series.
- Expose degeneracy and invalid-input status. A numerical `p = 0` from collinearity must not silently receive a perfect trading score.
- Check empirical null rejection frequency over seeded replications with uncertainty. Do not require every independent-random-walk fixture to avoid rejection, or claim an exact finite-sample false-positive rate from one run.
- Never substitute a normal-CDF transformation of the ADF statistic. If a custom MacKinnon implementation is chosen, validate its coefficients, deterministic-term cases, variable count, and sample-size convention against the reference implementation.

## 3. Point-in-time pairs trading

Whole-history pair selection, hedge-ratio estimation, or spread normalization leaks information into earlier decisions. At each formation cutoff, choose candidates and estimate the intercept, hedge ratio, spread parameters, and any half-life diagnostic using only then-available data. Either freeze those values during the following trading block or declare a causal refit schedule. An adaptive refit can use observations already realized during a test block; it cannot use later observations or retune the research design after viewing evaluation results.

Use a contemporaneously available universe and document unavailable or delisted instruments. Corporate-action adjustment, instrument membership, revisions, and timestamp alignment are part of data provenance. A final downloaded price history alone does not establish a point-in-time universe.

### Pair acceptance contract

- Every fold records formation and trading intervals, candidate universe, candidate tests, selection correction, chosen pairs, regression direction, hedge ratios, normalization, thresholds, and refit schedule.
- Altering observations strictly after timestamp `t` leaves all decisions, selections, and fitted state through `t` unchanged. Truncating the input at `t` produces the same decision prefix, subject to declared end-of-run liquidation handling.
- Pair selection runs again within each relevant inner training fold when it is part of the strategy under evaluation. Selecting the pair once on all outer training data and then presenting inner scores as an independent selection evaluation is insufficient.
- Keep statistical selection and trading performance separate. A multiplicity correction such as Holm can address a declared family of pair-test p-values; it does not correct an arbitrary repeated strategy search. Statsmodels documents Holm and other correction methods. [S5]
- Reconcile two-leg positions, cash, net/gross exposure, borrow cost, fees, and liquidation using hand-worked examples. A hedge ratio derived from log prices is not automatically a dollar-neutral allocation.

## 4. Signal availability and execution timing

Use explicit clocks for observation, strategy knowledge, order submission, exchange processing, and acknowledgement. The observation timestamp alone is not necessarily the time a strategy can use the observation.

For bar data, state the following order:

| Event | Earliest allowed dependency or effect |
|---|---|
| Bar `t` completes | Close-derived features become available after the bar is known. |
| Decision for bar `t` is produced | It depends only on features available by its decision time. |
| Order is submitted | It follows the decision; it cannot alter previously realized P&L. |
| Order becomes exchange-eligible | It follows submission and the declared entry latency. |
| Fill occurs | Only an eligible order can fill at an eligible market event. |
| Fill is observed by strategy | It follows the fill and declared response latency. |

Example: a signal first known after close `t` can execute at open `t+1` if opening prices and that execution rule are present. With close-only data and next-close execution, it executes at close `t+1`, so the new position earns the close-to-close interval `(t+1, t+2]`. If `r_j = P_j / P_(j-1) - 1`, that newly filled position must not be credited with `r_(t+1)`, which occurred before its fill.

An idealized instantaneous same-close fill needs an explicit assumption about data availability and fill price. It must not be described as realistic latency-aware execution. Do not mix next-open fills with close-only observations or credit a close-derived signal with an earlier return from the same completed bar.

### Timing and accounting acceptance contract

- A known jump before the first eligible fill cannot generate P&L for that newly opened position.
- A position closed at an eligible event receives the P&L accrued while it was actually held; costs occur at their declared execution events.
- Future-data perturbation leaves earlier orders and P&L unchanged. Separately test a mutation at the decision boundary and at the first eligible fill boundary.
- Report pending orders and unliquidated inventory at the end of history. Final liquidation must use a declared eligible price and cost rather than retrospective best-price selection.
- Reproduce a small event ledger exactly: starting cash, each fill quantity/price, fees, remaining inventory, mark value, and ending equity.

## 5. Chronological tuning, completed labels, purge, and embargo

Scikit-learn documents that non-nested tuning can produce an optimistic evaluation; the outer evaluation must assess the complete inner search. Its leakage guidance requires training-only fitting of preprocessing, and `Pipeline` helps enforce that separation. Both inner and outer splitters must preserve chronology for this project. [S6, S7]

`TimeSeriesSplit` uses ordered expanding training sets and provides a `gap` measured in samples excluded from the end of training. Comparable-duration folds assume equally spaced observations. It does not inspect forward-label intervals. [S8]

López de Prado defines purging as removing training observations whose labels overlap evaluation labels. His embargo removes immediately following training observations when a split also trains after the test block. A strict past-only walk-forward split has no post-test training observations in that same split, but forward training labels still must be complete before fitting. A fixed embargo percentage is not a universal leakage guarantee. [S9]

Give every record at least:

- `feature_available_at`: when all its input features are available.
- `decision_at`: forecast or order-decision time.
- `label_start` and `label_end`: the observations used to resolve its outcome.
- `label_available_at`: when the completed label is actually usable for fitting.

Historical observations used by a causal test feature may legitimately also occur in the training history. Distinguish that shared past context from fitting transformations on test data or using unresolved future outcomes.

### Split acceptance contract

- Training features and labels are available by the model's fit cutoff. Under a conservative strict ordering, training `label_end < first_evaluation_decision`; equality is allowed only if recorded event order establishes that the label resolved before fitting and prediction.
- Check actual timestamp intervals. A gap of `h` rows can stand in for a fixed `h`-row target only after endpoint conventions and spacing are established. Variable targets and irregular events require interval-based checks.
- Compare an efficient purge implementation with a brute-force interval-overlap oracle, including nested intervals, boundary equality, zero-length intervals, variable horizons, and multiple evaluation blocks.
- Inner training/validation observations are confined to outer training history. Fit scaling, imputation, feature selection, PCA, calibration, and any target transformation only on the fitting subset appropriate to that inner split.
- Preserve a separate final chronological holdout if the outer-fold results are used for subsequent research decisions. Repeatedly viewing and changing a strategy using outer scores turns those scores into development evidence.
- Record the indices, timestamps, removal reasons, data hash, seed, parameters, and software versions. Each reported evaluation prediction has one declared model and one evaluation date.

## 6. Meaning of multiple-testing diagnostics

**White's Reality Check.** The publisher's abstract states a null that the best model encountered in a specification search has no predictive superiority over a benchmark. The research family and benchmark therefore matter. A single winner's ordinary p-value does not express that search-wide hypothesis. [S10]

**PBO.** Bailey and coauthors define backtest overfitting in terms of an in-sample winner ranking below the out-of-sample median among candidates. Their CSCV implementation recombines contiguous slices and complementary halves. PBO is neither probability of an eventual loss nor proof that an execution model is correct. The paper warns about incomplete candidate reporting, incorrect costs/information assumptions, strong dependence, and using PBO as a search objective. Keep CSCV as a supplementary retrospective selection diagnostic; do not train a forecasting model using future observations in order to call its outputs chronological out of sample. [S11]

**DSR.** Bailey and López de Prado adjust a Sharpe rejection threshold for the searched alternatives and non-normal returns. Inputs include the selected return series' length, skewness, kurtosis, Sharpe ratio, dispersion across trial Sharpe estimates, and independent or implied-independent trial count. Annualization conventions must match. Effective trial count is an estimate requiring sensitivity analysis, not an exact tally of every correlated parameter point. A large DSR does not repair an invalid backtest or establish robustness to an unseen regime. [S12]

### Selection-diagnostic acceptance contract

- Maintain a research ledger including unsuccessful feasible candidates, pair-selection alternatives, parameter searches, feature choices, and seed selection. Declare which research process each diagnostic covers.
- Construct candidate return columns causally on the same dates and with the same cost/exposure conventions. Distinguish missing results from genuine zero-position returns.
- For a dependent-data Reality Check design, resample all candidate/benchmark differences with the same time-block indices, preserving joint cross-candidate alignment. Check the exact null centering and statistic against an accessible full paper before claiming a faithful implementation.
- Verify PBO rank direction, median rule, complementary splits, and tie handling using small manually ranked fixtures. Do not treat its combinatorial splits as independent observations when reporting uncertainty.
- Verify a DSR implementation against the paper's worked example; use nonannualized quantities in its calculation and ordinary kurtosis where the formula requires it. Report sensitivity to effective trial count and return dependence.
- Zero variance, too few observations, nonfinite higher moments, and missing trial information produce explicit unavailable/invalid diagnostics rather than arbitrary confident scores.
- These diagnostics accompany a chronological evaluation. Their numerical correctness is an implementation gate; any claimed trading edge requires its own stated evidence and uncertainty.

## 7. Market-making model versus execution simulator

Avellaneda–Stoikov models a diffusive mid-price, quote-dependent Poisson executions, exponential terminal utility, and continuously cost-free quote updates. The commonly used approximation is

`reservation = mid - inventory * gamma * sigma^2 * (T - t)`

`total_spread = gamma * sigma^2 * (T - t) + (2 / gamma) * log(1 + gamma / k)`

for its exponential intensity choice. These equations provide an inventory-aware benchmark, not a complete exchange simulator. Implement the approximation under its stated assumptions rather than labeling all its outputs exact optimal quotes. [S13]

HftBacktest's official documentation explicitly says historical replay does not change recorded market depth and assumes orders small enough to have negligible market impact. Market-by-price data requires a modeled queue position; it does not reveal individual orders. The documentation distinguishes feed latency, order-entry latency, and order-response latency, and warns that partial-fill or liquidity-taking assumptions can still be unrealistic. [S14, S15]

### Model and simulator acceptance contract

- Validate units and domains: `gamma`, volatility, remaining horizon, intensity parameters, tick size, lot size, and inventory. Use a stable `log1p` calculation and a declared branch or limit as `gamma -> 0`.
- At zero inventory, quotes center on the reference mid under the symmetric approximation. Positive inventory lowers the reservation price. The zero-risk-aversion spread limit is `2 / k` under the stated formula.
- Tick rounding, order size, inventory caps, crossing behavior, and whether quotes can become marketable are explicit. Do not apply a passive-fill law unquestioningly to a quote that is already crossing the market.
- No order fills before exchange eligibility; no fill can exceed its remaining quantity. A cancellation takes effect according to its exchange-processing time, so fills before effective cancellation remain possible.
- Account for queue position, price/time priority where applicable, partial fills, fees/rebates, stale quotes, pending orders, and final liquidation. A trade at a matching price alone does not guarantee the strategy's passive fill.
- Check conservation: for a buy of quantity `v` at price `p`, cash falls by `v*p + fee` and inventory rises by `v`; a sell applies the corresponding changes. Marking changes equity but never creates cash or inventory. A matching engine that models both counterparties conserves transfer quantities across them.
- Use handcrafted event sequences for queue exhaustion, an order arriving after a trade, partial execution, cancellation races, and delayed fill knowledge. A strategy cannot condition its next decision on an acknowledgement it has not yet received.
- Estimate volatility, intensity, queue parameters, and latency on training events. Evaluation uses separate events. Compare conservative and probabilistic queue assumptions and stress fees, latency, volatility, and order-flow regimes.
- Label synthetic model evaluation separately from recorded-data replay. Neither is live fill evidence. A replay's small-order assumption does not justify unlimited hypothetical liquidity taking or claim a measured market-impact model.

## 8. CPU ML baselines before RL

Use a constant/mean predictor as a reference, a regularized linear model for a simple signal, and shallow histogram gradient boosting for nonlinear interactions. Scikit-learn documents `DummyRegressor` as a baseline and Ridge as regularized least squares. These choices are recommended starting points, not a claim that one must win on this dataset. [S16, S17]

HGB's default automatic early stopping can activate above 10,000 observations and use a randomized internal validation split. Disable it for the first chronological experiment, or supply an explicit inner chronological validation block when the installed version supports that API. Fit preprocessing and calibration at each training cutoff. [S18]

Stable Baselines3 notes that model-free RL can require many interactions, sometimes millions, and can be unstable and sensitive to random seed. That supports a staged comparison with simple policies and a verified environment; it does not establish that RL is categorically inferior. Any RL evaluation needs separate held-out environments or event periods and several seeds. [S19]

### ML and RL acceptance contract

- Use identical information availability, trading dates, costs, exposure limits, and execution for candidate policies. Include no-trade, a declared simple trading rule, and simple predictive models.
- For continuous targets, compare an appropriate predictive loss against zero and training-mean predictions. For classification, include class-probability baselines and calibration measures. Report predictive metrics separately from costed P&L, turnover, drawdown, and inventory/exposure.
- Limit the feature count and candidate grid before evaluation. Log fitting time, evaluation time, data size, and peak RSS. Run trials sequentially with an explicit numerical-thread cap suitable for the device.
- No model promotion is based on training reward alone. If RL is added, freeze learned normalization during evaluation, distinguish terminal and truncated episodes, retain delayed observations in the state design, and include multiple seeds in the declared research budget.
- A smaller or more complex model is not required to beat every baseline. Honest negative and unavailable results are valid completed experiments.

## 9. Small complete experiments for a 16 GB CPU machine

These are proposed budgets, not measured runtime forecasts or claims of adequate statistical power. Keep the first versions sequential and measure actual memory before increasing them.

| Experiment | Initial scope | Complete deliverable |
|---|---|---|
| Pairs | Ten instruments, about 1,260 aligned daily observations; rolling 756-observation formation, eight successive 63-observation outer tests; three chronological inner splits; 45 predefined pair orientations and a small fixed threshold grid. | Causal selection/fit records, statistical diagnostics, costed two-leg equity, no-trade and predefined distance-rule comparisons, and source/timing limitations. Freeze membership and hedge ratio inside the first version's test blocks. |
| CPU ML | At most 100,000 rows and 32 causal features; dummy, Ridge/logistic, and HGB with about 100 iterations and 15–31 leaves. | Nested chronological predictions, predictive loss/calibration, identical costed trading comparison, trial ledger, and measured resources. A float64 feature matrix alone is 25.6 MB; peak process memory includes many other allocations. |
| Market-making laboratory | One instrument; fixed-spread and inventory-aware policies; about 100 independent synthetic paths of 10,000 events, streamed path by path. | Conservation and timing fixtures, inventory/drawdown/fill/fee/liquidation measurements, and paired comparisons using common exogenous randomness. Add a small separate recorded-event replay only when suitable depth, trades, and timestamps are available. |
| Selection-bias laboratory | Seeded null and weak-signal candidate-return fixtures, using the same declared search/evaluation process. | In-sample selection versus chronological evaluation, plus provisional Reality Check and CSCV/PBO diagnostics. Twelve CSCV slices yield 924 half-sample combinations; do not infer 924 independent pieces of evidence. |

Consider an initial peak-RSS ceiling below 12 GiB to leave room for the desktop and operating system. This is a proposed operational limit, not evidence of current device headroom. Store bar/event data in compact arrays, stream paths/days, and avoid retaining all path histories or running many independent training processes simultaneously.

## 10. Source registry and access limits

All links below were checked through research retrieval on the date above. Citation identifiers are internal labels for this document.

| ID | Primary source | Retrieval status and use |
|---|---|---|
| S1 | [Statsmodels: `coint`][S1] | Official API documentation read: test, null, assumptions, MacKinnon approximation, collinearity, missing-data limitation. |
| S2 | [Statsmodels: `adfuller`][S2] | Official API documentation read: unit-root null and inference. |
| S3 | [MacKinnon: Critical Values for Cointegration Tests, 2010][S3] | Primary university paper listing found. Several university PDF endpoints were inaccessible; no claim of inspecting its full tables here. |
| S4 | [MacKinnon: Approximate Asymptotic Distribution Functions, deposited precursor][S4] | Deposited working-paper record read; PDF retrieval failed. Implementation claims are corroborated by S1/S2. |
| S5 | [Statsmodels: `multipletests`][S5] | Official documentation read: available correction methods. |
| S6 | [Scikit-learn: nested versus non-nested CV][S6] | Official example read for general tuning/evaluation separation; its Iris split is not the proposed chronological splitter. |
| S7 | [Scikit-learn: common pitfalls][S7] | Official guidance read for train-only fitting and pipelines. |
| S8 | [Scikit-learn: `TimeSeriesSplit`][S8] | Official API documentation read for ordered splits, gap, and observation-spacing conditions. |
| S9 | [López de Prado: The 10 Reasons Most Machine Learning Funds Fail][S9] | Author's paper hosted by GARP; PDF available and relevant sections read for purge/embargo and walk-forward limitations. |
| S10 | [White: A Reality Check for Data Snooping, 2000][S10] | Publisher abstract read. Accessible retrieval did not provide full algorithm text; exact bootstrap/null-centering reproduction remains a prerequisite before implementation claims. |
| S11 | [Bailey et al.: The Probability of Backtest Overfitting][S11] | Author-hosted PDF available; relevant definitions, CSCV, ranks, limitations, and misuse sections read. |
| S12 | [Bailey and López de Prado: The Deflated Sharpe Ratio][S12] | Author-hosted PDF available; relevant inputs, worked-example conventions, and implied-independent-trials sections read. |
| S13 | [Avellaneda and Stoikov: High-frequency trading in a limit order book][S13] | Author-hosted 2006 manuscript PDF available and relevant assumptions/formula sections read; journal publication was in 2008. Formulas above refer to the manuscript's approximation. |
| S14 | [HftBacktest: Order Fill][S14] | Official documentation read: replay assumptions, queues, partial fills, and impact limitations. |
| S15 | [HftBacktest: Latency Models][S15] | Official documentation read: feed, entry, response, and calibration data. |
| S16 | [Scikit-learn: `DummyRegressor`][S16] | Official baseline documentation read. |
| S17 | [Scikit-learn: `Ridge`][S17] | Official regularized-regression documentation read. |
| S18 | [Scikit-learn: `HistGradientBoostingRegressor`][S18] | Official API documentation read, including validation and randomness controls. Verify installed-version support for explicit validation data. |
| S19 | [Stable Baselines3: RL Tips and Tricks][S19] | Official guidance read for sample requirements, instability, seeds, and evaluation. |
| S20 | [Engle and Granger: Co-Integration and Error Correction, 1987][S20] | Primary JSTOR record found; full text inaccessible in this retrieval. No attribution to uninspected passages. |

No local code was evaluated for strategy profitability in this research. Published empirical results were not transferred into a forecast for this engine. More simulations reduce simulation sampling noise under an assumed model; they do not establish the model's realism, remove selection bias, or supply unobserved market regimes.

[S1]: https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.coint.html
[S2]: https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.adfuller.html
[S3]: https://www.econ.queensu.ca/research/working-papers/1227
[S4]: https://ageconsearch.umn.edu/record/273255
[S5]: https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html
[S6]: https://scikit-learn.org/stable/auto_examples/model_selection/plot_nested_cross_validation_iris.html
[S7]: https://scikit-learn.org/stable/common_pitfalls.html
[S8]: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
[S9]: https://www.garp.org/hubfs/Whitepapers/a1Z1W0000054x6lUAA.pdf
[S10]: https://onlinelibrary.wiley.com/doi/10.1111/1468-0262.00152
[S11]: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf
[S12]: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
[S13]: https://people.orie.cornell.edu/sfs33/LimitOrderBook.pdf
[S14]: https://hftbacktest.readthedocs.io/en/latest/order_fill.html
[S15]: https://hftbacktest.readthedocs.io/en/latest/latency_models.html
[S16]: https://scikit-learn.org/stable/modules/generated/sklearn.dummy.DummyRegressor.html
[S17]: https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html
[S18]: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html
[S19]: https://stable-baselines3.readthedocs.io/en/master/guide/rl_tips.html
[S20]: https://www.jstor.org/stable/1913236
