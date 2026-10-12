"""Prospective precommit and settlement for a single newly arriving return.

Forecasts must be committed before outcomes exist. A separate evaluator account
must hold outcome files and independently timestamp the forecast commitment.
This module is a local integrity aid, not an external timestamp authority.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def prepare_forecast(*, dataset_sha256: str, index: int, model_commit: str,
                     candidate: float, historical_mean: float) -> dict:
    if not isinstance(dataset_sha256, str) or len(dataset_sha256) != 64:
        raise ValueError("Require dataset SHA-256.")
    try:
        int(dataset_sha256, 16)
    except ValueError as exc:
        raise ValueError("Invalid dataset SHA-256.") from exc
    if type(index) is not int or index < 0 or not model_commit:
        raise ValueError("Require nonnegative observation index and model commit.")
    if any(type(v) not in (float, int) or not math.isfinite(v)
           for v in (candidate, historical_mean)):
        raise ValueError("Forecasts must be finite numbers.")
    return {"dataset_sha256": dataset_sha256, "index": index, "model_commit": model_commit,
            "candidate": float(candidate), "baseline_zero": 0.0,
            "baseline_past_mean": float(historical_mean)}


def commit_forecast(envelope: dict, forecast_file, *, receipt_file):
    output = Path(forecast_file)
    receipt = Path(receipt_file)
    if output.exists() or receipt.exists():
        raise FileExistsError("Cannot overwrite committed forecasts or receipts.")
    raw = _canonical(envelope)
    # Exclusive creation prevents accidental replacement; external timestamps needed.
    with output.open("xb") as dest:
        dest.write(raw)
        dest.flush()
        os.fsync(dest.fileno())
    # Receipt time is recorded after the prediction bytes have been durably written.
    # This local clock is NOT an independent timestamp authority.
    receipt_content = _canonical({
        "forecast_sha256": hashlib.sha256(raw).hexdigest(),
        "local_receipt_issued_at": datetime.now(timezone.utc).isoformat(),
    })
    with receipt.open("xb") as dest:
        dest.write(receipt_content)
        dest.flush()
        os.fsync(dest.fileno())
    return _read(receipt)


def settle_forecast(forecast_file, receipt_file, *, outcome: float, settlement_file):
    if type(outcome) not in (float, int) or not math.isfinite(outcome):
        raise ValueError("Outcome must be finite numeric.")
    forecast = _read(forecast_file)
    raw = Path(forecast_file).read_bytes()
    receipt = _read(receipt_file)
    if receipt.get("forecast_sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("Forecast commitment does not match sealed receipt.")
    required = {"dataset_sha256", "index", "model_commit", "candidate", "baseline_zero", "baseline_past_mean"}
    if set(forecast) != required:
        raise ValueError("Forecast envelope has missing or unexpected fields.")
    for k in ("candidate", "baseline_zero", "baseline_past_mean"):
        if type(forecast[k]) not in (float, int) or not math.isfinite(forecast[k]):
            raise ValueError("Invalid forecast.")
    result = {"dataset_sha256": forecast["dataset_sha256"],
              "index": forecast["index"], "model_commit": forecast["model_commit"],
              "forecast_sha256": receipt["forecast_sha256"],
              "squared_losses": {k: (forecast[k] - outcome)**2
                                 for k in ("candidate", "baseline_zero", "baseline_past_mean")}}
    with Path(settlement_file).open("xb") as dest:
        dest.write(_canonical(result))
        dest.flush()
        os.fsync(dest.fileno())
    return result
