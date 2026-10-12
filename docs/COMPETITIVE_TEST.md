# Competitive test: situation-dependent decisions

## The actual experiment

Daily USD total-return research proxies for the CRSP broad US market and Nasdaq-100, plus compounded realized French RF cash income. These are not executable ETF bid/ask prices. Raw source files remain private in the hash-verified cache. Common closing dates end on **2026-08-31**, because the pinned broad-market source ends then; later available Nasdaq dates are excluded equally from all comparisons.

- Selection: 2000–2009; adoption: separate 2010–2014.
- Competitive evaluation: **2015-01-02 to 2026-08-31**, with a common preceding-close starting point, fresh starting capital and matching entry/exit cost convention.
- Context uses trailing prices only; candidates do not see their future period outcomes. Initial selection contains conservative indicator warmup; formal evaluation has full prior history.
- Three fixed candidates were frozen before the replay: situation router, volatility-capped router, and momentum rotation.
- Risk controls, known seeds, thresholds, fees, code hashes and exact source copies are retained in the protocol/evidence folders.
- Model selection and separate adoption both failed against the full-equity benchmarks. All following candidate paths are explicitly **shadow research**, not adopted or live accounts.

### State and transaction rules

1. Compute broad-market SMA200, 20-close efficiency ratio `abs(P_t-P_(t-20))/sum(abs(delta P))`, annualized 20-close log-return volatility, Wilder RSI14 and both assets' 126-close momentum using closes through t.
2. **Stress:** broad price below SMA200 and trailing volatility >25%; target cash.
3. **Trend:** broad price above SMA200 and efficiency ≥0.25; choose the better positive-momentum equity proxy.
4. **Range:** otherwise; mean-reversion broad exposure enters below RSI40 and exits above RSI60. This deliberately simple range definition is an unproven classifier, not a hindsight regime oracle.
5. Dispatch every fifth close or immediately on a stress observation. The volatility-capped variant limits exposure to `min(1,0.15/trailing sigma)` with a 5% weight-change band. The rotation comparator chooses positive momentum every 21 closes.
6. A signal computed after close s executes at close s+1; its first risky return is s+2. Every switch and final liquidation pays costs. Cash receives actual RF for the holding interval without using future RF as a model feature.

The accounting is self-financing on **actual** traded risky notional:

`W_after = W_before - c * sum(abs(target_weight * W_after - prior_risky_value))`

The fixed-point equation has a unique solution for the tested costs and unlevered targets. Cash is the residual capital. This prevents overinvesting while separately deducting fees or omitting a two-leg switch. No leverage, short-sale financing or borrowed capital is modeled.

## Matched results at 10bps per traded notional

Returns below are hypothetical, calendar-annualized, after the stated trading costs. Volatility and Sharpe use 252 observations/year; Sharpe subtracts realized cash income.

| Portfolio | CAGR | Volatility | Maximum drawdown | Sharpe |
|---|---:|---:|---:|---:|
| Broad-market buy-and-hold | 13.76% | 18.12% | −34.22% | 0.689 |
| Nasdaq-100 buy-and-hold | 19.20% | 22.12% | −35.04% | 0.813 |
| Situation router | 10.76% | 13.09% | −21.31% | 0.689 |
| Router with volatility cap | 9.60% | 10.92% | −15.28% | 0.706 |
| Momentum rotation | 11.89% | 18.31% | −27.71% | 0.594 |
| Broad-market passive rolling volatility cap | 11.32% | 13.26% | −19.63% | 0.721 |
| Nasdaq passive rolling volatility cap | **15.10%** | **14.82%** | **−20.90%** | **0.885** |

The strong passive rolling-volatility controls were added after inspecting the initial replay; this extension is **exposed development**, not a new untouched test. Candidate rules did not change. These controls use the same lookback, risk target, dispatch and weight-band conventions. They expose why lower drawdown alone cannot be attributed to clever state switching.

The Nasdaq control's observed Sharpe improvement over full Nasdaq was only **0.0727**. Paired stationary-bootstrap percentile 95% intervals include zero for mean blocks5/20/60 (approximately −0.11 to +0.27, −0.11 to +0.25, −0.11 to +0.23). Do not call it a proven forward risk-adjusted advantage. It is a promising risk-control direction with a visible return/protection trade-off.

### Five-year checks and uncertainty

2015–2019 router growth5.59% vs broad11.56% and Nasdaq16.92%; 2020–2024 router16.97% vs broad14.30% and Nasdaq20.17%. Later partial 2025–2026 router8.50% vs broad18.89% and Nasdaq23.26%. The router's apparent success in one five-year interval did not persist.

Multiple-model stationary-bootstrap diagnostics found no significant excess-return advantage against full-equity buy-and-hold (p=1.0). No candidate passed separate adoption. State-conditioned comparisons preserve the original daily time grid and use ratio-mean HAC uncertainty plus Bonferroni adjustment over 54 model/state/benchmark comparisons. None has a positive family-adjusted lower bound.

## Why the current dispatchers lost ground

- **Range identification:** low 20-day efficiency is not proof of a sideways market. Upward markets can be noisy. Sending those observations to an RSI strategy creates avoidable cash exposure and misses growth.
- **Stress timing:** volatility/200-day indicators react after prices have moved. In the observed stress-labeled days, subsequent index rebounds often made staying in cash costly. The test retains those misses; it does not pretend the first crash was predicted.
- **Fees:** router gross CAGR13.25% fell to10.76% at10bps and7.11% at25bps; capped router11.92→9.60→6.20%. Rotation's lower-turnover figures12.39→11.89→11.14% were less fee-sensitive. Execution quality matters, but even zero modeled costs did not give a clear router advantage over the full Nasdaq benchmark.
- **Asset choice / beta:** choosing Nasdaq exposure can raise equity returns because of concentration and market exposure. It does not establish model alpha. The stronger controls reveal that continuous risk sizing deserves testing before more regime-switching complexity.

These are falsifiable design diagnoses and accounting evidence, not proof of why markets moved. Do not redefine regimes using later realized returns or tune the same sample until it wins.

## Comparisons with competitors

### AI-based fund example: AIEQ

The issuer's **2025-09-30 annual shareholder report** supplies dividend-reinvested NAV results, net of fund expenses: **19.68%** for 2024-10-01–2025-09-30; **8.71% annualized** for the preceding five years. It is one AI-based equity fund, not a representative index of all trading bots.

Matched model results:

| Interval | Router | Capped router | Rotation | Nasdaq buy-and-hold | Nasdaq vol cap | Published AIEQ |
|---|---:|---:|---:|---:|---:|---:|
| One year to 2025-09-30 | −3.27% | 0.06% | −0.86% | 23.93% | 16.52% | 19.68% |
| Five-year annualized to 2025-09-30 | 10.64% | 10.62% | 13.52% | 17.59% | 15.37% | 8.71% |

The poor one-year result must be shown beside the favorable five-year comparison. Hypothetical models use index closes and modeled costs, while the ETF uses real NAV and expenses; these are **aggregate interval checks**, not daily paired fund/strategy inference. Additional 0.75% annual strategy-fee sensitivity is retained in results to expose fee differences. Full daily fund history and liquidity/capacity evidence would be needed for robust investable superiority.

Source: https://amplifyetfs.com/wp-content/uploads/files/AIEQ_Annual_Report.pdf . The issuer's current September2026 fact sheet was not substituted for this precisely matching historical interval.

### Hedge funds / Wall Street

A personal-use annual spot-check against the published HFRX Global2025 return was performed; all three active dispatchers underperformed that reference. The primary full history is subscription/licensed data and was not acquired. No HFR series or numeric benchmark is bundled in public source, product or marketing. Without paired history, volatility, drawdown, strategy mandate and fee normalization, there is no defensible population ranking against “most hedge funds”.

Public source and restrictions: https://www.hfr.com/media/performance-notes/hfrx-indices-december-2025-performance-notes/ and https://www.hfr.com/database/hfr-database/ . There was no broker transaction, subscription purchase or external contact.

The broad equity benchmark is CRSP total market, not the S&P500. AIEQ's report also provides an S&P500 figure, but it is not mislabeled as our broad-market series.

## Improvements justified for the next experiment

1. **Nasdaq:** use continuous, bounded risk sizing as the simple incumbent to beat. Compare any dispatcher against both full Nasdaq and this stronger risk control; reserve fresh data before adoption. Return reduction must remain visible.
2. **Regime routing:** test a predeclared persistent equity core with limited tactical changes or a genuinely trained state model on an isolated future stream. Do not use low efficiency alone as a sell-to-cash signal. This is a hypothesis, not another in-sample “winning” model.
3. **Hedge funds:** acquire permitted, strategy-specific net histories first. Establish a comparable mandate (e.g. equity long/cash or fixed volatility) rather than comparing different leverage and market exposures.
4. **AI competitors:** obtain verified daily NAV/account records and include all reported horizons. Distinguish lower fees, index exposure and predictive skill. More model complexity does not substitute for independently withheld labels.

## Reproduce and inspect

```sh
python -m unittest tests.test_competitive -v
python -m experiments.competitive_test --offline --output-dir .cache/competitive-new-run
python -m experiments.competitive_sharpe --output .cache/competitive-sharpe-new.json
```

Existing output paths are refused. `experiments/results/competitive_20261012/` retains the initial protocol/source/results; `competitive_20261012_controls/` retains the stronger-control replay, source snapshots, candidate-only daily paths and Sharpe sensitivity. Full reconstructible vendor benchmark paths remain outside the public repository. Source SHA-256: Nasdaq snapshot `e4a3f645aa8ae8d5e2e2c3b054c2111c322961770ba28c3662d3035f1bef3afe`; broad source `2f29e22546069914890a712680a6f81f3680ebc3543b52864484d209ca13a7db`.

This remains development research on revised public history. No forecast-superiority claim, live trade, automatic desktop adoption or independent future-data custody is implied.
