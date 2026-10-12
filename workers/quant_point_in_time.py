"""Point-in-time observations for revised macroeconomic data.

Values are usable only AFTER the publication time of their exact vintage.
Never substitute the latest revised observation for an unavailable vintage.
All datetimes must include a timezone and are normalized to UTC.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable


def _aware(raw: str) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("Timestamp must be an ISO-8601 string with timezone.")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO-8601 timestamp.") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("A timezone is required; naive dates are not point-in-time safe.")
    return dt.astimezone(timezone.utc)


def asof_snapshot(rows: Iterable[dict], forecast_at: str) -> dict[str, dict]:
    """Select each series+observation period's newest *available* publication.

    Each input requires: series_id, observation_date, published_at, value and
    optionally vintage_id. forecast_at is the precise forecast creation time.
    Returns keyed by series_id|observation_date.  A missing vintage means
    no observation is available. This never extrapolates/interpolates.
    """
    cutoff = _aware(forecast_at)
    chosen: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each observation must be an object.")
        series, date = row.get("series_id"), row.get("observation_date")
        publication = _aware(row.get("published_at"))
        if not isinstance(series, str) or not series.strip():
            raise ValueError("Missing series_id.")
        if not isinstance(date, str) or len(date) != 10:
            raise ValueError("Require YYYY-MM-DD observation_date.")
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("Invalid observation_date.") from exc
        import math
        value = row.get("value")
        if type(value) not in (float, int) or not math.isfinite(value):
            raise ValueError("PIT observation value must be finite numeric.")
        if publication > cutoff:
            continue
        key = f"{series}|{date}"
        existing = chosen.get(key)
        if existing is None or publication > _aware(existing["published_at"]):
            chosen[key] = dict(row)
        elif publication == _aware(existing["published_at"]) and value != existing["value"]:
            raise ValueError("Conflicting simultaneous vintages.")
    return chosen
