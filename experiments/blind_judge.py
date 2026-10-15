"""Two-party BlackBox evaluation: commit predictions, then let a separate judge score them.

Never place secret outcomes in a model's workspace. This module cannot itself
create an OS sandbox or protect a secret stored under candidate credentials.
The judge must run independently after the candidate's code and predictions
are frozen and the commitment is time-stamped by the custodian.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

try:
    from .exposure_ledger import ExposureLedger
except ImportError:
    from exposure_ledger import ExposureLedger


def _read(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Envelope must be a JSON object.")
    return value


def _check_envelope(value, field):
    digest = value.get("dataset_sha256")
    start, end = value.get("start"), value.get("end")
    numbers = value.get(field)
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("Missing dataset SHA-256.")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("Invalid dataset SHA-256.") from exc
    if type(start) is not int or type(end) is not int or not 0 <= start < end:
        raise ValueError("Invalid half-open evaluation interval.")
    if not isinstance(numbers, list) or len(numbers) != end - start:
        raise ValueError(f"Expected exactly {end-start} {field}.")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in numbers):
        raise ValueError(f"Nonfinite, Boolean, or nonnumeric {field}.")
    return digest, start, end


def commit(forecast_file):
    raw = Path(forecast_file).read_bytes()
    value = json.loads(raw)
    digest, start, end = _check_envelope(value, "predictions")
    return {
        "forecast_sha256": hashlib.sha256(raw).hexdigest(),
        "dataset_sha256": digest,
        "start": start, "end": end,
        "count": len(value["predictions"]),
    }


def evaluate(forecast_file, commitment_file, sealed_outcomes_file, ledger_file):
    # The sealed outcomes file must only be accessible to the external judge.
    commitment = _read(commitment_file)
    current = commit(forecast_file)
    if commitment != current:
        raise ValueError("Forecasts or evaluation interval differ from sealed commitment.")
    secret = _read(sealed_outcomes_file)
    dataset_sha256, start, end = _check_envelope(secret, "outcomes")
    if (dataset_sha256, start, end) != (
            current["dataset_sha256"], current["start"], current["end"]):
        raise ValueError("Sealed label block does not match forecast commitment.")
    predictions = _read(forecast_file)["predictions"]
    outcomes = secret["outcomes"]
    errors = [float(p) - float(y) for p, y in zip(predictions, outcomes)]
    baseline_errors = [float(y) for y in outcomes]  # Predeclared zero-return forecast.
    n = len(errors)
    report = {
        "status": "judged_development_or_sealed_by_external_custodian",
        "dataset_sha256": dataset_sha256, "start": start, "end": end,
        "count": n, "forecast_sha256": current["forecast_sha256"],
        "mse": sum(e*e for e in errors)/n,
        "mae": sum(abs(e) for e in errors)/n,
        "zero_baseline_mse": sum(e*e for e in baseline_errors)/n,
        "zero_baseline_mae": sum(abs(e) for e in baseline_errors)/n,
    }
    report["skill_mse_vs_zero"] = 1 - report["mse"] / report["zero_baseline_mse"] if report["zero_baseline_mse"] > 0 else None
    ExposureLedger(ledger_file).reveal(
        dataset_sha256, start, end, prediction_sha256=current["forecast_sha256"]
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    commit_cmd = sub.add_parser("commit")
    commit_cmd.add_argument("forecast_file")
    commit_cmd.add_argument("commitment_file")
    judge_cmd = sub.add_parser("judge")
    judge_cmd.add_argument("forecast_file")
    judge_cmd.add_argument("commitment_file")
    judge_cmd.add_argument("sealed_outcomes_file")
    judge_cmd.add_argument("ledger_file")
    judge_cmd.add_argument("report_file")
    args = parser.parse_args()
    if args.action == "commit":
        Path(args.commitment_file).write_text(json.dumps(commit(args.forecast_file), indent=2) + "\n")
    else:
        result = evaluate(args.forecast_file, args.commitment_file,
                          args.sealed_outcomes_file, args.ledger_file)
        Path(args.report_file).write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
