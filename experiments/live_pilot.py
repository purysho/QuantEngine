"""Live next-ticker-return pilot. Research only, never a complete trade tape.

A long-running Python process reads ticker observations from standard input,
commits the next-return forecast before the next tick, and settles on a later
receipt. Every forecast has a disk receipt. No trade instructions exist.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path

from experiments.prospective import prepare_forecast, commit_forecast, settle_forecast

def _time(text: str) -> dt.datetime:
    if not isinstance(text, str) or not text.endswith("Z"):
        raise ValueError("UTC receipt time required.")
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))

class LivePilot:
    def __init__(self, root: str | Path, *, product: str, model_commit: str, minimum_history: int = 3):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if type(minimum_history) is not int or minimum_history < 1:
            raise ValueError("minimum_history must be positive.")
        if any(self.root.iterdir()):
            raise ValueError("Existing pilot run detected; restart must use a new directory.")
        self.product = product
        self.model_commit = model_commit
        self.minimum_history = minimum_history
        self.dataset = hashlib.sha256(("coinbase_exchange_ticker:" + product).encode()).hexdigest()
        self.last = None
        self.returns: list[float] = []
        self.pending = None
        self.count = 0

    def _files(self, index):
        name = f"{index:010d}"
        return tuple(self.root / (name + suffix) for suffix in
                     (".forecast.json", ".receipt.json", ".settled.json"))

    def on_tick(self, tick: dict) -> dict:
        from workers.quant_live_feed import check_next
        if tick.get("source") != "coinbase_exchange_ticker" or tick.get("product_id") != self.product:
            raise ValueError("Unexpected feed source/product.")
        if tick.get("feed_is_complete") is not False:
            raise ValueError("Feed completeness must not be overstated.")
        price = tick.get("price")
        if type(price) not in (int, float) or not math.isfinite(price) or price <= 0:
            raise ValueError("Invalid price.")
        received = _time(tick.get("received_at"))
        _time(tick.get("event_at"))
        if self.last is not None:
            check_next(self.last, tick)
            previous_receipt = _time(self.last["received_at"])
            if received <= previous_receipt:
                raise ValueError("Non-increasing receipt clock; observation ineligible.")
            actual_return = price / self.last["price"] - 1
            if not math.isfinite(actual_return):
                raise ValueError("Nonfinite return.")
            if self.pending is not None:
                idx, opened_at = self.pending
                # Tick receipt must strictly follow the actual forecast commitment.
                if received <= opened_at:
                    raise ValueError("Tick received before forecast commitment: cannot claim prospective settlement.")
                p, receipt, settlement = self._files(idx)
                settle_forecast(p, receipt, outcome=actual_return, settlement_file=settlement)
                self.pending = None
            self.returns.append(actual_return)
        self.last = dict(tick)
        self.count += 1
        if len(self.returns) >= self.minimum_history:
            next_index = self.count
            # Frozen reference algorithm: momentum = latest observed tick return.
            candidate = self.returns[-1]
            baseline_mean = sum(self.returns) / len(self.returns)
            p, receipt, _ = self._files(next_index)
            envelope = prepare_forecast(dataset_sha256=self.dataset, index=next_index,
                                        model_commit=self.model_commit,
                                        candidate=candidate, historical_mean=baseline_mean)
            commit_forecast(envelope, p, receipt_file=receipt)
            # Capture local time AFTER durable write (conservative).
            committed_at = dt.datetime.now(dt.timezone.utc)
            self.pending = (next_index, committed_at)
        return {"ticks": self.count, "settled": max(0, self.count - self.minimum_history - 1),
                "pending": self.pending is not None}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--product", default="BTC-USD")
    parser.add_argument("--model-commit", required=True)
    parser.add_argument("--minimum-history", type=int, default=3)
    args = parser.parse_args()
    pilot = LivePilot(args.root, product=args.product, model_commit=args.model_commit,
                      minimum_history=args.minimum_history)
    for line in sys.stdin:
        if line.strip():
            state = pilot.on_tick(json.loads(line))
            print(json.dumps({"ack": state["ticks"], "pending": state["pending"]}), flush=True)
    print(json.dumps({"ticks": pilot.count, "pending_forecast": pilot.pending is not None,
                      "notice": "Unsettled forecasts remain unscored; no retrospective backfill."}))

if __name__ == "__main__":
    main()
