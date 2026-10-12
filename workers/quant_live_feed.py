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
