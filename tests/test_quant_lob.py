import math
import unittest

from workers import quant_lob as lob


class MarketMakingTests(unittest.TestCase):
    def test_closed_form_quotes(self):
        bid, ask, spread = lob.avellaneda_stoikov_quotes(100, 2, 1, gamma=.1, sigma=2, k=1.5)
        self.assertAlmostEqual(spread, .4 + 20 * math.log(1 + .1 / 1.5))
        self.assertAlmostEqual((bid + ask) / 2, 100 - 2 * .1 * 4)
        self.assertAlmostEqual(2 / .1 * math.log(1 + .1 / 1.5), 1.29, places=2)  # Table spread in the paper.

    def test_inventory_quotes_reduce_risk_versus_symmetric(self):
        for gamma in (.01, .1, .5):
            result = lob.compare({"gamma": gamma, "paths": 600, "spread_time_term": False})
            self.assertLess(result["inventory"]["final_inventory_std"], result["symmetric"]["final_inventory_std"])
            self.assertLess(result["inventory"]["profit_std"], result["symmetric"]["profit_std"])

    def test_reproduces_published_gamma_point_one_row(self):
        # Avellaneda & Stoikov (2008), gamma = 0.1, 1,000 paper simulations:
        # inventory 62.94 / 5.89 / q std 2.80; symmetric 67.21 / 13.43 / 8.66.
        # Our large-sample values are 62.15 and 67.02: close, not exact (see docs/WORK_LOG.md).
        result = lob.compare({"gamma": .1, "paths": 4000, "seed": 3, "spread_time_term": False})
        for name, mean, std in (("inventory", 62.94, 5.89), ("symmetric", 67.21, 13.43)):
            row = result[name]
            paper_error = std / math.sqrt(1000)
            tolerance = max(4 * math.hypot(row["profit_standard_error"], paper_error), .02 * mean)
            self.assertLess(abs(row["profit_mean"] - mean), tolerance, name)
            self.assertAlmostEqual(row["profit_std"] / std, 1, delta=.08)
        self.assertAlmostEqual(result["inventory"]["final_inventory_std"], 2.80, delta=.25)
        self.assertAlmostEqual(result["symmetric"]["final_inventory_std"], 8.66, delta=.6)

    def test_seeded_reproducibility_and_validation(self):
        args = {"paths": 200, "seed": 9, "mode": "realistic", "queue_depth": 1.0, "mean_order_size": 2.0}
        self.assertEqual(lob.simulate(args), lob.simulate(args))
        for bad in [{"paths": 0}, {"dt": .003}, {"mode": "live"}, {"strategy": "x"}, {"intensity": 300},
                    {"unknown": 1}, {"latency_steps": -1}, {"spread_time_term": 1}]:
            with self.assertRaises(ValueError):
                lob.simulate(bad)

    def test_inventory_limit_is_never_breached(self):
        result = lob.simulate({"mode": "realistic", "paths": 300, "inventory_limit": 3, "strategy": "symmetric",
                               "mean_order_size": 3.0, "quote_size": 2})
        self.assertLessEqual(result["max_abs_inventory_mean"], 3)

    def test_frictions_lower_profit(self):
        base = {"mode": "realistic", "paths": 1500, "seed": 4, "gamma": .1}
        clean = lob.simulate(base)
        frictions = lob.simulate({**base, "queue_depth": 3.0, "latency_steps": 3, "adverse_move": .05,
                                  "maker_fee_bps": .5, "taker_fee_bps": 2.0, "tick": .05})
        self.assertLess(frictions["profit_mean"], clean["profit_mean"])
        self.assertLess(frictions["fills_mean"], clean["fills_mean"])  # Queue ahead absorbs volume.
        self.assertGreater(frictions["fees_mean"], 0)


if __name__ == "__main__":
    unittest.main()
