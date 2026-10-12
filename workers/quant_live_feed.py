"""Strict normalization for publicly streamed Coinbase Exchange ticker messages.

Event time is not the receipt time. Ticker messages are batched, so their
sequence numbers do not guarantee every trade was observed.
"""
from __future__ import annotations

import datetime as dt
import math
import re


def parse_ticker(message: dict, *, product: str, received_at: str) -> dict | None:
    if not isinstance(message, dict):
        raise ValueError("Expected JSON object.")
    if message.get("type") != "ticker":
        return None
    if not re.fullmatch(r"[A-Z0-9]{2,12}-[A-Z0-9]{2,12}", product):
        raise ValueError("Invalid expected product.")
    if message.get("product_id") != product:
        raise ValueError("Unexpected product_id.")
    def timestamp(value):
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("Require explicit UTC event and receipt timestamps.")
        try:
            result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid timestamp.") from exc
        if result.tzinfo is None:
            raise ValueError("Timezone required.")
        return result
    event_at, received = timestamp(message.get("time")), timestamp(received_at)
    if received < event_at - dt.timedelta(seconds=5):
        raise ValueError("Event is implausibly after local receipt; check clock.")
    try:
        price = float(message["price"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid ticker price.") from exc
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Ticker price must be finite and positive.")
    seq, trade = message.get("sequence"), message.get("trade_id")
    if type(seq) is not int or seq < 0 or type(trade) is not int or trade < 0:
        raise ValueError("Invalid sequence/trade identifier.")
    return {"source": "coinbase_exchange_ticker", "product_id": product,
            "event_at": message["time"], "received_at": received_at,
            "sequence": seq, "trade_id": trade, "price": price,
            "feed_is_complete": False, "prediction_eligible": True}


def check_next(previous: dict | None, current: dict) -> None:
    """Reject replay/out-of-order ticker events; missing trades are not filled."""
    if previous is None:
        return
    if previous["source"] != current["source"] or previous["product_id"] != current["product_id"]:
        raise ValueError("Different feed identity.")
    if current["trade_id"] <= previous["trade_id"] or current["sequence"] <= previous["sequence"]:
        raise ValueError("Duplicate or out-of-order ticker event.")
    old = dt.datetime.fromisoformat(previous["event_at"].replace("Z", "+00:00"))
    new = dt.datetime.fromisoformat(current["event_at"].replace("Z", "+00:00"))
    if new < old:
        raise ValueError("Event timestamp moved backwards.")


def parse_kraken_ticker(message: dict, *, symbol: str, received_at: str) -> dict | None:
    """Normalize public Kraken Spot WS v2 *trade-triggered* ticker updates.

    Snapshots are observations, not proof of a new trade; an event's 'last'
    may refer to a trade up to 24 hours old. Do not feed snapshots into the
    prospective next-trade-return pilot.
    """
    if not isinstance(message, dict):
        raise ValueError("Expected JSON object.")
    if message.get("channel") != "ticker":
        return None
    if message.get("type") != "update":
        return None
    rows = message.get("data")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Kraken ticker must have exactly one update.")
    row = rows[0]
    if row.get("symbol") != symbol:
        raise ValueError("Unexpected Kraken symbol.")
    def aware(value):
        if not isinstance(value, str) or not value.endswith("Z"):
            raise ValueError("UTC timestamp required.")
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Invalid Kraken timestamp.") from exc
    event, receipt = aware(row.get("timestamp")), aware(received_at)
    if receipt < event - dt.timedelta(seconds=5):
        raise ValueError("Kraken event is after receipt clock.")
    try:
        bid, ask, last = (float(row[key]) for key in ("bid", "ask", "last"))
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Incomplete Kraken ticker prices.") from exc
    if not all(math.isfinite(v) and v > 0 for v in (bid, ask, last)) or bid > ask:
        raise ValueError("Invalid or crossed Kraken market prices.")
    return {"source": "kraken_spot_ticker_v2", "product_id": symbol,
            "event_at": row["timestamp"], "received_at": received_at,
            "price": last, "bid": bid, "ask": ask,
            "feed_is_complete": False, "prediction_eligible": False}
