import unittest

import numpy as np

from workers import quant_varbacktest as vb


class VarBacktestTests(unittest.TestCase):
    def test_kupiec_reference_values(self):
        # 250 days at 1%: 2.5 expected. Five exceptions: LR = -2[245 ln(.99/.98) + 5 ln(.01/.02)] = 1.9569 (hand-derived).
        hits = np.zeros(250, dtype=bool); hits[[10, 60, 110, 160, 210]] = True
        result = vb.kupiec_christoffersen(hits, .01)
        self.assertAlmostEqual(result["kupiec_lr"], 1.9568, places=3)
        self.assertEqual(result["transitions"]["n11"], 0)
        exact = vb.kupiec_christoffersen(np.r_[np.ones(10, bool), np.zeros(990, bool)], .01)
        self.assertAlmostEqual(exact["kupiec_lr"], 0.0, places=12)

    def test_clustered_exceptions_fail_independence(self):
        hits = np.zeros(1000, dtype=bool); hits[500:510] = True
        result = vb.kupiec_christoffersen(hits, .01)
        self.assertGreater(result["kupiec_p_value"], .5)
        self.assertLess(result["independence_p_value"], .001)

    def test_forecasts_never_see_their_own_day(self):
        r = np.random.default_rng(1).normal(0, .01, 400)
        base = vb.rolling_var(r, window=100, method="historical")
        shocked = r.copy(); shocked[300] = -.5
        changed = vb.rolling_var(shocked, window=100, method="historical")
        np.testing.assert_array_equal(base[:201], changed[:201])  # Forecasts for days 100..300.
        self.assertGreater(changed[201], base[201])

    def test_gaussian_var_fails_on_fat_tails_while_t_passes(self):
        r = np.random.default_rng(5).standard_t(3, 2500) * .01
        gauss = vb.backtest_var(r, window=500, p=.01, method="gaussian")
        student = vb.backtest_var(r, window=500, p=.01, method="student_t", refit_every=25)
        self.assertGreater(gauss["exception_rate"], student["exception_rate"])
        self.assertLess(gauss["kupiec_p_value"], .05)
        self.assertGreater(student["kupiec_p_value"], .05)

    def test_validation(self):
        for kw in [dict(window=10), dict(method="garch"), dict(window=5000), dict(method="student_t", refit_every=0)]:
            with self.assertRaises(ValueError):
                vb.rolling_var(np.zeros(300), **kw)


if __name__ == "__main__":
    unittest.main()
