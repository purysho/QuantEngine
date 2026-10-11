# Validation evidence · 0.1.0

Checks performed on 11 October 2026 in the Linux build environment. The numerical host interpreter is Python 3.12.14; the supplied Windows app carries its own Python 3.13.16. Actual Windows x64 execution on the target laptop remains pending.

| Check | Observed result |
|---|---|
| Full Python numerical/storage suite | 18 passed, 0 failed: exact returns, analytic allocation, Gaussian/bootstrap seed behavior, chronology, costed baselines, sensitivity, source validation, atomic reports, failed and interrupted history. |
| Full desktop/transport suite | 12 passed, 0 failed: serial worker, pause/recovery, Unicode pipes/paths, settings ordering, once-daily refresh failure, shutdown drain, repeated native Quit prevention, and 60,000-observation chart rendering. |
| Typecheck and build | Exited 0; main, isolated preload and renderer bundles produced. |
| Native hidden self-test | Actual preload/renderer plus a real 5,000-path numerical report, 504 example observations, no exposed Node require; exited 0. |
| Reproducible first experiment | Two 50,000-path runs with identical settings/seed/source returned identical numerical fields, unique run IDs and identical reopened reports. Host elapsed time 0.435 and 0.515 seconds. |
| Real ECB refresh | Fetched and persisted 65 observations across 8 FX reference series. CSV SHA-256: `2f37169b0e9e47401101083035e6fae99f0667a402e40559e750d1dff4fd2a2d`. Source retrieval was real, separate from fixture tests. |
| Native continuous loop | Completed three real reports, including work while the window was hidden in tray mode; reopened, paused, reopened a saved report and exported JSON. No renderer script errors. |
| Native repeated Quit | During a real 1,000,000-path, 252-observation-horizon job, two native Quit requests stopped every owned worker and left three completed runs plus one interrupted run, with no running history row. |
| Design inspection | Actual monitor rendered real values and costed equity curves with the dark/mint/cyan design. Synthetic data and report visibly labelled. |
| Independent review | IPC, cancellation statuses, UTF-8, long chart, ordered settings and shutdown-drain findings fixed. Final focused review found no remaining Important/Critical issue in those areas. |

`experiments/host-numerical.json` records the repeat-run, source and runtime evidence. The host timings are not laptop speed forecasts. `experiments/host-native-ui.json` records the completed tray/schedule/report/export loop. Linux tray-mode testing verifies window lifecycle and calculations while hidden; Windows notification-area behavior still needs device acceptance.

The optimized static risk weights and momentum strategy are separate calculations. The example backtest contains actual negative historical research returns; the app does not fabricate profitable results. Historical outputs and descriptive sensitivity do not establish future investment performance.

Linux GUI QA used a virtual X server and a QA-only bypass of POSIX singleton sockets, which this host blocks. Production Windows retains the single-instance lock and renderer sandbox. Root-only host testing passed --no-sandbox to the test executable; this is not a Windows launcher flag.

Official Python and PyPI wheel SHA-256 pins matched before extraction. Embedded Python is launched with explicit UTF-8/unbuffered flags, and libraries/worker modules are included with their actual licences. Windows PE identity, icon and required resources are inspected during packaging. Windows launch and DLL loading, native tray/login/file-dialog behavior, Chinese drive paths and actual device RAM/CPU measurements remain EVALUATION.md checks. The release is portable and unsigned.
