# Repository audit: data, research, and execution engines

Audit date: 2026-10-11 UTC. Target: Oliver's QuantEngine, an independent free Windows desktop application using Electron and Python 3.13.16, NumPy 2.3.5, and SciPy 1.17.0 on a 16 GB Intel Core 5 computer without a discrete GPU.

This is a source and documentation audit, not a benchmark or installation certification. All four supplied repositories were accessed through the connected GitHub service. Their default-branch commits, recursive trees, actual README and LICENSE files, manifests, selected implementations, tests, and CI definitions were inspected. No upstream source was copied into QuantEngine, no upstream package was installed, and no upstream tests were executed. Decisions below distinguish observed implementation from inference and from claims in documentation.

## Version and licensing evidence

| Supplied repository | Verified default branch and commit | Commit date and observed maintenance | Actual source license at that commit | Decision |
| --- | --- | --- | --- | --- |
| [AI4Finance-Foundation/FinRL](https://github.com/AI4Finance-Foundation/FinRL) | `master`, [00f3596facd01cced5217d875d8c1fc413a31665](https://github.com/AI4Finance-Foundation/FinRL/commit/00f3596facd01cced5217d875d8c1fc413a31665) | 2026-10-09 09:03:13 UTC; merge fixes NumPy-array initial holdings, with regression tests | MIT, copyright 2024 AI4Finance Foundation Inc. | Defer DRL to a bounded experimental extension; adapt interfaces and selected testing ideas |
| [openbq-org/OpenBB](https://github.com/openbq-org/OpenBB) | `develop`, [ae0268771f761b036996d81bd21522ce79d95415](https://github.com/openbq-org/OpenBB/commit/ae0268771f761b036996d81bd21522ce79d95415) | 2026-10-02 04:54:02 UTC; repository-wide dependency lock update | Apache-2.0, copyright 2021–2026 OpenBB Inc.; LICENSE explicitly covers all repository files | Adapt optional provider interfaces and local quantitative metrics; avoid the aggregate stack as a core dependency |
| [austin-starks/congressional-disclosures](https://github.com/austin-starks/congressional-disclosures) | `main`, [2965e8796bd4cb9423a83b964a1f9dbd076a0ad6](https://github.com/austin-starks/congressional-disclosures/commit/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6) | 2026-10-02 16:50:30 UTC; latest commit excludes a local dataset download; package is 2.2.2 | MIT, copyright 2026 Austin Starks | Optional dataset import and disclosure research; adapt provenance/versioning; defer automated model extraction and trade copying |
| [yutiansut/QUANTAXIS](https://github.com/yutiansut/QUANTAXIS) | `master`, [232aa7ac9869966108f02a8fff85f1f7b09a9ce2](https://github.com/yutiansut/QUANTAXIS/commit/232aa7ac9869966108f02a8fff85f1f7b09a9ce2) | 2026-09-18 04:59:48 UTC; README update, not proof that every subsystem is current | MIT, copyright 2016–2021 yutiansut/QUANTAXIS | Defer wholesale integration; reconsider selected Chinese-market and accounting concepts later |

MIT licenses require preserving their copyright and permission notices when source is reused. Apache-2.0 additionally has redistribution, change-notice, and notice-preservation conditions; it does not grant trademark rights. These are source licenses. None supplies an unrestricted license to all market, macroeconomic, or congressional data fetched by its code. This audit did not clear every transitive package or every source's redistribution terms.

### Exact OpenBB URL identity

The supplied `openbq-org/OpenBB` repository exists and was inspected directly. GitHub reports repository ID 323048702 and `fork: false`. The older [OpenBB-finance/OpenBB URL](https://github.com/OpenBB-finance/OpenBB) redirects to the supplied repository; its old GitHub API URL returned a permanent-move response to the same repository ID. This was verified, not substituted on the basis of name similarity.

The current source is OpenBB Platform v5 (`openbb` 5.0.0, core 2.0.1). The [official license FAQ](https://docs.openbb.co/odp/python/faqs/license) says v5 is Apache-2.0 and older v4 stays AGPL. The [official provider migration documentation](https://docs.openbb.co/odp/python/extensions/providers) explains that v5 uses provider namespaces, and old provider packages built for core 1.x are incompatible with core 2.x. Do not apply an old v4 licensing or integration assessment to the inspected v5 source.

## Evidence matrix

| Repository | What runs locally without fees | Dependencies that prevent a wholly offline/free end-to-end promise | Timing and data safeguards actually inspected | Windows / target stack evidence and limits |
| --- | --- | --- | --- | --- |
| FinRL | Training and environment simulation after data is present; small MLP policies can run on CPU | External Yahoo, Alpaca, WRDS, JoinQuant, Tushare, and other sources; broad RL/data stack, provider credentials or charges for some routes | Date splits and a chronological ensemble train/validation/trade loop exist; adjusted OHLC and fees exist. The inspected stock example still selects complete-history tickers and fills missing data before splitting, then permits same-close execution | Metadata/classifiers through Python 3.12; inspected CI uses Ubuntu Docker, not a Windows/3.13 matrix; no exact-stack validation |
| OpenBB v5 | Quantitative returns, ratios, factor regressions, and installed provider/client code | Fetching still requires external services. Some sources require free keys; access, availability, rate limits, and data rights remain source-specific | Typed OHLCV schemas, local statistical tests, trailing calculations. Inspected FRED convenience path drops real-time metadata; inspected equity paths do not establish a corporate-action or historical-universe contract | Python >=3.10,<4; quantitative NumPy/SciPy lower bounds accept target versions; CI defines Linux 3.13 and Windows 3.10/3.14 tests, not exact target validation |
| Congressional disclosures | Download an already parsed public snapshot; query a local SQLite lake without model/API keys | Official-source discovery requires internet; reconstructing House/paper Senate reports defaults to paid OpenRouter-compatible models and Mistral OCR plus native PDF/OCR tools | Filing/row/event grains, tested amendment versions, source hashes, atomic SQLite replacement, and consensus failure are implemented. Public availability is reconstructed from filing/submission dates, not observed publication | Node >=22.5 and `node:sqlite`; native `sharp` and OCR tooling matter. CI is Ubuntu Node 22; Electron's embedded Node version must be checked; Windows extraction not established |
| QUANTAXIS | Selected in-memory account operations (`nodatabase=True`) and Python analytics can be local | Full framework defaults to databases/services and Chinese external data/broker routes; Rust execution requires separate `qars3` | Corporate-action price adjustment and account state exist. Current-listed-only Tushare universe and endpoint-adjusted history do not establish point-in-time universes | Requirements explicitly pin NumPy <2, conflicting with 2.3.5. Python advice/classifiers stop at 3.12; stale CI installs published package rather than testing the checkout |

## FinRL: useful experiments, unsafe default research path

### Observed implementation

The [README](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/README.md) describes the classic educational/research framework and points production-oriented users toward separate FinRL-X/FinRL-Trading projects. Those projects were not part of this four-repository audit.

The 2026 stock example downloads a static Dow ticker list over the combined training and trading interval. In [preprocessors.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/meta/preprocessor/preprocessors.py), `clean_data` pivots closing prices and drops any ticker column missing an observation anywhere in that interval. `preprocess_data` subsequently performs global `ffill().bfill()`. The [data preparation example](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/examples/FinRL_StockTrading_2026_1_data.py) applies these operations before its chronological train/trade split.

This creates two concrete risks: future completeness determines which assets appear in the past, and backward filling can move a future value into an earlier observation. Global filling also does not enforce ticker boundaries. Filling the completed date-by-ticker grid with zero is not a substitute for distinguishing “not listed,” “no quote,” and “no position.” Rolling technical indicators and turbulence are not all inherently forward-looking; the problem identified here is the specific preparation pipeline and its universe/imputation rules.

In [env_stocktrading.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/meta/env_stock_trading/env_stocktrading.py), the state contains the current bar's closing price and indicators. `step` buys/sells at those current state prices before incrementing the day. A signal that uses a completed daily close cannot normally execute at that same close without a separately justified order/data cutoff. The example charges percentage buy/sell fees; the inspected environment does not establish a bid/ask, liquidity, action-event, or delayed-fill model.

[yahoodownloader.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/meta/preprocessor/yahoodownloader.py) requests `auto_adjust=False`, then applies the adjusted-close/close ratio to OHLC and removes the raw adjustment columns. A test checks this adjustment. This is useful price normalization, but it does not preserve an executable raw-price/action ledger, delisting settlement, or a historical investable universe. Volume is not adjusted by that routine. A current static Dow list is not a historical constituent list.

There are implemented safeguards worth recognizing:

- `data_split` uses chronological boundaries.
- `GroupByScaler` separates fitting and transformation by ticker; its tests verify transformation against another dataset. The caller still chooses the fitting window.
- [models.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/agents/stablebaselines3/models.py) implements an ensemble loop with training ending before validation and trading following validation. This does not repair upstream future imputation or universe selection.
- The backtest example's mean-variance calculation estimates its mean/covariance from training data.
- Current environment regression tests cover list/NumPy-array holdings and reset/step behavior.

These tests were inspected, not run. No inspected test established invariance of past decisions when future input is changed, or correct availability/fill timing.

### Resource and adoption decision

The example sequentially trains A2C, DDPG, PPO, TD3, and SAC for 20,000 steps each. It does not pass a fixed seed in the inspected example. Replay-buffer settings of one million transitions occur in configuration. For illustration, two float32 observations for a 301-field state at one million transitions require about 2.4 GB before actions, rewards, model tensors, and data copies. That is an arithmetic estimate, not a measured FinRL memory profile.

The manifest includes Ray, multiple RL ecosystems, provider packages, and auxiliary tooling. `setup.py` reads requirements without passing an `install_requires` argument, while `pyproject.toml` provides Poetry dependency metadata; this inconsistency warrants checking the actual build path rather than assuming either file alone governs installation.

The [official Stable-Baselines3 PPO documentation](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html) supports CPU use for non-CNN PPO. Lack of a GPU therefore does not rule out a small experiment. It also does not justify making five-agent optimization part of QuantEngine's default experience.

**Decision:** keep a deterministic, causal CPU backtester as core. Defer DRL to an isolated, cancelable experiment with one small CPU policy, explicit seeds, memory/time limits, an independent execution simulator, and recorded trials. Adapt environment abstractions only after their timing semantics meet QuantEngine's contract.

## OpenBB v5: optional adapters and analytics

### Observed implementation and migration

The inspected provider inventory contains public-source modules such as BLS, Cboe, CFTC, Deribit, ECB, EIA, Fama-French, Federal Reserve, FINRA, FRED, government-US, IMF, JODI, Nasdaq, OECD, SEC, and TMX. Some require or optionally accept free keys. These are remote data adapters running in a local process, not bundled offline datasets. Public market data from an exchange adapter is also not authorization to trade through that service.

V5 removed the bundled provider packages alpha-vantage, benzinga, biztoc, econdb, finviz, fmp, intrinio, multpl, seekingalpha, stockgrid, tiingo, tradier, tradingeconomics, wsj, and yfinance. No yfinance provider package appears in the inspected current tree. The README and [momentum notebook](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/examples/BacktestingMomentumTrading.ipynb) still demonstrate the old shared route and `provider="yfinance"`. That notebook shifts its signal by one bar, which is a useful causal convention, but is an illustrative vector-return calculation without the inspected costs/action ledger of an execution engine. Its old provider call is not a current v5 integration template.

The [quantitative extension](https://github.com/openbq-org/OpenBB/tree/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/extensions/quantitative) calculates return/performance statistics and fits factor regressions locally. Tests check financial formulas, scale invariance, flat/short series, and agreement with statsmodels. Factor regressions fit the supplied aligned interval; they do not automatically enforce out-of-sample prediction cutoffs.

The FRED [series implementation](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/providers/fred/openbb_fred/models/series.py) exposes observation date ranges and transformations, but the inspected query model has no vintage/as-of parameter. Its normalization removes returned `realtime_start` and `realtime_end`. This finding is scoped to that convenience path, not a claim that every OpenBB macro endpoint has been audited. The inspected broader query helper and release-table/router files do not establish point-in-time safety for this series call.

The [official FRED real-time-period documentation](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) says the default retrieves current knowledge; [series observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) supports real-time and vintage parameters. Historical observation dates alone therefore cannot establish what a strategy knew at an earlier date. QuantEngine must preserve/query vintages explicitly.

The inspected Nasdaq historical helper parses OHLCV from the public historical endpoint, with a 10,000-row request limit. The Cboe path has source-specific coverage and validates symbols using a current directory. Neither inspected path establishes a retained raw/adjusted dual-price model, action availability ledger, delisted universe, or historical listing membership. This is an adapter-contract gap, not evidence that every provider's underlying prices lack adjustments.

### Windows and resource decision

The aggregate `openbb` package installs many extensions/providers. Its local desktop directory is a Tauri/React/Rust backend/environment manager, not an Electron quantitative trading application. Its documented approximately 35 MB wrapper excludes the environments and their packages; initial setup involves a Python environment and server tooling.

The quantitative module requires NumPy >=1.24 and SciPy >=1.11, which admit the target pins. Its CI defines Linux 3.10–3.14 and Windows 3.10/3.14 jobs. This is meaningful intended coverage, but no run result or exact Windows 3.13.16 combination was verified.

**Decision:** adapt typed provider boundaries, provenance, and local performance/factor metrics. Make source adapters optional and source-specific. Do not require cloud Workspace, install the aggregate stack, adopt the Tauri wrapper, or treat stale v4 examples as a v5 specification. Keep data licensing and PIT completeness visible at import time.

## Congressional disclosures: real versioning, incomplete publication timing

### Implemented strengths

The code keeps three distinct grains: source filings, printed transaction rows, and consolidated economic event versions. [events.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/lake/events.ts) sorts observations and creates later versions for recognized amendments. Earlier versions receive `supersededAt`; original availability remains separately recorded. Golden tests exercise option amendments, repeated disclosures, and same-instant correction handling.

[storage/sqlite.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/storage/sqlite.ts) uses transaction boundaries for filing replacement and rebuilds affected filers' events. Tests cover rollback and consolidation. Source hashes, extraction metadata, and processing timestamps are implemented. Model extraction compares independent structured reads and can fail rather than silently accept disagreement. Agreement still does not prove accuracy when models share OCR or systematic errors.

A pre-parsed [public dataset](https://huggingface.co/datasets/austin-starks/congressional-stock-trades) can be downloaded and queried locally without model/API keys. Its [methodology](https://huggingface.co/datasets/austin-starks/congressional-stock-trades/blob/main/METHODOLOGY.md) documents reprocessing, manual corrections, and difficult legacy filings. These are real maintenance practices; they also mean a current snapshot is not an immutable record of what an earlier extraction system knew.

### Critical availability and amendment boundaries

In [dates.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/lake/dates.ts) and [normalize.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/lake/normalize.ts), `availableAt` is reconstructed as end of day New York time on the House index filing date or Senate submitted date. The source labels accurately describe those inputs. The implementation does not observe a public-release timestamp.

[Official Senate guidance](https://www.ethics.senate.gov/public/index.cfm/financialdisclosure) allows reports to become public within 30 calendar days after filing. It also describes PTR filing deadlines based on notification/transaction dates and subsequent amendments. At least the Senate filing-date proxy can therefore precede actual public access. End-of-day rounding does not eliminate this gap. The exact relation between the House index date and publication was not independently established here.

The dataset's [snapshot manifest](https://huggingface.co/datasets/austin-starks/congressional-stock-trades/blob/main/snapshot.json) distinguishes availability and processing dates; actual processing can occur later. A present-day snapshot cannot recover historical publication instants just by reusing filing dates.

When querying corrected fields, filter the selected version by `availableAt <= asOf` and `supersededAt IS NULL OR supersededAt > asOf`. Filtering the newest corrected record solely by the event's original `firstAvailableAt` leaks later corrections.

Further inspected limitations:

- Matching uses owner, action, transaction date, ticker/asset type, and amount ranges, but does not parse option-contract identity from comments. Distinct contracts or repeated same-sized transactions can be difficult to distinguish.
- Corrections with the same reconstructed availability instant replace the prior version in place. Date-only source timing cannot express every same-day sequence.
- Earlier event-version contributor lists can accumulate later supporting rows. Do not use these un-timestamped contributor lists as historical features.
- Atomic replacement and event rebuilding are not an append-only, bitemporal extraction-revision archive. Later parsing/manual changes can rewrite an older interpretation even when amendment versions are retained.
- Printed amount ranges are not exact trade sizes, executed prices, holdings, or realized returns. PTR coverage is not a complete portfolio; some pooled investment transactions are exempt.
- Source archives and historical coverage need explicit accounting. Current official retention does not guarantee an indefinitely complete archive.

**Required adaptation:** preserve source document hashes, source/observed publication evidence, `firstSeenAt`, filing/notification/transaction dates, extraction revisions, and every version's knowledge interval. Record when publication time is a proxy. A first-seen timestamp collected now cannot prove when a years-old filing first became public. For historical proxy data, report delay sensitivity and avoid a PIT-certified label. Adding hypothetical delays is a research assumption, not recovery of an observed timestamp.

### Cost, rights, and Windows

The MIT license applies to the software. The dataset's [LICENSE_DATA.md](https://huggingface.co/datasets/austin-starks/congressional-stock-trades/blob/main/LICENSE_DATA.md) does not grant CC0 or unrestricted use; it points to financial-disclosure restrictions. Official Senate guidance prohibits unlawful use, certain commercial uses except public news/communications dissemination, credit-rating use, and solicitation. Whether a particular distribution or use falls within an exception was not determined in this technical audit. “Public” and “free to download” must not be converted into an unrestricted redistribution promise.

The [House calculator](https://ethics.house.gov/periodic-transaction-report-calculator/) confirms filing-delay rules. A politician's transaction date is never an appropriate default signal availability date.

For reconstructing official documents, the inspected defaults use OpenRouter-compatible remote model requests and Mistral OCR, with Poppler/Tesseract tooling. Configurable model endpoints are implemented, but reliable extraction on a 16 GB CPU-only local model has not been demonstrated. Node >=22.5, `node:sqlite`, and native dependencies require checking Electron's actual embedded Node and packaged Windows binaries.

**Decision:** support optional imported disclosure snapshots with provenance and timing labels. Adapt versioning, failure visibility, and local SQLite concepts. Defer automatic paid extraction, a political-copy trading strategy, and claims of exact historical public availability.

## QUANTAXIS: Chinese-market concepts, incompatible aggregate requirements

The inspected requirements explicitly demand `numpy>=1.24,<2.0`, conflicting with NumPy 2.3.5. They also pin PyArrow >=15,<18, pandas >=2,<3, statsmodels >=0.14,<0.15, and older analysis packages. Exact Windows/Python 3.13 wheels for the full dependency graph were not established. Removing upper bounds is not a compatibility fix.

Although `setup.py` permits Python >=3.9,<4, its classifiers and advice list support only through 3.12. The inspected [CI workflow](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/.github/workflows/pythonapp.yml) uses Ubuntu Python 3.8, installs the published `quantaxis` package, and does not run a checkout test command. The backward-compatibility script treats several connection/import failures as normal without failing. These files cannot substantiate the README's complete compatibility claim.

[QARSBridge/__init__.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QARSBridge/__init__.py) can fall back to a Python account if Rust is absent, but its placeholder Rust backtester raises an import error. [qars_backtest.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QARSBridge/qars_backtest.py) is primarily a wrapper around the separate `qars3` dependency. Claimed 10x/100x performance was not benchmarked here or established by the inspected wrappers. Some `qapro-rs` tree entries are tiny placeholders; a listed subsystem is not necessarily an implemented one.

The full architecture has MongoDB/ClickHouse and messaging/service paths. [QifiAccount.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QIFI/QifiAccount.py) does implement `nodatabase=True`, so it would be inaccurate to say every account operation requires a database. Full framework defaults and strategy paths are substantially heavier than this isolated local mode.

[data_fq.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QAData/data_fq.py) implements Chinese price adjustment for dividends, rights, and bonus shares. Forward-adjusted historical prices depend on the chosen endpoint; this is not a substitute for as-of actions, raw execution prices, and cash/share ledger events. The inspected Tushare fetch uses `stock_basic(list_status="L")`, a currently listed universe. External Tushare/TDX/Baostock access and their terms/credentials remain independent of the MIT code license.

**Decision:** defer the full framework and Rust bridge. If Chinese instruments become an explicit requirement, reconsider market calendars, presets, and accounting ideas in a separate adapter after target-stack and causal-data checks. Do not introduce its database/messaging stack or downgrade the approved NumPy environment to enable an unrelated platform.

## Statsmodels: verified package feasibility, no environment change

Checked 2026-10-11. [PyPI](https://pypi.org/project/statsmodels/0.15.0/) identifies 0.15.0 as the latest stable release, dated 2026-08-27, and lists `statsmodels-0.15.0-cp313-cp313-win_amd64.whl` (approximately 11.3 MB). This is the appropriate Python/architecture wheel family for an ordinary 64-bit CPython 3.13 Windows interpreter; a wheel tag is not a test of the user's exact patch level.

The release tag resolves to [278ff9950636cdd4939b4055e339a8e681d79cab](https://github.com/statsmodels/statsmodels/tree/278ff9950636cdd4939b4055e339a8e681d79cab). Its actual [pyproject.toml](https://github.com/statsmodels/statsmodels/blob/278ff9950636cdd4939b4055e339a8e681d79cab/pyproject.toml) declares:

| Runtime requirement | Compatibility with currently declared QuantEngine environment |
| --- | --- |
| Python >=3.10 | Python 3.13.16 satisfies the declared bound |
| NumPy >=1.23.5,<3 | Existing 2.3.5 satisfies the bound |
| SciPy >=1.8,!=1.9.2 | Existing 1.17.0 satisfies the bound |
| pandas >=1.4,!=2.1.0 | Additional dependency; installed version on the user's machine was not observed |
| patsy >=0.5.6 | Additional dependency |
| packaging >=21.3 | Additional dependency |
| formulaic >=1.1.0 | Additional dependency in this release |

The actual [LICENSE.txt](https://github.com/statsmodels/statsmodels/blob/278ff9950636cdd4939b4055e339a8e681d79cab/LICENSE.txt) is BSD-3-Clause. The [installation page](https://www.statsmodels.org/stable/install.html) has some older support text; the inspected release manifest and PyPI wheel listing provide the more specific release evidence.

QuantEngine's requirements file currently pins only NumPy 2.3.5 and SciPy 1.17.0. There is no declared-range reason to upgrade either merely to evaluate statsmodels. Runtime constraints differ from source-build requirements: the release's build system uses Meson/Cython, build NumPy >=2,<3 and SciPy >=1.13,<2. A prebuilt wheel avoids making source compilation the default path.

**Decision:** an optional CPU econometrics module is plausible, but statsmodels was not installed and no compatibility or import test was performed. Before adoption, resolve all additions in an isolated environment with the existing NumPy/SciPy constraints, inspect the proposed package changes, use the Windows cp313 binary wheels, then test only the estimators QuantEngine actually needs. Pin the tested dependency set and preserve notices. Do not use a blanket upgrade command or assume satisfying metadata proves numerical/runtime compatibility.

## Research principles to carry into QuantEngine

The inspected sources support a smaller, explicit core:

1. Separate observation time, public/market availability time, ingestion time, and revision time. Apply as-of selection before feature construction and retain revision provenance.
2. Retain raw prices and separate corporate-action events. State whether a return is price-only or total return. Keep delisted assets and historical membership evidence where available; label incomplete datasets.
3. Compute close-derived signals after the close and fill at the next eligible bar under a declared execution rule. Charge fees and configurable spread/slippage; report unsupported liquidity assumptions.
4. Fit scaling, imputation, regressions, and model selection only inside each training window. A future-data mutation check should leave earlier features, choices, and fills unchanged.
5. Use chronological training/validation/testing with an untouched final interval, record every strategy/parameter trial, and report cost/delay sensitivity. The [Bailey et al. backtest-overfitting paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) explains why repeated selection can invalidate a seemingly independent holdout. PBO or a deflated performance statistic may be useful later, not a certificate of profitability.
6. Make paid data, remote models, broker integration, and heavy training explicit optional extensions. Local algorithms can operate on imported files without making claims about universal free historical data.
7. Distinguish package licensing, data access cost, data redistribution rights, and research-validity guarantees.

The [yfinance maintainer documentation](https://github.com/ranaroussi/yfinance) explicitly distinguishes its code license from Yahoo data rights and cautions about personal-use access. This is a source-specific caution, not a legal determination for every QuantEngine use.

## Access gaps and limits

- All four supplied repository roots and recursive trees were accessible. Tree responses were not truncated. The only transient file-read failure, a congressional SQLite file disconnect, succeeded on retry.
- Inspection covered the files listed below, not every code path in every repository. Absence statements are scoped to those paths or to named package entries in the inspected tree.
- CI definitions were read. Their latest statuses, full matrices' passing histories, released artifacts, dependency security, and installed Windows behavior were not independently verified.
- No upstream training, performance, reproducibility, or memory benchmark was run. README speed/accuracy claims remain claims.
- Source terms were examined where directly material. This was not a complete legal review of data-source terms or transitive licensing.
- The direct U.S. Code section page returned a maintenance response. Disclosure restrictions were corroborated through official Senate guidance and the dataset's own data-license file. No missing statutory text was invented.
- Long historical PIT publication evidence, historical delisted security masters, complete action-event rights, and all revision vintages were not obtained. These remain data-acquisition gaps, not features an engine library can infer.

## Inspected source-file inventory

Each file below was retrieved at the exact commit in the version table. Listing tests means their source was inspected; it does not mean they were executed.

### AI4Finance-Foundation/FinRL

- [.github/workflows/test.yml](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/.github/workflows/test.yml)
- [LICENSE](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/LICENSE)
- [README.md](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/README.md)
- [docs/source/start/installation.rst](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/docs/source/start/installation.rst)
- [examples/FinRL_StockTrading_2026_1_data.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/examples/FinRL_StockTrading_2026_1_data.py)
- [examples/FinRL_StockTrading_2026_2_train.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/examples/FinRL_StockTrading_2026_2_train.py)
- [examples/FinRL_StockTrading_2026_3_Backtest.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/examples/FinRL_StockTrading_2026_3_Backtest.py)
- [finrl/agents/stablebaselines3/models.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/agents/stablebaselines3/models.py)
- [finrl/config.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/config.py)
- [finrl/config_tickers.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/config_tickers.py)
- [finrl/meta/env_stock_trading/env_stocktrading.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/meta/env_stock_trading/env_stocktrading.py)
- [finrl/meta/preprocessor/preprocessors.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/meta/preprocessor/preprocessors.py)
- [finrl/meta/preprocessor/yahoodownloader.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/finrl/meta/preprocessor/yahoodownloader.py)
- [pyproject.toml](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/pyproject.toml)
- [requirements.txt](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/requirements.txt)
- [setup.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/setup.py)
- [unit_tests/environments/test_stocktrading.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/unit_tests/environments/test_stocktrading.py)
- [unit_tests/preprocessors/test_groupby_scaler.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/unit_tests/preprocessors/test_groupby_scaler.py)
- [unit_tests/preprocessors/test_yahoodownloader.py](https://github.com/AI4Finance-Foundation/FinRL/blob/00f3596facd01cced5217d875d8c1fc413a31665/unit_tests/preprocessors/test_yahoodownloader.py)

### openbq-org/OpenBB

- [.github/workflows/test-unit-openbb-quantitative.yml](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/.github/workflows/test-unit-openbb-quantitative.yml)
- [LICENSE](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/LICENSE)
- [README.md](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/README.md)
- [assets/extensions/provider.json](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/assets/extensions/provider.json)
- [desktop/README.md](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/desktop/README.md)
- [desktop/package.json](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/desktop/package.json)
- [examples/BacktestingMomentumTrading.ipynb](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/examples/BacktestingMomentumTrading.ipynb)
- [openbb_platform/core/openbb_core/provider/standard_models/equity_historical.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/core/openbb_core/provider/standard_models/equity_historical.py)
- [openbb_platform/core/openbb_core/provider/standard_models/fred_series.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/core/openbb_core/provider/standard_models/fred_series.py)
- [openbb_platform/core/pyproject.toml](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/core/pyproject.toml)
- [openbb_platform/extensions/quantitative/openbb_quantitative/factors.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/extensions/quantitative/openbb_quantitative/factors.py)
- [openbb_platform/extensions/quantitative/openbb_quantitative/performance.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/extensions/quantitative/openbb_quantitative/performance.py)
- [openbb_platform/extensions/quantitative/pyproject.toml](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/extensions/quantitative/pyproject.toml)
- [openbb_platform/extensions/quantitative/tests/test_factors.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/extensions/quantitative/tests/test_factors.py)
- [openbb_platform/extensions/quantitative/tests/test_performance.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/extensions/quantitative/tests/test_performance.py)
- [openbb_platform/providers/cboe/openbb_cboe/models/equity_historical.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/providers/cboe/openbb_cboe/models/equity_historical.py)
- [openbb_platform/providers/fred/openbb_fred/models/release_table.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/providers/fred/openbb_fred/models/release_table.py)
- [openbb_platform/providers/fred/openbb_fred/models/series.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/providers/fred/openbb_fred/models/series.py)
- [openbb_platform/providers/fred/openbb_fred/routers/economy.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/providers/fred/openbb_fred/routers/economy.py)
- [openbb_platform/providers/fred/openbb_fred/utils/query.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/providers/fred/openbb_fred/utils/query.py)
- [openbb_platform/providers/nasdaq/openbb_nasdaq/models/equity_historical.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/providers/nasdaq/openbb_nasdaq/models/equity_historical.py)
- [openbb_platform/providers/nasdaq/openbb_nasdaq/utils/helpers.py](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/providers/nasdaq/openbb_nasdaq/utils/helpers.py)
- [openbb_platform/pyproject.toml](https://github.com/openbq-org/OpenBB/blob/ae0268771f761b036996d81bd21522ce79d95415/openbb_platform/pyproject.toml)

### austin-starks/congressional-disclosures

- [.github/workflows/ci.yml](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/.github/workflows/ci.yml)
- [LICENSE](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/LICENSE)
- [README.md](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/README.md)
- [package.json](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/package.json)
- [packages/congressional-disclosures/package.json](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/package.json)
- [packages/congressional-disclosures/src/cli.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/cli.ts)
- [packages/congressional-disclosures/src/extraction/ptrConsensus.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/extraction/ptrConsensus.ts)
- [packages/congressional-disclosures/src/lake/dates.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/lake/dates.ts)
- [packages/congressional-disclosures/src/lake/events.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/lake/events.ts)
- [packages/congressional-disclosures/src/lake/normalize.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/lake/normalize.ts)
- [packages/congressional-disclosures/src/lake/tests/fixtures/senateOptionAmendment.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/lake/tests/fixtures/senateOptionAmendment.ts)
- [packages/congressional-disclosures/src/lake/tests/normalizationGolden.test.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/lake/tests/normalizationGolden.test.ts)
- [packages/congressional-disclosures/src/lake/types.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/lake/types.ts)
- [packages/congressional-disclosures/src/providers/mistralOcr.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/providers/mistralOcr.ts)
- [packages/congressional-disclosures/src/providers/openaiCompatible.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/providers/openaiCompatible.ts)
- [packages/congressional-disclosures/src/sources/senate.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/sources/senate.ts)
- [packages/congressional-disclosures/src/storage/sqlite.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/storage/sqlite.ts)
- [packages/congressional-disclosures/src/tests/sqliteRepository.test.ts](https://github.com/austin-starks/congressional-disclosures/blob/2965e8796bd4cb9423a83b964a1f9dbd076a0ad6/packages/congressional-disclosures/src/tests/sqliteRepository.test.ts)

### yutiansut/QUANTAXIS

- [.github/workflows/pythonapp.yml](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/.github/workflows/pythonapp.yml)
- [LICENSE](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/LICENSE)
- [QUANTAXIS/QAData/data_fq.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QAData/data_fq.py)
- [QUANTAXIS/QAFetch/QABaostock.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QAFetch/QABaostock.py)
- [QUANTAXIS/QAFetch/QATushare.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QAFetch/QATushare.py)
- [QUANTAXIS/QARSBridge/__init__.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QARSBridge/__init__.py)
- [QUANTAXIS/QARSBridge/qars_account.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QARSBridge/qars_account.py)
- [QUANTAXIS/QARSBridge/qars_backtest.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QARSBridge/qars_backtest.py)
- [QUANTAXIS/QAStrategy/qactabase.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QAStrategy/qactabase.py)
- [QUANTAXIS/QAUtil/QASetting.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QAUtil/QASetting.py)
- [QUANTAXIS/QIFI/QifiAccount.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/QIFI/QifiAccount.py)
- [QUANTAXIS/__init__.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/QUANTAXIS/__init__.py)
- [README.md](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/README.md)
- [requirements.txt](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/requirements.txt)
- [scripts/test_backward_compatibility.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/scripts/test_backward_compatibility.py)
- [scripts/test_dependencies.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/scripts/test_dependencies.py)
- [setup.py](https://github.com/yutiansut/QUANTAXIS/blob/232aa7ac9869966108f02a8fff85f1f7b09a9ce2/setup.py)

### Supplemental primary sources

- [OpenBB v5 license FAQ](https://docs.openbb.co/odp/python/faqs/license) — accessed 2026-10-11.
- [OpenBB v5 providers and migration](https://docs.openbb.co/odp/python/extensions/providers) — accessed 2026-10-11.
- [FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) — accessed 2026-10-11.
- [FRED series observations](https://fred.stlouisfed.org/docs/api/fred/series_observations.html) — accessed 2026-10-11.
- [Senate official financial-disclosure guidance](https://www.ethics.senate.gov/public/index.cfm/financialdisclosure) — accessed 2026-10-11.
- [House PTR deadline calculator](https://ethics.house.gov/periodic-transaction-report-calculator/) — accessed 2026-10-11.
- [Disclosure dataset card](https://huggingface.co/datasets/austin-starks/congressional-stock-trades) — accessed 2026-10-11.
- [Disclosure dataset methodology](https://huggingface.co/datasets/austin-starks/congressional-stock-trades/blob/main/METHODOLOGY.md) — accessed 2026-10-11.
- [Disclosure data license](https://huggingface.co/datasets/austin-starks/congressional-stock-trades/blob/main/LICENSE_DATA.md) — accessed 2026-10-11.
- [Disclosure snapshot manifest](https://huggingface.co/datasets/austin-starks/congressional-stock-trades/blob/main/snapshot.json) — accessed 2026-10-11.
- [Stable-Baselines3 PPO documentation](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html) — accessed 2026-10-11.
- [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) — accessed 2026-10-11.
- [yfinance maintainer documentation](https://github.com/ranaroussi/yfinance) — accessed 2026-10-11.
- [statsmodels PyPI release and Windows wheel listing](https://pypi.org/project/statsmodels/0.15.0/) — accessed 2026-10-11.
- [statsmodels installation documentation](https://www.statsmodels.org/stable/install.html) — accessed 2026-10-11.
- [statsmodels release manifest](https://github.com/statsmodels/statsmodels/blob/278ff9950636cdd4939b4055e339a8e681d79cab/pyproject.toml) — accessed 2026-10-11.
- [statsmodels actual source license](https://github.com/statsmodels/statsmodels/blob/278ff9950636cdd4939b4055e339a8e681d79cab/LICENSE.txt) — accessed 2026-10-11.

