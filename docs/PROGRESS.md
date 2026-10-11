# QuantEngine progress

## 2026-10-11 — source restoration and GitHub handoff

- Restored the previously delivered 0.1.0 source archive; verified its SHA-256 (`56438ea2e47694010bfcb50ab41af223f19e6d0fc42b9560453ab2001d2b2a24`) and archive integrity.
- Connected the independent project to https://github.com/purysho/QuantEngine. The repository initially contained only its newly created README.
- Re-ran the restored numerical baseline: **18/18 Python tests passed** on Python 3.12.14 / NumPy 2.3.5 / SciPy 1.17.0.
- Re-ran the desktop baseline: **12/12 TypeScript tests passed**, type checking passed and the production source build completed.
- Reviewed all supplied repository leads through the GitHub connector, including source, actual licences, manifests and relevant tests at pinned commits. Detailed audits are in `docs/research/`.
- The three book titles were identified using publishers. Their full texts were not present in the available attachments; publisher descriptions, contents and accessible samples must not be represented as full-book reading.

## Current build

Version 0.2 will retain the bounded offline numerical worker and add options research, a controlled chronological alpha experiment, and explicit next-close execution. Follow-on pairs trading and market-making work remains in the build plan until its statistical and accounting acceptance tests pass.

## Evidence boundaries

Host tests run on Linux; the target is the user's Windows 11 laptop with 16 GB RAM and integrated graphics. Historical 0.1 experiment files are retained with their original provenance. They do not establish that a later build ran on the target device. New Windows checks will be recorded separately.

## 2026-10-11 — 0.2 research release built

Implemented and pushed: exact empirical tails and next-close execution, Student-t/Hill risk, options engine and desktop page, purged chronological ridge, Engle–Granger pairs, and the Avellaneda–Stoikov market-making simulator, plus Linux/Windows CI. Per-task detail, including failures, is in `WORK_LOG.md`.
