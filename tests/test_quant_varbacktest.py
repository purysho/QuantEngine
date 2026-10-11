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


class GarchTests(unittest.TestCase):
    @staticmethod
    def simulate(seed, n=3000, omega=2e-6, alpha=.08, beta=.9, df=5):
        import math
        rng = np.random.default_rng(seed)
        z = rng.standard_t(df, n) / math.sqrt(df / (df - 2))
        r, v = np.empty(n), omega / (1 - alpha - beta)
        for t in range(n):
            r[t] = math.sqrt(v) * z[t]
            v = omega + alpha * r[t] ** 2 + beta * v
        return r

    def test_parameter_recovery(self):
        fit = vb.fit_garch_t(self.simulate(7)[:2500])
        self.assertAlmostEqual(fit["alpha"], .08, delta=.04)
        self.assertAlmostEqual(fit["beta"], .90, delta=.05)
        self.assertLess(fit["persistence"], 1)
        self.assertAlmostEqual(fit["nu"], 5, delta=2.5)

    def test_garch_var_is_causal_and_reacts_to_shocks(self):
        r = self.simulate(3, n=900)
        base = vb.rolling_var(r, window=500, method="garch_t", refit_every=50)
        shocked = r.copy(); shocked[700] = -.08
        changed = vb.rolling_var(shocked, window=500, method="garch_t", refit_every=50)
        np.testing.assert_array_equal(base[:201], changed[:201])  # Forecasts for days 500..700.
        self.assertGreater(changed[201], 1.5 * base[201])  # Volatility jumps the day after the shock.

    def test_extreme_inputs_do_not_overflow(self):
        r = np.r_[np.zeros(150), np.full(50, .2), -np.full(50, .2)] + np.random.default_rng(0).normal(0, 1e-4, 250)
        self.assertTrue(np.isfinite(vb.fit_garch_t(r)["nu"]))


class GjrFhsTests(unittest.TestCase):
    def test_gjr_recovers_leverage_effect(self):
        import math
        rng = np.random.default_rng(4)
        n, omega, alpha, gamma, beta = 4000, 2e-6, .03, .10, .9
        r, v = np.empty(n), omega / (1 - alpha - gamma / 2 - beta)
        z = rng.standard_t(6, n) / math.sqrt(6 / 4)
        for t in range(n):
            r[t] = math.sqrt(v) * z[t]
            v = omega + (alpha + gamma * (r[t] < 0)) * r[t] ** 2 + beta * v
        fit = vb.fit_garch_t(r, asymmetric=True)
        self.assertAlmostEqual(fit["gamma"], .10, delta=.06)
        self.assertGreater(fit["gamma"], fit["alpha"])
        self.assertLess(fit["persistence"], 1)

    def test_fhs_is_causal_and_calibrated_on_garch(self):
        r = GarchTests.simulate(11, n=2500)
        base = vb.rolling_var(r, window=500, method="gjr_fhs", refit_every=50)
        shocked = r.copy(); shocked[1500] = -.1
        changed = vb.rolling_var(shocked, window=500, method="gjr_fhs", refit_every=50)
        np.testing.assert_array_equal(base[:1001], changed[:1001])
        result = vb.backtest_var(r, window=500, p=.05, method="gjr_fhs", refit_every=50)
        self.assertAlmostEqual(result["exception_rate"], .05, delta=.015)
