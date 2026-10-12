# Learning from strategy underperformance

## What failed, and what the evidence supports

The daily index experiment was not representative of intraday/session or news trading. Its five long/cash rules were applied to a US total-return research index, with zero cash yield and next-close execution. That design tests conditional participation, not execution on real stocks or forecasts of their returns.

The measured loss attribution separates **missed market returns** from **fees** exactly in log wealth; adding CAGR differences would not give an exact decomposition. For every five-year block:

`net log gap = (strategy gross log wealth - benchmark gross log wealth) + (strategy net - gross log wealth) - (benchmark net - gross log wealth)`

We report exposure, turnover, invested-versus-cash-day mean returns, best/worst observed day participation, net CAGR and drawdown. Best/worst days are retrospective diagnostics only; they are never fed into signals or selection.

US snapshot: 1926-07-01 to 2026-08-31; original source hash remains `2f29e22546069914890a712680a6f81f3680ebc3543b52864484d209ca13a7db`. Descriptive annualization uses 252 observations per year; it is not an exact calendar CAGR. Costs are 10bps per changed notional, including initial and terminal fills; cash earns zero, so realistic cash yield is a remaining sensitivity.

| Original rule | Exposure | Changes/year | Gross annualized growth | Net annualized growth | Diagnosis supported by accounting |
|---|---:|---:|---:|---:|---|
| MA20/50 | 65.3% | 5.08 | 6.67% | 6.13% | Invested-day and missed-day returns were almost identical (4.30 vs 4.33 bps/day); the signal did not compensate for being out of the market. |
| RSI14 30/70 | 35.6% | 2.16 | 2.12% | 1.89% | Worse average returns while invested (3.32 vs 4.86 bps/day while in cash); held 70 of the 100 worst observed days. Oversold entries also encounter continuing declines. |
| Bollinger20/2 | 20.6% | 8.04 | 1.15% | 0.34% | Low participation missed much of the broad market's growth; fees further reduced already weak gross returns. |
| MACD12/26/9 | 51.3% | 19.09 | 5.88% | 3.88% | Small descriptive invested-day advantage was eroded by frequent reversals and fees. |
| Volatility breakout | 21.9% | 5.50 | 3.36% | 2.79% | Rare entry condition missed most growth days, while providing lower observed drawdown. This may be a risk trade-off rather than a forecasting defect. |

Buy-and-hold net annualized growth was **9.84%** on the same US proxy. These are realized descriptive associations, not a causal explanation for market regimes. Next-close delay is necessary with these data; replacing it with same-close fills would fabricate an advantage rather than fix the strategy.

Primary research review:
- Fidelity notes RSI's non-trending applicability and persistence of extreme readings: https://www.fidelity.com/viewpoints/active-investor/how-to-use-RSI
- AQR's original trend-following research concerns diversified long/short markets, not a single long/cash equity-index rule: https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing (searchable publication record reviewed; direct page fetch timed out).
- French's regional market factors are USD returns including dividends/capital gains, with a US T-bill subtraction; adding RF reconstructs the research market return: https://mba.tuck.dartmouth.edu/pages/faculty/Ken.french/Data_Library/f-f_3developed.html

No full-text access to the three previously named books is claimed.

## Three bounded remedies, frozen before the European check

No sweep over indicators or parameters was performed. The complete candidate set and hashes were written before the first European fetch.

1. **MA50/200:** lengthen trend horizon to reduce whipsaw, acknowledging slower recovery entry.
2. **MACD every five closes:** retain the original indicators but permit changes only every fifth observation, reducing fee-generating reversals. This is not a calendar-week rule.
3. **20-close channel breakout:** remove the rare two-sigma requirement, enter above the preceding 20-close maximum and exit below SMA20. It is a different declared channel rule, not a silently renamed volatility/ORB strategy.

| Remedy | US original → remedy growth | Europe original → remedy growth | What we learned |
|---|---:|---:|---|
| MA50/200 | 6.13% → **7.46%** | 6.16% → **5.65%** | US turnover fell 5.08 → 1.05/year, but drawdown worsened from −46.14% to −64.40%. Improvement did not transfer to Europe. |
| MACD every five closes | 3.88% → **4.11%** | −0.89% → **2.13%** | Lower turnover helped in both samples, but the rule still underperformed buy-and-hold. |
| Channel breakout | 2.79% → **4.97%** | 1.56% → **1.45%** | Higher US participation raised returns and risk; European improvement failed. It is not market-invariant alpha. |

Europe: 1990-07-02 to 2026-08-31, source SHA-256 `89b84ff3c1edbe6dcd237498b6a68a092f2467ad3fee5fa2dfa4c295ec946ddc`. Buy-and-hold growth was **7.47%**. This was new to this experiment at first fetch, but is **public historical development data, not a custodian-sealed unseen period**. It is now exposed and must never be represented as fresh again.

All three remedies lagged the benchmark in the full samples. The conservative stationary-bootstrap multiple-rule diagnostic returned p=1.0 in each sample. No positive forecasting claim or live adoption followed.

## The implemented learning process

`workers/quant_strategy_learning.py` adds numerical diagnostics and a causal gate, exercised by `experiments/strategy_learning.py`:

- Each deployment decision uses two completed five-year **selection** blocks, followed by a separate completed five-year **adoption** block.
- Candidate selection compares net returns with buy-and-hold using Bartlett/Newey–West lag5 and a Bonferroni-adjusted lower confidence bound for the three frozen candidates.
- Only the selected candidate is tested on the separate adoption block. It must again show positive lower-bound evidence before the following five-year deployment.
- Outcomes from that deployment block do not affect its decision. Future-perturbation tests verify this.
- Selection eligibility is explicitly separate from actual adoption status; a search winner failing adoption is rejected, not called a deployed champion.
- The deployed backtest stitches **targets**, then recomputes holdings and fees. It does not splice standalone strategy returns and omit model-switch costs.
- The default is the buy-and-hold **research comparator** when no remedy qualifies. This does not change the desktop allocation engine, connect a broker or recommend buying a particular instrument.

**Actual result:** zero remedy deployments in both histories. The process rejected the proposed improvements despite some better original-versus-revised returns. That avoids replacing a strong comparator with a weaker strategy; it does not prove the comparator will always win.

These gates are conservative nominal historical diagnostics, not a sequential-testing theorem. Repeated research choices, serial-dependence/bandwidth uncertainty, revised historical data, execution approximation, zero cash yield and independent future custody remain limitations. The candidate set was chosen after inspecting US failures; that selection bias cannot be erased by replaying earlier dates.

## Reproduction and retained failures

```sh
python -m unittest tests.test_strategy_learning -v
python -m experiments.strategy_learning --offline --output-dir .cache/strategy-learning-new-run
```

An existing output directory is rejected. First-run files remain in `experiments/results/strategy_learning_20261012/`. The schema2 run renames a selection-eligibility field to avoid confusing it with adoption; no trading rule or statistical threshold changed. The verified run additionally extracts target stitching into a tested helper, proving that regime switches pay entry/exit costs and use previous-close signals. All three runs, complete per-block losses, hash-verified source snapshots, frozen protocols, choices and rejected candidates are retained. The later runs are exposed replays, not another unseen test; neither trading rules nor inference thresholds changed.

## What enables the remaining strategy families

| Need | Verified starting source | Conditions before a credible test |
|---|---|---|
| Session FX quotes | Dukascopy official history-tick API: https://www.dukascopy.com/wiki/en/development/strategy-api/historical-data/history-ticks/ | Bid/ask, UTC/DST and session definitions, explicit algorithm, completeness and usage/redistribution rights. No source integration or commercial rights are implied by documentation. |
| ORB and stock gaps | Alpaca official historical stock API/FAQ: https://docs.alpaca.markets/us/docs/market-data-faq | Account/API credentials and entitlements; historical SIP older than 15 minutes is described separately from free live IEX. Use venue coverage and trade/quote conditions correctly, with delisted securities and calendars. No credential is available here. |
| Earnings/catalysts | SEC public APIs: https://data.sec.gov/ and https://www.sec.gov/edgar/sec-api-documentation | Filing acceptance time is not necessarily the first earnings announcement time. Need original publication timestamps, revisions and matching executable price history. |

Do not fabricate successful ORB/session/news backtests from the daily index. Next research should test a genuinely different source of information or a predeclared risk-control objective, with data frozen before evaluation, rather than another indicator parameter sweep on these exposed outcomes.
