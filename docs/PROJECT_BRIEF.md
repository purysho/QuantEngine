# Quant Engine project brief

Quant Engine is a free-to-run, independent local numerical research desktop application. Its provisional name describes its purpose: repeatedly calculate portfolio, risk and chronological strategy results using this computer's CPU. It has its own application identity, source, storage, runtime and release package.

## First release

- A native Windows Electron window with monitor, datasets, run history and preferences.
- NumPy/SciPy analysis: sample covariance/correlation, diagonal shrinkage and long-only minimum-variance optimization.
- Seeded Gaussian and empirical circular block-bootstrap horizon risk, including VaR and expected shortfall.
- Chronological positive-momentum/inverse-volatility backtest with drift, costs, equal-weight/cash baselines and descriptive lookback sensitivity.
- Offline synthetic example, validated imported CSV snapshots and optional public ECB reference-rate snapshots.
- One active worker, bounded risk batches, saved reports/provenance, deterministic pause cancellation, close to tray, explicit Quit and opt-in startup behavior.

The target device is Windows 11 Home x64, Intel Core 5 210H, 16 GB RAM and integrated graphics. Default storage is `D:\Quant-Engine`; another writable local folder can be selected through a native dialog. Ordinary use does not require a terminal, paid API or account. Graphics display numerical outputs; GPU acceleration is not required.

## Acceptance

1. Extract and open the Windows application with its dedicated numerical runtime.
2. Run the clearly labeled offline example and receive a complete numerical report.
3. Import valid chronological prices, reject invalid input, and preserve immutable source evidence.
4. Start continuous work, observe actual completed calculations, pause an active worker, and reopen history after restart.
5. Export a complete reproducible report or equity CSV through a native save dialog.

This first release is research software. It does not route orders or provide brokerage access. Gaussian assumptions, finite historical sampling, dataset adjustment limitations and reused-history sensitivity are visible in the report. The static risk allocation and the momentum strategy backtest are separate analyses.

See `DISCOVERY.md` for the research landscape, `ARCHITECTURE.md` for implementation boundaries, `BUILD_PLAN.md` for milestone gates, `EVALUATION.md` for verification, and `USER_GUIDE.md` for the Windows workflow.
