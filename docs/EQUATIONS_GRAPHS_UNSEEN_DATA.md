# QuantEngine: Equations, Graphs and Unseen-Data Readiness

**Audit scope:** repository source modules examined on 2026-10-12. This inventory distinguishes algorithms implemented in source from research proposals. Formula names describe the model family; the exact code and numerical conventions are authoritative. None of these alone demonstrates predictive value on new market data.

## Mathematical inventory — implemented systems

| System | Core equations / assumptions | Code | Required unseen-data check |
|---|---|---|---|
| Simple price returns | \(r_t=P_t/P_{t-1}-1\); adjusted-price/total-return input conventions matter | `quant_core.price_returns` | No future closes at prediction time; splits/dividends adjusted correctly |
| Covariance portfolio allocation | \(w=\Sigma^{-1}\mathbf 1/(\mathbf 1^T\Sigma^{-1}\mathbf 1)\), under unconstrained minimum variance; regularized/diagonal shrinkage covariance and rebalancing costs | `quant_core.minimum_variance`, `walk_forward` | Fit covariance on strictly prior data; compare equal weight/cash after realistic costs |
| Covariance shrinkage | \(\hat\Sigma=(1-\lambda)S+\lambda\operatorname{diag}(S)\) | `quant_core.analyse` | Select shrinkage from past windows, not future |
| Geometric wealth versus linear P&L | True compounded wealth \(W_T=W_0\prod_t(1+r_t)\); linear price-risk approximation sums returns | `quant_core.simulate_risk`, `bootstrap_risk` | Distinguish approximation from compounded portfolio loss, especially long horizons |
| Normal and Student-t return risk | \(\mathrm{VaR}_p=-[\mu+\sigma F^{-1}(p)]\); \(\mathrm{ES}_p=-E[r\mid r\le -\mathrm{VaR}_p]\) | `quant_core.student_t_risk`, `empirical_tail` | Tail calibration and ES realized-loss scoring on withheld returns |
| Historical / filtered bootstrap Monte Carlo | Empirical return draws, Monte Carlo path aggregation, random seeds, tail quantiles | `quant_core.bootstrap_risk`, `simulate_risk` | Withheld volatility regimes, cost/stress sensitivity, MC uncertainty |
| Heavy-tail Hill estimator | \(\hat\alpha=[k^{-1}\sum_{j=1}^{k}\ln(X_{(j)}/X_{(k+1)})]^{-1}\) (positive tail magnitudes) | `quant_core.hill_tail_index` | Holdout tail index instability across window sizes |
| Risk forecasting backtests | Exception indicator \(I_t=1[r_t<-\mathrm{VaR}_{t|t-1}]\); Kupiec likelihood-ratio unconditional coverage; Christoffersen independence and conditional coverage | `quant_varbacktest.kupiec_christoffersen`, `rolling_var_levels` | Record forecast before outcome; cluster, regime and fat-tail adversarial cases |
| GARCH and GJR | \(\sigma_t^2=\omega+[\alpha+\gamma 1(r_{t-1}<0)]\epsilon_{t-1}^2+\beta\sigma_{t-1}^2\); Student-t innovations and constrained MLE | `quant_varbacktest.fit_garch_t`, `garch_filter` | Fit only past returns, convergence checks, independent volatility shocks |
| Filtered historical simulation | Standardized residuals \(z_t=(r_t-\hat\mu)/\hat\sigma_t\), next-tail forecast \(\hat\mu+\hat\sigma_{t+1}Q_p(z)\) | `quant_varbacktest.rolling_var_levels(method='gjr_fhs')` | Non-Gaussian asymmetric unseen tail scenarios |
| Black–Scholes | \(C=S N(d_1)-Ke^{-rT}N(d_2)\); \(d_1=[\ln(S/K)+(r+\sigma^2/2)T]/(\sigma\sqrt T)\) | `quant_options.black_scholes` | Analytic identities, dividends/convention checks, not confused with realized forecasting |
| Cox–Ross–Rubinstein binomial tree | \(u=e^{\sigma\sqrt{\Delta t}},d=1/u,q=(e^{r\Delta t}-d)/(u-d)\); backward discounted expectations and possible American exercise | `quant_options.crr_price` | Tree-step convergence, early exercise benchmark |
| Options Monte Carlo | Discounted simulated payoff mean, standard error, path-number convergence | `quant_options.monte_carlo_price` | Independent seeds, analytic BS reference under matching assumptions |
| Implied volatility and surface | Numerically solve option price = observed market option price; SVI/SSVI parameterized total variance \(w(k,T)\) | `quant_options.implied_volatility`, `fit_svi`, `ssvi_surface` | Hold out strikes/maturities; arbitrage and stale quote constraints |
| Pairs stationarity | ADF regression \(\Delta y_t=\rho y_{t-1}+\sum_i\phi_i\Delta y_{t-i}+\epsilon_t\); Engle–Granger spread residual stationarity | `quant_pairs.adf`, `engle_granger`, MacKinnon critical values/p-values | Rolling formation/trading split; multiple-comparison correction; size under random-walk null |
| Pairs execution and discovery | Hedge regression, spread z-score and half-life, Holm adjustment; turnover, borrow and trading costs | `quant_pairs.select_pairs`, `pairs_backtest` | Previously undisclosed markets, next-close execution, selection bias |
| Market making | Avellaneda–Stoikov reservation price \(r=S-q\gamma\sigma^2(T-t)\) and spread approximations involving \(2/\gamma\ln(1+\gamma/k)\); Poisson fills | `quant_lob.avellaneda_stoikov_quotes`, `simulate` | Exogenous order flow, latency, tick, queue, fees, adverse selection |
| Alpha models | Baseline zero/mean; penalized ridge \(\hat\beta=(X^TX+\lambda I)^{-1}X^Ty\); tanh MLP trained by Adam with chronological early stopping | `quant_evolve.alpha_task`, `MLP` | Train-only feature scaling, unseen return streams, baseline and CI |
| Evolutionary model search | Mutation/crossover plus fitness on earlier windows; independent adoption windows under `guard=True` | `quant_evolve.Evolution`, `prequential` | Freeze choices before block, no future experience, selection/adoption isolation |
| Evidence gate | Weighted fitness \(\sum_i\lambda^i s_i/\sum_i\lambda^i\); guarded adoption uses mean advantage minus two sample SE on separate past windows | `quant_evolve.prequential` | Serial dependence and many-model selection still require stronger inference |

## Graph and visualization inventory

1. **Historical wealth / equity curves:** cumulative realized/strategy return versus benchmark; never plot simulated performance as realized.
2. **Risk distributions:** simulated Monte Carlo loss histogram/density, VaR and ES tail thresholds, empirical observed tails.
3. **Volatility over time:** rolling and conditional GARCH forecast \(\sigma_t\), realized volatility and stress overlays.
4. **VaR exception chart:** forecast lower quantile vs realized daily returns, with flagged exceptions and time ordering.
5. **Volatility surface:** implied volatility or total variance over strikes/moneyness and expiries (SVI/SSVI), with observed versus fitted points.
6. **Options convergence charts:** binomial-tree steps and Monte Carlo paths versus analytical reference and estimation uncertainty.
7. **Pairs charts:** two normalized price paths, residual spread, rolling z-score, exposure/trade P&L and drawdown.
8. **Market-making graphs:** inventory over time, mean ± variability of terminal P&L, simulated fills and friction ablations.
9. **Evolution lineage graph:** nodes representing genomes/champions and directed mutation/crossover/elite relationships; visually distinguish searched models from deployed models.
10. **Prequential learning curves:** frozen champion versus baseline per *chronologically forward* block, with attribution of model changes.
11. **Calibration plots:** empirical exception rate vs nominal tail probability; uncertainty bands, independent period breakdowns.
12. **Unseen-data audit graphs (to add):** per-block MAE/MSE relative to zero baseline, cumulative score difference, number of fresh vs exposed points, 5-year holdout regime annotation, and calibration after transaction costs.

Not all listed graphs are currently rendered in the desktop UI. Existing graph/data plumbing must be audited separately before claiming feature completeness; this is an architectural graph inventory, not a screenshot inventory.

## What genuinely unseen means

**Five conditions** must all hold:

- *Data availability*: no future return, revised macro observation, outcome, publication date, or target-derived feature can enter a fit or decision at forecast time.
- *Unexposed evaluation*: there is an entirely new block not previously read, selected on, optimized against, or replayed by the candidate team.
- *Frozen implementation*: source, parameters, seed policies, preprocessing and statistical acceptance rules are recorded and sealed before outcomes are revealed.
- *Independent custody*: candidate cannot read hidden future labels, judge files, dataset secrets, or evaluator network resources. A tuple-prefix Python evaluator alone is not an OS sandbox.
- *Forward metrics*: timestamps, misses, fees, uncertainty and baseline comparisons are computed externally after forecasts are committed.

## Implemented protocol interfaces

- `experiments/sequential_unseen.py`: stepwise predictor receives immutable tuples of *past* observations only; result scored after collecting predictions. Reuse prohibited via `ExposureLedger`. Not safe against malicious Python closure/filesystem access.
- `experiments/blind_judge.py`: external evaluation against sealed numeric targets, checksum verification and block exposure ledger. Requires independently operated, restricted custody.
- `experiments/verify_acceptance.py`: fail-closed checks; CI removes stale results so checks cannot silently pass on a previous JSON result.

To verify a genuinely fresh period, use an independent producer that starts streaming data **after code freeze**, never expose market labels or unpublished synthetic generators to the candidate, and retire each interval immediately after first scoring. Evaluate newly arriving data prospectively; historically withheld data cannot become truly unpublished once read.

## Known current validation blockers

- AIC lag-selection Engle–Granger null size did not meet the precommitted binomial-size band. Do **not** change the band retrospectively to make CI green; investigate theoretical size, finite sample critical values and conditional lag search.
- Reproducing the Avellaneda–Stoikov published gamma=0.5 inventory-profit benchmark fails under the stated strategy. The experiment explicitly reports this discrepancy. Do not force a match by tuning a coefficient against the target.
- Neither problem is evidence that live-market predictions work. Keep these experiment acceptance failures visible until independently justified resolution or an explicitly documented distinction between known reference mismatch and a required product safety criterion.

## Further statistical research, not implemented

Hansen SPA, Model Confidence Set, PBO / CSCV, Deflated Sharpe, dynamic quantile and expected-shortfall testing, point-in-time FRED/ALFRED release-vintage alignment, Sobol quasi-Monte Carlo, Ledoit–Wolf covariance, Kalman/VECM cointegration, American Longstaff–Schwartz, Heston simulation. All are proposed research, **not existing features**.

## Audited additions

Stationary bootstrap, a White-style reality-check diagnostic and Bartlett HAC for a mean are now implemented in `quant_model_selection.py` (not Hansen SPA or a general covariance estimator). Fixed daily rules and exact next-close cost equations are documented in `STRATEGY_VALIDATION.md`; historical outputs are development evidence.
