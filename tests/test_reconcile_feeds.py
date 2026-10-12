import unittest
from experiments.reconcile_feeds import reconcile


class ReconciliationTests(unittest.TestCase):
    @staticmethod
    def cb(time, price=100.0):
        return {"source": "coinbase_exchange_ticker", "product_id": "BTC-USD",
                "received_at": time, "price": price}

    @staticmethod
    def kr(time, bid=99.9, ask=100.1):
        return {"source": "kraken_spot_ticker_v2", "product_id": "BTC/USD",
                "received_at": time, "bid": bid, "ask": ask, "price": 100}

    def test_never_uses_reference_received_after_coinbase_trade(self):
        c = [self.cb("2026-10-12T01:00:02Z"), self.cb("2026-10-12T01:00:04Z"),
             self.cb("2026-10-12T01:00:16Z")]
        k = [self.kr("2026-10-12T01:00:03Z"), self.kr("2026-10-12T01:00:15Z")]
        result = reconcile(c, k, max_age_seconds=5)
        self.assertEqual(result["reconciled"], 1)
        self.assertEqual(result["missing_or_stale_reference"], 2)
        self.assertEqual(result["comparisons"][0]["reference_received_at"], "2026-10-12T01:00:03Z")

    def test_reports_price_disagreement(self):
        result = reconcile([self.cb("2026-10-12T01:00:04Z", 110)],
                           [self.kr("2026-10-12T01:00:03Z")], tolerance_bps=20)
        self.assertEqual(result["disagreements"], 1)

    def test_rejects_crossed_quotes(self):
        with self.assertRaisesRegex(ValueError, "Crossed"):
            reconcile([self.cb("2026-10-12T01:00:04Z")],
                      [self.kr("2026-10-12T01:00:03Z", bid=105, ask=100)])


if __name__ == "__main__":
    unittest.main()
