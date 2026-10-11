# Quant Engine architecture

## Native process boundary

`desktop/main.ts` owns application identity `org.quantengine.desktop`, the native window, tray, path dialogs, login preference, settings sequencing and IPC authorization. The application uses its own `QuantEngine` user-data folder. The renderer is sandboxed, has no Node integration, has an explicit content-security policy and cannot open new windows or navigate away.

`desktop/preload.ts` exposes a small frozen `window.quant` API. Requests use `quant:command`; state events use `quant:state`. Main-process authorization checks the trusted window and main frame. Commands return `{ok,value}` or `{ok:false,error}`. Native dialogs select import/export/storage paths. Renderer input cannot request an arbitrary executable or report pathname.

`desktop/engine.ts` schedules one numerical operation at a time. A cycle starts after its predecessor completes; interval defaults to 60 seconds. Preference writes are queued, and starting new research is blocked until they settle. A normal close hides the window in the system tray. Pause closes the owned worker and recovers incomplete database entries before releasing the scheduler lock. Quit rejects new work and drains accepted settings, storage and worker operations before the application exits.

## Numerical process

`desktop/transport.ts` launches Python without a shell, with a hidden Windows console and explicit `-X utf8 -u` options. UTF-8 pipe decoders preserve characters across chunks. Numerical-library threads are capped at two, or one with lower worker priority in low-CPU mode. The worker has a 10-minute job limit and no child executables.

Development resolves `QUANT_PYTHON` or local Python. The Windows release resolves exactly `process.resourcesPath/quant-python/python.exe`. The entry point is `app.getAppPath()/workers/quant_worker.py`. The build emits `dist/main.cjs`, `dist/preload.cjs` and `app/ui.js` from authored TypeScript/JavaScript.

`workers/quant_worker.py` accepts one JSON-line stdin request. It emits real stage/progress events, followed by one final result. Commands are `inspect`, `import`, `refresh`, `analyse`, `history` and `report`. Cancellation kills only the owned numerical child; the next recovery marks unfinished runs interrupted. A successfully committed report is the only source of completed UI metrics.

`workers/quant_core.py` independently implements simple returns, covariance estimation, SLSQP allocation, Gaussian cumulative arithmetic risk, bounded circular block resampling, historical stress and rolling momentum decisions. Every backtest decision sees only prior returns. Costs apply to traded risky notional, including initial entry; holdings drift between rebalances. The equal-weight baseline follows the same fee convention and cash yields zero.

## Storage boundary

`workers/quant_store.py` owns SQLite writes. Under the selected storage folder:

| Path | Contents |
| --- | --- |
| `quant.sqlite3` | Dataset provenance and completed/failed/interrupted run history |
| `datasets/` | Immutable hashed UTF-8 CSV snapshots |
| `sources/` | Original ECB XML bytes keyed by their hash |
| `reports/` | Full atomic JSON reports after successful numerical completion |

Each completed report retains source type, retrieval time, snapshot SHA-256, parameters, actual seed, runtime versions, output and timing. Report publication writes a temporary file, flushes it and replaces the final pathname before SQLite marks the run completed. A crash can leave an unreferenced completed file; it cannot promote an unfinished row to completed. Import validation occurs before dataset registration, so failed imports do not replace the selection.

Wide CSV imports require strictly increasing unique ISO dates and positive finite prices. The ECB XML cache uses currency units per EUR and stores reference rates, not executable prices. Continuous ECB research attempts one refresh per UTC date only when selected and enabled; failure retains the snapshot and error. Imported and synthetic data work fully offline.

## Interpretation boundary

Static minimum-variance weights describe risk over the entire supplied history. The costed momentum backtest is a separate chronological experiment. Parameter sensitivity reuses history with different warm-up windows; it does not select an independently validated winning strategy. Gaussian and bootstrap horizon returns use arithmetic aggregation. The report discloses fixed historical moments, limited tail coverage, circular wrapping, no dividend/split correction and no execution model.
