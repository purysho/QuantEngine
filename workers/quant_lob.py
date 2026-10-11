"""Stylised limit-order-book market-making simulator (Avellaneda–Stoikov 2008).

Reduced-form book: market orders that reach depth delta from the mid arrive as a
Poisson process with intensity A exp(-k delta) per side. The mid follows a
binomial arithmetic random walk with volatility sigma. Two modes:

* ``paper``: the original setting (``spread_time_term=False`` matches the spreads
  printed in the paper's tables), with unit orders, at most one fill per side per step,
  no fees, latency, queue or adverse selection. Used to reproduce the paper's table.
* ``realistic``: FIFO queue position at the quoted level (volume must clear the
  queue ahead first), random market-order sizes with partial fills, quote
  latency, tick rounding, maker/taker fees, adverse mid moves after fills, hard
  inventory limits and a costed terminal liquidation.

Synthetic research only; no historical book or venue rules are modelled.
"""
from __future__ import annotations

import math

import numpy as np

STRATEGIES = ("inventory", "symmetric")
DEFAULTS = {"mid": 100.0, "horizon": 1.0, "sigma": 2.0, "dt": .005, "gamma": .1, "k": 1.5, "intensity": 140.0,
            "paths": 1000, "seed": 17, "mode": "paper", "quote_size": 1, "mean_order_size": 1.0,
            "queue_depth": 0.0, "latency_steps": 0, "tick": 0.0, "maker_fee_bps": 0.0, "taker_fee_bps": 0.0,
            "adverse_move": 0.0, "inventory_limit": 0, "spread_time_term": True}


def _validate(p):
    unknown = set(p) - set(DEFAULTS) - {"strategy"}
    if unknown:
        raise ValueError("Unknown market-making parameter: " + ", ".join(sorted(unknown)))
    q = {**DEFAULTS, **p}
    for name, low, high in (("mid", 1e-6, 1e9), ("horizon", 1e-6, 100), ("sigma", 0, 1e6), ("dt", 1e-6, 1),
                            ("gamma", 1e-9, 1e3), ("k", 1e-6, 1e3), ("intensity", 0, 1e6), ("mean_order_size", 1, 1e4),
                            ("queue_depth", 0, 1e6), ("tick", 0, 1e3), ("maker_fee_bps", -100, 100),
                            ("taker_fee_bps", 0, 100), ("adverse_move", 0, 1e3)):
        value = q[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{name} must be a finite number in [{low}, {high}].")
    for name, low, high in (("paths", 1, 100_000), ("seed", 0, 2**32 - 1), ("quote_size", 1, 10_000),
                            ("latency_steps", 0, 1_000), ("inventory_limit", 0, 1_000_000)):
        value = q[name]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{name} must be an integer in [{low}, {high}].")
    steps = q["horizon"] / q["dt"]
    if abs(steps - round(steps)) > 1e-9 or not 1 <= round(steps) <= 100_000:
        raise ValueError("horizon / dt must be a whole number of steps between 1 and 100,000.")
    if q["paths"] * round(steps) > 20_000_000:
        raise ValueError("paths x steps is limited to 20 million.")
    if not isinstance(q["spread_time_term"], bool):
        raise ValueError("spread_time_term must be true or false.")
    if q["mode"] not in ("paper", "realistic"):
        raise ValueError("mode must be 'paper' or 'realistic'.")
    if q["intensity"] * q["dt"] > 1 and q["mode"] == "paper":
        # At most one fill per step is assumed; A dt must stay a probability at zero depth.
        raise ValueError("Paper mode needs intensity x dt <= 1.")
    return q, int(round(steps))


def avellaneda_stoikov_quotes(mid, inventory, time_left, *, gamma, sigma, k):
    """Reservation price and optimal bid/ask distances (approximation in the paper)."""
    reservation = mid - inventory * gamma * sigma ** 2 * time_left
    spread = gamma * sigma ** 2 * time_left + 2 / gamma * math.log(1 + gamma / k)
    return reservation - spread / 2, reservation + spread / 2, spread


def simulate(parameters: dict) -> dict:
    p, steps = _validate(parameters)
    strategy = parameters.get("strategy", "inventory")
    if strategy not in STRATEGIES:
        raise ValueError("strategy must be 'inventory' or 'symmetric'.")
    rng = np.random.default_rng(p["seed"])
    n, dt, sigma, gamma, k, A = p["paths"], p["dt"], p["sigma"], p["gamma"], p["k"], p["intensity"]
    realistic = p["mode"] == "realistic"
    size = p["quote_size"] if realistic else 1
    limit = p["inventory_limit"]
    mid = np.full(n, p["mid"])
    history = [mid.copy()]
    cash = np.zeros(n)
    inventory = np.zeros(n)
    fills = np.zeros(n)
    filled_volume = np.zeros(n)
    fees = np.zeros(n)
    max_abs_inventory = np.zeros(n)
    queue = {side: np.zeros(n) for side in ("bid", "ask")}
    remaining = {side: np.full(n, float(size)) for side in ("bid", "ask")}
    resting = {side: np.full(n, np.nan) for side in ("bid", "ask")}
    spreads = []
    for step in range(steps):
        time_left = p["horizon"] - step * dt
        observed = history[max(0, len(history) - 1 - p["latency_steps"])]  # Stale mid under latency.
        reservation = observed - (inventory * gamma * sigma ** 2 * time_left if strategy == "inventory" else 0.0)
        spread = (gamma * sigma ** 2 * time_left if p["spread_time_term"] else 0.0) + 2 / gamma * math.log(1 + gamma / k)
        spreads.append(spread)
        quotes = {"bid": reservation - spread / 2, "ask": reservation + spread / 2}
        if p["tick"] > 0:
            quotes["bid"] = np.floor(quotes["bid"] / p["tick"] + 1e-9) * p["tick"]
            quotes["ask"] = np.ceil(quotes["ask"] / p["tick"] - 1e-9) * p["tick"]
        # Quotes are set at the start of the step; the mid then moves and orders arrive
        # against the new mid, so fills carry the latest price move (adverse to the quoter).
        mid = mid + np.where(rng.random(n) < .5, 1.0, -1.0) * sigma * math.sqrt(dt)
        for side, sign in (("bid", 1), ("ask", -1)):
            price = quotes[side]
            active = np.ones(n, dtype=bool)
            if limit:
                active = (inventory < limit) if side == "bid" else (inventory > -limit)
            # Depth is measured against the true current mid: stale quotes can sit too close or cross.
            depth = np.maximum(sign * (mid - price), 0.0)
            rate = A * np.exp(-k * depth) * dt
            if not realistic:
                hit = active & (rng.random(n) < rate)
                volume = np.where(hit, 1.0, 0.0)
            else:
                moved = ~np.isclose(price, resting[side], rtol=0, atol=1e-12)
                # A new price joins the back of the queue; an unchanged price keeps FIFO priority.
                queue[side] = np.where(moved, rng.exponential(p["queue_depth"], n) if p["queue_depth"] else 0.0, queue[side])
                remaining[side] = np.where(moved, float(size), remaining[side])
                resting[side] = price
                arrivals = rng.poisson(rate)
                extra = rng.negative_binomial(np.maximum(arrivals, 1), 1 / p["mean_order_size"]) * (arrivals > 0)
                incoming = np.where(arrivals > 0, arrivals + extra, 0).astype(float)
                cleared = np.minimum(incoming, queue[side])
                queue[side] -= cleared
                volume = np.where(active, np.minimum(incoming - cleared, remaining[side]), 0.0)
                if limit:
                    room = (limit - inventory) if side == "bid" else (inventory + limit)
                    volume = np.minimum(volume, np.maximum(room, 0))
                remaining[side] -= volume
                done = remaining[side] <= 0
                remaining[side] = np.where(done, float(size), remaining[side])
                resting[side] = np.where(done, np.nan, resting[side])
            inventory += sign * volume
            cash -= sign * volume * price
            fee = volume * price * p["maker_fee_bps"] / 10_000
            cash -= fee
            fees += fee
            fills += volume > 0
            filled_volume += volume
            if p["adverse_move"]:
                # Informed flow: after we buy, the mid tends to fall, and vice versa.
                mid = mid - sign * p["adverse_move"] * (volume > 0)
        max_abs_inventory = np.maximum(max_abs_inventory, np.abs(inventory))
        history.append(mid.copy())
    # Paper convention marks inventory at the mid; realistic mode crosses half the spread and pays taker fees.
    if realistic:
        half = max(p["tick"], spreads[-1] / 2)
        exit_price = mid - np.sign(inventory) * half
        liquidation_fee = np.abs(inventory) * exit_price * p["taker_fee_bps"] / 10_000
        wealth = cash + inventory * exit_price - liquidation_fee
        fees += liquidation_fee
    else:
        wealth = cash + inventory * mid
    return {"strategy": strategy, "mode": p["mode"], "parameters": {**p, "strategy": strategy}, "steps": steps,
            "profit_mean": float(wealth.mean()), "profit_std": float(wealth.std(ddof=1)) if n > 1 else 0.0,
            "profit_standard_error": float(wealth.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0,
            "final_inventory_mean": float(inventory.mean()), "final_inventory_std": float(inventory.std(ddof=1)) if n > 1 else 0.0,
            "max_abs_inventory_mean": float(max_abs_inventory.mean()), "fills_mean": float(fills.mean()),
            "filled_volume_mean": float(filled_volume.mean()), "fees_mean": float(fees.mean()),
            "initial_spread": spreads[0], "average_spread": float(np.mean(spreads)),
            "profit_percentiles": {str(q): float(v) for q, v in zip((1, 5, 50, 95, 99), np.percentile(wealth, [1, 5, 50, 95, 99]))},
            "assumptions": ["Reduced-form Poisson fills, not a reconstructed historical order book.",
                            "Arithmetic binomial mid; no jumps, intraday seasonality or volatility clustering.",
                            "Realistic mode: exponential queue ahead at each new price, geometric order sizes, quote latency, "
                            "tick rounding, maker fees, adverse post-fill moves, hard inventory limits and a costed exit."]}


def compare(parameters: dict) -> dict:
    """Inventory-aware quotes vs the symmetric benchmark on identical random numbers."""
    rows = {s: simulate({**parameters, "strategy": s}) for s in STRATEGIES}
    return {"inventory": rows["inventory"], "symmetric": rows["symmetric"],
            "inventory_std_ratio": rows["inventory"]["final_inventory_std"] / max(rows["symmetric"]["final_inventory_std"], 1e-12),
            "profit_std_ratio": rows["inventory"]["profit_std"] / max(rows["symmetric"]["profit_std"], 1e-12),
            "no_quote_baseline_profit": 0.0}
