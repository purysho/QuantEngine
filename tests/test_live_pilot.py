import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.live_pilot import LivePilot
from experiments.prospective import _read


class LivePilotTests(unittest.TestCase):
    def test_seals_before_next_tick_and_scores_only_future_receipt(self):
        now = dt.datetime.now(dt.timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            pilot = LivePilot(root, product="BTC-USD", model_commit="sealed-code-v1",
                              minimum_history=2)
            def tick(i, price, seconds):
                timestamp = (now + dt.timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")
                return {"source": "coinbase_exchange_ticker", "product_id": "BTC-USD",
                        "event_at": timestamp, "received_at": timestamp,
                        "sequence": i+100, "trade_id": i+100, "price": price,
                        "feed_is_complete": False}
            pilot.on_tick(tick(1, 100, -5))
            pilot.on_tick(tick(2, 101, -4))
            pilot.on_tick(tick(3, 102, -3))
            self.assertTrue((Path(root) / "0000000003.forecast.json").exists())
            self.assertFalse((Path(root) / "0000000003.settled.json").exists())
            result = pilot.on_tick(tick(4, 103, 3))
            self.assertEqual(result["settled"], 1)
            settled = _read(Path(root) / "0000000003.settled.json")
            self.assertIn("baseline_past_mean", settled["squared_losses"])
            with self.assertRaises(ValueError):
                pilot.on_tick(tick(4, 103, 3))

    def test_rejects_tick_that_was_received_before_commit(self):
        now = dt.datetime.now(dt.timezone.utc)
        with tempfile.TemporaryDirectory() as root:
            pilot = LivePilot(root, product="BTC-USD", model_commit="fixed", minimum_history=1)
            def tick(i):
                timestamp = (now + dt.timedelta(seconds=i - 10)).isoformat().replace("+00:00", "Z")
                return {"source": "coinbase_exchange_ticker", "product_id": "BTC-USD",
                        "event_at": timestamp, "received_at": timestamp,
                        "sequence": i+1, "trade_id": i+1, "price": float(100+i),
                        "feed_is_complete": False}
            pilot.on_tick(tick(0))
            pilot.on_tick(tick(1))
            with self.assertRaisesRegex(ValueError, "before forecast commitment"):
                pilot.on_tick(tick(2))


if __name__ == "__main__":
    unittest.main()
