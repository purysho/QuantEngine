"""Cross-source market quality checks using *receipt-time* causality.

Coinbase last-trade samples and Kraken best bid/ask snapshots are NOT synchronized,
equivalent tradable instruments. This flags disagreement, not an arbitrage signal.
"""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path


def _receipt(row):
    if not isinstance(row, dict):
        raise ValueError("Market record must be an object.")
    raw = row.get("received_at")
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise ValueError("UTC receipt timestamp required.")
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid market receipt time.") from exc


def load_jsonl(path: str | Path, *, source: str) -> list[dict]:
    values = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("source") != source:
                raise ValueError(f"{path}:{number}: unexpected source")
            if type(row.get("price")) not in (float, int) or not math.isfinite(row["price"]) or row["price"] <= 0:
                raise ValueError("Invalid cross-venue price.")
            if values and _receipt(row) <= _receipt(values[-1]):
                raise ValueError("Receipt clock is not strictly increasing.")
            values.append(row)
    return values


def reconcile(coinbase: list[dict], kraken: list[dict], *, max_age_seconds: float = 5.0,
              tolerance_bps: float = 50.0) -> dict:
    if not math.isfinite(max_age_seconds) or max_age_seconds <= 0 or not math.isfinite(tolerance_bps) or tolerance_bps < 0:
        raise ValueError("Invalid reconciliation parameters.")
    for row in coinbase:
        if row.get("source") != "coinbase_exchange_ticker" or row.get("product_id") != "BTC-USD":
            raise ValueError("Only BTC-USD Coinbase is supported.")
    for row in kraken:
        if row.get("source") != "kraken_spot_ticker_v2" or row.get("product_id") != "BTC/USD":
            raise ValueError("Only BTC/USD Kraken is supported.")
        for key in ("bid", "ask"):
            if type(row.get(key)) not in (float, int) or not math.isfinite(row[key]) or row[key] <= 0:
                raise ValueError("Invalid Kraken quote.")
        if row["bid"] > row["ask"]:
            raise ValueError("Crossed Kraken book.")
    samples = []
    lagged = 0
    j = 0
    last = None
    for row in coinbase:
        at = _receipt(row)
        while j < len(kraken) and _receipt(kraken[j]) <= at:
            last = kraken[j]
            j += 1
        if last is None or (at-_receipt(last)).total_seconds() > max_age_seconds:
            lagged += 1
            continue
        mid = (last["bid"] + last["ask"])/2
        bps = 10000*(row["price"]/mid - 1)
        samples.append({"received_at": row["received_at"],
                        "reference_received_at": last["received_at"],
                        "relative_difference_bps": bps,
                        "within_tolerance": abs(bps) <= tolerance_bps})
    return {"coinbase_observations": len(coinbase),
            "reconciled": len(samples), "missing_or_stale_reference": lagged,
            "disagreements": sum(not sample["within_tolerance"] for sample in samples),
            "comparisons": samples,
            "warning": "Not arbitrage or tradable bid/ask evidence; independent feeds have different latency and execution."}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("coinbase_jsonl")
    parser.add_argument("kraken_jsonl")
    parser.add_argument("--max-age-seconds", type=float, default=5.0)
    parser.add_argument("--tolerance-bps", type=float, default=50.0)
    args = parser.parse_args()
    a = load_jsonl(args.coinbase_jsonl, source="coinbase_exchange_ticker")
    b = load_jsonl(args.kraken_jsonl, source="kraken_spot_ticker_v2")
    print(json.dumps(reconcile(a,b,max_age_seconds=args.max_age_seconds,
                               tolerance_bps=args.tolerance_bps),indent=2))


if __name__ == "__main__":
    main()
