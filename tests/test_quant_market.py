import datetime as dt
import math
import tempfile
import unittest
from pathlib import Path

from workers import quant_options as qo
from workers import quant_store as qs


def chain(spot=100.0, rate=0.04, as_of=dt.date(2026, 10, 18)):
    points = []
    for days in (14, 30, 60, 120, 250):
        T, expiry = days / 365, (as_of + dt.timedelta(days=days)).isoformat()
        for strike in [70 + 2.5 * i for i in range(25)]:
            k = math.log(strike / (spot * math.exp(rate * T)))
            iv = 0.22 - 0.15 * k + 0.4 * k * k
            kind = "put" if strike < spot else "call"
            price = qo.black_scholes(spot, strike, T, rate, iv, 0, kind)["price"]
            points.append({"strike": strike, "expiry": expiry, "type": kind, "bid": price * .98, "ask": price * 1.02, "iv": iv})
    return {"symbol": "TEST", "spot": spot, "asOf": "2026-10-18T15:00:00Z", "points": points}


class MarketSurfaceTests(unittest.TestCase):
    def test_recovers_the_smile_used_to_price_the_chain(self):
        out = qo.market_surface(chain(), .04, as_of="2026-10-18")
        self.assertEqual(out["symbol"], "TEST")
        self.assertGreaterEqual(len(out["expiries"]), 4)
        self.assertTrue(out["arbitrage_free"])
        self.assertLess(out["alpaca_iv_median_abs_difference"], 1e-6)
        for T, row in zip(out["expiries"], out["implied_volatility"]):
            for k, iv in zip(out["log_moneyness"], row):
                self.assertAlmostEqual(iv, .22 - .15 * k + .4 * k * k, delta=2e-3)

    def test_grid_stays_inside_quoted_strikes(self):
        out = qo.market_surface(chain(), .04, as_of="2026-10-18")
        for T in out["expiries"]:
            ks = [p["log_moneyness"] for p in out["points"] if p["expiry"] == T]
            self.assertGreaterEqual(out["log_moneyness"][0], min(ks) - 1e-12)
            self.assertLessEqual(out["log_moneyness"][-1], max(ks) + 1e-12)

    def test_illiquid_or_in_the_money_quotes_are_skipped(self):
        data = chain()
        for p in data["points"]:
            p["bid"] = 0.0  # No two-sided market anywhere.
        with self.assertRaisesRegex(ValueError, "Not enough liquid"):
            qo.market_surface(data, .04, as_of="2026-10-18")


class IngestTests(unittest.TestCase):
    def test_ingest_accepts_only_staged_files_and_market_ids(self):
        with tempfile.TemporaryDirectory() as root:
            store = qs.Store(root)
            try:
                rows = "date,SPY,QQQ\n" + "".join(f"2026-0{1 + i // 28}-{1 + i % 28:02d},{500 + i},{400 + i}\n" for i in range(60))
                staged = Path(root) / "sources" / "staged-1.csv"
                staged.write_text(rows)
                dataset = store.ingest(str(staged), "alpaca-spy-qqq", "SPY, QQQ", {"source": "alpaca", "symbols": ["SPY", "QQQ"], "years": 5})
                self.assertEqual(dataset["kind"], "alpaca")
                self.assertTrue(dataset["metadata"]["refreshable"])
                self.assertFalse(staged.exists())
                outside = Path(root) / "elsewhere.csv"
                outside.write_text(rows)
                with self.assertRaisesRegex(ValueError, "staged"):
                    store.ingest(str(outside), "alpaca-x", "x", {})
                staged.write_text(rows)
                with self.assertRaisesRegex(ValueError, "identifier"):
                    store.ingest(str(staged), "sample", "x", {})
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
