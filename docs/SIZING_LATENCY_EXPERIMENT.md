# Controlled risk-sizing interval experiment — 2026-10-13

The previous audit implicated stale risk allocations. This experiment varies **only the minimum interval between target updates**. It leaves existing strategies unchanged and performs no automatic adoption. All matched history was previously exposed; this is development evidence, not independent prospective validation.

## Frozen comparison

Three arms: minimum1,5 or21 closes between updates. Every arm uses only Nasdaq total-return exposure and RF cash,252-close warmup,20-close trailing sample log-return volatility,15% target,10-percentage-point absolute weight-change band, no periodic override and no leverage. The same initial sizing occurs at close252. Signal at s executes at s+1 and earns the first risky return at s+2. Daily proportional drift rebalances, entry and final exit remain charged at actual notional. Update frequency is not actual trade frequency.

This isolates the minimum-interval constraint, including the way that constraint interacts with subsequent band crossings. The old faster control differs in its5% band and periodic override; its results are contextual, not an isolated interval comparison. The new21-close arm must reproduce the existing slow passive targets exactly; it does.

Protocol SHA256 `7c48171c4396c1a15d0b8a1979a4909702c167abfef8016ed660c37467278448`. Frozen before execution:3 arms,2 primary paired comparisons versus21 closes, HAC lag20 with Bonferroni2 correction, cost sensitivities0/10/25bps,1,000 paired stationary-bootstrap samples for mean blocks5/20/60 and seed17. Secondary metrics are calendar-annualized log-growth difference, cash-relative Sharpe difference and maximum-drawdown improvement;18-way percentile sensitivity covers2 alternatives×3 metrics×3 blocks. There was no interval sweep or parameter tuning after results.

## Matched results

Jan2 2015–Aug31 2026,10bps per risky traded notional:

| Minimum update interval | CAGR | Volatility | Maximum drawdown | Sharpe |
|---|---:|---:|---:|---:|
| 1 close | 15.14% | 14.94% | −20.05% | 0.882 |
| 5 closes | 15.24% | 15.01% | −20.05% | 0.884 |
| 21 closes | 14.15% | 15.74% | −24.59% | 0.790 |
| Old faster control, contextual | 15.10% | 14.82% | −20.90% | 0.885 |
| Full Nasdaq, contextual | 19.20% | 22.12% | −35.04% | 0.813 |

| Window | 1 close CAGR | 5 closes CAGR | 21 closes CAGR |
|---|---:|---:|---:|
| 2015–2019 | 13.66% | 13.52% | **14.49%** |
| 2020–2024 | **16.53%** | 16.39% | 13.61% |
| 2025–Aug2026, partial | 15.48% | **17.02%** | 14.79% |

Both responsive arms improved the overall point estimates but lost the first complete five-year window. Do not promote5 closes merely because it has the highest full-period CAGR. No statistical1-vs5 selection was prescribed, and none was performed.

| Cost | 1 close CAGR | 5 closes CAGR | 21 closes CAGR |
|---|---:|---:|---:|
| 0bps | 15.44% | 15.52% | 14.40% |
| 10bps | 15.14% | 15.24% | 14.15% |
| 25bps | 14.71% | 14.81% | 13.79% |

The positive full-sample difference survives the tested cost sensitivities as a point estimate. This does not establish real execution or robustness to other costs/spreads/liquidity.

## What changed mechanically

Average risky fractions:1-close80.37%,5-close80.04%,21-close80.74%. Responsive arms held slightly **less** average equity yet achieved better observed growth and drawdown. Average absolute deviations from the contemporaneous trailing-volatility target were2.45,3.00 and7.11 percentage points respectively, directly showing the staleness imposed by the longer minimum interval. A synthetic abrupt volatility shock separately proves that the interval alone can block an otherwise eligible adjustment.

Target adjustments during evaluation were169,161 and92. Drift trades were1,847,1,987 and1,776. Actual transaction counts are2,018,2,150 and1,870 including entry/final exits, so5 closes did not mean fewer trades than1 close. Paths of cash/equity drift affect notional trades independently of update counts.

Using the fixed-order log accounting from the audit, the1-close arm's risk-sizing contribution improved by0.903 annual log percentage points versus21, with extra cost drag0.040, giving net0.863. The5-close arm improved sizing by0.981, with extra cost0.036, net0.946. These are telescoping annual log contributions, not CAGR differences or randomised causal effects. There is no asset-choice effect here because all arms use the same single risky asset.

## Uncertainty and decision

Primary mean daily net advantage versus21 was0.294bps for1 close and0.331bps for5 closes. Family-adjusted HAC intervals were approximately−0.565..+1.153bps and−0.588..+1.250bps. Both include zero. All nominal95% and18-way stationary-bootstrap sensitivity intervals for growth, Sharpe and drawdown across blocks5/20/60 also include zero. No positive significance gate passed and no model was adopted.

The controlled replay supports **responsiveness as a promising mechanism**, not a guarantee that faster updates win or a proven alpha claim. The adverse2015–2019 results remain part of that conclusion. Full Nasdaq still has the higher observed raw growth because it takes substantially more equity risk.

Do not change the band or search additional intervals to improve this sample. The next defensible evaluation requires independently reserved observations, fixed candidates and primary objective. A21-close hard delay is worth challenging; choosing1 or5 as a live policy is not justified by these data alone. Existing custody and execution-source limitations remain.

## Reproduce

`python -m experiments.sizing_latency --output-dir <new-output-directory>`

Pinned sources are offline and hash-verified. Existing output directories are refused. `experiments/results/sizing_latency_20261013/` retains source archives/protocol/aggregate results; verified replay is separate and must match. No daily benchmark/vendor return paths are publicly exported. Existing `quant_competitive.py`, trading rules and desktop behaviour remain unchanged.

Verification:168 numerical tests (one optional SymPy skip),27 desktop tests,typecheck/build passed. First/verified protocol/results are byte-identical; all frozen dependency source hashes match. Current-head CI is required before integration. Research uncertainty remains regardless of software checks.
