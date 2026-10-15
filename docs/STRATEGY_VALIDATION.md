# Trading-strategy validation — frozen daily research tranche

This extends the existing chronological experiment flow, not the desktop or brokerage feature set. User purpose: test realistic named strategy families, report mistakes, and protect unseen observations. No additional dependency, parameter search, automatic adoption or trading integration is introduced.

## Predeclared daily rules and equations

All are long/cash. At close s the rule sets a target; execution occurs at close s+1 and first earns the s+1 to s+2 return. Costs are 10 bps per changed notional with 0/25 bps sensitivity, charged at execution; final holdings are liquidated with costs. Cash earns zero. State carries through calendar blocks, with no fictitious five-year liquidations.

| Rule | Explicit definition |
|---|---|
| MA crossover | Long when trailing inclusive SMA20 > SMA50, otherwise cash; first signal after 50 closes. SMA_n = sum of the last n closes / n. |
| RSI thresholds / range oscillator | Wilder14: seeded average gains/losses over 14 differences, then A_t=(13 A_(t-1)+x_t)/14. RSI=100-100/(1+G/L). Enter below 30, exit above 70; flat=50, gains-only=100, losses-only=0. |
| Bollinger mean reversion | Inclusive SMA20 ± 2 population standard deviations (ddof=0). Enter below lower band, exit at/above SMA20. No assertion that a band is a normal 95% interval. |
| MACD | EMA12-EMA26 vs EMA9 of that difference; EMA alpha=2/(n+1), first-price causal seed, warmup 34 closes. Long while MACD > signal. |
| Volatility breakout | Enter when close exceeds previous 20-close maximum and current log-return exceeds 2 times SD of the preceding 20 log-returns (ddof=1); exit below inclusive SMA20. This is our fixed daily variant, not ORB. |

EMA seeding conventions vary between vendors; these exact conventions are part of the frozen rule. No claim that these trading rules are uniquely or canonically optimal.

Primary references checked 2026-10-12:
- Fidelity RSI formula and 30/70 convention: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI
- Fidelity Bollinger price envelopes: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands
- Fidelity MACD: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd
- Chronological splits and gap concept: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- Kenneth French daily total-market source: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_daily_CSV.zip

The books named earlier are not available as full texts; no claim of reading or implementing all textbook research is made.

## Reproduce

```sh
python -m unittest tests.test_strategy_validation -v
python -m experiments.strategy_five_year
python -m experiments.strategy_five_year --offline
```

Source snapshot is pinned and hash-verified by the existing data adapter. The experiment stores source SHA-256, URL, retrieval time, commit and rule-source hash in `experiments/results/strategy_five_year.json`. Raw vendor data remains in `.cache/data` and is not committed. CRSP-derived Mkt-RF + RF is compounded into a daily total-return research index. This is **not an executable security**; it cannot support individual-stock, intraday or futures-fill claims. Any source methodology changes or revisions are part of snapshot uncertainty; this is not point-in-time vintage certification.

All five fixed rules are evaluated on the same source dates. Reports retain every block's net/gross/cost-stressed returns, buy-and-hold/cash baselines, drawdown, paired HAC excess-return uncertainty and a multiple-rule stationary-bootstrap diagnostic. Return scores are not point-forecast MSE. Comparisons use HAC lag 5, mean bootstrap block 5, 500 repetitions, seed 17; there is no search for favorable bandwidths. Per-block nominal statistics are not adjusted across repeated windows/costs; none establishes alpha.

## Observed result and mistake policy

Snapshot 1926-07-01 through 2026-08-31, SHA-256 `2f29e22546069914890a712680a6f81f3680ebc3543b52864484d209ca13a7db`. Nineteen complete windows (1930–2025), partial 1925–1930 and 2025–2030. At 10 bps, numbers of complete windows beating buy-and-hold were MA **4/19**, RSI **1/19**, Bollinger **1/19**, MACD **1/19**, volatility breakout **3/19**. These losses are evidence, not CI bugs. Do not delete poor windows, tune thresholds to erase losses, or label already public data “unseen”.

Per-window cost drag and realized opportunity gaps diagnose *what* contributed numerically; they do not establish *why* a market regime occurred. Model redesign requires a falsifiable hypothesis and a newly reserved adoption sample. Deterministic software errors are fixed with synthetic regressions before rerunning history; reruns remain development. Truly unseen testing still needs frozen code and independent future-label custody.

## Applicability gates for remaining requested families

| Family | Current status and required evidence |
|---|---|
| 3-session FX system | Not a fully specified trading algorithm. Needs Asian/London/New York session definitions, explicit entry/exit rules, time-zone/DST calendars, intraday FX bid/ask and costs. No daily-close substitute. |
| Opening range breakout | Not evaluated: requires intraday OHLCV, exchange opening calendar, opening-range duration and next-bar fill/stop ordering. |
| Breakout-retest confirmation | Not evaluated: define breakout, retest tolerance, confirmation and expiry; validate intrabar order uncertainty and fills. |
| Range oscillators | Fixed RSI long/cash variant evaluated; no invented range-regime oracle. |
| ML signal ensembles | Existing chronological ML/evolution experiments remain, including underperformance. A new frozen ensemble requires separate selection/adoption data and independent outcomes. |
| Statistical arbitrage | Existing pairs tests/results retained; paper/synthetic and oil reference prices cannot establish executable trading alpha. Need synchronized tradable legs, borrow availability and structural-break tests. |
| Volatility breakout | Fixed daily variant evaluated; no statement that it implements intraday ORB or any proprietary rule set. |
| Gap-and-go earnings | Not evaluated: earnings publication time, premarket/open prices, volume, spreads and a point-in-time universe incl. delistings are absent. |
| News/catalyst driven | Not evaluated: original publication timestamps, revisions, latency and price observations must be independently archived before outcomes. No retrospective sentiment from later summaries. |

## Five-phase status after this tranche

1. Pipeline: exclusive journals, durable processing status and bounded ACK failures tested. Automatic restart/backfill, filesystem crash atomicity across files and independent live health remain open.
2. Data: real French source fetched, historical rules evaluated. Real intraday equities/FX/event data and external vintage custody remain absent.
3. Evidence: recomputed losses and cross-platform reveal locking tested. External timestamps, protected labels and signing still need custodian infrastructure.
4. Statistics: negative historical results preserved with baseline/uncertainty/multiple-rule diagnostics. AIC/null-size, published market-making mismatch and incumbent alpha failure remain documented.
5. Product: no UI complexity added. CI/security/native-package checks require current-head verification. No production tag or release is created by this experiment.
