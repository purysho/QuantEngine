# Quant Engine build milestones

| Milestone | Deliverable | Acceptance gate | State |
| --- | --- | --- | --- |
| 1. Numerical core | Returns, covariance, constrained allocation, Gaussian/block risk, chronological strategy and baselines | Python tests prove .8/.2 analytic allocation, seeded repeatability, tail ordering, costs and no lookahead | Implemented |
| 2. Durable evidence | Immutable snapshots, source hashes, SQLite and atomic complete reports | Subprocess tests reopen exact reports; invalid import/failure retain completed data; killed worker recovers interrupted | Implemented |
| 3. Native engine | Dedicated worker transport, settings queue, scheduling, pause, tray and opt-in startup | TypeScript tests prove one worker, immediate history recovery, UTF-8 paths, ordered settings and shutdown drain | Implemented |
| 4. Scientific interface | Monitor, four metrics, equity/risk/correlation/sensitivity, datasets, history and preferences | Native preload/renderer health test plus actual numerical run; large-history renderer regression | Implemented; visual review documented separately |
| 5. Windows portable release | Native executable, separate embedded Python/NumPy/SciPy, icons, complete source and guides | Build archive inspection, published dependency hashes and on-device extraction/run/import/pause/restart/export check | Package integration and Windows device check |

## Commands

From the project root:

```sh
npm ci
npm run typecheck
npm test
python3 -m unittest discover -s tests -p 'test_*.py'
npm run build
npm start
```

Development Python requires `pip install -r requirements.txt`. Windows release assembly is `npm run package:win`; it includes the separate embedded runtime prepared for that build. `--self-test` creates isolated temporary storage and checks the native renderer, preload, absence of renderer Node integration, and a real 5,000-path completed report.

## Deferred scope

Event-driven strategy plugins, stronger out-of-sample experiment selection, additional market-data adapters, a paper execution environment, an automatic updater and signing are separate milestones. The current application already performs and persists actual continuous numerical work; deferred features are not represented as completed controls.
