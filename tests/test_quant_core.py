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

    def test_fractional_tail_mass_and_ties(self):
        tail = core.empirical_tail([2, 0, -1, -10], .375)
        self.assertAlmostEqual(tail["expected_shortfall"], 7.0)
        self.assertAlmostEqual(tail["var"], 1.0)
        self.assertIn("inverse CDF", tail["quantile_method"])
        tied = core.empirical_tail([-5, -5, -5, -5, 1], .5)
        self.assertAlmostEqual(tied["var"], 5.0)
        self.assertAlmostEqual(tied["expected_shortfall"], 5.0)
        # 5% of 100 must be exactly five whole observations despite float rounding.
        tail = core.empirical_tail(np.arange(100.0), .05)
        self.assertAlmostEqual(tail["expected_shortfall"], -2.0)
        self.assertAlmostEqual(tail["var"], -4.0)  # Signed loss: the whole tail is a gain.
        self.assertGreaterEqual(tail["expected_shortfall"], tail["var"])

    def test_tail_rejects_invalid_input(self):
        for samples, p in [([], .05), ([1, np.nan], .05), ([1, 2], 0), ([1, 2], 1.5), ([1, 2], np.nan), ([1, 2], True)]:
            with self.assertRaises(ValueError):
                core.empirical_tail(samples, p)

    def test_signal_close_does_not_trade_and_executes_next_close(self):
        # Asset 0 is flat until a large rise into close 21, which creates the first positive momentum.
        prices = np.ones((40, 2)) * 100.0
        prices[21:, 0] = np.linspace(110, 130, 19)
        prices[:, 1] = 100 * (1 - .001) ** np.arange(40)  # Steady decline: never selected.
        result = core.walk_forward(prices, lookback=20, rebalance=1, cost_bps=0)
        decisions = {d["signal_price_index"]: d for d in result["decisions"]}
        first = decisions[min(decisions)]
        self.assertEqual(first["execution_price_index"], first["signal_price_index"] + 1)
        self.assertEqual(first["first_return_interval"], [first["execution_price_index"], first["execution_price_index"] + 1])
        # The rise from close 20 to 21 is observed at close 21, so it cannot be earned.
        self.assertEqual(decisions[20]["weights"], [0.0, 0.0])
        self.assertEqual(decisions[21]["weights"][0], 1.0)
        self.assertEqual(decisions[21]["execution_price_index"], 22)
        returns = core.price_returns(prices)
        offset = result["timing"]["first_execution_price_index"]
        self.assertAlmostEqual(result["gross_returns"][22 - offset], returns[22, 0])
        self.assertEqual(result["gross_returns"][21 - offset], 0.0)

    def test_costs_are_charged_at_execution_close(self):
        r = np.random.default_rng(3).normal(.001, .01, (90, 2))
        prices = 100 * np.vstack([np.ones(2), np.cumprod(1 + r, axis=0)])
        result = core.walk_forward(prices, lookback=20, rebalance=5, cost_bps=25)
        offset = result["timing"]["first_execution_price_index"]
        for decision in result["decisions"]:
            i = decision["execution_price_index"] - offset
            self.assertAlmostEqual(result["cost_fractions"][i], decision["turnover"] * 25 / 10_000)
            self.assertAlmostEqual(result["net_returns"][i], (1 - result["cost_fractions"][i]) * (1 + result["gross_returns"][i]) - 1)

    def test_curve_dates_align_with_delayed_execution(self):
        dates, assets, prices = core.example_prices()
        report = core.analyse(dates, assets, prices, paths=2000, horizon=5, lookback=20)
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["engine_version"], "0.2.0")
        self.assertEqual(report["curve"][0]["date"], dates[21])
        self.assertEqual(report["curve"][-1]["date"], dates[-1])
        self.assertEqual(len(report["curve"]), len(report["backtest"]["net_returns"]) + 1)

    def test_student_t_risk_is_heavier_than_gaussian_on_fat_tailed_data(self):
        r = np.random.default_rng(8).standard_t(3, (2000, 1)) * .01
        w = np.array([1.0])
        t = core.student_t_risk(r, w, paths=20000, horizon=1, seed=4)
        g = core.simulate_risk(r, w, paths=20000, horizon=1, seed=4)
        self.assertLess(t["degrees_of_freedom"], 6)
        self.assertGreater(t["var99"], g["var99"])
        self.assertGreater(t["es99"], g["es99"])
        self.assertGreater(t["sample_excess_kurtosis"], 1)
        # Analytic one-day quantile matches the simulation within sampling error.
        self.assertAlmostEqual(t["one_day_analytic"]["var95"], t["var95"], delta=.0015)
        self.assertEqual(t, core.student_t_risk(r, w, paths=20000, horizon=1, seed=4))

    def test_hill_estimator_recovers_pareto_index(self):
        x = np.random.default_rng(12).pareto(3.0, 20000) + 1
        estimate = core.hill_tail_index(x, k=1000)
        self.assertAlmostEqual(estimate["alpha"], 3.0, delta=.3)
        self.assertIsNone(core.hill_tail_index([1, 2, 3])["alpha"])

if __name__ == "__main__": unittest.main()

