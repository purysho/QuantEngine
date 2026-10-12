# Persistent core and bounded tactical rotation — 2026-10-12

The approved follow-up tested whether preserving equity participation and limiting switches remedies the previous router's weaknesses. It did not qualify for adoption. All data below were already exposed before the new rules were written: this is **development evidence**, not a fresh holdout or forecasting superiority.

## Fixed rules

`workers.quant_competitive.core_tactical_targets` starts after 252 closes. An 80% Nasdaq core stays invested within the current risk budget. The remaining 20% starts in Nasdaq and rotates to the other equity index only when its trailing 126-close log momentum exceeds the current asset's by more than 0.05 for five consecutive closes, with at least 21 closes between switches. No efficiency/range/stress classification sends the core to cash. This replaces an unreliable range classifier with a bounded relative-strength decision, not a claim to know the true market regime.

The risk budget is `min(1,0.15/sigma20)`, where sigma20 is the sample standard deviation of the current composition's trailing 20 daily log returns times sqrt(252). Sizing changes require both 21 closes since the last adjustment and a 0.10 absolute weight change. The initial sizing occurs at close252. A passive Nasdaq control uses the identical sizing rule. Thus tactical benefit can be compared without confusing it with a different risk policy. Target composition is rebalanced daily in the existing accounting; all proportional drift rebalances remain charged. This is not a simulator of tax lots, partial fills, spread or capacity.

Signals execute at the next close and first earn risky returns one close later. Cash interest, actual-notional entry/switch costs and final liquidation follow the existing self-financing account. Two fixed candidates were frozen before this replay. No rule or threshold was altered after observing their results.

## Matched replay

January2 2015–August31 2026, 10bps per traded risky notional, no leverage:

| Strategy | CAGR | Volatility | Maximum drawdown | Cash-relative Sharpe |
|---|---:|---:|---:|---:|
| Previous situation router | 10.76% | 13.09% | −21.31% | 0.689 |
| Persistent core / 20% tactical | 14.05% | 15.69% | −23.42% | 0.786 |
| Nasdaq with matching slower sizing | 14.15% | 15.74% | −24.59% | 0.790 |
| Nasdaq with previous faster sizing | **15.10%** | **14.82%** | **−20.90%** | **0.885** |
| Full Nasdaq buy-and-hold | 19.20% | 22.12% | −35.04% | 0.813 |

| Interval | Core/tactical CAGR | Slow passive CAGR | Faster passive CAGR |
|---|---:|---:|---:|
| 2015–2019 | 14.25% | 14.49% | 13.63% |
| 2020–2024 | 13.60% | 13.61% | 16.46% |
| 2025–August2026, partial | 14.79% | 14.79% | 15.48% |

Core/tactical CAGR at0/10/25bps was14.31/14.05/13.66%; slow passive14.40/14.15/13.79%. Cost sensitivity is much smaller than the old router's13.25/10.76/7.11%, but strategy/risk exposure changed too. It is not a causal estimate of a single modification.

Paired mean daily excess over faster passive Nasdaq was −0.311bps for core/tactical (nominal HAC95% interval −1.142 to +0.520bps), and −0.271bps for slow passive (−1.104 to +0.562bps). No advantage was established. Frozen selection2000–2009 and separate adoption2010–2014 rejected candidates against full broad market, full Nasdaq and faster volatility-managed Nasdaq. These historical gates are also development checks, not newly secret labels.

The 80% core improved growth versus an often-cash router while raising realized risk. Tactical rotation added no demonstrated value over its matched passive control. Less frequent risk updates reduced fee sensitivity but failed to protect as well in the observed2020–2024 interval. Do not select the attractive2015–2019 interval and discard the rest. These are descriptive associations, not causal market explanations.

## Reproducibility and next decision

Run `python -m experiments.competitive_test --offline --core-tactical --output-dir <new-directory>`. Existing output directories are refused. `experiments/results/core_tactical_20261012/` retains the initial frozen protocol, source archives, scores, cost sensitivities, state diagnostics and derived candidate paths. The protocol SHA-256 is `2af131ddb0fea567c54b8e2d1a502257b86ddf881365d5f58802aa7d532e5366`. Source pins require the exact previous French and Nasdaq snapshots. Later verified replay is separate evidence; it is not a second independent sample.

Keep the faster passive volatility control as a **research comparator**, not an adopted live strategy. Do not tune tactical weight, confirmation or risk bands against these outcomes. A further adoption experiment needs a separately operated evaluator to reserve equity total-return observations received after a committed freeze, with vendor availability timestamps, identical asset/calendar/cash conventions, and independently recorded next-close targets before outcomes. Existing crypto next-ticker forecasts do not provide this equity-portfolio test. No external custodian or verified equity execution source has been established, so prospective superiority remains untested.

Research context: Moreira and Muir, *Volatility-Managed Portfolios* (2017), DOI10.1111/jofi.12513; https://www.nber.org/papers/w22208 . Their volatility-management research motivates a strong risk-control comparator; our bounded inverse-volatility sizing is not a replication of their inverse-variance factor portfolios and inherits none of their performance claims.

The candidate CSV and conditional tables retain the original router's trailing trend/range/stress labels as exploratory context. Those labels do not control this core policy; its tactical decisions use the relative-momentum confirmations above. The matching source/first/verified replay byte comparisons passed. Full verification:155 numerical tests (one optional skip),27 desktop tests,typecheck/build passed.
