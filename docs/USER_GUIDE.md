# Quant Engine · 0.2 research release

## Start on Windows

1. Download **[QuantEngine-win-x64.zip](https://github.com/purysho/QuantEngine/releases/latest/download/QuantEngine-win-x64.zip)**. This link always points to the newest release; checksums are on the [release page](https://github.com/purysho/QuantEngine/releases/latest).
2. Extract the entire ZIP into a folder such as `D:\Apps`, then open **QuantEngine\QuantEngine.exe**. Keep its resources and DLL files beside it. The app is not code-signed yet, so if SmartScreen says it is unrecognised, choose **More info, then Run anyway**.
3. Confirm the storage location. The default is `D:\Quant-Engine`; choose another writable folder if necessary.
4. Keep **Synthetic example prices** selected and choose **Run once**.
5. Inspect the completed risk, portfolio, backtest and sensitivity results. Then select **Start engine** to repeat research on the configured interval.

The app includes Python, NumPy and SciPy. Ordinary use needs no development terminal, Docker, API subscription or paid data account. The example dataset works offline.

## Downloading: troubleshooting

These are the problems found during the first install on the target laptop.

- **Wrong file.** The app is `QuantEngine-win-x64.zip`, about 220 MB. A zip of a few MB, named after the repository or a branch (for example `QuantEngine-main.zip`), is the source code from the green **Code** button. It has no `QuantEngine.exe`. Check the size in PowerShell with `(Get-Item .\QuantEngine-win-x64.zip).Length`.
- **Checking the download.** `(Get-FileHash .\QuantEngine-win-x64.zip -Algorithm SHA256).Hash` must match the SHA-256 on the [release page](https://github.com/purysho/QuantEngine/releases/latest) (case does not matter). A mismatch almost always means an interrupted download; download it again.
- **Use the browser.** It shows progress, can resume (Ctrl+J, then **Resume**) and uses the same network route that opens GitHub for you.
- **PowerShell downloads.**
  - With `$ProgressPreference = 'SilentlyContinue'`, `Invoke-WebRequest` shows nothing until it finishes, so a 220 MB download looks frozen. Leave it running, or use the browser.
  - `curl.exe` does not use the Windows proxy settings. If you connect through a VPN or proxy app, it can fail with "Failed to connect to github.com:443" even though the browser works. Add `--proxy http://host:port`, using the `ProxyServer` value from `Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'`. Add `-C -` to resume a partial file.
- **Extracting.** Extract into a new, empty folder (for example `D:\QuantEngine-0.2.0`), not over an older copy or a source-code folder. `Expand-Archive .\QuantEngine-win-x64.zip -DestinationPath D:\QuantEngine-0.2.0` takes a few minutes because the zip holds about 3,500 files.
- **Self-test.** In the extracted `QuantEngine` folder, `.\QuantEngine.exe --self-test | Out-String` prints `QUANT_SELF_TEST_OK` followed by the runtime versions and a reference option price of 4.7594. It uses a temporary folder and does not touch your data.

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

## Market terminal

The app opens on the **Terminal**. Type in the command line at the top (press **/** to jump there) and press Enter:

| Type | Shows |
| --- | --- |
| `AAPL` (or `BTC/USD`) | Chart, description and news for a symbol |
| `AAPL GP`, `1D` `5D` `1M` `6M` `1Y` `5Y` `MAX` | Price chart and range |
| `AAPL DES` | Day range, bid/ask and spread, 52-week range, 1-year return, average volume, realised volatility and the typical daily move (σ/√252, the same idea as VIX ÷ 16) |
| `N`, `AAPL N` | Market news or news for one symbol (Benzinga via Alpaca) |
| `AAPL OMON` | Fetches the option chain, fits an implied-volatility surface and opens it on the Options page (**Market** view) |
| `MOST` | Most active stocks, gainers and losers |
| `ECO` | VIX (with VIX ÷ 16), 2- and 10-year Treasury yields, the curve, Fed funds, the broad dollar and Brent, from FRED |
| `ADD TLT`, `DEL TLT` | Change the watchlist (up to 40 symbols) |
| `RESEARCH SPY QQQ TLT` | Downloads 5 years of adjusted daily closes, saves them as a research dataset and analyses it |

**Connecting live US stock data.** Create a free account at alpaca.markets, open the **paper trading** dashboard and generate API keys. In **Preferences → Market data (Alpaca)**, paste the key ID and secret, choose a feed and press **Save and test**. The keys are tested with Alpaca before they are saved, are encrypted by Windows, and are never shown again. QuantEngine only reads market data; it cannot place orders. Never paste your keys into a chat or a file.

- **Feeds.** *IEX* (free) is real-time but covers about 2.5% of US volume, so its volume figures are partial. *All exchanges, 15 min delay* (free) is complete but delayed. *All exchanges, real-time* needs Alpaca's paid plan. Charts of a day or longer always use complete, split- and dividend-adjusted history.
- **Live updates.** The watchlist streams trades over one connection; the free plan allows one live connection and 30 streamed stock symbols. If another program uses the same keys, QuantEngine says so and shows 15-second snapshots instead.
- **Without keys**, crypto prices, the economy panel and the official datasets still work.
- **Option surfaces** use Alpaca's free *indicative* option feed: quotes derived from, but not identical to, the official OPRA quotes. The surface uses out-of-the-money mid prices (American options' early-exercise premium is smallest there), fits a raw SVI curve per expiry, shows only the strike range that every expiry actually quotes, and reports static-arbitrage flags and the gap to Alpaca's own implied volatilities.

Data from Alpaca is "not warranted as to completeness or accuracy" (Alpaca's terms). Everything stays on this computer.

**Official datasets.** On the **Datasets** page, **Free official data** downloads the S&P 500, Nasdaq Composite and Dow Jones (FRED, about ten years), the US market and 12 industries since 2000 (Ken French library, total-return indexes, updated monthly by the source) or ECB exchange rates. While the engine runs continuously, these refresh once a day and Alpaca datasets hourly until the latest close arrives; a failed refresh keeps the saved snapshot.

## Options calculator

Open **Options** to price a hypothetical call or put. Enter spot, strike, years to expiry, and volatility, rate and dividend yield as annual percentages. The page shows the Black–Scholes price, CRR tree prices (European and American, with the early-exercise premium), a seeded Monte Carlo price with its standard error, the put–call parity gap, and Greeks with units. Enter a market price to get implied volatility; impossible quotes are rejected with the bound they violate. The implied-move panel explains the "VIX ÷ 16" rule: it is a one-standard-deviation daily move (√252 ≈ 15.87), and the expected absolute move is only about 0.8 of that.

The calculation uses the same single worker as research. If a continuous cycle is waiting, it resumes afterwards; **Pause** cancels it. Option results never change stored datasets or research history.

## Ask (Ctrl+K) and voice

Press **Ctrl+K** and type or dictate: "what is my VaR", "explain Black–Scholes", "price a put strike 95 spot 100 6 months vol 25%", "show the vol surface", "learn now", "set paths to 100000". For voice on Windows, install **Handy** (`winget install cjpais.Handy`; free and offline; choose the Parakeet model on a laptop without a GPU), hold its shortcut and speak into the Ask box. Changes to settings always ask you to confirm and can be undone ("undo"). Requests to buy, sell or trade are refused: QuantEngine has no brokerage connection. Every request is logged in `assistant-log.jsonl` in your storage folder. Optionally, point Preferences → Assistant at a model server on this computer (llama.cpp, Ollama, LM Studio) for free-form questions; only localhost addresses are accepted.

## Evolution: the engine keeps learning

When the engine runs continuously, each cycle ends with a short, time-boxed learning step. Model configurations are bred and tested, and the best is frozen and judged only on data that came after the choice. A challenger must significantly beat the current model before it is replaced. The **Evolution** page shows this as a 3D graph: each glowing node is a tested model, lines show how it was bred, and clusters are model families. The learning curve shows the frozen champion against a fixed baseline. Memories are kept in `learning/` in your storage folder, so learning continues across restarts.

## The maths, step by step

Under the option results and the risk report, **The maths** shows each formula with your numbers substituted (d₁, d₂, N(d), tree probabilities, the Monte Carlo error, VaR and expected shortfall, the Student-t tail, the minimum-variance portfolio). The workings are recomputed from the same inputs as the results, and tests check they agree.

## Research modules outside the desktop (Python)

`workers/quant_pairs.py` (cointegration pairs), `workers/quant_lob.py` (market-making simulator), `workers/quant_validation.py` (leak-proof chronological ridge) and the real-data backtests (`experiments/real_world_backtest.py`, `experiments/evolution_real.py`) run from the scripts in `experiments/`, for example `python experiments/pairs_cointegration.py`. Each writes measured JSON evidence to `experiments/results/`. They do not have desktop pages yet.

## Interpretation and next release

Treat these calculations as research and scenario analysis. QuantEngine reads market data but has no order routing or execution, and the assistant refuses trading requests. Data import and the numerical methods are the first complete loop. An event-driven strategy framework, stronger out-of-sample experiment selection and paper execution are later milestones.

## Release status

Version 0.2 is a portable native application. It is not yet code-signed or equipped with an automatic updater. This environment validates the desktop and numerical routines on Linux and inspects the Windows package; testing on your Windows laptop is still required. See EVALUATION.md for the device check. The product label is provisional.
