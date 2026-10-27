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
    """Asset matrix each family expects: industries for sectors; otherwise market, industries, 3 quality portfolios,
    bonds, 3 value and 3 momentum portfolios (columns 17-22)."""
    if family in ("trend", "sectors"):
        return assets
    rng = np.random.default_rng(seed)
    quality = market[:, None] * .9 + rng.normal(.0002, .004, (len(market), 3))
    bonds = rng.normal(.0002, .004, len(market))[:, None]
    value = market[:, None] * 1.1 + rng.normal(.0001, .006, (len(market), 3))
    momentum = market[:, None] + rng.normal(.0002, .012, (len(market), 3))
    return np.column_stack([market, assets, quality, bonds, value, momentum])


def french_zip(body: str) -> bytes:
    import io
    import zipfile
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("test.csv", body)
    return buffer.getvalue()


def french_file(columns, rows, section="Average Value Weighted Returns -- Daily"):
    lines = ["Header", "", f"  {section}" if section else "", "," + ",".join(columns)]
    lines += [d + "," + ",".join(f"{v:.2f}" for v in values) for d, values in rows]
    return french_zip("\n".join(lines) + "\n\nCopyright\n")


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


class MultifactorTests(unittest.TestCase):
    def test_equal_weights_hold_a_third_of_each_sleeve(self):
        dates, market, rf, assets = market_data(n=400)
        data = layout("multifactor", market, assets)
        for cut, columns in (("Hi 30", [15, 19, 22]), ("Hi 10", [13, 17, 20])):
            run = st.backtest("multifactor", {"cut": cut, "weighting": "equal", "rebalance": "month"}, dates, market, rf, data, cost_bps=0)
            np.testing.assert_allclose(run["net"], data[run["start"]:, columns].mean(axis=1), rtol=0, atol=1e-15)
            self.assertEqual(run["max_exposure"], 1.0)

    def test_inverse_volatility_favours_the_calmer_sleeve_and_stays_fully_invested(self):
        dates, market, rf, assets = market_data(n=400)
        data = layout("multifactor", market, assets)
        w = st.target_weights("multifactor", {"cut": "Hi 30", "weighting": "inverse_vol", "rebalance": "month"}, market, rf, data)
        self.assertTrue(np.isnan(w[st.VOL_WINDOW - 2]).all())
        row = w[300]
        np.testing.assert_allclose(row.sum(), 1.0, atol=1e-12)
        self.assertGreater(row[15], row[22])  # Quality sleeve is calmer than the momentum sleeve in this data.
        window = data[300 - st.VOL_WINDOW + 1:301, [15, 19, 22]]
        inverse = 1 / window.std(axis=0, ddof=1)
        np.testing.assert_allclose(row[[15, 19, 22]], inverse / inverse.sum(), rtol=1e-9)

    def test_paper_signal_holds_qual_vlue_and_mtum(self):
        dates, market, rf, assets = market_data(n=400, k=3)
        closes = 100 * np.cumprod(1 + np.column_stack([market, assets]), axis=0)
        out = st.paper_signal("multifactor", dates, closes, st.PAPER_UNIVERSE["multifactor"], 0.04, since=dates[350])
        self.assertEqual(out["targets"], {"QUAL": 1 / 3, "VLUE": 1 / 3, "MTUM": 1 / 3})
        self.assertTrue(all(d >= dates[350] for d in out["simulated"]))

    def test_lab_inputs_add_value_and_averaged_momentum_columns(self):
        days = ["19630701", "19630702", "19630703", "19630705", "19630708"]
        factors = french_file(["Mkt-RF", "SMB", "HML", "RF"], [(d, [1.0, 0, 0, .01]) for d in days], section=None)
        industries = french_file([f"I{i}" for i in range(12)], [(d, [float(i)] * 12) for i, d in enumerate(days)])
        cuts = ["Lo 30", "Med 40", "Hi 30", "Lo 20", "Qnt 2", "Qnt 3", "Qnt 4", "Hi 20", "Lo 10", "Dec 2", "Hi 10"]
        op = french_file(cuts, [(d, [.1] * len(cuts)) for d in days])
        bm = french_file(["<= 0"] + cuts, [(d, [9.0] + [.2] * 7 + [.3, 0, 0, .4]) for d in days])
        deciles = ["Lo PRIOR"] + [f"PRIOR {i}" for i in range(2, 10)] + ["Hi PRIOR"]
        mom = french_file(deciles, [(d, [0.0] * 7 + [1.0, 2.0, 6.0]) for d in days])
        dgs10 = b"observation_date,DGS10\n" + b"".join(f"{d[:4]}-{d[4:6]}-{d[6:]},4.0\n".encode() for d in days)
        out = st.lab_inputs(factors, industries, op, dgs10, bm, mom)
        dates, m, r, matrix = out["full"]
        self.assertEqual(matrix.shape[1], 23)
        np.testing.assert_allclose(matrix[:, 20], .06)              # Hi 10 = top decile (6%).
        np.testing.assert_allclose(matrix[:, 21], .04)              # Hi 20 = mean of deciles 9-10.
        np.testing.assert_allclose(matrix[:, 22], .03)              # Hi 30 = mean of deciles 8-10.
        np.testing.assert_allclose(matrix[:, 17], .004)             # Value Hi 10.
        self.assertEqual(st.lab_inputs(factors, industries, op, dgs10)["full"][3].shape[1], 17, "without the new files nothing changes")

    def test_registration_names_the_multifactor_family(self):
        self.assertIn("multifactor", st.FAMILIES)
        self.assertEqual(st.REGISTERED_MULTIFACTOR, "2026-10-27")
        self.assertEqual(len(st.specs("multifactor")), 6)
        self.assertEqual(sum(len(st.specs(f)) for f in st.FAMILIES), 49)


if __name__ == "__main__":
    unittest.main()
