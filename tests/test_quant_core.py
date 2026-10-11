import importlib.util
import unittest
import tempfile
from pathlib import Path
import numpy as np

SPEC = importlib.util.find_spec("workers.quant_core")
core = __import__("workers.quant_core", fromlist=["*"]) if SPEC else None

class QuantCoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(core, "quant_core implementation is missing")

    def test_rejects_nonpositive_and_nonfinite_prices(self):
        for prices in [np.array([[1.,2.],[0.,3.]]), np.array([[1.,2.],[np.nan,3.]])]:
            with self.assertRaises(ValueError):
                core.price_returns(prices)

    def test_exact_simple_returns(self):
        result = core.price_returns(np.array([[100.,50.],[110.,45.],[99.,54.]]))
        np.testing.assert_allclose(result, [[.1,-.1],[-.1,.2]], atol=1e-12)

    def test_known_minimum_variance_solution(self):
        result = core.minimum_variance(np.diag([.04,.16]))
        np.testing.assert_allclose(result, [.8,.2], atol=1e-5)
        self.assertAlmostEqual(float(result.sum()),1.)
        self.assertTrue(np.all(result >= 0))

    def test_zero_risk_portfolio_is_zero_under_simulation(self):
        r = np.tile([.01,-.01],(100,1))
        risk = core.simulate_risk(r,np.array([.5,.5]),paths=5000,horizon=1,seed=17)
        self.assertLess(abs(risk["var95"]),1e-12)
        self.assertLess(abs(risk["es95"]),1e-12)

    def test_seeded_simulation_reproduces_and_tail_order_is_valid(self):
        r=np.random.default_rng(10).normal(0,.01,(300,3))
        args=dict(paths=10000,horizon=5,seed=29)
        a=core.simulate_risk(r,np.ones(3)/3,**args)
        b=core.simulate_risk(r,np.ones(3)/3,**args)
        self.assertEqual(a,b)
        self.assertGreaterEqual(a["es95"],a["var95"])
        self.assertGreater(a["var95"],0)

    def test_future_data_cannot_change_earlier_backtest_decisions(self):
        r=np.random.default_rng(5).normal(.0003,.008,(180,3))
        prices=100*np.vstack([np.ones(3),np.cumprod(1+r,axis=0)])
        altered=prices.copy()
        altered[140:]*=np.linspace(1,2,len(altered[140:]))[:,None]
        a=core.walk_forward(prices,lookback=20,rebalance=5,cost_bps=10)
        b=core.walk_forward(altered,lookback=20,rebalance=5,cost_bps=10)
        np.testing.assert_allclose(a["net_returns"][:110],b["net_returns"][:110])
        self.assertLess(a["total_return"],a["gross_total_return"])

    def test_csv_dates_and_missing_prices_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"input.csv"
            for text in ["date,A,B\n2026-01-01,10,20\n2026-01-01,11,21\n",
                         "date,A,B\n2026-01-02,10,20\n2026-01-01,11,21\n",
                         "date,A,B\n2026-01-01,10,20\n2026-01-02,,21\n"]:
                p.write_text(text)
                with self.assertRaises(ValueError):
                    core.load_prices(p)

    def test_report_has_real_engine_outputs_and_cost_baselines(self):
        dates,assets,prices=core.example_prices()
        report=core.analyse(dates,assets,prices,paths=5000,horizon=5,seed=19)
        self.assertEqual(report["monte_carlo"]["paths"],5000)
        self.assertAlmostEqual(sum(report["weights"].values()),1.,places=6)
        self.assertIn("equal_weight",report["backtest"]["baselines"])
        self.assertIn("cash",report["backtest"]["baselines"])
        self.assertGreater(len(report["curve"]),20)
        self.assertTrue(np.isfinite(report["backtest"]["sharpe"]))

    def test_block_bootstrap_reproduces_and_has_valid_empirical_tail(self):
        self.assertTrue(hasattr(core, "bootstrap_risk"), "Block-bootstrap comparison is missing")
        r = np.random.default_rng(31).normal(0, .02, (150, 2))
        a = core.bootstrap_risk(r, np.array([.6, .4]), paths=5000, horizon=10, seed=23, block_size=5)
        b = core.bootstrap_risk(r, np.array([.6, .4]), paths=5000, horizon=10, seed=23, block_size=5)
        self.assertEqual(a, b)
        self.assertGreaterEqual(a["es95"], a["var95"])
        self.assertEqual(a["block_size"], 5)
        self.assertLessEqual(a["max_batch_bytes"], 16 * 1024 * 1024)

    def test_parameter_sensitivity_is_computed_from_real_costed_backtests(self):
        dates, assets, prices = core.example_prices()
        report = core.analyse(dates, assets, prices, paths=5000)
        self.assertTrue("bootstrap" in report, "Empirical risk report is missing")
        self.assertTrue("sensitivity" in report, "Parameter comparison is missing")
        for variant in report["sensitivity"]:
            expected = core.walk_forward(prices, lookback=variant["lookback"], cost_bps=10)
            self.assertAlmostEqual(variant["total_return"], expected["total_return"])
            self.assertAlmostEqual(variant["equal_weight_return"], expected["baselines"]["equal_weight"]["total_return"])

if __name__ == "__main__": unittest.main()

