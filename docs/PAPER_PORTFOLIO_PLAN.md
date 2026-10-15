# Capital-aware Paper Portfolio Implementation Plan

> For agentic workers: use superpowers:executing-plans task-by-task. User explicitly requested planning followed by building in this session; implementation proceeds inline without another approval pause.

Goal: durable nine-book paper comparison and desktop dashboard, with executable capital constraints.
Architecture: Python SQLite ledger/simulator, existing serial worker and Electron IPC, existing renderer. No new dependencies or services.
Spec: `docs/PAPER_PORTFOLIO_SPEC.md`.

Global constraints: same three capital scales and fixed strategies; no broker connection; no retrospective success as forward alpha; preserve failures; no independent-custody claim; no fabricated feed or constituent data.
Review focus: stale/future timestamps; crash between fill and commit; tiny-account fee affordability; large-account quoted capacity; renderer injection and worker shutdown. Each has a test below.

## Task1 — Atomic ledger and executable books
Files: workers/quant_paper.py; tests/test_paper.py.
Interfaces: PaperLedger(root).create(mode,source,assumptions), ingest(id,quote), control(id,halted), summary(id=None), export(id).
- [x] Write failing tests for no same-event fill, scale-specific fills/cash, min-order rounding, partial fills, dividends/splits, gap/restart/tamper/clock rejection.
- [x] Implement frozen source/config, SQLite immediate transaction and event hash chain, decimal fills and fixed strategy commitments.
- [x] Run `python -m unittest tests.test_paper`; all tests pass; quantities/cash reconcile.
- [x] Review limitations and commit coherent implementation.

## Task2 — Worker/desktop integration
Files: workers/quant_worker.py; desktop/engine.ts; desktop/main.ts; desktop/preload.ts; tests/test_quant_worker.py; tests/desktop.test.ts.
Interfaces: worker paper commands with operation/create/ingest/control/summary/export; engine.paperCommand(values) -> paper summary, snapshot.paper.
- [x] Test worker persisted paper roundtrip and invalid payload, engine busy/pause/shutdown ownership.
- [x] Add bounded IPC actions, native quote-file import and native JSON export; use shared worker slot and owned shutdown promise.
- [x] Run numerical/desktop tests and typecheck/build.

## Task3 — Dashboard and reproducible acceptance
Files: app/index.html; app/ui-source.js; app/style.css; tests/renderer.test.ts; experiments/paper_acceptance.py; docs/WORK_LOG.md; README.md; CI evidence step.
- [x] Add renderer test for paper state, mode warning, safely escaped source and scale table.
- [x] Add campaign controls, quote import, pause/resume, order/fill/equity display and export. No fake live counter.
- [x] Run deterministic synthetic stream through all scales; archive actual outcomes, config/source hashes and operational limits.
- [x] Run complete applicable checks, native self-test and visual QA. Record milestones and publish coherent branch batch; fresh current-head CI required before merge.

## Subsequent project — Information hypothesis
After foundation works, obtain/audit permitted historical membership plus price/corporate-action data; predeclare one relative-strength candidate and independently reserve labels. Missing data is a gate, not a reason to invent a successful stock-selection backtest. This first build does not complete that research or certify live-money readiness.

Execution note: implementation/testing steps completed in this session. External feed/custody/capacity and constituent research are explicitly unfulfilled prerequisites; current-head CI remains a post-publication gate.
