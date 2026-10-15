"""Past-only sequential evaluation for never-before-seen observations.

Use *only* with externally supplied data that was not used for candidate
training, tuning or development. This evaluates prequential forecasts but does
not sandbox arbitrary malicious Python code.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path

from experiments.exposure_ledger import ExposureLedger, AlreadyExposedError


def evaluate_stream(observations, predictor, *, dataset_sha256: str, ledger_path,
                    start: int = 0, minimum_history: int = 1):
    """Call predictor with *only* observed prefix (tuple) before revealing each next value.

    Store predictions only after a successful full pass. Never train or tune
    predictor on outcomes from the same sealed interval and call it fresh again.
    """
    values = tuple(float(x) for x in observations)
    if not values or not all(math.isfinite(v) for v in values):
        raise ValueError("Require finite nonempty observations.")
    if not isinstance(minimum_history, int) or not 1 <= minimum_history < len(values):
        raise ValueError("Invalid minimum_history.")
    digest = str(dataset_sha256)
    if len(digest) != 64:
        raise ValueError("Expected dataset SHA-256.")
    ledger = ExposureLedger(ledger_path)
    block_start, end = start + minimum_history, start + len(values)
    if ledger.exposed(digest, block_start, end):
        raise AlreadyExposedError("Already viewed this evaluation block.")
    predictions = []
    for offset in range(minimum_history, len(values)):
        history = tuple(values[:offset])
        prediction = predictor(history)
        if type(prediction) not in (int, float) or not math.isfinite(prediction):
            raise ValueError("Predictor returned invalid next-step forecast.")
        predictions.append(float(prediction))
    outcomes = values[minimum_history:]
    report = {
        "dataset_sha256": digest, "start": block_start, "end": end,
        "n": len(outcomes),
        "mse": sum((a-b)**2 for a,b in zip(predictions,outcomes))/len(outcomes),
        "mae": sum(abs(a-b) for a,b in zip(predictions,outcomes))/len(outcomes),
        "baseline_zero_mse": sum(y*y for y in outcomes)/len(outcomes),
        "disclosure_status": "development_unless_externally_sealed",
    }
    commitment = hashlib.sha256(json.dumps(predictions, separators=(",", ":")).encode()).hexdigest()
    ledger.reveal(digest, block_start, end, prediction_sha256=commitment)
    report["predictions_sha256"] = commitment
    return report
