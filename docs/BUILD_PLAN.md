# Quant Engine build milestones

| Milestone | Deliverable | Acceptance gate | State |
| --- | --- | --- | --- |
| 1. Numerical core | Returns, covariance, constrained allocation, Gaussian/block risk, chronological strategy and baselines | Python tests prove .8/.2 analytic allocation, seeded repeatability, tail ordering, costs and no lookahead | Implemented |
| 2. Durable evidence | Immutable snapshots, source hashes, SQLite and atomic complete reports | Subprocess tests reopen exact reports; invalid import/failure retain completed data; killed worker recovers interrupted | Implemented |
| 3. Native engine | Dedicated worker transport, settings queue, scheduling, pause, tray and opt-in startup | TypeScript tests prove one worker, immediate history recovery, UTF-8 paths, ordered settings and shutdown drain | Implemented |
| 4. Scientific interface | Monitor, four metrics, equity/risk/correlation/sensitivity, datasets, history and preferences | Native preload/renderer health test plus actual numerical run; large-history renderer regression | Implemented; visual review documented separately |
| 4b. 0.2 research release | Exact empirical tails, next-close execution, Student-t/Hill risk, options engine and page, chronological ridge, pairs and market-making modules, CI | 67 Python + 17 TypeScript tests; four measured experiments; native self-test prices a reference option through the bridge | Implemented on Linux; Windows CI and laptop checks pending |
| 5. Windows portable release | Native executable, separate embedded Python/NumPy/SciPy, icons, complete source and guides | Build archive inspection, published dependency hashes and on-device extraction/run/import/pause/restart/export check | Package integration and Windows device check |

## Commands

From the project root:

```sh
npm ci
npm run typecheck
npm test
npm run test:quant
npm run build
npm start
```

Development Python requires `pip install -r requirements.txt`. Windows release assembly is `npm run package:win`; it includes the separate embedded runtime prepared for that build. `--self-test` creates isolated temporary storage and checks the native renderer, preload, absence of renderer Node integration, and a real 5,000-path completed report.

## Deferred scope

Desktop pages for pairs/market making/alpha, VaR exception backtests, Newey–West and deflated Sharpe, GARCH-t risk, Kalman hedge ratios, event-driven strategy plugins, additional market-data adapters, a paper execution environment, an automatic updater and signing are separate milestones. The current application already performs and persists actual continuous numerical work; deferred features are not represented as completed controls.
