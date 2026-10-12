# BlackBox Judge: custody and operation (prototype)

This is a two-party *commit-before-reveal* protocol for single-step return
predictions. It does not make a Python process a security sandbox. The owner
of secret outcomes and the researcher MUST use isolated machines, OS accounts
or a managed sandbox preventing the candidate from reading hidden labels,
cached backtests, judge code/data, networking, system dates identifying the
period, and future observations.

## Before research begins

1. The external evaluator privately builds a continuous history in chronological
   blocks, including unpublished synthetic streams and truly unrevealed real
   intervals. Do not use committed `experiments/results/*.json` as secret
   holdout: they are already development evidence.
2. Create an opaque dataset id using SHA-256 of the evaluator's canonical
   source bytes, not an asset name or human-readable market interval.
3. Freeze the candidate's source commit and environment/dependency hashes.
4. Candidate receives only past observations and the length of the **next**
   anonymous block. A separate simulator must emit observations one-by-one,
   committing a prediction before revealing each next observation. This file
   grader does NOT enforce online sequential prediction on its own.
5. Candidate produces `forecasts.json`, for example:

```json
{"dataset_sha256":"<64 lowercase hex characters>", "start":0, "end":3,
 "predictions":[0.001,-0.002,0.000]}
```

6. Still **without** the hidden labels, the researcher runs:

```bash
python -m experiments.blind_judge commit forecasts.json commitment.json
sha256sum commitment.json
```

The independent evaluator receives the source commit, candidate prediction
file, commitment file and an externally time-stamped digest **before** scoring.
Self-published hashes are NOT enough if the researcher controls both records.

## Scoring, by independent evaluator only

The evaluator's secret file contains exactly the matching anonymous interval:

```json
{"dataset_sha256":"<same dataset SHA-256>", "start":0, "end":3,
 "outcomes":[0.002,0.001,-0.001]}
```

With the candidate no longer permitted to change forecasts or see the labels:

```bash
python -m experiments.blind_judge judge forecasts.json commitment.json \
  secret_outcomes.json exposures.jsonl report.json
```

The report includes MSE, MAE, zero-prediction baseline and relative MSE skill.
Labels are not written into the report. `exposures.jsonl` prohibits repeated or
overlapping label reveals for a dataset. A failed forecast cannot be rerun
on the same labels and counted as a fresh blind test; it becomes development
evidence and needs a new locked holdout.

## Interpret and iterate

After each 5-year block, archive candidate commit, commitment digest, versions,
the block's metrics, calibration and miss classifications. Distinguish
deterministic implementation bugs, unexpected regimes, random variability,
statistical selection, and true causal leakage. Before modifying the model,
write a falsifiable fix hypothesis and design synthetic unit tests that do
not expose the next holdout. Prefer retaining the incumbent if improvement
does not survive a separately reserved adoption sample. Only evaluate the
next *unseen* chronological interval after a model change.

## Limitations — do not claim otherwise

- This implementation does **not** generate secret markets or stream past-only
  observations to an untrusted candidate, and it does not prevent reading
  judge-private files when executed under the same filesystem credentials.
- SHA-256 is an integrity commitment, **not** proof of timestamp or independence.
- The exposure ledger is a local append-only file, not tamperproof against its owner.
- The score is a point-return metric, not VaR/ES coverage, alpha after fees,
  causal identification or economic profit. Add specialized blind tests for those.
- Do not label already published 1928–2026 CRSP and FRED reruns as fresh holdout.

See `ASTRA_QUANTENGINE_AUDIT_BLACKBOX_PROTOCOL.md` outside this branch for
the broader statistical and adversarial evaluation checklist.

## Cross-platform disclosure serialization

`ExposureLedger.reveal` now uses an exclusive sidecar `<ledger>.lock` on both Windows and POSIX, enclosing overlap checking and fsynced append. Competing reveals fail closed. A process crash leaves the lock as evidence; the custodian must inspect ledger completeness before manually removing it. The control is single-filesystem local mutual exclusion, not a tamperproof or network-distributed ledger. Six concurrent subprocesses are regression-tested to produce at most one successful reveal of the same block.
