# Quant Engine

An independent local desktop application for continuous numerical research. It calculates covariance, constrained portfolios, Gaussian/block-bootstrap/Student-t risk with exact empirical tails, next-close costed momentum backtests, baselines, stress and parameter sensitivity, and prices options (Black–Scholes Greeks, CRR trees, Monte Carlo, implied volatility). Completed reports retain their source snapshots, seeds, parameters and software versions.

Python research modules, each with tests and a measured experiment in `experiments/results/`:

| Module | What it does |
| --- | --- |
| `quant_options` | BSM and Greeks, European/American CRR, antithetic Monte Carlo, implied volatility, SVI surface and static-arbitrage checks |
| `quant_validation` | Purged chronological ridge with information clocks; leaked features are rejected before scoring |
| `quant_pairs` | ADF / Engle–Granger with MacKinnon inference (matches statsmodels to 1e-13), Holm pair selection, costed next-close pairs backtest |
| `quant_lob` | Avellaneda–Stoikov market making with FIFO queue, partial fills, latency, fees and adverse selection |

See the [work log](docs/WORK_LOG.md) for what worked and what did not, and the [research index](docs/research/RESEARCH_INDEX.md) for how each curriculum topic maps to code.

For ordinary Windows use, extract the complete portable release and open `QuantEngine.exe`. The application contains its own Python/NumPy/SciPy runtime. Its default data folder is `D:\Quant-Engine`. The offline example is visibly synthetic; wide CSV imports and optional official ECB reference-rate snapshots supply real user-selected data.

For development:

```sh
npm ci
python3 -m pip install -r requirements.txt
npm run typecheck
npm test
npm run test:quant
npm run build
python3 experiments/options_reference.py   # likewise first_alpha, pairs_cointegration, market_making
npm start
```

Set `QUANT_PYTHON` to a development Python executable if needed. To assemble a Windows package, first run `python packaging/prepare_runtime.py`, then `npm run package:win`; see [the complete build recipe](packaging/BUILD_FROM_SOURCE.md). Authored desktop source is in `desktop/`, renderer source in `app/ui-source.js`, and the independent numerical engine in `workers/`. The build emits `dist/main.cjs`, `dist/preload.cjs` and `app/ui.js`.

One worker runs at a time, with at most two numerical threads. Pause terminates the owned worker and recovers unfinished history immediately. Closing the window keeps work in the tray; **Quit Quant Engine** drains accepted preferences and stops work. Login launch and automatic calculation resumption are separate opt-in preferences.

[User guide](docs/USER_GUIDE.md) · [Work log](docs/WORK_LOG.md) · [Research index](docs/research/RESEARCH_INDEX.md) · [Project brief](docs/PROJECT_BRIEF.md) · [Architecture](docs/ARCHITECTURE.md) · [Build milestones](docs/BUILD_PLAN.md) · [Evaluation](docs/EVALUATION.md) · [Discovery](docs/DISCOVERY.md)

The product label is provisional. First-party source licensing has not been assigned; third-party notices/licenses remain with their dependencies.
