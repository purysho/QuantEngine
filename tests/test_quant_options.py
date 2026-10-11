import math
import unittest

import numpy as np

from workers import quant_options as opt


class BlackScholesTests(unittest.TestCase):
    def test_published_reference_prices(self):
        # Hull, Options, Futures and Other Derivatives: S=42, K=40, r=10%, sigma=20%, T=0.5.
        self.assertAlmostEqual(opt.black_scholes(42, 40, .5, .1, .2)["price"], 4.7594, places=4)
        self.assertAlmostEqual(opt.black_scholes(42, 40, .5, .1, .2, kind="put")["price"], .8086, places=4)
        # Haug, Complete Guide to Option Pricing Formulas: generalized BSM and Merton (1973) puts.
        self.assertAlmostEqual(opt.black_scholes(75, 70, .5, .1, .35, .05, "put")["price"], 4.0870, places=4)
        self.assertAlmostEqual(opt.black_scholes(100, 95, .5, .1, .2, .05, "put")["price"], 2.4648, places=4)

    def test_put_call_parity(self):
        for s, k, t, r, v, q in [(100, 80, 2, .03, .5, .01), (50, 70, .1, -.01, .15, .04), (10, 10, 5, .2, 1.5, 0)]:
            c = opt.black_scholes(s, k, t, r, v, q, "call")["price"]
            p = opt.black_scholes(s, k, t, r, v, q, "put")["price"]
            self.assertAlmostEqual(c - p, s * math.exp(-q * t) - k * math.exp(-r * t), places=9)

    def test_greeks_match_finite_differences(self):
        base = dict(spot=100.0, strike=105.0, time=.75, rate=.04, volatility=.25, dividend=.02)
        for kind in opt.KINDS:
            g = opt.black_scholes(**base, kind=kind)
            def price(**change):
                return opt.black_scholes(**{**base, **change}, kind=kind)["price"]
            h = 1e-4
            self.assertAlmostEqual(g["delta"], (price(spot=100 + h) - price(spot=100 - h)) / (2 * h), places=6)
            self.assertAlmostEqual(g["gamma"], (price(spot=100 + 1e-2) - 2 * g["price"] + price(spot=100 - 1e-2)) / 1e-4, places=5)
            self.assertAlmostEqual(g["vega"], (price(volatility=.25 + h) - price(volatility=.25 - h)) / (2 * h), places=5)
            self.assertAlmostEqual(g["rho"], (price(rate=.04 + h) - price(rate=.04 - h)) / (2 * h), places=5)
            self.assertAlmostEqual(g["theta_per_year"], -(price(time=.75 + h) - price(time=.75 - h)) / (2 * h), places=5)
            delta = lambda v: opt.black_scholes(**{**base, "volatility": v}, kind=kind)["delta"]
            self.assertAlmostEqual(g["vanna"], (delta(.25 + h) - delta(.25 - h)) / (2 * h), places=5)
            vega = lambda v: opt.black_scholes(**{**base, "volatility": v}, kind=kind)["vega"]
            self.assertAlmostEqual(g["volga"], (vega(.25 + h) - vega(.25 - h)) / (2 * h), places=4)
            self.assertAlmostEqual(g["theta_per_day"] * 365, g["theta_per_year"])

    def test_expired_and_zero_volatility_contracts(self):
        self.assertEqual(opt.black_scholes(110, 100, 0, .05, .2)["price"], 10.0)
        self.assertEqual(opt.black_scholes(90, 100, 0, .05, .2)["price"], 0.0)
        deterministic = opt.black_scholes(100, 90, 1, .05, 0)
        self.assertAlmostEqual(deterministic["price"], 100 - 90 * math.exp(-.05))
        self.assertAlmostEqual(deterministic["theta_per_year"],
                               -(opt.black_scholes(100, 90, 1 + 1e-5, .05, 0)["price"] - opt.black_scholes(100, 90, 1 - 1e-5, .05, 0)["price"]) / 2e-5, places=5)
        # Near-zero volatility converges to the deterministic price.
        self.assertAlmostEqual(opt.black_scholes(100, 90, 1, .05, 1e-6)["price"], deterministic["price"], places=6)

    def test_invalid_inputs_are_rejected(self):
        for args in [(0, 100, 1, .05, .2), (100, -1, 1, .05, .2), (100, 100, -1, .05, .2),
                     (100, 100, 1, .05, float("nan")), (100, 100, 1, .05, 9), (True, 100, 1, .05, .2)]:
            with self.assertRaises(ValueError):
                opt.black_scholes(*args)
        with self.assertRaises(ValueError):
            opt.black_scholes(100, 100, 1, .05, .2, kind="straddle")


class TreeAndMonteCarloTests(unittest.TestCase):
    def test_crr_converges_to_black_scholes(self):
        exact = opt.black_scholes(100, 100, 1, .05, .2)["price"]
        errors = [abs(opt.crr_price(100, 100, 1, .05, .2, steps=n) - exact) for n in (50, 200, 1000)]
        self.assertLess(errors[2], errors[0])
        self.assertLess(errors[2], 2e-3)

    def test_american_exercise_dominance_and_reference(self):
        # Hull: American put, S=K=50, r=10%, sigma=40%, T=5/12, five-step tree = 4.49.
        self.assertAlmostEqual(opt.crr_price(50, 50, 5 / 12, .1, .4, kind="put", steps=5, american=True), 4.49, places=2)
        american = opt.crr_price(50, 50, 5 / 12, .1, .4, kind="put", steps=500, american=True)
        european = opt.crr_price(50, 50, 5 / 12, .1, .4, kind="put", steps=500)
        self.assertGreater(american, european)
        self.assertAlmostEqual(american, 4.283, places=2)
        # No dividends: an American call is never exercised early.
        self.assertAlmostEqual(opt.crr_price(50, 50, 1, .1, .4, steps=300, american=True),
                               opt.crr_price(50, 50, 1, .1, .4, steps=300), places=12)
        # Deep in-the-money puts are worth at least intrinsic value.
        self.assertGreaterEqual(opt.crr_price(20, 50, 1, .1, .4, kind="put", steps=200, american=True), 30)

    def test_tree_rejects_invalid_probability(self):
        with self.assertRaises(ValueError):
            opt.crr_price(100, 100, 10, .9, .05, steps=1)

    def test_monte_carlo_is_reproducible_and_within_sampling_error(self):
        exact = opt.black_scholes(100, 110, 1, .03, .3, .01, "put")["price"]
        a = opt.monte_carlo_price(100, 110, 1, .03, .3, .01, "put", paths=200_000, seed=5)
        self.assertEqual(a, opt.monte_carlo_price(100, 110, 1, .03, .3, .01, "put", paths=200_000, seed=5))
        self.assertLess(abs(a["price"] - exact), 3 * a["standard_error"])
        small = opt.monte_carlo_price(100, 110, 1, .03, .3, .01, "put", paths=2_000, seed=5)
        self.assertGreater(small["standard_error"], a["standard_error"] * 5)
        with self.assertRaises(ValueError):
            opt.monte_carlo_price(100, 100, 1, .05, .2, paths=1001)


class ImpliedVolatilityTests(unittest.TestCase):
    def test_round_trip(self):
        for kind in opt.KINDS:
            for sigma in (.05, .2, .8, 2.5):
                price = opt.black_scholes(100, 120, .5, .02, sigma, .01, kind)["price"]
                self.assertAlmostEqual(opt.implied_volatility(price, 100, 120, .5, .02, .01, kind), sigma, places=7)

    def test_impossible_quotes_are_rejected(self):
        with self.assertRaises(ValueError):
            opt.implied_volatility(1.0, 42, 40, .5, .1)  # Below the discounted intrinsic value.
        with self.assertRaises(ValueError):
            opt.implied_volatility(43, 42, 40, .5, .1)  # Above spot.
        with self.assertRaises(ValueError):
            opt.implied_volatility(5, 42, 40, 0, .1)

    def test_rule_of_sixteen(self):
        move = opt.implied_move(.16)
        self.assertAlmostEqual(move["rule_of_16"], .01)
        self.assertAlmostEqual(move["one_sigma"], .16 / math.sqrt(252))
        self.assertAlmostEqual(move["expected_absolute_move"] / move["one_sigma"], math.sqrt(2 / math.pi))


class SurfaceTests(unittest.TestCase):
    def quotes(self, params_by_expiry, spot=100, rate=.02):
        quotes = []
        for expiry, params in params_by_expiry.items():
            forward = spot * math.exp(rate * expiry)
            for strike in np.linspace(70, 140, 9):
                k = math.log(strike / forward)
                sigma = math.sqrt(float(opt.svi_total_variance(params, k)) / expiry)
                kind = "put" if strike < forward else "call"
                quotes.append({"strike": float(strike), "expiry": expiry, "kind": kind,
                               "price": opt.black_scholes(spot, strike, expiry, rate, sigma, 0, kind)["price"]})
        return quotes

    def test_svi_recovery_and_arbitrage_free_surface(self):
        truth = {.25: (.005, .08, -.4, .0, .15), 1.0: (.02, .12, -.35, .02, .2)}
        surface = opt.volatility_surface(self.quotes(truth), 100, .02)
        self.assertEqual(surface["rejected"], [])
        self.assertTrue(surface["arbitrage_free"], surface["arbitrage_violations"])
        for row in surface["slices"]:
            self.assertLess(row["svi"]["rmse_total_variance"], 1e-6)
            self.assertAlmostEqual(row["svi"]["rho"], truth[row["expiry"]][2], places=3)

    def test_calendar_arbitrage_is_detected(self):
        # Later expiry has lower total variance at every moneyness.
        truth = {.25: (.03, .08, -.4, .0, .15), 1.0: (.005, .05, -.35, .0, .2)}
        surface = opt.volatility_surface(self.quotes(truth), 100, .02)
        self.assertIn("calendar", {v["type"] for v in surface["arbitrage_violations"]})

    def test_butterfly_violation_and_rejected_quote(self):
        quotes = [{"strike": 90, "expiry": .5, "price": 12.0}, {"strike": 100, "expiry": .5, "price": 9.0},
                  {"strike": 110, "expiry": .5, "price": 3.0}, {"strike": 100, "expiry": .5, "price": 500.0}]
        surface = opt.volatility_surface(quotes, 100, .0)
        self.assertIn("butterfly", {v["type"] for v in surface["arbitrage_violations"]})
        self.assertEqual([r["index"] for r in surface["rejected"]], [3])


class ReportTests(unittest.TestCase):
    def test_report_cross_checks_methods(self):
        report = opt.options_report({"spot": 100, "strike": 95, "time": .5, "rate": .03, "volatility": .25,
                                     "kind": "put", "paths": 50_000, "steps": 400, "market_price": 4.0})
        self.assertLess(abs(report["put_call_parity_gap"]), 1e-10)
        self.assertTrue(report["monte_carlo"]["within_three_standard_errors"])
        self.assertGreaterEqual(report["trees"]["early_exercise_premium"], 0)
        self.assertLess(abs(report["trees"]["european_tree_error"]), .01)
        self.assertGreater(report["implied"]["implied_volatility"], 0)

    def test_unknown_or_missing_parameters_fail(self):
        with self.assertRaises(ValueError):
            opt.options_report({"spot": 100})
        with self.assertRaises(ValueError):
            opt.options_report({"spot": 100, "strike": 100, "time": 1, "rate": 0, "volatility": .2, "barrier": 1})


if __name__ == "__main__":
    unittest.main()


class SsviTests(unittest.TestCase):
    def test_atm_level_and_static_arbitrage(self):
        surface = opt.ssvi_surface(.25, rho=-.5, eta=1.2)
        self.assertTrue(surface["sufficient_no_arbitrage"])
        k = np.asarray(surface["log_moneyness"])
        atm = int(np.argmin(np.abs(k)))
        np.testing.assert_allclose(np.asarray(surface["implied_volatility"])[:, atm], .25, rtol=1e-12)
        # Re-price the model surface and run the independent arbitrage checks on it.
        spot, quotes = 100.0, []
        for i, T in enumerate(surface["expiries"][::6]):
            for j, kk in enumerate(surface["log_moneyness"][::5]):
                sigma = surface["implied_volatility"][i * 6][j * 5]
                strike = spot * math.exp(kk)
                quotes.append({"strike": strike, "expiry": T, "kind": "call",
                               "price": opt.black_scholes(spot, strike, T, 0, sigma)["price"]})
        checked = opt.volatility_surface(quotes, spot, 0)
        self.assertEqual(checked["rejected"], [])
        self.assertTrue(checked["arbitrage_free"], checked["arbitrage_violations"])

    def test_negative_rho_is_put_skew_and_bounds_are_flagged(self):
        surface = opt.ssvi_surface(.2, rho=-.6, eta=1.0)
        row = surface["implied_volatility"][5]
        self.assertGreater(row[0], row[-1])
        self.assertFalse(opt.ssvi_surface(.2, rho=.9, eta=1.5)["sufficient_no_arbitrage"])
        with self.assertRaises(ValueError):
            opt.ssvi_surface(0)

    def test_report_includes_surface(self):
        report = opt.options_report({"spot": 100, "strike": 100, "time": 1, "rate": .02, "volatility": .3,
                                     "paths": 2000, "surface_rho": -.3})
        self.assertEqual(report["surface"]["parameters"]["rho"], -.3)
