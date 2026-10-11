# Discovery record · Quant Engine

## Scope and access

Research date: 11 October 2026. Build a standalone free local Windows research application that performs repeated numerical analysis, persists experiment evidence and remains controllable from a native monitor/tray. Target: Intel Core 5 210H, 16 GB RAM, integrated graphics and ample D: storage.

All four supplied Quant examples were opened and read. UCI and quant-research.org initially failed retrieval, then succeeded on retry; they are no longer access gaps. GitHub README, repository metadata and actual LEAN licence were inspected. The awesome-quant list supplies discovery leads, not blanket verification of every listed project.

The user's QuantOS repository was inspected at commit 57f508cf15cbd6599d873d2cecf7b1b838bff066 as prior context. Its tested synthetic workflow and source tracking informed acceptance criteria; this release uses a new small numerical core and original desktop rather than its browser launcher. Broker accounts, licensed market datasets and target-device execution were not accessed.

## Evidence ledger

| Pick | Evidence and relevance | Licence / maintenance / remaining verification |
|---|---|---|
| [QuantConnect](https://www.quantconnect.com/) and [LEAN](https://github.com/QuantConnect/Lean) | Primary platform/docs and actual LEAN licence read. Strong event-driven backtesting baseline; current recommended CLI requires a paid-tier organisation and Docker. | LEAN Apache-2.0; repo pushed 9 October 2026 at inspection. Platform/data entitlements are separate. No engine code copied. |
| [awesome-quant](https://github.com/wilsonfreitas/awesome-quant) | Supplied curated README read; library discovery across risk, data, pricing and backtesting. | Repository licence metadata is unknown at inspection; last push 11 October 2026. Candidate-library licences require individual review. List not copied or treated as endorsed. |
| [UCI quantitative software guide](https://guides.lib.uci.edu/dataanalysis/quant) | Primary university guide read; establishes Python/R alongside commercial analysis tools. | Page updated 15 September 2026. A guide is not a reproducibility study or software licence. |
| [QuantDeveloper Studio](https://quant-research.org/) | Primary product page read: source provenance, chronological validation, costs and saved experiment context. Relevant workflow competitor. | Proprietary product; advertised $100 monthly lease with online subscriptions not yet open at inspection. Implementation and performance not independently reproduced. |
| [NumPy random generators](https://numpy.org/doc/stable/reference/random/generator.html) | Official interfaces and actual wheel metadata checked; seeded numerical sampling and vector algebra. | NumPy 2.3.5 BSD-3-Clause and bundled notices retained; Windows cp313 wheel SHA matched PyPI. Pin and seed do not guarantee bitwise cross-platform equality. |
| [SciPy SLSQP](https://docs.scipy.org/doc/scipy/reference/optimize.minimize-slsqp.html) | Primary solver documentation and executable constrained portfolio tests. | SciPy 1.17.0 BSD-3-Clause plus bundled licences retained; Windows cp313 wheel SHA matched PyPI. Optimization success and constraints checked. |
| [Circular block resampling, Politis & Romano](https://statistics.stanford.edu/technical-reports/circular-block-resampling-procedure-stationary-data) | Primary Stanford report record and author publication list identify the established method. | Research reference; report code not redistributed. The release uses a fixed five-observation circular bootstrap; its assumptions do not establish coverage on a new dataset. |
| [ECB exchange reference rates](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) | Primary ECB reference-rate and disclaimer pages inspected; public historical XML source. | Reference observations, not tradable quotes. Attribution retained; future redistribution/use still follows ECB terms. No paid entitlement assumed. |
| [Python 3.13.16](https://www.python.org/downloads/release/python-31316/) | Official embeddable Windows x64 archive matched the published windows-3.13.16.json SHA-256. | PSF licence bundled; 30 September 2026 maintenance release. Windows execution remains a device acceptance check. |

## Decision

Start with a local NumPy/SciPy research engine: validated CSV and synthetic/ECB datasets, long-only minimum variance, Gaussian and empirical-bootstrap risk, costed chronological momentum tests, descriptive sensitivity and durable source snapshots. A serial scheduler and two BLAS threads bound resource use; larger path counts supply meaningful optional workload.

Strong baselines: equal-weight and zero-yield cash for the backtest, an analytic two-asset minimum-variance solution for optimization, and direct Gaussian sampling for deterministic risk checks. LEAN is the stronger alternative for multi-asset event-driven strategies and later execution; it would add runtime/setup and data scope to this first complete loop.

Differentiation is the original research monitor, offline-first setup, bounded continuous jobs and inspectable source/run evidence. These numerical methods are established. Competitor review does not prove an unprecedented algorithm or investment advantage, and product-name clearance is unresolved.

The main uncertainty is usefulness on genuine point-in-time market data under defensible costs and data rights. Reverse or extend the architecture when richer instruments/corporate actions/event availability cannot be represented faithfully by daily wide prices.

## First experiment

Hypothesis: the native application can continuously run reproducible numerical research and persist truthful completed, cancelled and failed states without overloading a 16 GB computer.

Protocol: analyse the seeded example twice at 50,000 paths and a 20-observation horizon; compare numerical outputs within tolerance, metadata, run IDs and source hashes. Compare the optimizer against the analytic two-asset optimum and the backtest against equal-weight/cash on the same evaluation dates. Start the schedule, close to tray, reopen, pause an active heavy run, then restart and reopen saved evidence. Repeat with an authorised adjusted-price CSV; explicitly refresh and cache ECB reference observations.

Budget: one worker, two BLAS threads; default 50,000 paths, optional 1,000,000, batched draws; 60-second interval after completion. Metrics: elapsed time, peak memory, schedule responsiveness, constraint error, seed reproducibility, gross/net returns and provenance completeness. Equal timestamps or repeated static data are not marketed as fresh market information.

Success: real completed reports, unique persisted runs, no overlapping worker, cancellation/quit stops it, invalid data rejected without replacing the chosen valid dataset, no orphan worker, readable export and at least 2 GB free system RAM on the target device. Failure: premature completed state, future-dependent decisions, lost source/report evidence, or uncontrolled memory/CPU.

Fresh host evidence is in VALIDATION.md. Host timing does not predict target Windows performance. Next action: device acceptance, then formal chronological parameter-selection and independent held-out evaluation before paper execution.
