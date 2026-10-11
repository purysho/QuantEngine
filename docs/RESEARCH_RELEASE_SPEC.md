# QuantEngine 0.2 research release

## Purpose

Turn the existing local desktop engine into a numerical research workbench whose timing, assumptions and reproducibility can be inspected. The first experiment asks whether a small chronological model beats explicit baselines under controlled null and signal data, and whether a deliberately leaked feature is rejected. It does not claim a profitable market strategy.

## Binding constraints

- Independent QuantEngine identity; no references to or shared runtime with another product.
- Windows 11 x64, 16 GB RAM, integrated graphics; default data folder `D:\Quant-Engine`.
- One worker at a time, two BLAS threads normally and one in low CPU mode; pause cancels active work.
- No hosted inference, broker, paid API, model download or new numerical runtime dependency.
- Keep NumPy 2.3.5 and SciPy 1.17.0; the bundled Windows runtime remains Python 3.13.16.
- Immutable source snapshots, SHA-256 provenance and completed/failed/interrupted report history remain supported.
- Imported wide CSV is close-only data. Signals observed after close t are eligible at close t+1; exposure first earns the return from t+1 to t+2. Equal-weight baseline uses the same evaluation interval and entry-cost convention.
- Version 0.1 reports remain readable. New reports use schema version 2 and engine version 0.2.0.

## Scope

1. Correct empirical expected-shortfall tail mass, including tied observations and a fractional boundary observation. Record the empirical VaR convention. Risk output is a signed loss: negative VaR can represent gains across the whole distribution.
2. Analytic European Black–Scholes prices and Greeks, European/American CRR trees, risk-neutral Monte Carlo with sampling error and implied-volatility inversion. Inputs are manual hypothetical contracts; units and model assumptions are visible. No live options chain or calibrated market surface is claimed.
3. A NumPy ridge alpha experiment with train-only scaling, chronological inner parameter choice and an untouched final block. Features have availability indices and labels have completion indices; inconsistent clocks are rejected. Cash and constant-mean forecasts are explicit baselines. Every candidate tried is logged.
4. An offline experiment harness writes actual JSON results with seeds, runtime, data hashes, timings and acceptance outcomes. Include null data, known weak synthetic signal and a deliberately unavailable feature as a negative control. Synthetic evidence validates mechanisms, not market alpha.
5. An options page uses the existing isolated worker/IPC transport. Its calculations do not overlap the continuous engine. Results can be viewed without changing stored price data or the monitor's last completed portfolio report.
6. Portable development commands and GitHub CI for Linux and Windows. A Windows job assembles the verified embedded runtime, executes its numerical tests and exercises the native app's self-test. Do not describe a configured workflow as a passed check until its run is observed.

## Deferred modules

Pairs trading requires an optional validated statsmodels dependency, I(1) checks, MacKinnon Engle–Granger inference, formation-only pair selection and hedge fitting, multiple-testing policy, close-to-execution delay and reconciled two-leg costs/borrow/liquidation. Order-book market making requires event clocks, FIFO/partial-fill accounting, latency, inventory limits and fees before any historical profitability claim. ML extensions and data adapters must preserve availability clocks. None is silently folded into the first options calculator.

## Acceptance

- Black–Scholes published reference fixture, put–call parity and finite-difference Greeks; CRR convergence and American exercise dominance; seeded Monte Carlo convergence within its reported sampling error; impossible implied-volatility quotes rejected.
- Toy price paths prove no reaction at the signal close, correct next-close entry, cost timing, aligned curve dates and prefix invariance when future prices change.
- Tail fixture `[−10, −1, 0, 2]` at 37.5% lower-tail mass has ES `7`, with quantile conventions recorded; finite input and boundary validation.
- Alpha training excludes every label completed on or after an evaluation start; scalers and parameter choice never read evaluation observations. Future perturbations leave prior fits and forecasts unchanged. A leaked feature is rejected before scoring.
- Native options controls obey the same busy/pause rules as numerical work; invalid input produces a useful error; renderer remains sandboxed and displays safe text.
- Linux and Windows numerical/desktop checks are recorded separately from the user's laptop acceptance.
