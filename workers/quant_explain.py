"""Step-by-step workings for QuantEngine's calculations ("show the maths").

Each explainer returns a list of steps: {title, formula, substitution, result, note}. The numbers are
recomputed from the same inputs the engine used, and tests assert that the final step equals the
engine's own answer, so an explanation can never silently disagree with a result.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import stats


def _f(x, digits=6):
    return f"{x:.{digits}g}" if isinstance(x, (int, float)) and math.isfinite(x) else str(x)


def step(title, formula, substitution, result, note=""):
    return {"title": title, "formula": formula, "substitution": substitution, "result": result, "note": note}


def black_scholes_steps(spot, strike, time, rate, volatility, dividend=0.0, kind="call") -> list[dict]:
    S, K, T, r, sigma, q = (float(v) for v in (spot, strike, time, rate, volatility, dividend))
    steps = [step("Inputs", "S, K, T, r, q, σ", f"S={_f(S)}, K={_f(K)}, T={_f(T)} y, r={_f(r)}, q={_f(q)}, σ={_f(sigma)}", "",
                  "Continuously compounded rate and dividend yield; σ is annual volatility.")]
    if T <= 0 or sigma * math.sqrt(T) < 1e-12:
        sign = 1 if kind == "call" else -1
        forward = S * math.exp((r - q) * T)
        value = math.exp(-r * T) * max(sign * (forward - K), 0.0)
        steps.append(step("Deterministic payoff", "V = e^(−rT)·max(±(S·e^((r−q)T) − K), 0)",
                          f"e^(−{_f(r)}·{_f(T)})·max({'+' if sign > 0 else '−'}({_f(forward)} − {_f(K)}), 0)", _f(value),
                          "With no time or no volatility the forward is certain."))
        return steps
    root = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + sigma ** 2 / 2) * T) / root
    d2 = d1 - root
    steps += [
        step("Volatility over the life", "σ√T", f"{_f(sigma)} × √{_f(T)}", _f(root), "Standard deviation of ln(S_T/S_0) under the model."),
        step("d₁", "d₁ = [ln(S/K) + (r − q + σ²/2)T] / (σ√T)",
             f"[ln({_f(S)}/{_f(K)}) + ({_f(r)} − {_f(q)} + {_f(sigma)}²/2)·{_f(T)}] / {_f(root)}", _f(d1)),
        step("d₂", "d₂ = d₁ − σ√T", f"{_f(d1)} − {_f(root)}", _f(d2)),
    ]
    N = stats.norm.cdf
    if kind == "call":
        value = S * math.exp(-q * T) * N(d1) - K * math.exp(-r * T) * N(d2)
        steps += [step("Normal probabilities", "N(d₁), N(d₂)", f"N({_f(d1)}), N({_f(d2)})", f"{_f(N(d1))}, {_f(N(d2))}",
                       "N(d₂) is the risk-neutral probability the call finishes in the money."),
                  step("Call price", "C = S·e^(−qT)·N(d₁) − K·e^(−rT)·N(d₂)",
                       f"{_f(S)}·e^(−{_f(q)}·{_f(T)})·{_f(N(d1))} − {_f(K)}·e^(−{_f(r)}·{_f(T)})·{_f(N(d2))}", _f(value))]
    else:
        value = K * math.exp(-r * T) * N(-d2) - S * math.exp(-q * T) * N(-d1)
        steps += [step("Normal probabilities", "N(−d₁), N(−d₂)", f"N({_f(-d1)}), N({_f(-d2)})", f"{_f(N(-d1))}, {_f(N(-d2))}",
                       "N(−d₂) is the risk-neutral probability the put finishes in the money."),
                  step("Put price", "P = K·e^(−rT)·N(−d₂) − S·e^(−qT)·N(−d₁)",
                       f"{_f(K)}·e^(−{_f(r)}·{_f(T)})·{_f(N(-d2))} − {_f(S)}·e^(−{_f(q)}·{_f(T)})·{_f(N(-d1))}", _f(value))]
    delta = math.exp(-q * T) * (N(d1) if kind == "call" else N(d1) - 1)
    delta_sub = (f"e^(−{_f(q)}·{_f(T)})·{_f(N(d1))}" if kind == "call" else f"e^(−{_f(q)}·{_f(T)})·({_f(N(d1))} − 1)")
    steps += [step("Delta", "Δ = e^(−qT)·N(d₁)  (call);  e^(−qT)·(N(d₁) − 1)  (put)", delta_sub, _f(delta),
                   "Change in option value per 1 unit change in spot."),
              step("Put–call parity check", "C − P = S·e^(−qT) − K·e^(−rT)",
                   f"{_f(S)}·e^(−{_f(q)}·{_f(T)}) − {_f(K)}·e^(−{_f(r)}·{_f(T)})", _f(S * math.exp(-q * T) - K * math.exp(-r * T)),
                   "Holds for any model without arbitrage; a quick sanity check on any pair of quotes.")]
    steps[-3]["value"] = value
    return steps


def crr_steps(spot, strike, time, rate, volatility, dividend=0.0, steps_count=500) -> list[dict]:
    dt = time / steps_count
    u = math.exp(volatility * math.sqrt(dt)); d = 1 / u
    p = (math.exp((rate - dividend) * dt) - d) / (u - d)
    return [step("Time step", "Δt = T / N", f"{_f(time)} / {steps_count}", _f(dt)),
            step("Up and down factors", "u = e^(σ√Δt), d = 1/u", f"u = e^({_f(volatility)}·√{_f(dt)})", f"u={_f(u)}, d={_f(d)}"),
            step("Risk-neutral probability", "p = (e^((r−q)Δt) − d) / (u − d)", f"(e^(({_f(rate)}−{_f(dividend)})·{_f(dt)}) − {_f(d)}) / ({_f(u)} − {_f(d)})",
                 _f(p), "Must lie in (0, 1), otherwise the tree admits arbitrage and is rejected."),
            step("Backward induction", "V = e^(−rΔt)[p·V_up + (1−p)·V_down];  American: V = max(V, exercise value)",
                 f"{steps_count} levels from expiry back to today", "", "As N grows, the European tree converges to Black–Scholes at rate O(1/N).")]


def monte_carlo_steps(result: dict) -> list[dict]:
    n = result["independent_pairs"]
    return [step("Estimator", "V̂ = (1/n) Σ e^(−rT)·½[payoff(S_T(Z)) + payoff(S_T(−Z))]", f"n = {n:,} antithetic pairs, seed {result['seed']}",
                 _f(result["price"]), "Pairing Z with −Z cancels much of the odd-order noise."),
            step("Standard error", "SE = s / √n  (s = standard deviation of pair means)", f"SE over {n:,} independent pairs", _f(result["standard_error"]),
                 "Pairs are independent; the two paths inside a pair are not, so the error uses pair means."),
            step("95% interval", "V̂ ± 1.96·SE", f"{_f(result['price'])} ± 1.96·{_f(result['standard_error'])}",
                 f"[{_f(result['confidence_95'][0])}, {_f(result['confidence_95'][1])}]")]


def implied_move_steps(volatility) -> list[dict]:
    sd = volatility / math.sqrt(252)
    return [step("One-sigma daily move", "σ_day = σ_annual / √252", f"{_f(volatility)} / {_f(math.sqrt(252))}", _f(sd),
                 "The trader's VIX/16 rule uses √256 = 16 in place of √252 ≈ 15.87."),
            step("Expected absolute move", "E|X| = σ_day·√(2/π)", f"{_f(sd)} × {_f(math.sqrt(2 / math.pi))}", _f(sd * math.sqrt(2 / math.pi)),
                 "On real data (1990–2026) the market stayed inside ±1σ on 81% of days, not 68%: VIX usually exceeds realised volatility.")]


def tail_steps(samples, p=.05) -> list[dict]:
    x = np.sort(np.asarray(samples, dtype=np.float64))
    n = len(x); mass = p * n
    if abs(mass - round(mass)) <= 1e-9 * max(1, mass):
        mass = float(round(mass))
    k = max(1, math.ceil(mass)); whole = math.floor(mass)
    tail = float(x[:whole].sum()) + (mass - whole) * float(x[whole]) if whole < n else float(x.sum())
    return [step("Sort outcomes", "x₍₁₎ ≤ x₍₂₎ ≤ … ≤ x₍ₙ₎", f"n = {n:,} simulated horizon returns", f"lowest = {_f(x[0])}"),
            step("Tail probability mass", "m = p·n", f"{_f(p)} × {n:,}", _f(mass), "Counts whole observations plus a fraction of the boundary one."),
            step("Value at Risk", "VaR_p = −x₍⌈m⌉₎  (lower empirical inverse CDF)", f"−x₍{k}₎ = −({_f(x[k - 1])})", _f(-x[k - 1]),
                 "Signed loss: a negative VaR means even the tail is a gain."),
            step("Expected shortfall", "ES_p = −[Σᵢ₌₁^⌊m⌋ x₍ᵢ₎ + (m − ⌊m⌋)·x₍⌊m⌋₊₁₎] / m",
                 f"−[{_f(float(x[:whole].sum()))} + {_f(mass - whole)}·{_f(float(x[whole]) if whole < n else 0)}] / {_f(mass)}", _f(-tail / mass),
                 "The average loss given that you are in the worst p of outcomes.")]


def gaussian_horizon_steps(daily_mean, daily_sd, horizon) -> list[dict]:
    m, s = daily_mean * horizon, daily_sd * math.sqrt(horizon)
    return [step("Scale to the horizon", "μ_h = h·μ,  σ_h = √h·σ", f"μ_h = {horizon}·{_f(daily_mean)},  σ_h = √{horizon}·{_f(daily_sd)}",
                 f"μ_h={_f(m)}, σ_h={_f(s)}", "Assumes independent, identically distributed daily returns."),
            step("Closed-form 95% VaR", "VaR = −(μ_h + σ_h·z₀.₀₅),  z₀.₀₅ = −1.6449", f"−({_f(m)} + {_f(s)}·(−1.6449))", _f(-(m - 1.6448536 * s)),
                 "The engine reports the simulated value, which converges to this as paths grow.")]


def student_t_steps(df, loc, scale, p=.01) -> list[dict]:
    q = stats.t.ppf(p, df)
    es = -(loc - scale * (df + q * q) / (df - 1) * stats.t.pdf(q, df) / p) if df > 1 else math.inf
    return [step("Fitted Student-t", "r ~ loc + scale·T_ν (maximum likelihood)", f"ν={_f(df)}, loc={_f(loc)}, scale={_f(scale)}", "",
                 "A smaller ν means fatter tails; ν ≤ 2 means infinite variance."),
            step(f"One-day VaR at {100 * (1 - p):.0f}%", "VaR = −(loc + scale·t_ν⁻¹(p))", f"−({_f(loc)} + {_f(scale)}·{_f(q)})", _f(-(loc + scale * q))),
            step("One-day expected shortfall", "ES = −[loc − scale·(ν + q²)/(ν − 1)·f_ν(q)/p]", f"q = {_f(q)}, f_ν(q) = {_f(stats.t.pdf(q, df))}", _f(es),
                 "On 100 years of real data a fixed-window t underestimates risk (1.99× breaches at 99%) because it mixes calm and volatile regimes.")]


def minimum_variance_steps(covariance, weights) -> list[dict]:
    w = np.asarray(weights); cov = np.asarray(covariance)
    return [step("Objective", "minimise wᵀΣw  subject to Σwᵢ = 1, wᵢ ≥ 0", f"{len(w)} assets, Σ annualised", "",
                 "Long-only, fully invested; solved with SLSQP."),
            step("Portfolio variance", "σ²_p = wᵀΣw", "w = [" + ", ".join(_f(v, 4) for v in w) + "]", _f(float(w @ cov @ w)),
                 "Without the w ≥ 0 bounds the solution would be w = Σ⁻¹1 / (1ᵀΣ⁻¹1)."),
            step("Portfolio volatility", "σ_p = √(wᵀΣw)", f"√{_f(float(w @ cov @ w))}", _f(math.sqrt(max(float(w @ cov @ w), 0))))]


SOURCES = {"black_scholes": "Black & Scholes (1973); Merton (1973) dividend yield; checked against Hull and Haug reference prices.",
           "crr": "Cox, Ross & Rubinstein (1979).", "var": "Lower empirical quantile with exact tail mass; Acerbi & Tasche (2002) on expected shortfall.",
           "student_t": "Maximum-likelihood location-scale Student-t.", "garch": "Glosten, Jagannathan & Runkle (1993); filtered historical simulation (Barone-Adesi et al., 1999).",
           "min_variance": "Markowitz (1952) minimum-variance portfolio."}
