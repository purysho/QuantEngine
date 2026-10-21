"""Reliable public historical data with provenance: FRED series and the Kenneth R. French Data Library.

Downloads are cached under a caller-chosen folder with their SHA-256, URL and retrieval
time. Raw data is never committed to the repository: FRED series carry source-specific
terms, and the French library asks for attribution. Parsers are strict: unknown layouts,
duplicate or unsorted dates, and missing-value sentinels are reported, never filled silently.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import http.client
import time
import io
import json
import math
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={ids}"
FRENCH_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{name}_CSV.zip"
USER_AGENT = "QuantEngine/0.3 (+https://github.com/purysho/QuantEngine)"  # FRED stalls some UA strings; an identifying URL is served.


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def fetch(url: str, cache: str | Path, name: str, *, offline: bool = False, max_bytes: int = 64 * 1024 * 1024) -> tuple[bytes, dict]:
    """Return cached bytes for ``name`` or download them once; provenance is stored alongside."""
    folder = Path(cache)
    folder.mkdir(parents=True, exist_ok=True)
    meta_path = folder / f"{name}.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        data = (folder / meta["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise ValueError(f"Cached {name} no longer matches its recorded SHA-256; delete it to re-download.")
        return data, meta
    if offline:
        raise FileNotFoundError(f"{name} is not cached and offline mode is on.")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):  # Public endpoints occasionally drop connections; retry with backoff.
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read(max_bytes + 1)
            break
        except (OSError, http.client.HTTPException) as exc:
            if attempt == 2:
                raise ConnectionError(f"Could not download {name} from {url}: {exc}") from exc
            time.sleep(2 * 2 ** attempt)
    if len(data) > max_bytes:
        raise ValueError(f"{name} exceeded {max_bytes} bytes.")
    digest = hashlib.sha256(data).hexdigest()
    file = f"{name}-{digest[:16]}{Path(url.split('?')[0]).suffix or '.csv'}"
    (folder / file).write_bytes(data)
    meta = {"name": name, "url": url, "sha256": digest, "bytes": len(data), "retrieved_at": _now(), "file": file}
    meta_path.write_text(json.dumps(meta, indent=2))
    return data, meta


def parse_fred(content: bytes | str) -> dict:
    """FRED graph CSV: observation_date (or DATE) then one column per series; blanks or '.' are missing."""
    text = content.decode("utf-8-sig") if isinstance(content, bytes) else content
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or rows[0][0].strip().lower() not in ("observation_date", "date") or len(rows[0]) < 2:
        raise ValueError("Not a FRED graph CSV.")
    names = [c.strip() for c in rows[0][1:]]
    dates, values = [], []
    for row in rows[1:]:
        if not row:
            continue
        date = dt.date.fromisoformat(row[0].strip())
        if dates and date <= dates[-1]:
            raise ValueError("FRED dates must be strictly increasing.")
        dates.append(date)
        values.append([float(v) if v.strip() not in ("", ".") else math.nan for v in row[1:]])
    array = np.asarray(values, dtype=np.float64)
    return {"dates": dates, "series": {name: array[:, i] for i, name in enumerate(names)}}


def parse_french(content: bytes, section: str | None = None) -> dict:
    """Kenneth French daily CSV (zipped). Values are percent; returns are converted to decimals.

    ``section`` selects a titled block such as "Average Value Weighted Returns -- Daily";
    by default the first data block is used. -99.99 / -999 become NaN.
    """
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError("Expected exactly one CSV inside the French library archive.")
        text = archive.read(names[0]).decode("latin-1")
    lines = text.splitlines()
    start = 0
    if section:
        matches = [i for i, line in enumerate(lines) if line.strip().lower() == section.lower()]
        if not matches:
            raise ValueError(f"Section not found: {section}")
        start = matches[0] + 1
    header_index = next(i for i in range(start, len(lines)) if lines[i].startswith(","))
    header = [c.strip() for c in lines[header_index].split(",")[1:]]
    dates, values = [], []
    for line in lines[header_index + 1:]:
        cells = [c.strip() for c in line.split(",")]
        if len(cells) != len(header) + 1 or not cells[0].isdigit() or len(cells[0]) != 8:
            break  # End of this block (blank line, next title, or copyright).
        date = dt.date(int(cells[0][:4]), int(cells[0][4:6]), int(cells[0][6:]))
        if dates and date <= dates[-1]:
            raise ValueError("French library dates must be strictly increasing.")
        row = [float(c) for c in cells[1:]]
        values.append([math.nan if v in (-99.99, -999.0) else v / 100 for v in row])
        dates.append(date)
    if len(dates) < 2:
        raise ValueError("No daily rows found in the French library file.")
    array = np.asarray(values, dtype=np.float64)
    return {"dates": dates, "series": {name: array[:, i] for i, name in enumerate(header)}, "units": "decimal daily returns"}


def fred(ids: list[str], cache: str | Path, *, offline: bool = False) -> tuple[dict, dict]:
    name = "fred-" + "-".join(ids)
    data, meta = fetch(FRED_URL.format(ids=",".join(ids)), cache, name, offline=offline)
    return parse_fred(data), meta


def french(name: str, cache: str | Path, *, section: str | None = None, offline: bool = False) -> tuple[dict, dict]:
    data, meta = fetch(FRENCH_URL.format(name=name), cache, "french-" + name, offline=offline)
    return parse_french(data, section), meta


def us_market_returns(cache: str | Path, *, offline: bool = False) -> tuple[list, np.ndarray, dict]:
    """Daily total US equity market return (CRSP value-weighted) = Mkt-RF + RF, from 1926."""
    table, meta = french("F-F_Research_Data_Factors_daily", cache, offline=offline)
    market = table["series"]["Mkt-RF"] + table["series"]["RF"]
    keep = np.isfinite(market)
    return [d for d, k in zip(table["dates"], keep) if k], market[keep], meta


def align(dates_a, values_a, dates_b, values_b):
    """Inner-join two dated series on common dates, dropping NaNs."""
    index_b = {d: i for i, d in enumerate(dates_b)}
    pairs = [(d, values_a[i], values_b[index_b[d]]) for i, d in enumerate(dates_a)
             if d in index_b and math.isfinite(values_a[i]) and math.isfinite(values_b[index_b[d]])]
    return [p[0] for p in pairs], np.array([p[1] for p in pairs]), np.array([p[2] for p in pairs])
