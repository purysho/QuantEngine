# Quant Engine · 0.2 research release

## Start on Windows

1. Extract the entire ZIP into a folder such as `D:\Apps\QuantEngine`.
2. Open **QuantEngine.exe**. Keep its resources and DLL files beside it.
3. Confirm the storage location. The default is `D:\Quant-Engine`; choose another writable folder if necessary.
4. Keep **Synthetic example prices** selected and choose **Run once**.
5. Inspect the completed risk, portfolio, backtest and sensitivity results. Then select **Start engine** to repeat research on the configured interval.

The app includes Python, NumPy and SciPy. Ordinary use needs no development terminal, Docker, API subscription or paid data account. The example dataset works offline.

## What each research cycle calculates

- Sample covariance and correlation, configurable diagonal shrinkage, and a constrained long-only minimum-variance portfolio.
- Seeded Gaussian horizon simulation with Value at Risk and Expected Shortfall at 95% and 99%. Tails use exact empirical probability mass, and VaR/ES are signed losses (a negative value means even the tail is a gain).
- Empirical circular block resampling, retaining short sequences of observed returns.
- A fitted Student-t model (fat tails) with its degrees of freedom, plus a Hill estimate of the loss-tail index.
- A chronological trailing-momentum/inverse-volatility backtest with holdings drift and explicit transaction costs, compared with equal-weight and cash baselines. A signal formed after a close trades at the **next** close; it never earns the move that created it.
- Descriptive parameter sensitivity, historical stress and hypothetical shocks.

The optimized static risk portfolio and the momentum backtest are different analyses. Their results are labelled separately. Sensitivity trials reuse history and have different warm-up windows; a high historical score is not independent evidence of a trading advantage.

Default settings are 50,000 simulation paths, a 20-observation horizon and a 60-second cycle interval. Simulation paths can reach 1,000,000. Work is batched, with at most one job and two numerical-library threads. Higher settings increase work; they do not improve the underlying data or guarantee a better investment decision.

## Bring your own data

Import a UTF-8 wide price CSV:

```csv
date,AssetA,AssetB
2025-01-02,100,80
2025-01-03,101,79.8
```

Supply at least 40 rows, positive finite prices, unique asset names and strictly increasing unique ISO dates. The CSV must have no missing values. Prefer equally spaced trading-day observations and adjusted prices from a source you are entitled to use. The engine does not correct splits, dividends or survivorship bias for you.

**Synthetic example prices** are visibly labelled. **Refresh ECB rates** obtains public historical FX reference observations quoted as currency units per euro. The euro is the numeraire, not a separate constant-price asset in the allocation. These are reference data, with no executable quote or bid/ask spread. Source bytes, retrieval time and data hash are retained. The first refresh is explicit. When an ECB dataset is selected in continuous mode, the default daily-refresh preference checks for a new snapshot once per UTC date; disable that preference to use the existing cache. A failed fetch retains the saved snapshot and displays the refresh error. Imported CSV and synthetic data never fetch new prices.

## Continuous use and saved evidence

Start engine schedules a new cycle after the prior cycle finishes. By default, successful runs rotate the selected momentum lookback with 20, 40 and 60 observations where the dataset permits; disable rotation for the chosen lookback only. Each successful run advances the base seed by one, and the complete report retains the actual seed. Pause stops the schedule, cancels an active calculation and marks its unfinished history as interrupted. Closing the window keeps the engine in the notification tray; use the tray to reopen it or **Quit Quant Engine** to stop it completely. Running at Windows login and resuming calculations when the app opens are separate opt-in settings in Preferences. Work runs only while Windows is awake.

Completed and failed runs are recorded in a local SQLite history. A completed run retains the dataset snapshot/hash, settings, random seed, software versions and report. Reopen a run or export its report. A cancelled or failed run is not labelled completed.

Changing the storage root selects another workspace; it does not migrate existing data automatically. Back up your chosen storage folder while the engine is paused and closed.

Use **Win + Ctrl + D** to create a Windows desktop and **Win + Tab** to move this app's window there. Virtual desktops organise windows; they share CPU and RAM. Closing this app's window hides it in the notification tray and keeps the configured research schedule running.

## Options calculator

Open **Options** to price a hypothetical call or put. Enter spot, strike, years to expiry, and volatility, rate and dividend yield as annual percentages. The page shows the Black–Scholes price, CRR tree prices (European and American, with the early-exercise premium), a seeded Monte Carlo price with its standard error, the put–call parity gap, and Greeks with units. Enter a market price to get implied volatility; impossible quotes are rejected with the bound they violate. The implied-move panel explains the "VIX ÷ 16" rule: it is a one-standard-deviation daily move (√252 ≈ 15.87), and the expected absolute move is only about 0.8 of that.

The calculation uses the same single worker as research. If a continuous cycle is waiting, it resumes afterwards; **Pause** cancels it. Option results never change stored datasets or research history.

## Research modules outside the desktop (Python)

`workers/quant_pairs.py` (cointegration pairs), `workers/quant_lob.py` (market-making simulator) and `workers/quant_validation.py` (leak-proof chronological ridge) run from the scripts in `experiments/`, for example `python experiments/pairs_cointegration.py`. Each writes measured JSON evidence to `experiments/results/`. They do not have desktop pages yet.

## Interpretation and next release

Treat these calculations as research and scenario analysis. The initial release has no broker connection, order routing or live execution. Data import and the numerical methods are the first complete loop. An event-driven strategy framework, stronger out-of-sample experiment selection and paper execution are later milestones.

## Release status

Version 0.2 is a portable native application. It is not yet code-signed or equipped with an automatic updater. This environment validates the desktop and numerical routines on Linux and inspects the Windows package; testing on your Windows laptop is still required. See EVALUATION.md for the device check. The product label is provisional.
