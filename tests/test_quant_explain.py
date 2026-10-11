import math
import unittest

import numpy as np

from workers import quant_core as core
from workers import quant_explain as ex
from workers import quant_options as opt


class ExplanationTests(unittest.TestCase):
    def test_black_scholes_steps_reproduce_engine_price(self):
        for kind in ("call", "put"):
            steps = ex.black_scholes_steps(42, 40, .5, .1, .2, 0, kind)
            price = next(s for s in steps if s["title"].endswith("price"))
            self.assertAlmostEqual(float(price["result"]), opt.black_scholes(42, 40, .5, .1, .2, 0, kind)["price"], places=4)
            self.assertTrue(all({"title", "formula", "substitution", "result"} <= set(s) for s in steps))

    def test_tail_steps_match_engine_tail(self):
        x = np.random.default_rng(1).normal(size=1001)
        steps = ex.tail_steps(x, .05)
        tail = core.empirical_tail(x, .05)
        self.assertAlmostEqual(float(steps[2]["result"]), tail["var"], places=5)
        self.assertAlmostEqual(float(steps[3]["result"]), tail["expected_shortfall"], places=5)
        fixture = ex.tail_steps([-10, -1, 0, 2], .375)
        self.assertAlmostEqual(float(fixture[3]["result"]), 7.0)

    def test_reports_carry_explanations(self):
        report = opt.options_report({"spot": 100, "strike": 95, "time": .5, "rate": .03, "volatility": .25, "paths": 2000})
        self.assertGreater(len(report["explanation"]["black_scholes"]), 4)
        self.assertAlmostEqual(float(report["explanation"]["monte_carlo"][0]["result"]), report["monte_carlo"]["price"], places=4)
        dates, assets, prices = core.example_prices()
        analysis = core.analyse(dates, assets, prices, paths=1000, horizon=5)
        steps = analysis["explanation"]["minimum_variance"]
        self.assertAlmostEqual(float(steps[-1]["result"]), math.sqrt(float(np.array(list(analysis["weights"].values())) @ np.array(analysis["shrunk_covariance"]) @ np.array(list(analysis["weights"].values())))), places=4)

    def test_greeks_match_symbolic_differentiation(self):
        try:
            import sympy as sp
        except ImportError:
            self.skipTest("sympy is a development-only dependency (requirements-dev.txt)")
        S, K, T, r, q, v = sp.symbols("S K T r q v", positive=True)
        N = lambda x: (1 + sp.erf(x / sp.sqrt(2))) / 2
        d1 = (sp.log(S / K) + (r - q + v ** 2 / 2) * T) / (v * sp.sqrt(T))
        d2 = d1 - v * sp.sqrt(T)
        call = S * sp.exp(-q * T) * N(d1) - K * sp.exp(-r * T) * N(d2)
        values = {S: 100, K: 105, T: .75, r: .04, q: .02, v: .25}
        engine = opt.black_scholes(100, 105, .75, .04, .25, .02, "call")
        symbolic = {"price": call, "delta": sp.diff(call, S), "gamma": sp.diff(call, S, 2), "vega": sp.diff(call, v),
                    "rho": sp.diff(call, r), "theta_per_year": -sp.diff(call, T), "vanna": sp.diff(call, S, v), "volga": sp.diff(call, v, 2)}
        for name, expression in symbolic.items():
            self.assertAlmostEqual(float(expression.subs(values).evalf(30)), engine[name], places=9, msg=name)


if __name__ == "__main__":
    unittest.main()
