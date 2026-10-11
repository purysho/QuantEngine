# Research index: from the supplied curriculum to code and evidence

Every topic from the supplied learning list is mapped to where it lives in QuantEngine, how it is verified, and what is still missing. "Verified" means a test or measured experiment in this repository, not a reading note. Experiment JSON files are in `experiments/results/` and record seeds, data hashes, runtime versions and acceptance gates.

## Mathematics and statistics

| Topic | Where | Verification | Open gaps |
| --- | --- | --- | --- |
| Probability, expected value | Monte Carlo risk (`quant_core`), option expectations (`quant_options.monte_carlo_price`) | Monte Carlo is within 3 SE of the analytic price; SE shrinks by √10 per 10× paths (`options_reference.json`) | — |
| Conditional probability and Bayes | Expected shortfall is a conditional expectation `E[−X \| X ≤ VaR]`. Holm/Bonferroni treats p-values as conditional on the null | Exact fractional-tail ES fixture (ES = 7) | No Bayesian model (e.g. shrinkage priors or a Bayesian ridge) yet |
| Combinatorics | Binomial tree path counts (CRR), ordered pair enumeration `n(n−1)` in `select_pairs`, which drives the multiple-testing burden | Tree convergence; Holm tests | — |
| Binomial distribution | CRR risk-neutral up-probability; binomial mid-price walk in the LOB simulator; binomial ±3σ bands for test size | Hull's 5-step American put = 4.49 | — |
| Lognormal distribution | GBM terminal price `S·exp((r−q−σ²/2)T + σ√T·Z)` in Monte Carlo and Black–Scholes | Haug/Hull reference prices | Lognormal is the BS assumption, not an empirical claim |
| Poisson distribution | Market-order arrivals `λ(δ) = A·e^{−kδ}` (`quant_lob`) | Reproduces 5 of 6 Avellaneda–Stoikov rows within 1.3% | γ = 0.5 inventory row not reproduced (`market_making.json`) |
| Student-t distribution | `student_t_risk`: MLE fit, horizon simulation, closed-form one-day ES | Heavier VaR99/ES99 than Gaussian on t(3) data; analytic and simulated quantiles agree | iid only; no GARCH-t |
| Pareto distribution | `hill_tail_index` on daily losses, reported over several k | Recovers α = 3 ± 0.3 on Pareto samples | Hill is k-sensitive; no peaks-over-threshold/GPD fit |
| Value at Risk | `empirical_tail`: lower inverse-CDF VaR and exact-mass ES at 95/99%, under Gaussian, block bootstrap and Student-t | Ties, fractional boundary, float rounding (5% of 100) | Kupiec/Christoffersen backtests in `quant_varbacktest` (`var_backtest.json`): Gaussian 99% fails on fat tails; all static windows fail independence under GARCH clustering. GARCH(1,1)-t fixes it: 1.01 exception ratio with nominal 5% independence rejections |
| Black–Scholes | `black_scholes`, with all Greeks including vanna/volga; implied vol by Brent | Published references, put–call parity, every Greek against finite differences, IV round trip from 5% to 250% | — |
| Binomial trees | `crr_price`, European and American | O(1/N) convergence; American ≥ European; no early call exercise without dividends | No discrete dividends |
| Monte Carlo | Gaussian/bootstrap/t risk; antithetic option pricing; LOB paths | Seeded reproducibility, SE scaling | No quasi-Monte Carlo or control variates |
| Cointegration | `quant_pairs`: ADF, Engle–Granger, MacKinnon 1994/2010 inference, Holm selection | Matches statsmodels to 1e-13; measured size and power (`pairs_cointegration.json`) | AIC lag search over-rejects (7.1% at 5%), so BIC is used for screening. No Johansen test or dynamic hedge |
| Walk-forward testing and no data leakage | Next-close execution in `walk_forward` and `pairs_backtest`; purged chronological ridge with information clocks (`quant_validation`) | Signal-close tests, prefix-invariance tests, holdout cannot affect selection, a leaked feature is rejected (with a falsified clock it would have scored R² 0.99999998) | No combinatorial purged CV |
| Statistics and distributions | Skew, excess kurtosis, Campbell–Thompson OOS R², hit rates | `first_alpha.json` null vs signal distributions over 200 seeds | Newey–West standard errors for strategy means (see nexustrade-py below) |
| Linear algebra | Covariance and shrinkage, PSD checks, ridge normal equations, OLS via least squares | Analytic 0.8/0.2 minimum-variance allocation; coefficient recovery | — |
| Calculus and optimisation | Greeks as derivatives; SLSQP minimum variance; Brent root-finding; SVI least squares | Finite-difference Greeks; SVI recovery RMSE < 1e-6 | — |
| Stochastic processes | GBM, random walks, AR(1)/Ornstein–Uhlenbeck spreads and half-life, Poisson point processes | Half-life recovery; size/power by AR coefficient | — |
| Game theory | Market making as a game against informed flow: adverse-selection moves after fills, and inventory-averse quoting | Friction ablation: queue position is the largest friction; adverse selection hurts symmetric quoting most | No strategic (Glosten–Milgrom/Kyle) equilibrium model |
| "VIX / 16 = S&P move" | `implied_move` | Test: σ/16 vs σ/√252 (= σ/15.87); expected absolute move ≈ 0.80σ; ±1σ holds about 68% of days | VIX is 30-day implied variance under Q, not a forecast of realised volatility |

## Similar projects folded into QuantEngine

| Project | Status |
| --- | --- |
| Options pricing, Greeks, volatility surfaces | Done: analytic, tree and Monte Carlo pricing; IV; per-expiry raw SVI; vertical/butterfly/calendar arbitrage checks; desktop Options page. Surfaces are API-only (no surface page yet) |
| Pairs-trading backtester | Done as a module and experiment: formation-only fit, Holm selection, next-close execution, share-based legs, costs, borrow, stops, liquidation |
| Limit-order-book market-making simulator | Done as a module and experiment: Avellaneda–Stoikov with FIFO queue, partial fills, latency, tick, fees, adverse selection and inventory limits |
| Machine-learning alpha signal | Done for linear ridge with an information-clock protocol. Nonlinear models (gradient boosting) should reuse the same protocol |

## Supplied repositories

Detailed audits: `REPO_AUDIT_ENGINES.md` (FinRL, OpenBB, congressional-disclosures, QUANTAXIS) and `AI_RESOURCE_AUDIT.md` (grok-build, agent-skills, Muse-Glimmer, institutional AI resources). Additions from this session:

| Repository | Inspected | What QuantEngine takes | What it does not take |
| --- | --- | --- | --- |
| `austin-starks/chrono-ta` | `39141072`, 2026-09-22, MIT (Rust) | The idea of **elapsed-time windows** (a 30-day window means calendar time, not 30 rows), same-bucket replacement, and streaming/batch parity tests. QuantEngine currently uses observation-count windows on equally spaced closes and says so in its methodology | No Rust dependency |
| `austin-starks/nexustrade-py` | `61c2d455`, 2026-10-11, MIT | Candidate statistics: `newey_west_slope`, `benjamini_hochberg`, `block_bootstrap_corr`, `spec_curve` (specification curves) and session-calendar alignment | The SDK is a client of the hosted NexusTrade platform (API key); not a local engine dependency |
| `numpy/numpy`, `scikit-learn/scikit-learn`, `matplotlib/matplotlib` | Pinned NumPy 2.3.5 is the core runtime; scikit-learn docs informed `TimeSeriesSplit`/`Ridge` semantics (`VALIDATION_EXECUTION_RESEARCH.md`) | NumPy only; ridge is implemented in about 30 lines rather than adding scikit-learn to the Windows runtime | No matplotlib: the desktop draws on canvas |
| FinRL, OpenBB, QUANTAXIS, congressional-disclosures | See `REPO_AUDIT_ENGINES.md` | Provider-interface and testing ideas; disclosure-snapshot provenance | DRL, aggregate stacks, NumPy < 2 pins, paid OCR paths |

## Books

*Crisis Engineering*, *The Infinity Machine* and *AI for Good* were named in the request, but their full texts are not available to this project. Nothing in QuantEngine is attributed to their content, and no summary is offered. If the texts or notes are supplied, specific ideas can be mapped into this index with page references.

## Additional resources

AIA Macro (Bridgewater), Alpha-GPT, the Citadel AI assistant and Balyasny's tools are institutional programmes or papers without downloadable systems (see `AI_RESOURCE_AUDIT.md`). The transferable idea is in place in the Quant half: generate a candidate signal, then judge it **only** through a pre-registered chronological protocol with baselines, a candidate ledger and leak controls (`quant_validation`, `first_alpha.json`). Muse-Glimmer-30B (about 59.6 GB full precision) does not fit the 16 GB integrated-graphics laptop and belongs to the separate AI-workspace track, which is out of scope here.

## Next research steps (ranked)

1. ~~VaR exception backtests~~ and ~~GARCH(1,1)-t conditional VaR~~ (done; Tasks 8 and 10).
2. Newey–West standard errors and a deflated Sharpe ratio for every reported strategy mean.
3. Specification curve across lookback/rebalance/cost so parameter choice is visibly not cherry-picked.
4. GARCH(1,1)-t volatility for risk; a Kalman-filter hedge ratio for pairs, evaluated with the same clocks.
5. Desktop pages for pairs, market making and alpha, using the shared worker slot.
6. Elapsed-time windows (chrono-ta semantics) for irregular CSV data.

## Real-data evidence and the learning system (added)

- `experiments/results/real_world_backtest.json`: 100 years of CRSP US-market data, the VIX/16 rule, Black–Scholes priced at VIX vs realised payoffs, Brent–WTI cointegration through the 2020 negative price, and industry momentum since 1926. GJR-GARCH filtered historical simulation is the best VaR model on real data.
- `experiments/results/evolution_real.json`: prequential evolutionary learning (v1 → v3) with an honest comparison against the best fixed choice in hindsight.
- Additional references are triaged in `WORK_LOG.md` Task 17.
