import math
import unittest

import numpy as np

from workers import quant_stats as qs
from workers import quant_strategies as st


def ar1(n=3000, phi=.3, seed=42):
    rng = np.random.default_rng(seed)
    e = rng.normal(0, .01, n)
    r = np.empty(n)
    r[0] = e[0]
    for i in range(1, n):
        r[i] = phi * r[i - 1] + e[i]
    return r + .0005


def market_data(n=3000, seed=5, k=12):
    rng = np.random.default_rng(seed)
    days, dates = 0, []
    import datetime as dt
    day = dt.date(2000, 1, 3)
    while len(dates) < n:
        if day.weekday() < 5:
            dates.append(day.isoformat())
        day += dt.timedelta(days=1)
    common = rng.normal(.0003, .01, n)
    assets = common[:, None] + rng.normal(.0001, .006, (n, k))
    return dates, common, np.full(n, .00008), assets


class StatsTests(unittest.TestCase):
    def test_newey_west_matches_statsmodels_reference(self):
        # statsmodels 0.15.0 OLS(r, 1).fit(cov_type="HAC", maxlags=10, use_correction=False).bse[0]
        self.assertAlmostEqual(qs.newey_west_mean(ar1(), lags=10)["se"], 0.0002597771584470582, delta=1e-15)

    def test_autocorrelation_widens_the_standard_error(self):
        nw = qs.newey_west_mean(ar1(phi=.5))
        self.assertGreater(nw["se"], 1.4 * nw["naive_se"])

    def test_psr_is_one_half_at_the_benchmark_and_dsr_falls_with_more_trials(self):
        r = np.random.default_rng(1).normal(.0004, .01, 2520)
        sr = r.mean() / r.std(ddof=1)
        self.assertAlmostEqual(qs.probabilistic_sharpe(r, sr), .5, places=12)
        trials = np.random.default_rng(2).normal(0, .01, 100)
        few, many = qs.deflated_sharpe(r, trials[:5]), qs.deflated_sharpe(r, trials)
        self.assertGreater(many["threshold_per_period"], few["threshold_per_period"])
        self.assertLess(many["dsr"], few["dsr"])

    def test_bootstrap_interval_contains_the_estimate_and_is_reproducible(self):
        r = np.random.default_rng(3).normal(.0004, .01, 2520)
        a, b = qs.bootstrap_sharpe(r, draws=300), qs.bootstrap_sharpe(r, draws=300)
        self.assertEqual(a, b)
        self.assertLess(a["ci95"][0], a["sharpe"])
        self.assertGreater(a["ci95"][1], a["sharpe"])
        same = qs.bootstrap_sharpe_difference(r, r, draws=100)
        self.assertEqual(same["ci95"], [0.0, 0.0])


class StrategyTests(unittest.TestCase):
    def test_no_look_ahead_future_data_cannot_change_past_returns(self):
        dates, market, rf, assets = market_data()
        for family in st.FAMILIES:
            spec = st.FAMILIES[family]["primary"]
            base = st.backtest(family, spec, dates, market, rf, assets)
            shocked_market, shocked_assets = market.copy(), assets.copy()
            shocked_market[2000:] *= -3
            shocked_assets[2000:] *= -3
            other = st.backtest(family, spec, dates, shocked_market, rf, shocked_assets)
            cut = 2000 - base["start"]
            np.testing.assert_array_equal(base["net"][:cut], other["net"][:cut])

    def test_signal_trades_at_the_next_close(self):
        dates, market, rf, assets = market_data(n=600)
        spec = {"lookback": 126, "target_vol": None, "rebalance": "month"}
        wanted = st.target_weights("trend", spec, market, rf)
        run = st.backtest("trend", spec, dates, market, rf, cost_bps=0)
        s = int(np.flatnonzero(st.rebalance_days(dates, "month") & ~np.isnan(wanted[:, 0]))[0])
        self.assertEqual(run["start"], s + 2)
        w = wanted[s, 0]
        self.assertAlmostEqual(run["net"][0], w * market[s + 2] + (1 - w) * rf[s + 2], places=15)

    def test_costs_are_charged_on_turnover(self):
        dates, market, rf, assets = market_data()
        spec = st.FAMILIES["sectors"]["primary"]
        free, costly = st.backtest("sectors", spec, dates, market, rf, assets, 0), st.backtest("sectors", spec, dates, market, rf, assets, 50)
        self.assertGreater(free["net"].sum() - costly["net"].sum(), 0)
        self.assertAlmostEqual(free["net"].sum() - costly["net"].sum(), free["turnover_per_year"] * len(free["net"]) / 252 * 50 / 1e4, places=10)

    def test_evaluation_reports_gates_and_registration(self):
        dates, market, rf, assets = market_data(n=3000)
        result = st.evaluate("sectors", dates, market, rf, assets, first_walk_forward_year=2005, holdout_years=3, bootstrap_draws=100)
        self.assertEqual(set(result["gates"]), set(st.GATES))
        self.assertEqual(result["spec_curve"]["count"], len(st.specs("sectors")))
        self.assertEqual(len(st.registration_hash()), 64)

    def test_live_signal_uses_the_backtest_rule(self):
        dates, market, rf, assets = market_data(n=400)
        closes = 100 * np.cumprod(1 + np.column_stack([market, assets[:, :3]]), axis=0)
        signal = st.latest_signal("sectors", {"lookback": 252, "top": 2, "trend_filter": False, "rebalance": "month"}, dates, closes, ["SPY", "A", "B", "C"])
        self.assertAlmostEqual(sum(signal["targets"].values()), 1.0)
        self.assertEqual(len(signal["targets"]), 2)
        self.assertNotIn("SPY", signal["targets"])  # The market column only drives the trend filter.
        with self.assertRaisesRegex(ValueError, "lookback"):
            st.latest_signal("trend", st.FAMILIES["trend"]["primary"], dates[:100], closes[:100], ["SPY", "A", "B", "C"])

    def test_paper_signal_simulates_the_same_rule_on_the_traded_etfs(self):
        dates, market, rf, assets = market_data(n=700)
        closes = 100 * np.cumprod(1 + np.column_stack([market, assets[:, :5]]), axis=0)
        out = st.paper_signal("sectors", dates, closes, ["SPY", "A", "B", "C", "D", "E"], 0.04, since=dates[500])
        self.assertEqual(len(out["targets"]), st.FAMILIES["sectors"]["primary"]["top"])
        self.assertTrue(all(d >= dates[500] for d in out["simulated"]))
        self.assertEqual(set(out["prices"]), {"SPY", "A", "B", "C", "D", "E"})
        trend = st.paper_signal("trend", dates, closes[:, :1], ["SPY"], 0.04)
        self.assertIn("SPY", trend["targets"])
        self.assertLessEqual(trend["targets"]["SPY"], 1.0)


if __name__ == "__main__":
    unittest.main()
