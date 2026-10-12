# Transaction attribution and classifier examination — 2026-10-13

This step examines the existing frozen rules. It changes no strategy, signal, parameter, execution convention or adoption gate. All observations are previously exposed historical development data. Local protocol/source freezing is integrity evidence, not independent future custody.

## What actually explains the gap

Jan2 2015–Aug31 2026, common total-return sources, RF cash,10bps, same next-close execution and terminal liquidation. A telescoping **log-wealth** decomposition reconciles every day and every period:

1. Full Nasdaq with common execution timing.
2. Replace Nasdaq with cash on the candidate's fully uninvested days: participation.
3. On invested days, reduce Nasdaq to the candidate's risky fraction: risk sizing.
4. Replace that fraction's Nasdaq exposure with the actual broad/Nasdaq composition: asset choice.
5. Subtract candidate costs and credit the comparator's costs.

These counterfactual components are order-dependent accounting. They are not causal effects of independently randomized modifications, and do not sum as CAGR percentage-point differences.

| Annual log-return contribution to gap vs full Nasdaq | Original router | Core/tactical | Faster passive Nasdaq | Slower passive Nasdaq |
|---|---:|---:|---:|---:|
| Cash participation | −4.23 | 0.00 | 0.00 | 0.00 |
| Risk sizing | 0.00 | −4.00 | −3.17 | −4.13 |
| Asset choice | −0.90 | −0.20 | 0.00 | 0.00 |
| Strategy costs | −2.23 | −0.23 | −0.35 | −0.21 |
| Comparator cost credit | +0.02 | +0.02 | +0.02 | +0.02 |
| Total | **−7.34** | **−4.41** | **−3.50** | **−4.32** |

Units are100×cumulative log contribution/calendar years: annual log percentage points, not CAGR. Original router cash participation explains approximately58% of its negative net log gap; costs approximately30%. For the core, risk sizing explains approximately91%, asset choice5%, costs5% before the small comparator credit. This quantifies the chosen decomposition rather than proving cash or risk control is intrinsically bad.

The original router was fully cash on **1,214/2,932 days** and averaged58.59% risky exposure. The core averaged81.07%; slower Nasdaq80.74%; faster Nasdaq80.29%. The slower control held **slightly more equity on average yet earned less**. Its failure cannot be explained simply as having a smaller average risk budget. The timing/path of allocations matters. Faster sizing's better gross risk contribution outweighed its additional modeled costs by about0.82 annual log percentage points.

Core vs matching slow control: the core's risk-sizing contribution was better by0.125 annual log points, but asset choice contributed−0.200 and extra costs−0.017, giving a net−0.092. Thus tactical rotation's unfavorable asset substitution outweighed its small sizing benefit in this replay. This is a sharper explanation than saying all tactical effects were negative.

## Every modeled transaction examined

The diagnostic reconstructs asset deltas at execution from actual post-fee capital and prior marked-to-market holdings, records two-leg switches separately from risk adjustments and drift trades, and checks that every fee reconciles with the frozen account. Terminal exits remain charged. Daily log components reconcile to the independently calculated terminal wealth ratio with numerical error below1.4e−17 for these portfolios.

Original router:84 entries,83 exits,46 asset switches,1 terminal exit. Core:1 entry,92 risk-sizing adjustments,6 asset switches,**1,896 drift rebalances**,1 terminal exit. Slower passive:1 entry,92 risk adjustments,1,776 drift rebalances,1 terminal exit. Faster passive:1 entry,641 risk adjustments,1,173 drift rebalances,1 terminal exit. These are nonzero modeled ledger rows, not real broker fills.

Therefore a21-close sizing interval does not mean the portfolio trades monthly: daily target-proportion restoration still trades. Private ledgers retain each execution date, originating signal date/state, target, per-asset buy/sell deltas, fee, past-only SMA/efficiency/momentum context and subsequent realized strategy path. Subsequent outcomes overlap and reflect later decisions: they are not causal profits attributable to individual trades. Raw ledgers/daily components stay in private cache because they can reconstruct vendor observations; public evidence contains aggregates and ledger hashes only.

## Did the situation classifier choose useful rules?

At each original signal close, compute the frozen branch proposals using only prior closes:
- Trend: stronger positive126-close momentum asset, else cash.
- Range: original RSI14 entry40/exit60 latch on the broad index.
- Stress: cash.

Execute no earlier than the next close and evaluate gross, fixed-position returns over the following1/5/20 closes. Apply each proposal outside its named state too, so the contrast tests whether the label actually improves its applicability. These are hypothetical gross recommendation payoffs, not live transactions or the dispatcher's costed multi-switch P&L.

Original-grid ratio-mean HAC uses lags max(5,horizon), including overlapping horizons. Bonferroni covers18 conditional-edge/inside-vs-outside comparisons. All nine **state-versus-outside** family confidence intervals include zero. The classifier has no established differential advantage for assigning these rules.

| State | Mean broad return over next eligible20 closes | Assigned rule mean gross log advantage vs broad over20 closes |
|---|---:|---:|
| Trend | +1.08% | +0.30% |
| Range | +0.85% | −0.28% |
| Stress | **+3.59%** | **−3.19%** |

The stress sample includes238 signal days and heavily overlapping outcomes, not238 independent crises. Approximately70% of its20-close outcomes were positive. A stress flag describing recent weakness did not reliably justify the subsequent cash response. Range-labeled windows also had positive average growth, so low efficiency alone did not identify a zero-growth environment. Neither table is a validated market-state ground truth.

**Preserve the favorable finding:** trend's1-close mean gross advantage was4.24bps of log return, with family-adjusted interval approximately+0.23 to+8.24bps. That isolated conditional edge survives this declared18-way check. But its inside-vs-outside contrast includes zero, longer horizons include zero, it compares partly Nasdaq exposure against broad market, excludes fees and comes from exposed history. It is a lead for investigation, not proof that classification or routing predicts returns.

## Decision from this examination

The old router's primary failure was missed participation plus costly entry/exit churn. The new core's primary gap is risk allocation; its gross asset-choice effect was also negative. Delayed risk updates are a stronger concern than cost reduction for the next bounded hypothesis, because slower sizing held more average equity but produced worse growth/protection. The stress-to-cash response and range classifier remain unvalidated. No new strategy is proposed, tuned or adopted by this diagnostic.

Before redesign: a controlled comparison would have to isolate sizing latency from its weight band, and isolate asset substitution from the resulting risk estimate. The existing comparisons changed both together. Any new candidate needs independently reserved evaluation and costs/uncertainty; historical diagnoses cannot certify forecasting alpha.

## Reproduce and retained evidence

`python -m experiments.trade_audit --output-dir <new-public-summary-directory> --private-dir <new-private-cache-directory>`

Both output directories must be new. Pinned offline sources are reused. `experiments/results/trade_audit_20261013/` archives protocol/source/aggregate results. Protocol SHA256 `4930dc553b8785de56834d318c251dc3ea5cfd23a6d0626a4ecdb9df0811bcf7`. A separate verified run retains identical results. Raw daily vendor observations and execution ledgers must not be published as CI artifacts. The existing research failures and source rules remain unchanged.

Boundary and gate notes: subsequent private-ledger outcome windows cover up to five available closes and may be truncated at the dataset end; they are descriptive only. In the previous competitive selection results, every candidate's `selected` field was null and `adoption_evidence` was null. The independent adoption block was **not reached**, rather than tested and failed. This diagnostic performs no new selection or adoption.

Verification:163 numerical tests (one optional SymPy skip),27 desktop tests,typecheck/build passed. First/verified result and protocol bytes match; frozen source hashes verified. Original strategy files are unchanged. New-head CI must pass before integration; historical findings do not establish prospective alpha.
