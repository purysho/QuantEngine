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


def layout(family, market, assets, seed=9):
    """Asset matrix each family expects: industries for sectors; market, industries, 3 quality portfolios and bonds otherwise."""
    if family in ("trend", "sectors"):
        return assets
    rng = np.random.default_rng(seed)
    quality = market[:, None] * .9 + rng.normal(.0002, .004, (len(market), 3))
    bonds = rng.normal(.0002, .004, len(market))[:, None]
    return np.column_stack([market, assets, quality, bonds])


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
            data = layout(family, market, assets)
            base = st.backtest(family, spec, dates, market, rf, data)
            shocked_market, shocked = market.copy(), data.copy()
            shocked_market[2000:] *= -3
            shocked[2000:] *= -3
            if family not in ("trend", "sectors"):
                shocked[:, 0] = shocked_market
            other = st.backtest(family, spec, dates, shocked_market, rf, shocked)
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

    def test_ensemble_balances_sleeves_caps_leverage_and_pays_for_borrowing(self):
        dates, market, rf, assets = market_data(n=1500)
        data = layout("ensemble", market, assets)
        spec = {"weighting": "inverse_vol", "target_vol": .30, "leverage_cap": 1.5, "rebalance": "month"}
        weights = st.target_weights("ensemble", spec, market, rf, data, dates)
        rows = weights[~np.isnan(weights).any(axis=1)]
        self.assertTrue(len(rows) > 10)
        self.assertLessEqual(rows.sum(axis=1).max(), 1.5 + 1e-12)
        self.assertTrue((rows >= 0).all())
        self.assertTrue((rows[:, st.ENSEMBLE_BONDS] > 0).all())
        levered = st.backtest("ensemble", spec, dates, market, rf, data, cost_bps=0)
        self.assertGreater(levered["max_exposure"], 1.0)
        # Same weights with free borrowing would earn more: the margin spread is charged.
        spread, st.BORROW_SPREAD = st.BORROW_SPREAD, 0.0
        try:
            free = st.backtest("ensemble", spec, dates, market, rf, data, cost_bps=0)
        finally:
            st.BORROW_SPREAD = spread
        self.assertGreater(free["net"].sum(), levered["net"].sum())

    def test_paper_signals_for_quality_and_the_levered_ensemble(self):
        dates, market, rf, assets = market_data(n=700, k=13)
        closes = 100 * np.cumprod(1 + np.column_stack([market, assets]), axis=0)  # SPY, 11 sectors, QUAL, IEF.
        universe = st.PAPER_UNIVERSE["ensemble"]
        ens = st.paper_signal("ensemble", dates, closes, universe, 0.04, since=dates[600])
        self.assertLessEqual(ens["gross_exposure"], 1.5 + 1e-9)
        self.assertIn("IEF", ens["targets"])
        self.assertIn("QUAL", ens["targets"])
        quality = st.paper_signal("quality", dates, closes[:, [0, 12]], st.PAPER_UNIVERSE["quality"], 0.04)
        self.assertEqual(quality["targets"], {"QUAL": 1.0})
        with self.assertRaisesRegex(ValueError, "expects these symbols"):
            st.latest_signal("quality", st.FAMILIES["quality"]["primary"], dates, closes[:, [0, 12]], ["SPY", "XLK"])

    def test_treasury_returns_reprice_a_par_bond(self):
        r = st.treasury_returns(["a", "b", "c", "d"], ["a", "b", "c"], [4.0, 4.0, 5.0])
        self.assertTrue(np.isnan(r[0]))
        self.assertAlmostEqual(r[1], .04 / 252, places=12)       # Unchanged yield: one day of coupon.
        self.assertAlmostEqual(r[2], -.0778, delta=5e-4)          # +100 bp on a 10-year 4% par bond.
        self.assertAlmostEqual(r[3], .05 / 252, places=12)       # Missing yield carries the last value.

    def test_quality_holds_the_chosen_portfolio(self):
        dates, market, rf, assets = market_data(n=400)
        data = layout("quality", market, assets)
        run = st.backtest("quality", {"portfolio": "Hi 20", "rebalance": "month"}, dates, market, rf, data, cost_bps=0)
        s = run["start"]
        np.testing.assert_allclose(run["net"], data[s:, 14])


if __name__ == "__main__":
    unittest.main()
