# Quant Engine

An independent local desktop application for continuous numerical research. It calculates covariance, constrained portfolios, Gaussian and block-bootstrap risk, chronological costed momentum backtests, baselines, stress and parameter sensitivity. Actual completed reports retain their source snapshots, seeds, parameters and software versions.

For ordinary Windows use, extract the complete portable release and open `QuantEngine.exe`. The application contains its own Python/NumPy/SciPy runtime. Its default data folder is `D:\Quant-Engine`. The offline example is visibly synthetic; wide CSV imports and optional official ECB reference-rate snapshots supply real user-selected data.

For development:

```sh
npm ci
python3 -m pip install -r requirements.txt
npm run typecheck
npm test
npm run test:quant
npm run build
npm start
```

Set `QUANT_PYTHON` to a development Python executable if needed. To assemble a Windows package, first run `python packaging/prepare_runtime.py`, then `npm run package:win`; see [the complete build recipe](packaging/BUILD_FROM_SOURCE.md). Authored desktop source is in `desktop/`, renderer source in `app/ui-source.js`, and the independent numerical engine in `workers/`. The build emits `dist/main.cjs`, `dist/preload.cjs` and `app/ui.js`.

One worker runs at a time, with at most two numerical threads. Pause terminates the owned worker and recovers unfinished history immediately. Closing the window keeps work in the tray; **Quit Quant Engine** drains accepted preferences and stops work. Login launch and automatic calculation resumption are separate opt-in preferences.

[User guide](docs/USER_GUIDE.md) · [Project brief](docs/PROJECT_BRIEF.md) · [Architecture](docs/ARCHITECTURE.md) · [Build milestones](docs/BUILD_PLAN.md) · [Evaluation](docs/EVALUATION.md) · [Discovery](docs/DISCOVERY.md)

The product label is provisional. First-party source licensing has not been assigned; third-party notices/licenses remain with their dependencies.
