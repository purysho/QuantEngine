# ASTRA HANDOFF — QuantEngine verification and completion

**Date:** 2026-10-12  
**Repository:** https://github.com/purysho/QuantEngine  
**Working PR:** https://github.com/purysho/QuantEngine/pull/2  
**Branch:** `fix/phase1-research-integrity`  
**Current status:** Extensive engineering changes committed; **not merged**, not fully externally validated. Check current HEAD and GitHub Actions rather than relying on timestamps or this snapshot.

## Mission

Act as a skeptical, independent senior quantitative-engineering reviewer. **Do not simply add features or declare the five phases complete.** Finish the verification and reliability work, fix legitimate defects, remove unnecessary complexity only after proving it is unused, and design/execute a genuinely unseen-data experiment where an external custodian controls the future observations. All source changes must be tested and logged stepwise.

The user has authorized thoroughly tested changes to `main`, but only merge after the full current-head CI and packaging gates pass and scientific limitations are explicitly documented. Do not claim that green CI establishes forecasting alpha.

## Read these in order

1. `docs/WORK_LOG.md` — prior commits, known failures, unresolved tasks, and chronological progress.
2. `docs/BLACKBOX_JUDGE.md` — experimental custody design and explicit trust limitations.
3. `docs/EQUATIONS_GRAPHS_UNSEEN_DATA.md` — implemented formulas, graph inventory, absent methods, and unseen-data criteria.
4. `docs/LIVE_DATA_FEEDS.md` — Coinbase/Kraken public feed setup and the pilot's limitations.
5. `docs/ARCHITECTURE.md`, `docs/VALIDATION.md`, `docs/RESEARCH_RELEASE_SPEC.md`, `README.md`, and the existing tests.
6. Inspect `.github/workflows/ci.yml` and `.github/workflows/release.yml`, then retrieve actual failed-job logs from GitHub Actions.

The wider `ASTRA_QUANTENGINE_AUDIT_BLACKBOX_PROTOCOL.md` was supplied in an earlier conversation. If that file is unavailable, **say so**; do not pretend to have read it. This handoff and the repository documentation describe the currently actionable tasks.

## Immediate order of work

### P0 — Verify the actual final HEAD

- Inspect the latest run of `fix/phase1-research-integrity`, including *all* OS checks, real-data experiments, security audit, packaged Windows self-test and mock live-pipeline test. Most recent observed run at handoff: https://github.com/purysho/QuantEngine/actions/runs/38255617177 (still in progress when last checked).
- Investigate any failing tests by reading logs. Correct production code or test fixtures **only with a justified hypothesis**. Keep statistical failures visible and do not relax thresholds to force green status.
- Run full tests locally if supported, including `npm ci`, `npm run typecheck`, `npm test`, `npm run test:quant`, `npm run build`, `node tests/live_pipeline_smoke.mjs`, and numerical/research acceptance checks.
- Verify that GitHub Actions SHA pins, npm audit, Python pip-audit, CycloneDX SBOM and versioned release protections work end to end. Do not run a production release purely to test tag publishing.

### P0 — Review the *actual* live causality boundary

Files:
- `experiments/collect_coinbase.mjs`
- `experiments/live_pilot.py`
- `experiments/prospective.py`
- `experiments/audit_live_pilot.py`
- `tests/mock_coinbase_ws.mjs`
- `tests/live_pipeline_smoke.mjs`
- `workers/quant_live_feed.py`

The current collector accepts a ticker, journals it, pipes to Python, and waits for a flushed ACK before accepting another ticker. Python writes a durable next-observation forecast, then settles it only against a tick received **after** the forecast was durably committed. Verify this happens in practice and cannot be fooled by queueing, process crashes, stale timestamps, buffer backpressure, reordering, premature child exit, duplicate source events, clock drift, dropped ACKs, path reuse or poisoned local files.

**Potential critical issue to inspect:** The collector can append a raw ticker **before** its Python processing/ACK. Any failure or reconnect leaves the journal and scored observations different. Design a proper durable journal with entry status and atomic recovery rules. Check that the last event's ACK is received before treating collector termination as success.

Use deterministic simulated transport-failure fixtures including missing ACKs, multiple rapid events, same/future timestamps, failure between forecast fsync and receipt fsync, failure between score and settlement fsync, duplicate files, and restart into an existing directory.

### P1 — Independent data and timestamps

- Validate a real read-only **live** connection to Coinbase and Kraken (separately) where geographic access and vendor terms permit. This has **not** been demonstrated.
- Validate vendor schemas and feed completeness. Coinbase ticker is batched, not the complete trade tape. Kraken ticker snapshots and quote updates are not identical to Coinbase trades.
- Review `experiments/reconcile_feeds.py`: use only quote observations **received before** the Coinbase receipt; quantify clock skew, missingness and stale references. Never call different last-trade/quote observations a tradable arbitrage signal.
- Provide reconnect and gap recovery or explicitly mark each affected interval ineligible. Add raw payload digests, receipt provenance, feed-health counters and clock-sync diagnostics.
- Implement a durable third-party timestamp/custody mechanism, with external evaluator credentials and sealed future labels. A local SHA-256 receipt is integrity evidence only, **not** independent timestamp or secrecy proof.
- Connect `workers/quant_point_in_time.py` to a real publication-vintage source where applicable; show that revised macro series cannot leak backwards into earlier forecasts.

### P1 — Meaningful statistical validation

- Retain zero-return and past-only mean baselines; a candidate must outperform them on **paired held-out observations**, not only in retrospective backtests.
- Inspect `workers/quant_model_selection.py` HAC, stationary bootstrap and White-style multiple-model reality check for null calibration, serial correlation, false discoveries, small-sample instability, block-length sensitivity and silent performance overclaims. Predeclare model set, bootstrap rules and horizon.
- Fix or explain the **Engle–Granger AIC false-rejection rate** discrepancy and **Avellaneda–Stoikov gamma=0.5** published-profit mismatch; never tune acceptance to a reference outcome.
- Alpha learner has previously underperformed its mean-forecast baseline. Preserve the negative finding. If a new learner is created, evaluate it on an independently reserved unseen period and retain the incumbent if evidence is weak.
- Perform chronological five-year windows where data permits, but label previously exposed history as **development** and not as an untouched final test. The final evaluation requires genuinely withheld future or independently sealed data.
- Include effect sizes, uncertainty, drawdowns, VaR/ES backtests, execution costs and model-specific applicability. Not every formula predicts returns.

### P2 — Lean desktop product and trustworthy release

- Audit runtime dependencies and unused code across `desktop/`, `app/`, `workers/`, `experiments/`, `packaging/` and tests. Remove only proven dead code; do not delete research evidence or legally required bundled licenses.
- Confirm graphs and numerical tables reflect actual source data and provenance; no baked-in historical success claims. Ensure imported or legacy absolute local filesystem paths cannot leak into exported reports.
- Ensure UI reports expose feed gaps, forecast latency, rejected/replayed ticks, unsettled commitments, confidence intervals and verified-versus-unverified source status. Investigate portability, persistence and readable exports.
- Signing and an independent custody system require owner-managed credentials or infrastructure. Clearly describe what cannot be implemented autonomously.

## Required engineering discipline

After every meaningful step, append to **`docs/WORK_LOG.md`**:
- exact files changed and commit SHA;
- issue/hypothesis and why the change addresses it;
- tests performed, CI run URL, actual pass/fail, and relevant outcome numbers;
- assumptions, remaining limitations, and next precise action.

Use small reversible commits, add tests before calling any fix complete, and inspect live CI output. Do not continuously push trivial log-only commits while a long CI run is in progress because branch concurrency cancels older runs. Prefer one log update per coherent testable batch.

Keep `main` stable; merge only once all applicable tests and safety gates are green, and the release/experiment documentation is honest about unverified predictive claims.

## Acceptance checklist

- [ ] Current-head Linux and Windows numerical/desktop tests green.
- [ ] Mock transport failure, disk/crash/restart and receipt-ordering tests green.
- [ ] Real-data historical acceptance honestly reports failures and successes.
- [ ] Windows packaged application self-test green.
- [ ] npm/Python security audits and generated SBOM pass and are accessible.
- [ ] Feed-health/incomplete data flags, causal matching and local reports independently tested.
- [ ] Real public live-data smoke independently observed, timestamped and documented.
- [ ] New unseen label custody prevents candidate code from reading future outcomes.
- [ ] Frozen candidate, baseline, horizon and test criteria verified before reveal.
- [ ] Measured prospective comparison reports misses and uncertainty with multiple-model correction.
- [ ] Desktop report/export is legible, accurate and free of private local path disclosures.
- [ ] Release strategy and owner-required code-signing needs documented.
- [ ] Full notes, failed experiments and residual research uncertainty in `docs/WORK_LOG.md`.

**Do not mark checked simply because code exists.** The project should emerge more *trustworthy*, not merely bigger.

## First Astra response requested

Start by checking the latest GitHub Actions result and the file contents. Report the **top three concrete defects/risks with tests to reproduce**, then begin fixing them on the existing branch, with stepwise repository logging. No need to ask the user to restate prior decisions.
