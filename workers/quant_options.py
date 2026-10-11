"""European/American option mathematics for hypothetical contracts.

Inputs are manual research values: no live option chain, quote feed or calibrated
market surface is implied. Rates and dividend yields are continuously compounded
annual decimals; time is in years; volatility is an annual decimal.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
from scipy import stats
from scipy.optimize import brentq, least_squares

TRADING_DAYS = 252
MAX_STEPS = 5_000
MAX_PATHS = 2_000_000
KINDS = ("call", "put")


def _finite(name, value, low, high, *, low_open=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number.")
    if value < low or value > high or (low_open and value == low):
        bound = "(" if low_open else "["
        raise ValueError(f"{name} must be in {bound}{low}, {high}].")
    return float(value)


def _contract(spot, strike, time, rate, volatility, dividend, kind):
    spot = _finite("Spot", spot, 0, 1e9, low_open=True)
    strike = _finite("Strike", strike, 0, 1e9, low_open=True)
    time = _finite("Time to expiry", time, 0, 50)
    rate = _finite("Rate", rate, -.2, 1)
    volatility = _finite("Volatility", volatility, 0, 5)
    dividend = _finite("Dividend yield", dividend, -.2, 1)
    if kind not in KINDS:
        raise ValueError("Option kind must be 'call' or 'put'.")
    return spot, strike, time, rate, volatility, dividend, kind


def _bounds(spot, strike, time, rate, dividend, kind):
    """No-arbitrage price bounds for a European option."""
    forward_spot = spot * math.exp(-dividend * time)
    discounted_strike = strike * math.exp(-rate * time)
    if kind == "call":
        return max(forward_spot - discounted_strike, 0.0), forward_spot
    return max(discounted_strike - forward_spot, 0.0), discounted_strike


def black_scholes(spot, strike, time, rate, volatility, dividend=0.0, kind="call") -> dict:
    """Black–Scholes–Merton price and Greeks with a continuous dividend yield.

    Units: delta per 1 unit of spot, gamma per unit spot squared, vega and volga
    per 1.00 volatility (``vega_per_point`` per 1 volatility point), theta per
    year and per calendar day, rho per 1.00 rate (``rho_per_point`` per 1%).
    """
    spot, strike, time, rate, volatility, dividend, kind = _contract(spot, strike, time, rate, volatility, dividend, kind)
    sign = 1 if kind == "call" else -1
    dq, dr = math.exp(-dividend * time), math.exp(-rate * time)
    root = volatility * math.sqrt(time)
    if root < 1e-12:
        # Expiry or zero volatility: the payoff on the deterministic forward is discounted.
        forward = spot * math.exp((rate - dividend) * time)
        intrinsic = max(sign * (forward - strike), 0.0)
        in_money = sign * (forward - strike) > 0
        price = dr * intrinsic
        delta = sign * dq if in_money else 0.0
        # In the money: price = sign (S e^{-qT} - K e^{-rT}); theta = -dV/dT.
        theta = sign * (dividend * spot * dq - rate * strike * dr) if in_money and time > 0 else 0.0
        return {"kind": kind, "price": price, "delta": delta, "gamma": 0.0, "vega": 0.0,
                "vega_per_point": 0.0, "theta_per_year": theta, "theta_per_day": theta / 365,
                "rho": sign * strike * time * dr if in_money else 0.0,
                "rho_per_point": (sign * strike * time * dr if in_money else 0.0) / 100,
                "vanna": 0.0, "volga": 0.0, "d1": None, "d2": None,
                "degenerate": "expired" if time == 0 else "zero volatility"}
    d1 = (math.log(spot / strike) + (rate - dividend + .5 * volatility ** 2) * time) / root
    d2 = d1 - root
    n1 = stats.norm.pdf(d1)
    cdf = stats.norm.cdf
    price = sign * (spot * dq * cdf(sign * d1) - strike * dr * cdf(sign * d2))
    delta = sign * dq * cdf(sign * d1)
    gamma = dq * n1 / (spot * root)
    vega = spot * dq * n1 * math.sqrt(time)
    theta = (-spot * dq * n1 * volatility / (2 * math.sqrt(time))
             - sign * rate * strike * dr * cdf(sign * d2)
             + sign * dividend * spot * dq * cdf(sign * d1))
    rho = sign * strike * time * dr * cdf(sign * d2)
    vanna = -dq * n1 * d2 / volatility
    volga = vega * d1 * d2 / volatility
    return {"kind": kind, "price": float(price), "delta": float(delta), "gamma": float(gamma),
            "vega": float(vega), "vega_per_point": float(vega / 100),
            "theta_per_year": float(theta), "theta_per_day": float(theta / 365),
            "rho": float(rho), "rho_per_point": float(rho / 100),
            "vanna": float(vanna), "volga": float(volga), "d1": float(d1), "d2": float(d2),
            "degenerate": None}


def crr_price(spot, strike, time, rate, volatility, dividend=0.0, kind="call", *, steps=500, american=False) -> float:
    """Cox–Ross–Rubinstein binomial tree; American exercise is checked at every node."""
    spot, strike, time, rate, volatility, dividend, kind = _contract(spot, strike, time, rate, volatility, dividend, kind)
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= MAX_STEPS:
        raise ValueError(f"Tree steps must be an integer between 1 and {MAX_STEPS:,}.")
    sign = 1 if kind == "call" else -1
    if time == 0 or volatility == 0:
        european = black_scholes(spot, strike, time, rate, volatility, dividend, kind)["price"]
        return max(european, max(sign * (spot - strike), 0.0)) if american else european
    dt = time / steps
    up = math.exp(volatility * math.sqrt(dt))
    down = 1 / up
    growth = math.exp((rate - dividend) * dt)
    probability = (growth - down) / (up - down)
    if not 0 < probability < 1:
        raise ValueError("Tree risk-neutral probability is outside (0, 1); increase steps or reduce rate/dividend.")
    discount = math.exp(-rate * dt)
    j = np.arange(steps + 1)
    prices = spot * up ** (steps - 2 * j)  # Index j counts down-moves.
    values = np.maximum(sign * (prices - strike), 0.0)
    for level in range(steps - 1, -1, -1):
        values = discount * (probability * values[:-1] + (1 - probability) * values[1:])
        if american:
            prices = prices[:-1] * down
            values = np.maximum(values, sign * (prices - strike))
    return float(values[0])


def monte_carlo_price(spot, strike, time, rate, volatility, dividend=0.0, kind="call", *,
                      paths=50_000, seed=17, progress: Callable[[str, float], None] | None = None) -> dict:
    """Risk-neutral terminal lognormal sampling with antithetic pairs and sampling error."""
    spot, strike, time, rate, volatility, dividend, kind = _contract(spot, strike, time, rate, volatility, dividend, kind)
    if isinstance(paths, bool) or not isinstance(paths, int) or not 1_000 <= paths <= MAX_PATHS or paths % 2:
        raise ValueError(f"Monte Carlo paths must be an even integer between 1,000 and {MAX_PATHS:,}.")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must be an integer between 0 and 4,294,967,295.")
    sign = 1 if kind == "call" else -1
    rng = np.random.default_rng(seed)
    pairs = paths // 2
    drift = (rate - dividend - .5 * volatility ** 2) * time
    diffusion = volatility * math.sqrt(time)
    discount = math.exp(-rate * time)
    total = total_sq = 0.0
    batch = 262_144
    for start in range(0, pairs, batch):
        count = min(batch, pairs - start)
        z = rng.standard_normal(count)
        up = spot * np.exp(drift + diffusion * z)
        dn = spot * np.exp(drift - diffusion * z)
        # Average each antithetic pair first: pairs are independent, paths within a pair are not.
        pair = .5 * discount * (np.maximum(sign * (up - strike), 0) + np.maximum(sign * (dn - strike), 0))
        total += float(pair.sum())
        total_sq += float((pair * pair).sum())
        if progress:
            progress("Sampling risk-neutral terminal prices", (start + count) / pairs)
    mean = total / pairs
    variance = max(total_sq / pairs - mean * mean, 0.0) * pairs / max(pairs - 1, 1)
    error = math.sqrt(variance / pairs)
    return {"price": mean, "standard_error": error, "confidence_95": [mean - 1.96 * error, mean + 1.96 * error],
            "paths": paths, "independent_pairs": pairs, "seed": seed,
            "method": "Risk-neutral terminal GBM sampling with antithetic pairs; error from independent pair means."}


def implied_volatility(price, spot, strike, time, rate, dividend=0.0, kind="call") -> float:
    """Black–Scholes implied volatility by bracketed root finding; impossible quotes are rejected."""
    price = _finite("Option price", price, 0, 1e9)
    spot, strike, time, rate, _, dividend, kind = _contract(spot, strike, time, rate, .2, dividend, kind)
    if time <= 0:
        raise ValueError("Implied volatility is undefined at expiry.")
    low, high = _bounds(spot, strike, time, rate, dividend, kind)
    tolerance = 1e-10 * max(1.0, spot, strike)
    if price <= low + tolerance:
        raise ValueError(f"Quote {price:.6g} is at or below the no-arbitrage lower bound {low:.6g}; implied volatility is zero or undefined.")
    if price >= high - tolerance:
        raise ValueError(f"Quote {price:.6g} is at or above the no-arbitrage upper bound {high:.6g}.")
    objective = lambda sigma: black_scholes(spot, strike, time, rate, sigma, dividend, kind)["price"] - price
    upper = 5.0
    if objective(upper) < 0:
        raise ValueError("Quote implies volatility above 500%; check the contract inputs.")
    return float(brentq(objective, 1e-9, upper, xtol=1e-12, rtol=1e-12, maxiter=200))


def implied_move(volatility, days=1, *, trading_days=TRADING_DAYS) -> dict:
    """One-standard-deviation move implied by an annual volatility (e.g. VIX / 100).

    The trader's rule "VIX / 16" uses sqrt(256) = 16 as a round stand-in for
    sqrt(252) ~= 15.87. It is a one-sigma lognormal-return approximation, not an
    expected absolute move: under normality E|X| = sqrt(2/pi) sigma ~= 0.80 sigma.
    """
    volatility = _finite("Volatility", volatility, 0, 5)
    if isinstance(days, bool) or not isinstance(days, (int, float)) or not 0 < days <= 3650:
        raise ValueError("Days must be in (0, 3650].")
    sigma = volatility * math.sqrt(days / trading_days)
    return {"one_sigma": sigma, "rule_of_16": volatility * math.sqrt(days) / 16,
            "expected_absolute_move": sigma * math.sqrt(2 / math.pi),
            "probability_within_one_sigma": float(stats.norm.cdf(1) - stats.norm.cdf(-1)),
            "days": days, "trading_days": trading_days}


# --- Volatility surface -----------------------------------------------------

def svi_total_variance(params, k):
    """Raw SVI (Gatheral 2004): w(k) = a + b (rho (k - m) + sqrt((k - m)^2 + sigma^2))."""
    a, b, rho, m, sigma = params
    k = np.asarray(k, dtype=np.float64)
    return a + b * (rho * (k - m) + np.sqrt((k - m) ** 2 + sigma ** 2))


def fit_svi(log_moneyness, total_variance) -> dict:
    """Least-squares raw SVI fit with b >= 0, |rho| < 1, sigma > 0 and a nonnegative minimum."""
    k = np.asarray(log_moneyness, dtype=np.float64)
    w = np.asarray(total_variance, dtype=np.float64)
    if k.shape != w.shape or k.ndim != 1 or len(k) < 5 or not (np.isfinite(k).all() and np.isfinite(w).all()) or (w <= 0).any():
        raise ValueError("SVI needs at least five finite quotes with positive total variance.")
    def residual(x):
        a, b, rho, m, sigma = x
        # Soft penalty keeps the minimum total variance a + b sigma sqrt(1 - rho^2) nonnegative.
        floor = a + b * sigma * math.sqrt(max(1 - rho * rho, 0))
        return np.r_[svi_total_variance(x, k) - w, 10 * min(floor, 0.0)]
    span = max(float(k.max() - k.min()), .1)
    start = [float(w.min()) * .5, .1, 0.0, float(k[np.argmin(w)]), .1]
    lower = [-float(w.max()), 0.0, -.999, float(k.min()) - span, 1e-4]
    upper = [float(w.max()) * 2, 10.0, .999, float(k.max()) + span, 5.0]
    result = least_squares(residual, start, bounds=(lower, upper), xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=5000)
    fitted = svi_total_variance(result.x, k)
    a, b, rho, m, sigma = (float(v) for v in result.x)
    return {"a": a, "b": b, "rho": rho, "m": m, "sigma": sigma,
            "rmse_total_variance": float(np.sqrt(np.mean((fitted - w) ** 2))),
            "minimum_total_variance": a + b * sigma * math.sqrt(1 - rho * rho),
            "roger_lee_wing_ok": bool(b * (1 + abs(rho)) <= 2), "converged": bool(result.success)}


def volatility_surface(quotes, spot, rate, dividend=0.0) -> dict:
    """Implied volatilities, per-expiry raw SVI slices and static-arbitrage checks.

    ``quotes`` holds dictionaries with strike, expiry (years), price and kind.
    Checks: call prices nonincreasing and convex in strike (butterfly), and total
    implied variance nondecreasing in expiry at equal forward log-moneyness (calendar).
    """
    spot = _finite("Spot", spot, 0, 1e9, low_open=True)
    rate = _finite("Rate", rate, -.2, 1)
    dividend = _finite("Dividend yield", dividend, -.2, 1)
    if not isinstance(quotes, list) or not 3 <= len(quotes) <= 2_000:
        raise ValueError("A surface needs 3–2,000 quotes.")
    points, rejected = [], []
    for i, quote in enumerate(quotes):
        try:
            if not isinstance(quote, dict):
                raise ValueError("Quote must be an object.")
            strike, expiry, price, kind = quote.get("strike"), quote.get("expiry"), quote.get("price"), quote.get("kind", "call")
            sigma = implied_volatility(price, spot, strike, expiry, rate, dividend, kind)
            forward = spot * math.exp((rate - dividend) * expiry)
            # Express every quote as a call through put–call parity for the strike checks.
            call = price if kind == "call" else price + spot * math.exp(-dividend * expiry) - strike * math.exp(-rate * expiry)
            points.append({"index": i, "strike": float(strike), "expiry": float(expiry), "kind": kind,
                           "price": float(price), "call_equivalent": float(call), "implied_volatility": sigma,
                           "log_moneyness": math.log(strike / forward), "total_variance": sigma * sigma * expiry})
        except (ValueError, TypeError) as exc:
            rejected.append({"index": i, "reason": str(exc)})
    expiries = sorted({p["expiry"] for p in points})
    slices, violations = [], []
    for expiry in expiries:
        row = sorted((p for p in points if p["expiry"] == expiry), key=lambda p: p["strike"])
        strikes = np.array([p["strike"] for p in row])
        calls = np.array([p["call_equivalent"] for p in row])
        tolerance = 1e-8 * spot
        for j in range(1, len(row)):
            if strikes[j] == strikes[j - 1]:
                continue
            if calls[j] > calls[j - 1] + tolerance:
                violations.append({"type": "vertical", "expiry": expiry, "strikes": [float(strikes[j - 1]), float(strikes[j])]})
        for j in range(1, len(row) - 1):
            k0, k1, k2 = strikes[j - 1:j + 2]
            if k0 == k1 or k1 == k2:
                continue
            weight = (k2 - k1) / (k2 - k0)
            if calls[j] > weight * calls[j - 1] + (1 - weight) * calls[j + 1] + tolerance:
                violations.append({"type": "butterfly", "expiry": expiry, "strikes": [float(k0), float(k1), float(k2)]})
        fit = None
        if len(row) >= 5:
            try:
                fit = fit_svi([p["log_moneyness"] for p in row], [p["total_variance"] for p in row])
            except ValueError:
                fit = None
        slices.append({"expiry": expiry, "quotes": len(row), "svi": fit,
                       "atm_implied_volatility": float(np.interp(0.0, [p["log_moneyness"] for p in row],
                                                                 [p["implied_volatility"] for p in row]))})
    for earlier, later in zip(expiries, expiries[1:]):
        a = sorted((p for p in points if p["expiry"] == earlier), key=lambda p: p["log_moneyness"])
        b = sorted((p for p in points if p["expiry"] == later), key=lambda p: p["log_moneyness"])
        lo = max(a[0]["log_moneyness"], b[0]["log_moneyness"])
        hi = min(a[-1]["log_moneyness"], b[-1]["log_moneyness"])
        if lo > hi:
            continue
        grid = np.linspace(lo, hi, 11)
        wa = np.interp(grid, [p["log_moneyness"] for p in a], [p["total_variance"] for p in a])
        wb = np.interp(grid, [p["log_moneyness"] for p in b], [p["total_variance"] for p in b])
        bad = grid[wb < wa - 1e-10]
        if len(bad):
            violations.append({"type": "calendar", "expiries": [earlier, later],
                               "log_moneyness": [float(bad.min()), float(bad.max())]})
    return {"spot": spot, "rate": rate, "dividend": dividend, "points": points, "rejected": rejected,
            "slices": slices, "arbitrage_violations": violations,
            "arbitrage_free": not violations,
            "assumptions": ["European quotes; American quotes contain early-exercise value and bias implied volatility upward.",
                            "Flat continuous rate and dividend yield; forward = spot * exp((r - q) T).",
                            "Calendar checks interpolate total variance linearly in forward log-moneyness on overlapping ranges.",
                            "Raw SVI slices are fitted independently; slice fits are not jointly arbitrage-free by construction."]}


def ssvi_surface(atm_volatility, *, rho=-.4, eta=1.0, gamma=.5, expiries=None, log_moneyness=None) -> dict:
    """Model implied-volatility surface from SSVI (Gatheral & Jacquier 2014).

    w(k, T) = theta/2 * (1 + rho phi k + sqrt((phi k + rho)^2 + 1 - rho^2)), with
    ATM total variance theta = sigma_atm^2 T and power-law phi = eta / (theta^gamma (1 + theta)^(1 - gamma)).
    Sufficient no-arbitrage conditions: 0 < gamma <= 1/2 and eta (1 + |rho|) <= 2.
    It is a parametric model surface, not a fit to market quotes.
    """
    sigma = _finite("ATM volatility", atm_volatility, 0, 5, low_open=True)
    rho = _finite("Surface skew rho", rho, -.99, .99)
    eta = _finite("Surface curvature eta", eta, 0, 4, low_open=True)
    gamma = _finite("Surface gamma", gamma, 0, 1, low_open=True)
    T = np.asarray(expiries if expiries is not None else np.linspace(.1, 2, 24), dtype=np.float64)
    k = np.asarray(log_moneyness if log_moneyness is not None else np.linspace(-.5, .5, 41), dtype=np.float64)
    if T.ndim != 1 or k.ndim != 1 or len(T) < 2 or len(k) < 3 or (T <= 0).any() or not np.isfinite(k).all():
        raise ValueError("Surface needs positive expiries and finite log-moneyness grids.")
    theta = sigma * sigma * T
    phi = eta / (theta ** gamma * (1 + theta) ** (1 - gamma))
    pk = phi[:, None] * k[None, :]
    w = theta[:, None] / 2 * (1 + rho * pk + np.sqrt((pk + rho) ** 2 + 1 - rho * rho))
    iv = np.sqrt(w / T[:, None])
    return {"model": "SSVI power-law", "parameters": {"atm_volatility": sigma, "rho": rho, "eta": eta, "gamma": gamma},
            "expiries": T.tolist(), "log_moneyness": k.tolist(), "implied_volatility": iv.tolist(),
            "sufficient_no_arbitrage": bool(gamma <= .5 and eta * (1 + abs(rho)) <= 2),
            "note": "Model surface from the contract's volatility and the chosen skew/curvature; not market quotes."}


# --- Desktop report ---------------------------------------------------------

OPTION_PARAMETERS = {"spot", "strike", "time", "rate", "volatility", "dividend", "kind",
                     "steps", "paths", "seed", "market_price", "surface_rho", "surface_eta"}


def options_report(parameters: dict, progress: Callable[[str, float], None] | None = None) -> dict:
    if not isinstance(parameters, dict):
        raise ValueError("Option parameters must be an object.")
    unknown = set(parameters) - OPTION_PARAMETERS
    if unknown:
        raise ValueError("Unknown option parameter: " + ", ".join(sorted(unknown)))
    p = {"dividend": 0.0, "kind": "call", "steps": 500, "paths": 100_000, "seed": 17,
         "surface_rho": -.4, "surface_eta": 1.0, **parameters}
    missing = [name for name in ("spot", "strike", "time", "rate", "volatility") if name not in p]
    if missing:
        raise ValueError("Missing option parameter: " + ", ".join(missing))
    contract = (p["spot"], p["strike"], p["time"], p["rate"], p["volatility"], p["dividend"])
    kind = p["kind"]
    other = "put" if kind == "call" else "call"
    if progress:
        progress("Pricing Black–Scholes and Greeks", 0.0)
    analytic = black_scholes(*contract, kind)
    counterpart = black_scholes(*contract, other)
    spot, strike, time, rate, _, dividend = (float(v) for v in contract)
    call, put = (analytic, counterpart) if kind == "call" else (counterpart, analytic)
    parity_gap = call["price"] - put["price"] - (spot * math.exp(-dividend * time) - strike * math.exp(-rate * time))
    if progress:
        progress("Building binomial trees", .2)
    european_tree = crr_price(*contract, kind, steps=p["steps"])
    american_tree = crr_price(*contract, kind, steps=p["steps"], american=True)
    monte_carlo = monte_carlo_price(*contract, kind, paths=p["paths"], seed=p["seed"],
                                    progress=(lambda stage, f: progress(stage, .3 + .65 * f)) if progress else None)
    implied = None
    if p.get("market_price") is not None:
        implied = {"market_price": float(p["market_price"]),
                   "implied_volatility": implied_volatility(p["market_price"], spot, strike, time, rate, dividend, kind)}
    move = implied_move(p["volatility"], 1)
    surface = ssvi_surface(p["volatility"], rho=p["surface_rho"], eta=p["surface_eta"]) if p["volatility"] > 0 else None
    horizon_days = max(time * TRADING_DAYS, 1e-9)
    report = {
        "kind": "options", "engine_version": "0.2.0",
        "parameters": {**p, "spot": spot, "strike": strike, "time": time, "rate": rate, "dividend": dividend},
        "black_scholes": analytic, "counterpart": counterpart,
        "put_call_parity_gap": parity_gap,
        "trees": {"steps": p["steps"], "european": european_tree, "american": american_tree,
                  "early_exercise_premium": american_tree - european_tree,
                  "european_tree_error": european_tree - analytic["price"]},
        "monte_carlo": {**monte_carlo, "error_vs_analytic": monte_carlo["price"] - analytic["price"],
                        "within_three_standard_errors": abs(monte_carlo["price"] - analytic["price"]) <= 3 * monte_carlo["standard_error"] + 1e-12},
        "implied": implied,
        "surface": surface,
        "implied_moves": {"daily": move, "to_expiry": implied_move(p["volatility"], min(horizon_days, 3650)) if time > 0 else None},
        "units": {"time": "years", "rate": "continuously compounded annual decimal",
                  "volatility": "annual decimal", "vega": "price per 1.00 volatility", "vega_per_point": "price per 1 volatility point",
                  "theta_per_day": "price per calendar day (theta per year / 365)", "rho_per_point": "price per 1% rate"},
        "assumptions": ["Hypothetical contract entered manually; not a live quote or a calibrated surface.",
                        "Geometric Brownian motion with constant rate, dividend yield and volatility.",
                        "European analytic prices; CRR trees value early exercise for the American comparison.",
                        "No transaction costs, discrete dividends, borrow fees or early-exercise frictions."],
    }
    if progress:
        progress("Option calculation complete", 1.0)
    return report
