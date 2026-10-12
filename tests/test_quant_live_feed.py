import unittest

from workers.quant_live_feed import parse_ticker, check_next


class PublicFeedTests(unittest.TestCase):
    def ticker(self, **overrides):
        return {"type": "ticker", "sequence": 100, "product_id": "BTC-USD",
                "price": "100.5", "time": "2026-10-12T10:01:00.123Z",
                "trade_id": 20, **overrides}

    def test_public_ticker_tracks_exchange_and_receive_clocks(self):
        sample = parse_ticker(self.ticker(), product="BTC-USD",
                              received_at="2026-10-12T10:01:01.000Z")
        self.assertEqual(sample["price"], 100.5)
        self.assertFalse(sample["feed_is_complete"])
        self.assertNotEqual(sample["event_at"], sample["received_at"])
        self.assertIsNone(parse_ticker({"type": "heartbeat"}, product="BTC-USD",
                                        received_at="2026-10-12T10:01:01Z"))

    def test_replay_and_unexpected_asset_rejected(self):
        a = parse_ticker(self.ticker(), product="BTC-USD",
                         received_at="2026-10-12T10:01:01Z")
        with self.assertRaises(ValueError):
            check_next(a, a)
        with self.assertRaises(ValueError):
            parse_ticker(self.ticker(product_id="ETH-USD"), product="BTC-USD",
                         received_at="2026-10-12T10:01:01Z")

    def test_nonfinite_stale_clock_and_negative_prices_fail_closed(self):
        for invalid in ("nan", "-5", "inf", "0"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_ticker(self.ticker(price=invalid), product="BTC-USD",
                             received_at="2026-10-12T10:01:01Z")
        with self.assertRaises(ValueError):
            parse_ticker(self.ticker(), product="BTC-USD",
                         received_at="2026-10-12T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
