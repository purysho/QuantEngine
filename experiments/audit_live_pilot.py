"""Audit committed/settled live forecasts; never hide misses.

Reads only settlement evidence produced before analysis, refuses duplicate and
unmatched outcomes, and compares a fixed candidate to two past-only baselines.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from workers.quant_model_selection import paired_loss_comparison


def audit(root: str | Path, *, hac_lags: int = 0, min_settled: int = 3) -> dict:
    root = Path(root)
    forecasts = sorted(root.glob("*.forecast.json"))
    if not forecasts:
        raise ValueError("No prospective forecasts found.")
    losses: dict[str, list[float]] = {"candidate": [], "baseline_zero": [], "baseline_past_mean": []}
    missing = []
    indices = set()
    for forecast in forecasts:
        name = forecast.name.removesuffix(".forecast.json")
        if not name.isdigit() or int(name) in indices:
            raise ValueError("Duplicate/invalid forecast index.")
        indices.add(int(name))
        receipt = root / (name + ".receipt.json")
        settlement = root / (name + ".settled.json")
        if not receipt.exists():
            raise ValueError(f"Missing commitment receipt: {name}")
        from experiments.prospective import _read
        import hashlib
        digest = hashlib.sha256(forecast.read_bytes()).hexdigest()
        if _read(receipt).get("forecast_sha256") != digest:
            raise ValueError(f"Tampered forecast: {name}")
        if not settlement.exists():
            missing.append(name)
            continue
        result = _read(settlement)
        if result.get("forecast_sha256") != digest or result.get("index") != _read(forecast).get("index"):
            raise ValueError(f"Unmatched settlement: {name}")
        squared = result.get("squared_losses", {})
        for key in losses:
            value = squared.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid loss {name}/{key}")
            losses[key].append(value)
    expected_settlements = {p.name.replace(".forecast.json", ".settled.json") for p in forecasts}
    for orphan in root.glob("*.settled.json"):
        if orphan.name not in expected_settlements:
            raise ValueError(f"Orphan settlement without matching forecast: {orphan.name}")
    n = len(losses["candidate"])
    report = {
        "total_forecasts": len(forecasts), "settled": n,
        "unsettled": len(missing), "unsettled_ids": missing,
        "mean_squared_loss": {k: sum(v) / n if n else None for k, v in losses.items()},
        "confidence": "insufficient_data",
        "disclaimer": "Local-development evidence, not an independent live-market experiment.",
    }
    if n >= max(min_settled, 3):
        report["candidate_vs_zero"] = paired_loss_comparison(
            losses["candidate"], losses["baseline_zero"], lags=hac_lags)
        report["candidate_vs_past_mean"] = paired_loss_comparison(
            losses["candidate"], losses["baseline_past_mean"], lags=hac_lags)
        report["confidence"] = "nominal_HAC_only"
    if n >= 20:
        from workers.quant_model_selection import white_reality_check
        import numpy as np
        candidates = np.column_stack((losses["candidate"], losses["baseline_past_mean"]))
        report["global_model_search_diagnostic"] = white_reality_check(
            candidates, losses["baseline_zero"], expected_block=min(5, n),
            repetitions=500, seed=17)
        report["warning"] = "Repeatedly inspecting the same data invalidates nominal inference; do not treat this as fresh alpha proof."
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root")
    parser.add_argument("--hac-lags", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(audit(args.root, hac_lags=args.hac_lags), indent=2))


if __name__ == "__main__":
    main()
