import math
import unittest

import numpy as np

from workers import quant_pairs as qp


def cointegrated(n=600, seed=0, phi=.9, beta=.8):
    rng = np.random.default_rng(seed)
    x = 4 + np.cumsum(rng.normal(0, .01, n))
    spread = np.zeros(n)
    for t in range(1, n):
        spread[t] = phi * spread[t - 1] + rng.normal(0, .01)
    y = .5 + beta * x + spread
    return np.exp(y), np.exp(x)


class InferenceTests(unittest.TestCase):
    def test_published_mackinnon_values(self):
        # MacKinnon (2010) asymptotic constant-case values.
        self.assertEqual(qp.mackinnon_critical_values(1), {"1%": -3.43035, "5%": -2.86154, "10%": -2.56677})
        self.assertAlmostEqual(qp.mackinnon_critical_values(2)["5%"], -3.33613)
        # Finite-sample response surface: tau(100) = b0 + b1/100 + b2/100^2 + b3/100^3.
        self.assertAlmostEqual(qp.mackinnon_critical_values(1, 100)["5%"], -2.86154 - .028903 - .0004234 - .00004004)
        self.assertAlmostEqual(qp.mackinnon_p_value(-2.86154, 1), .05, delta=.002)
        self.assertEqual(qp.mackinnon_p_value(5, 1), 1.0)
        self.assertEqual(qp.mackinnon_p_value(-30, 2), 0.0)

    def test_adf_distinguishes_random_walk_from_stationary(self):
        rng = np.random.default_rng(2)
        walk = np.cumsum(rng.normal(size=500))
        self.assertGreater(qp.adf_test(walk)["p_value"], .05)
        self.assertLess(qp.adf_test(np.diff(walk))["p_value"], .01)

    def test_engle_granger_power_and_hedge_ratio(self):
        y, x = cointegrated()
        result = qp.engle_granger(np.log(y), np.log(x))
        self.assertTrue(result["rejects_5pct"])
        self.assertAlmostEqual(result["hedge_ratio"], .8, delta=.1)
        self.assertAlmostEqual(result["half_life"], math.log(2) / -math.log(.9), delta=3)

    def test_collinear_and_short_series_are_rejected(self):
        x = np.cumsum(np.random.default_rng(1).normal(size=100))
        with self.assertRaises(ValueError):
            qp.engle_granger(2 * x + 1, x)
        with self.assertRaises(ValueError):
            qp.engle_granger(x[:20], x[:20] + 1)

    def test_holm_step_down(self):
        self.assertEqual(qp.holm([.01, .04, .03, .2], .05), [True, False, False, False])
        self.assertEqual(qp.holm([.001, .01, .02], .05), [True, True, True])


class SelectionAndBacktestTests(unittest.TestCase):
    def test_selection_finds_planted_pair_with_holm(self):
        y, x = cointegrated(seed=4)
        rng = np.random.default_rng(9)
        noise = 4 + np.cumsum(rng.normal(0, .01, (600, 2)), axis=0)
        prices = np.column_stack([np.log(y), np.log(x), noise])
        result = qp.select_pairs(prices[:400], ["Y", "X", "N1", "N2"])
        pairs = {(t["y"], t["x"]) for t in result["selected"]}
        self.assertTrue({("Y", "X"), ("X", "Y")} & pairs)
        self.assertFalse({("N1", "N2"), ("N2", "N1")} & pairs)
        self.assertEqual(result["tests_run"], len(result["tests"]))

    def test_formation_only_fit_and_prefix_invariance(self):
        y, x = cointegrated(seed=1)
        base = qp.pairs_backtest(y, x, formation=300)
        y2 = y.copy(); y2[450:] *= 1.5
        changed = qp.pairs_backtest(y2, x, formation=300)
        self.assertEqual(base["hedge_ratio"], changed["hedge_ratio"])
        self.assertEqual(base["spread_std"], changed["spread_std"])
        np.testing.assert_allclose(base["equity"][:449 - 300 + 1], changed["equity"][:449 - 300 + 1])

    def test_signal_close_does_not_trade(self):
        y, x = cointegrated(seed=1)
        result = qp.pairs_backtest(y, x, formation=300, cost_bps=0, borrow_bps=0)
        self.assertGreater(len(result["trades"]), 1)
        for trade in result["trades"]:
            if not trade.get("liquidation"):
                self.assertEqual(trade["execution_close"], trade["signal_close"] + 1)
        first = result["trades"][0]
        # Equity cannot move before the first execution close.
        flat = first["execution_close"] - 300
        self.assertTrue(all(v == 1.0 for v in result["equity"][:flat + 1]))

    def test_costs_and_borrow_reduce_returns_and_positions_close(self):
        y, x = cointegrated(seed=3)
        free = qp.pairs_backtest(y, x, formation=300, cost_bps=0, borrow_bps=0)
        costly = qp.pairs_backtest(y, x, formation=300, cost_bps=20, borrow_bps=300)
        self.assertLess(costly["total_return"], free["total_return"])
        self.assertGreater(costly["costs_paid"], 0)
        self.assertGreater(costly["borrow_paid"], 0)
        self.assertEqual(costly["trades"][-1]["position"], 0)

    def test_invalid_backtest_inputs(self):
        y, x = cointegrated()
        for kw in [dict(formation=10), dict(entry_z=.4, exit_z=.5), dict(cost_bps=-1)]:
            with self.assertRaises(ValueError):
                qp.pairs_backtest(y, x, **kw)
        with self.assertRaises(ValueError):
            qp.pairs_backtest(-y, x)


if __name__ == "__main__":
    unittest.main()
