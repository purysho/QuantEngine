"""Backtest QuantEngine's mathematics against what actually happened.

Sources: Kenneth R. French Data Library (CRSP-based daily US market and 12 industry
portfolios, 1926-present) and FRED (CBOE VIX, Brent and WTI spot). Raw data is cached
under .cache/data and never committed; this script records URLs, SHA-256 and dates.
Run with --offline to require the cache.
"""
import argparse
import datetime as dt
import math
import time

import numpy as np
from scipy import stats

from _common import ROOT, write
from workers import quant_data as qd
from workers.quant_core import walk_forward
from workers.quant_options import black_scholes
from workers.quant_pairs import engle_granger, pairs_backtest
from workers.quant_varbacktest import METHODS, backtest_var, kupiec_christoffersen, rolling_var_levels

parser = argparse.ArgumentParser()
parser.add_argument("--offline", action="store_true")
args = parser.parse_args()
CACHE = ROOT / ".cache" / "data"
started = time.perf_counter()
sources = {}

# ---------------------------------------------------------------- R1 VaR on 100 years of the US market
dates, market, meta = qd.us_market_returns(CACHE, offline=args.offline)
sources["us_market"] = {**{k: meta[k] for k in ("url", "sha256", "retrieved_at")}, "first": str(dates[0]), "last": str(dates[-1]), "days": len(dates),
                        "construction": "Mkt-RF + RF (CRSP value-weighted total market), decimal daily returns"}
WINDOW = 500
var_rows, by_decade, crisis = [], {}, {}
forecast_dates = dates[WINDOW:]
realised = market[WINDOW:]
crises = {"1929 crash and early Depression (1929-10 to 1932-07)": ("1929-10-01", "1932-07-31"),
          "1987 crash (1987-10)": ("1987-10-01", "1987-10-31"),
          "Global financial crisis (2008-09 to 2009-03)": ("2008-09-01", "2009-03-31"),
          "COVID crash (2020-02-20 to 2020-04-30)": ("2020-02-20", "2020-04-30")}
pinball = {}
for method in METHODS:
    levels = rolling_var_levels(market, window=WINDOW, levels=(.05, .01), method=method, refit_every=50)
    for p in (.05, .01):
        result = backtest_var(market, window=WINDOW, p=p, method=method, forecasts=levels[p])
        var_rows.append({"method": method, "p": p, **{k: result[k] for k in ("forecasts", "exceptions", "expected_exceptions",
                         "exception_rate", "kupiec_p_value", "independence_p_value", "conditional_coverage_p_value")},
                         "exception_ratio": result["exceptions"] / result["expected_exceptions"]})
        hits = realised < -levels[p]
        # Quantile (pinball) loss: a strictly consistent score for VaR forecasts; lower is better.
        q = -levels[p]
        pinball[f"{method}@{p}"] = float(np.mean((p - (realised < q)) * (realised - q)))
        decades = {}
        for d, h in zip(forecast_dates, hits):
            key = f"{d.year // 10 * 10}s"
            n, x = decades.get(key, (0, 0))
            decades[key] = (n + 1, x + int(h))
        by_decade[f"{method}@{p}"] = {k: round(x / (n * p), 2) for k, (n, x) in decades.items()}
        for label, (a, b) in crises.items():
            a, b = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
            mask = np.array([a <= d <= b for d in forecast_dates])
            crisis.setdefault(label, {})[f"{method}@{p}"] = {"days": int(mask.sum()), "exceptions": int(hits[mask].sum()),
                                                            "expected": round(mask.sum() * p, 1)}
worst = int(np.argmin(market))
garch_1987 = None
i1987 = dates.index(dt.date(1987, 10, 19))
lv = rolling_var_levels(market[: i1987 + 1], window=WINDOW, levels=(.01,), method="garch_t", refit_every=50)[.01]
garch_1987 = {"date": "1987-10-19", "return": float(market[i1987]), "garch_t_var99_forecast": float(lv[-1]),
              "loss_in_forecast_multiples": float(-market[i1987] / lv[-1])}

# ---------------------------------------------------------------- R2 VIX / 16 rule vs realised moves
vix_table, vix_meta = qd.fred(["VIXCLS"], CACHE, offline=args.offline)
sources["vix"] = {k: vix_meta[k] for k in ("url", "sha256", "retrieved_at")}
vdates, vix, mret = qd.align(vix_table["dates"], vix_table["series"]["VIXCLS"], dates, market)
sigma_daily = vix[:-1] / 100 / math.sqrt(252)        # VIX at close t ...
next_move = mret[1:]                                 # ... against the market move on the next trading day.
z = next_move / sigma_daily
normal = {k: float(2 * stats.norm.sf(k)) for k in (1, 2, 3, 4)}
forward_rv = np.array([mret[t + 1:t + 22].std(ddof=1) * math.sqrt(252) for t in range(len(mret) - 22)])
vix_rule = {"days": int(len(z)), "first": str(vdates[0]), "last": str(vdates[-1]),
            "share_within_1_sigma": float(np.mean(np.abs(z) <= 1)), "normal_within_1_sigma": 1 - normal[1],
            "share_beyond": {f"{k}_sigma": float(np.mean(np.abs(z) > k)) for k in (2, 3, 4)},
            "normal_beyond": {f"{k}_sigma": normal[k] for k in (2, 3, 4)},
            "mean_abs_move_over_sigma": float(np.mean(np.abs(z))), "normal_mean_abs_over_sigma": math.sqrt(2 / math.pi),
            "vix_minus_forward_21d_realised_vol_points": {"mean": float(np.mean(vix[:-22] - 100 * forward_rv)),
                                                         "median": float(np.median(vix[:-22] - 100 * forward_rv)),
                                                         "share_vix_above_realised": float(np.mean(vix[:-22] > 100 * forward_rv))},
            "rule_of_16_vs_sqrt252_error": 1 - 16 / math.sqrt(252)}

# ---------------------------------------------------------------- R3 Black-Scholes with VIX vs actual 1-month outcomes
ff, _ = qd.french("F-F_Research_Data_Factors_daily", CACHE, offline=args.offline)
rf_by_date = dict(zip(ff["dates"], ff["series"]["RF"]))
H = 21
price_call, price_put, pay_call, pay_put, pits = [], [], [], [], []
for t in range(0, len(mret) - H, H):  # Non-overlapping months: independent-ish samples.
    sigma = vix[t] / 100
    T = H / 252
    rate = math.log1p(rf_by_date[vdates[t]]) * 252
    growth = float(np.prod(1 + mret[t + 1:t + H + 1]))  # Total-return index, so no dividend yield.
    c = black_scholes(1.0, 1.0, T, rate, sigma, 0, "call")["price"]
    p_ = black_scholes(1.0, 1.0, T, rate, sigma, 0, "put")["price"]
    disc = math.exp(-rate * T)
    price_call.append(c); price_put.append(p_)
    pay_call.append(disc * max(growth - 1, 0)); pay_put.append(disc * max(1 - growth, 0))
    pits.append(stats.norm.cdf((math.log(growth) - (rate - sigma ** 2 / 2) * T) / (sigma * math.sqrt(T))))
pits = np.array(pits)
deciles = np.histogram(pits, bins=10, range=(0, 1))[0] / len(pits)
bs_reality = {"months": len(pits), "horizon_trading_days": H,
              "atm_put_realised_payoff_over_bs_price": float(np.mean(pay_put) / np.mean(price_put)),
              "atm_call_realised_payoff_over_bs_price": float(np.mean(pay_call) / np.mean(price_call)),
              "put_payoff_ratio_95ci": [float(x) for x in np.percentile(
                  [np.mean(np.array(pay_put)[i]) / np.mean(np.array(price_put)[i])
                   for i in np.random.default_rng(1).integers(0, len(pits), (2000, len(pits)))], [2.5, 97.5])],
              "pit_deciles": [round(float(x), 4) for x in deciles],
              "pit_ks_statistic": float(stats.kstest(pits, "uniform").statistic),
              "pit_ks_p_value": float(stats.kstest(pits, "uniform").pvalue),
              "share_below_1pct_quantile": float(np.mean(pits < .01)), "share_above_99pct_quantile": float(np.mean(pits > .99)),
              "note": "VIX is 30-calendar-day S&P 500 implied vol under Q; the underlying here is the CRSP total market. "
                      "The ratio compares average realised payoff to the Black-Scholes price at VIX vol."}

# ---------------------------------------------------------------- R4 Brent-WTI cointegration through structural breaks
oil, oil_meta = qd.fred(["DCOILBRENTEU", "DCOILWTICO"], CACHE, offline=args.offline)
sources["oil"] = {k: oil_meta[k] for k in ("url", "sha256", "retrieved_at")}
odates, brent, wti = qd.align(oil["dates"], oil["series"]["DCOILBRENTEU"], oil["dates"], oil["series"]["DCOILWTICO"])
FORM, TRADE = 252, 126
windows, skipped_nonpositive = [], []
for start in range(0, len(odates) - FORM - TRADE, TRADE):
    seg = slice(start, start + FORM + TRADE)
    b, w = brent[seg], wti[seg]
    label = f"{odates[start + FORM]}..{odates[start + FORM + TRADE - 1]}"
    if (b <= 0).any() or (w <= 0).any():
        skipped_nonpositive.append(label)  # WTI settled at -36.98 on 2020-04-20: log prices do not exist.
        continue
    test = engle_granger(np.log(b[:FORM]), np.log(w[:FORM]), criterion="bic")
    bt = pairs_backtest(b, w, formation=FORM, cost_bps=5, borrow_bps=50)
    windows.append({"trading": label, "cointegrated": test["rejects_5pct"], "p_value": test["p_value"],
                    "hedge_ratio": test["hedge_ratio"], "half_life": test["half_life"], "return": bt["total_return"],
                    "round_trips": bt["round_trips"]})
traded = [w_ for w_ in windows if w_["cointegrated"]]
always = [w_["return"] for w_ in windows]
pairs_real = {"windows": len(windows), "cointegrated_share": len(traded) / max(len(windows), 1),
              "skipped_nonpositive_prices": skipped_nonpositive,
              "selected_mean_return": float(np.mean([w_["return"] for w_ in traded])) if traded else None,
              "selected_share_profitable": float(np.mean([w_["return"] > 0 for w_ in traded])) if traded else None,
              "unselected_mean_return": float(np.mean([w_["return"] for w_ in windows if not w_["cointegrated"]])) if len(traded) < len(windows) else None,
              "all_windows_mean_return": float(np.mean(always)) if always else None,
              "worst_windows": sorted(windows, key=lambda w_: w_["return"])[:3]}

# ---------------------------------------------------------------- R5 Momentum on 12 US industries since 1926
ind, ind_meta = qd.french("12_Industry_Portfolios_daily", CACHE, section="Average Value Weighted Returns -- Daily", offline=args.offline)
sources["industries"] = {k: ind_meta[k] for k in ("url", "sha256", "retrieved_at")}
names = list(ind["series"])
R = np.column_stack([ind["series"][n] for n in names])
ok = np.isfinite(R).all(axis=1)
R, idates = R[ok], [d for d, k in zip(ind["dates"], ok) if k]
prices = np.vstack([np.ones(len(names)), np.cumprod(1 + R, axis=0)])
momentum = {}
for lookback in (60, 252):
    bt = walk_forward(prices, lookback=lookback, rebalance=21, cost_bps=10)
    net = np.asarray(bt["net_returns"]); eq = np.asarray(bt["baselines"]["equal_weight"]["net_returns"])
    first = bt["timing"]["first_execution_price_index"]
    ret_dates = idates[first:]  # Return index t is the move ending on idates[t].
    decades = {}
    for d, a, b in zip(ret_dates, net, eq):
        key = f"{d.year // 10 * 10}s"
        decades.setdefault(key, [[], []]); decades[key][0].append(a); decades[key][1].append(b)
    momentum[str(lookback)] = {"sharpe": bt["sharpe"], "annualized_return": bt["annualized_return"], "max_drawdown": bt["max_drawdown"],
                               "equal_weight_sharpe": bt["baselines"]["equal_weight"]["sharpe"],
                               "equal_weight_annualized": bt["baselines"]["equal_weight"]["annualized_return"],
                               "turnover": bt["turnover"],
                               "by_decade_excess_annualized": {k: float((np.mean(v[0]) - np.mean(v[1])) * 252) for k, v in decades.items()}}

finished = time.perf_counter()
get = lambda m, p: next(r for r in var_rows if r["method"] == m and r["p"] == p)
findings = [
    f"VaR, 100 years: at 99%, Gaussian windows breach {get('gaussian', .01)['exception_ratio']:.2f}x the promised rate, historical {get('historical', .01)['exception_ratio']:.2f}x, "
    f"Student-t {get('student_t', .01)['exception_ratio']:.2f}x, GARCH-t {get('garch_t', .01)['exception_ratio']:.2f}x, GJR-GARCH filtered historical simulation "
    f"{get('gjr_fhs', .01)['exception_ratio']:.2f}x (Kupiec p {get('gjr_fhs', .01)['kupiec_p_value']:.2f}). Lowest pinball loss at 99%: "
    f"{min((k for k in pinball if k.endswith('@0.01')), key=pinball.get)}.",
    f"1987-10-19: the market fell {-100 * garch_1987['return']:.1f}%, {garch_1987['loss_in_forecast_multiples']:.1f}x the GARCH-t 99% VaR. No model "
    "estimated from prior data anticipates a one-day jump of that size; that is what stress tests are for.",
    f"VIX/16: next-day moves stayed within one implied sigma {100 * vix_rule['share_within_1_sigma']:.1f}% of days (normal: 68.3%), "
    f"yet moves beyond 3 sigma happened {vix_rule['share_beyond']['3_sigma'] / normal[3]:.1f}x as often as a normal predicts. "
    f"VIX exceeded subsequent 21-day realised volatility {100 * vix_rule['vix_minus_forward_21d_realised_vol_points']['share_vix_above_realised']:.0f}% of the time "
    f"(mean gap {vix_rule['vix_minus_forward_21d_realised_vol_points']['mean']:.1f} points): the variance risk premium.",
    f"Black-Scholes at VIX: 1-month ATM puts paid back {bs_reality['atm_put_realised_payoff_over_bs_price']:.2f} of their price on average "
    f"(95% CI {bs_reality['put_payoff_ratio_95ci'][0]:.2f}-{bs_reality['put_payoff_ratio_95ci'][1]:.2f}); calls {bs_reality['atm_call_realised_payoff_over_bs_price']:.2f}. "
    f"Outcomes below the 1% lognormal quantile: {100 * bs_reality['share_below_1pct_quantile']:.1f}% of months.",
    f"Brent-WTI: {100 * pairs_real['cointegrated_share']:.0f}% of rolling formation windows passed Engle-Granger; "
    f"{len(skipped_nonpositive)} window(s) skipped because WTI went negative in April 2020.",
    f"Industry momentum (252-day, monthly rebalance, 10 bps): Sharpe {momentum['252']['sharpe']:.2f} vs equal weight {momentum['252']['equal_weight_sharpe']:.2f}.",
]
payload = {"purpose": "Compare QuantEngine's models with realised history across a century, several asset classes and named crises.",
           "sources": sources, "attribution": "Kenneth R. French Data Library (CRSP); FRED, Federal Reserve Bank of St. Louis (CBOE VIX; EIA spot oil).",
           "var_us_market": {"window": WINDOW, "refit_every": 50, "rows": var_rows, "pinball_loss": pinball,
                             "exception_ratio_by_decade": by_decade, "crises": crisis, "black_monday": garch_1987},
           "vix_rule": vix_rule, "black_scholes_vs_reality": bs_reality, "pairs_brent_wti": pairs_real,
           "industry_momentum": momentum, "findings": findings,
           "acceptance": {
               "gjr_fhs_passes_kupiec_at_99": get("gjr_fhs", .01)["kupiec_p_value"] > .05,
               "gjr_fhs_lowest_pinball_at_99": min((k for k in pinball if k.endswith("@0.01")), key=pinball.get) == "gjr_fhs@0.01",
               "gaussian_window_fails_at_99": get("gaussian", .01)["kupiec_p_value"] < .05,
               "vix_exceeds_realised_most_days": vix_rule["vix_minus_forward_21d_realised_vol_points"]["share_vix_above_realised"] > .5,
               "negative_oil_price_windows_refused": len(skipped_nonpositive) > 0}}
path = write("real_world_backtest", payload, started, finished)
print("\n".join(findings))
print("written", path, round(finished - started, 1), "s")
