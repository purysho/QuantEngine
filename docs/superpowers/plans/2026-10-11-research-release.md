# QuantEngine Research Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push a reproducible, independently branded local quant workbench with verified options mathematics and a causal first alpha experiment.

**Architecture:** Keep the Electron sandbox and serialized Python transport. Numerical modules return JSON-compatible dictionaries; separate experiments import the same modules. The options calculator shares worker ownership but does not replace completed portfolio reports.

**Tech Stack:** Electron 44.7.0, TypeScript, authored JavaScript/CSS, NumPy 2.3.5, SciPy 1.17.0; embedded Windows Python 3.13.16.

**Spec:** `docs/RESEARCH_RELEASE_SPEC.md`.

## Global Constraints

- One worker at a time, two BLAS threads normally and one in low CPU mode; pause cancels active work.
- No hosted inference, broker, paid API, model download or new numerical runtime dependency.
- Keep NumPy 2.3.5 and SciPy 1.17.0; the bundled Windows runtime remains Python 3.13.16.
- Version 0.1 reports remain readable. New reports use schema version 2 and engine version 0.2.0.

## Review Focus

- Tied tails and fractional empirical probability mass.
- Signals from completed closes cannot fill at the same close.
- Expired or deterministic option contracts; nonfinite/extreme inputs and impossible implied volatility.
- Overlapping labels and unavailable features; model selection must finish before holdout.
- Options work during continuous scheduling, cancellation and native Quit; older stored reports.

### Task 1: Causal timing and tail accounting

**Files:** Modify `workers/quant_core.py`; extend `tests/test_quant_core.py`.

**Interfaces:** Add `empirical_tail(samples, tail_probability=.05) -> dict` containing `var`, `expected_shortfall`, `tail_probability` and `quantile_method`. Keep existing risk report keys. `walk_forward` additionally records signal, execution and return price indices; `analyse` aligns curve dates with the delayed start.

- [ ] Write toy-path tests for next-close timing, fractional-tail ES `7`, invalid probabilities and future perturbation.
- [ ] Run `python3 -m unittest tests.test_quant_core`; expect new tests to fail before the change.
- [ ] Implement lower empirical inverse-CDF VaR and exact probability-mass ES; lag signals one close before execution.
- [ ] Run the numerical suite; expect all tests to pass and existing schema-1 loading to remain valid.
- [ ] Commit the timing/tail change.

### Task 2: Options mathematics

**Files:** Create `workers/quant_options.py`, `tests/test_quant_options.py`, `experiments/options_reference.py`.

**Interfaces:** `black_scholes(spot, strike, time, rate, volatility, dividend=0, kind='call') -> dict`; `crr_price(..., steps=500, american=False) -> float`; `monte_carlo_price(..., paths=50000, seed=17) -> dict`; `implied_volatility(price, spot, strike, time, rate, dividend=0, kind='call') -> float`; `options_report(parameters: dict) -> dict`. Use relative or script-compatible imports as needed; the worker passes the validated parameters unchanged.

- [ ] Add reference-price, parity, Greeks, deterministic/expiry, CRR and quote-bound tests.
- [ ] Execute only `test_quant_options.py`; expect missing implementation failure.
- [ ] Implement prices, explicit Greek units, risk-neutral iid terminal sampling and bounded inversion with SciPy.
- [ ] Execute the module tests; expect all pass.
- [ ] Run `experiments/options_reference.py` and save measured reference/convergence evidence, then commit.

### Task 3: Chronological alpha experiment

**Files:** Create `workers/quant_validation.py`, `tests/test_quant_validation.py`, `experiments/first_alpha.py`.

**Interfaces:** `chronological_ridge(features, targets, *, feature_available, label_end, initial_train=120, test_size=40, final_holdout=80, alphas=(.1,1.,10.)) -> dict`. Rows use integer observation clocks; feature availability is a vector with one time per row. Predictions and fit metadata identify evaluation row indices. Model selection uses only pre-evaluation blocks and completed labels. `experiments/first_alpha.py` emits a JSON artifact using bounded deterministic synthetic arrays.

- [ ] Add rejection tests for future feature clocks, incomplete labels, invalid arrays, future perturbation and train-only scaling, plus a known linear relationship.
- [ ] Run `test_quant_validation.py`; expect missing implementation failure.
- [ ] Implement chronological inner splits, ridge scaling/fitting, a frozen final holdout model and all-candidate ledger. Record cash/zero and training-mean forecast errors.
- [ ] Run tests, then the null/signal/leak experiment; save actual results with data hash, versions, seeds and duration.
- [ ] Commit the module and experiment.

### Task 4: Desktop integration and delivery

**Files:** Modify worker, engine, preload/main, renderer/HTML/CSS, portable test scripts, `package.json`, docs and notices; create `.github/workflows/ci.yml`.

**Interfaces:** A single `options` worker command consumes an options parameter object and returns the report without creating a portfolio history entry. `engine.calculateOptions(parameters)` uses existing operation ownership and emits busy state. Renderer obtains it only through `window.quant.calculateOptions`.

- [ ] Add transport/engine tests proving options work cannot overlap a portfolio run and interrupted options work releases ownership; test actual worker calculations.
- [ ] Run the targeted tests and observe failure before implementing.
- [ ] Add an Options navigation page with bounded numeric inputs, price/Greek/error results and sampling assumptions.
- [ ] Make test Python selection respect `QUANT_PYTHON`, otherwise `python` on Windows and `python3` elsewhere.
- [ ] Configure Linux/Windows numerical + desktop CI and a Windows embedded-runtime/native self-test artifact job.
- [ ] Run typecheck, full tests, build, the native host self-test and experiments. Record actual results and outstanding laptop checks.
- [ ] Consolidate all supplied resource coverage, the next pairs/LOB experiment gates and an honest differentiation statement in the research index and updated build plan.
- [ ] Review the final diff, commit, push without force, and verify the remote commit and observed CI outcome.
