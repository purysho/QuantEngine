# Quant Engine · first Windows release

## Start on Windows

1. Extract the entire ZIP into a folder such as `D:\Apps\QuantEngine`.
2. Open **QuantEngine.exe**. Keep its resources and DLL files beside it.
3. Confirm the storage location. The default is `D:\Quant-Engine`; choose another writable folder if necessary.
4. Keep **Synthetic example prices** selected and choose **Run once**.
5. Inspect the completed risk, portfolio, backtest and sensitivity results. Then select **Start engine** to repeat research on the configured interval.

The app includes Python, NumPy and SciPy. Ordinary use needs no development terminal, Docker, API subscription or paid data account. The example dataset works offline.

## What each research cycle calculates

- Sample covariance and correlation, configurable diagonal shrinkage, and a constrained long-only minimum-variance portfolio.
- Seeded Gaussian horizon simulation with Value at Risk and Expected Shortfall.
- Empirical circular block resampling, retaining short sequences of observed returns.
- A chronological trailing-momentum/inverse-volatility backtest with holdings drift and explicit transaction costs, compared with equal-weight and cash baselines.
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

## Interpretation and next release

Treat these calculations as research and scenario analysis. The initial release has no broker connection, order routing or live execution. Data import and the numerical methods are the first complete loop. An event-driven strategy framework, stronger out-of-sample experiment selection and paper execution are later milestones.

## Release status

Version 0.1 is a portable native application. It is not yet code-signed or equipped with an automatic updater. This environment validates the desktop and numerical routines on Linux and inspects the Windows package; testing on your Windows laptop is still required. See EVALUATION.md for the device check. The product label is provisional.
