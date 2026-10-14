# Why responsive sizing lost in 2015–2019 — 2026-10-14

This examination follows the controlled1/5/21-close sizing experiment. It changes no strategy, parameter, signal, account or adoption gate. The adverse window and ranked intervals were chosen after observing the results: this is exposed retrospective diagnosis, not new discovery or independent validation.

## The measured answer

Nearly all the gap was exposure timing, not fees. The shortfall was concentrated in2018, especially its first quarter. Responsive sizing held less equity during a recovery, then more equity during renewed losses. That mechanism can now be demonstrated on recorded decision intervals rather than offered only as a hypothesis.

| Comparison against21-close arm | 1-close arm | 5-close arm |
|---|---:|---:|
| 2015–2019 net CAGR | 13.66% | 13.52% |
| Reference net CAGR | 14.49% | 14.49% |
| Annual gross log-return gap | −0.686pp | −0.808pp |
| Additional annual log cost drag | −0.043pp | −0.042pp |
| Annual net log-return gap | **−0.729pp** | **−0.851pp** |
| Share of net log shortfall from gross timing | **94.1%** | **95.0%** |
| Share from extra costs | 5.9% | 5.0% |
| Share of net shortfall accumulated in2018 | **87.6%** | **85.1%** |
| Average equity exposure | 88.57% | 88.02% |
| Reference average equity exposure | 88.23% | 88.23% |

Log-return contributions add exactly; CAGR differences do not. The daily difference is `log(gross_fast)-log(gross_slow)` plus `(log(net_fast)-log(gross_fast))-(log(net_slow)-log(gross_slow))`. Both portfolios follow the original full-history account; no artificial liquidation at2019 is added. Fees remain charged on their actual calendar day, which can precede the associated target's first risky return.

The1-close arm actually held slightly more average equity than the reference. Its underperformance cannot be explained by a uniformly lower average budget. Prices and relative exposure changed together over time.

## Specific decision intervals

Intervals are non-overlapping and bounded by either arm changing its effective held target. Signals at close s first earn risky returns at s+2. No overlapping event-window profits are counted as independent contributions.

| Interval | Responsive arm | Its equity exposure |21-close exposure | Gross log-performance difference |
|---|---:|---:|---:|---:|
| 2018-02-12–2018-03-08 |1 close |56.15% |77.17% |−1.72pp |
| 2018-02-14–2018-03-08 |5 closes |53.35% |77.17% |−1.43pp |
| 2018-03-21–2018-03-23 |1 close |86.31% |61.80% |−1.40pp |
| 2018-03-19–2018-03-23 |5 closes |92.59% |61.80% |−2.36pp |

The first1-close interval began with a trailing volatility estimate26.72%, implying target15/26.72=56.15%. Nasdaq's cumulative return relative to RF cash over that interval was+8.21 log percentage points, approximately+8.56% compounded relative to cash. Keeping less exposure missed part of that recovery.

For the5-close March19–23 interval, the context signal's trailing volatility was16.20%, implying target92.59%. Nasdaq subsequently lost7.61 log percentage points relative to cash, approximately−7.33% compounded. The responsive portfolio held substantially more exposure during those renewed losses. The analogous1-close March21–23 interval had trailing volatility17.38%, target86.31%, and negative subsequent returns.

These observations demonstrate the allocation mechanism on these price paths. They do not establish why the market moved, claim the slower policy predicted the moves, or justify trading a hindsight “rebound” label. A20-close realized-volatility estimate measures recent turbulence; matching it faster cannot itself distinguish recovery from another fall.

Other losses remain recorded: both arms held about99.6–99.7% versus89.2% in their July/August2015 negative intervals, and held less exposure in the June2019 recovery. The public evidence retains five worst gross intervals per arm; it does not represent those ranked losses as a new predictive rule.

## Gains avoided and losses avoided, across the entire window

Days are partitioned using relative held exposure and Nasdaq return relative to cash. Each day belongs to exactly one cell. Units below are annual log percentage-point contributions to responsive-minus-slow **gross** performance:

| Relative exposure and market outcome |1 close |5 closes |
|---|---:|---:|
| Less equity; Nasdaq beats cash: missed gains |−3.372 |−3.736 |
| Less equity; Nasdaq trails cash: avoided losses |+2.566 |+2.864 |
| More equity; Nasdaq beats cash: additional gains |+2.671 |+2.737 |
| More equity; Nasdaq trails cash: additional losses |−2.551 |−2.673 |
| Net gross timing contribution |**−0.686** |**−0.808** |

The responsive cuts did avoid losses, but those benefits were smaller than missed gains on the reduced-exposure days. Its increased-exposure days were slightly favourable in aggregate, despite the severe March examples. That distinction matters: the worst individual interval does not explain every part of the total.

For1 close,2018 first-quarter net difference was−4.183 cumulative log percentage points, followed by+1.222 in Q2, approximately zero in Q3 and−0.229 in Q4. For5 closes, the corresponding differences were−3.894,+0.710,−0.458,+0.021. Subsequent gains partially offset the first-quarter damage.2015 itself was favourable overall for both responsive arms, despite the large August loss; the full-year ledger must stay beside selected episodes.

## What the examination changes in our understanding

The earlier explanation that faster sizing sometimes missed recoveries is supported for the recorded February2018 intervals. It was incomplete: responsive sizing also increased exposure before renewed declines. Extra fees were a small contributor in this window. The failure was a mismatch between a backward-looking risk estimate and the subsequent market path, not a demonstrated software timing error.

The21-close arm benefited from its different exposure path in this window; it still lost the later2020–2024 and partial2025–2026 comparisons in the prior experiment. No interval is universally superior in the observed samples, and previous uncertainty intervals included zero. We should preserve both abrupt reversals and recovery paths in independent validation rather than tune rules to avoid these now-known dates.

## Verification and provenance

`python -m experiments.sizing_window_audit --output-dir <new-public-summary-directory> --private-dir <new-private-cache-directory>`

Public and private directories must be disjoint and new. Daily partitions, transaction counts and non-overlapping intervals reconcile with the original account. Complete interval ledgers remain private cache because they can reconstruct vendor observations. Public output contains aggregates, hashes and five ranked interval summaries only.

Initial result/source evidence: `experiments/results/sizing_window_audit_20261014/`, protocol SHA256 `57334b85b384c49c58b64818fa4cebc104d648c3ca7f169c1ee89e17b6993be2`. A context-only extension renamed an ambiguous signal-date label and added past-only volatility/desired-target metadata; no arithmetic or strategy changed. Its source/protocol and verified replay are preserved separately in `sizing_window_audit_20261014_context/` and `sizing_window_audit_20261014_verified/`, protocol SHA256 `237db0462137f30ae033c97f37c29e5f90e7e10006f77f12979ef7589119576b`. These reruns are not additional independent samples.

Fresh verification:168 numerical tests,one optional SymPy skip,0 failures; context/verified results and protocols are byte-identical. Initial/context primary arithmetic is unchanged. Net gaps independently reconcile to the previous frozen five-year CAGR ratios within1e−12. Existing strategy/account modules are unchanged. Fresh diagnostic-head CI remains required before integration.
