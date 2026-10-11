# Quant Engine evaluation

## Verification record

Host verification uses Linux Python 3.12 with NumPy 2.3.5 and SciPy 1.17.0. The Windows portable package has its own Python 3.13.16 and corresponding Windows x64 NumPy/SciPy wheels. Host tests establish numerical and desktop process behavior; they do not substitute for running the Windows binaries on the target laptop.

The full Python suite has 18 tests covering strict prices/dates, exact returns, analytical constrained allocation, deterministic Gaussian/bootstrap tails, chronological decisions, transaction costs and baselines, real sensitivity, persistence/reopening, source hash retention, invalid input, unknown report IDs and killed-worker recovery. The desktop suite additionally exercises a real UTF-8 worker path, pause/recover/next-run sequence, concurrent preference persistence, cached-data refresh failure, shutdown drain and a 60,000-observation renderer curve.

Native `--self-test` checks the trusted preload transport, sandboxed renderer, dataset inspection and a real completed 5,000-path report. Visual QA checks every primary page and completed chart using the native Electron renderer. Build output is `dist/main.cjs`, `dist/preload.cjs` and `app/ui.js`; numerical entry is `workers/quant_worker.py`.

Exact latest command results, counts, timings and native evidence are retained in `PROGRESS.md`.

## Windows device acceptance

1. Extract the full portable ZIP into a local folder. Open `QuantEngine.exe` without a development terminal.
2. Confirm the default `D:\Quant-Engine` or choose a writable local folder. Keep the synthetic example selected and run once.
3. Confirm actual values, four chart tabs, Gaussian/bootstrap comparison and separately labeled risk allocation/backtest. Open the report's methods and snapshot hash.
4. Import a valid UTF-8 CSV from a path containing non-ASCII characters. Verify its copied snapshot. Try missing, duplicate or unsorted rows and confirm the previous selection remains usable.
5. Set one million paths and a long horizon; start, then pause while computing. Verify interrupted history appears immediately and the last completed report remains available. Run again successfully.
6. Start continuous mode, close the window, reopen from the tray and confirm completed history advanced while awake. Pause; choose **Quit Quant Engine** and confirm the worker stops.
7. Reopen and confirm settings/history restore while calculation remains paused by default. Test startup/login/resumption only after explicitly enabling their separate preferences.
8. Export JSON and equity CSV through the native save dialog. Reopen the JSON and inspect seed, parameters, source SHA-256 and runtime versions.
9. Optionally refresh ECB with network access. Confirm quote basis per EUR, retrieval time and source cache. Disconnect and verify the prior cached dataset remains usable and any refresh failure stays visible.

## Limits to assess

- Prices need consistent observation spacing and appropriate adjustment supplied by the importer.
- Gaussian risk can miss fat tails; empirical blocks cannot generate unobserved regimes.
- Different sensitivity windows are descriptive overlapping-history experiments.
- More paths reduce simulation sampling noise; they do not fix data/model assumptions.
- Runs are retained rather than automatically deleted. Large imported histories produce larger report archives; monitor free disk space and back up the selected folder while paused and closed.
- The first release is portable, unsigned and has no automatic updater or brokerage/order interface.
