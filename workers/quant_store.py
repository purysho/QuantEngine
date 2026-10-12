"""Immutable source snapshots and durable independent research history."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import urllib.request
import uuid
import xml.etree.ElementTree as ET

import numpy as np

try:
    from .quant_core import example_prices, load_prices, parse_prices, MIN_OBSERVATIONS
except ImportError:
    from quant_core import example_prices, load_prices, parse_prices, MIN_OBSERVATIONS

ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def atomic_write(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def prices_csv(dates, assets, prices):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["date", *assets])
    writer.writerows([date, *[format(float(x), ".17g") for x in row]] for date, row in zip(dates, prices))
    return buffer.getvalue().encode("utf-8")


def parse_ecb(content: bytes, minimum=MIN_OBSERVATIONS):
    try:
        envelope = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError("ECB response is not valid XML.") from exc
    observations = {}
    for element in envelope.iter():
        date = element.attrib.get("time")
        if not date:
            continue
        if date in observations:
            raise ValueError("ECB response contains duplicate dates.")
        rates = {}
        for child in element:
            currency, rate = child.attrib.get("currency"), child.attrib.get("rate")
            if currency and rate:
                if currency in rates:
                    raise ValueError("ECB response contains duplicate currencies.")
                try:
                    rates[currency] = float(rate)
                except ValueError as exc:
                    raise ValueError("ECB response contains a nonnumeric rate.") from exc
        if rates:
            observations[date] = rates
    if not observations:
        raise ValueError("ECB response has no dated reference rates.")
    available = set.intersection(*(set(row) for row in observations.values()))
    preferred = {"USD", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK"}
    currencies = sorted(available & preferred)
    if not currencies:
        raise ValueError("ECB response has no supported currencies with complete observations.")
    dates = sorted(observations)
    assets = [f"{currency} per EUR" for currency in currencies]
    prices = np.asarray([[observations[date][currency] for currency in currencies] for date in dates])
    # Reuse strict date/price validation after reversing ECB's latest-first rows.
    return parse_prices(prices_csv(dates, assets, prices).decode(), minimum=minimum)


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        for name in ["datasets", "reports", "sources"]:
            (self.root / name).mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / "quant.sqlite3", timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS datasets (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
                path TEXT NOT NULL, sha256 TEXT NOT NULL, source_url TEXT,
                retrieved_at TEXT NOT NULL, observation_end TEXT NOT NULL,
                assets_json TEXT NOT NULL, rows INTEGER NOT NULL, metadata_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, started_at TEXT NOT NULL, completed_at TEXT,
                dataset_id TEXT NOT NULL, dataset_hash TEXT NOT NULL, parameters_json TEXT NOT NULL,
                status TEXT NOT NULL, report_path TEXT, summary_json TEXT,
                duration_ms REAL, error TEXT, source_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS runs_by_started ON runs(started_at DESC);
        """)
        self.db.commit()
        if not self.db.execute("SELECT 1 FROM datasets WHERE id='sample'").fetchone():
            dates, assets, prices = example_prices()
            self.add_dataset("sample", "Synthetic example prices", "synthetic", prices_csv(dates, assets, prices),
                             dates, assets, {"generator": "Deterministic synthetic correlated returns with a stress segment",
                                            "generator_seed": 2048, "tradable": False})

    @staticmethod
    def dataset_row(row):
        value = dict(row)
        value["assets"] = json.loads(value.pop("assets_json"))
        value["metadata"] = json.loads(value.pop("metadata_json"))
        # Legacy imports stored absolute paths. Never expose them in dataset APIs.
        original_path = value["metadata"].pop("original_path", None)
        if original_path is not None:
            value["metadata"].setdefault("original_filename", Path(original_path).name)
        return value

    def add_dataset(self, dataset_id, name, kind, content, dates, assets, metadata, source_url=None):
        digest = hashlib.sha256(content).hexdigest()
        path = self.root / "datasets" / f"{dataset_id}-{digest[:16]}.csv"
        if not path.exists():
            atomic_write(path, content)
        self.db.execute("""INSERT INTO datasets VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name, kind=excluded.kind,
            path=excluded.path, sha256=excluded.sha256, source_url=excluded.source_url,
            retrieved_at=excluded.retrieved_at, observation_end=excluded.observation_end,
            assets_json=excluded.assets_json, rows=excluded.rows, metadata_json=excluded.metadata_json""",
            (dataset_id, name[:100], kind, str(path), digest, source_url, now(), dates[-1],
             encode(assets), len(dates), encode(metadata)))
        self.db.commit()
        return self.dataset(dataset_id)

    def dataset(self, dataset_id):
        row = self.db.execute("SELECT * FROM datasets WHERE id=?", (dataset_id,)).fetchone()
        if not row:
            raise ValueError("The selected dataset does not exist. Select an available dataset.")
        return self.dataset_row(row)

    def datasets(self):
        rows = self.db.execute("SELECT * FROM datasets ORDER BY CASE WHEN id='sample' THEN 0 ELSE 1 END, retrieved_at DESC")
        return [self.dataset_row(row) for row in rows]

    def import_csv(self, path):
        source = Path(path).expanduser().resolve()
        if not source.is_file() or source.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("Choose a CSV file smaller than 32 MB.")
        content = source.read_bytes()
        try:
            dates, assets, prices = parse_prices(content.decode("utf-8-sig"))
        except UnicodeDecodeError as exc:
            raise ValueError("CSV must use UTF-8 text encoding.") from exc
        digest = hashlib.sha256(content).hexdigest()
        return self.add_dataset("csv-" + digest[:24], source.stem, "csv", content, dates, assets,
                                {"original_filename": source.name, "raw_sha256": digest,
                                 "adjustment_status": "Provided by importer; dividends/splits not inferred",
                                 "currency": "Provided by importer; no currency conversion"})

    def refresh_ecb(self):
        request = urllib.request.Request(ECB_URL, headers={"User-Agent": "Quant-Engine/0.2 research", "Accept": "application/xml"})
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise ValueError(f"ECB server returned HTTP {response.status}.")
            content = response.read(2 * 1024 * 1024 + 1)
        if len(content) > 2 * 1024 * 1024:
            raise ValueError("ECB response exceeded the expected size.")
        dates, assets, prices = parse_ecb(content)
        digest = hashlib.sha256(content).hexdigest()
        raw_path = self.root / "sources" / f"ecb-{digest}.xml"
        if not raw_path.exists():
            atomic_write(raw_path, content)
        return self.add_dataset("ecb", "ECB foreign-exchange reference rates", "ecb", prices_csv(dates, assets, prices),
                                dates, assets, {"raw_sha256": digest, "raw_path": str(raw_path),
                                               "quote_basis": "Currency units per EUR",
                                               "tradable": False,
                                               "notice": "ECB reference rates are information-only, not executable quotes."}, ECB_URL)

    def load(self, dataset_id):
        dataset = self.dataset(dataset_id)
        path = Path(dataset["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != dataset["sha256"]:
            raise ValueError("The saved price snapshot hash has changed. Import the source again.")
        return dataset, load_prices(path)

    def begin_run(self, dataset, parameters):
        run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
        self.db.execute("INSERT INTO runs(id,started_at,dataset_id,dataset_hash,parameters_json,status,source_json) VALUES(?,?,?,?,?,?,?)",
                        (run_id, now(), dataset["id"], dataset["sha256"], encode(parameters), "running", encode(dataset)))
        self.db.commit()
        return run_id

    def finish_run(self, run_id, report, duration_ms):
        path = self.root / "reports" / f"{run_id}.json"
        report["run"] = {"id": run_id, "completed_at": now(), "duration_ms": duration_ms}
        atomic_write(path, (json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode())
        summary = {"volatility": report["annualized_volatility"], "var95": report["monte_carlo"]["var95"],
                   "sharpe": report["backtest"]["sharpe"], "total_return": report["backtest"]["total_return"],
                   "paths": report["monte_carlo"]["paths"], "seed": report["parameters"]["seed"],
                   "lookback": report["parameters"]["lookback"], "kind": report["provenance"]["kind"]}
        self.db.execute("UPDATE runs SET status='completed',completed_at=?,report_path=?,summary_json=?,duration_ms=? WHERE id=?",
                        (report["run"]["completed_at"], str(path), encode(summary), duration_ms, run_id))
        self.db.commit()
        return str(path)

    def fail_run(self, run_id, error):
        self.db.execute("UPDATE runs SET status='failed',completed_at=?,error=? WHERE id=?", (now(), str(error), run_id))
        self.db.commit()

    def recover(self):
        count = self.db.execute("UPDATE runs SET status='interrupted',completed_at=?,error='Worker stopped before completing the report' WHERE status='running'", (now(),)).rowcount
        self.db.commit()
        # Temporary report/source fragments never represent completed work.
        for folder in ["reports", "datasets", "sources"]:
            for path in (self.root / folder).glob("*.tmp"):
                path.unlink(missing_ok=True)
        return count

    def history(self, limit=200):
        rows = self.db.execute("SELECT * FROM runs ORDER BY started_at DESC, rowid DESC LIMIT ?", (min(int(limit), 500),))
        result = []
        for row in rows:
            value = dict(row)
            value["parameters"] = json.loads(value.pop("parameters_json"))
            value["summary"] = json.loads(value.pop("summary_json") or "null")
            value["source"] = json.loads(value.pop("source_json"))
            result.append(value)
        return result

    def stats(self):
        rows = self.db.execute("SELECT status,COUNT(*) AS count FROM runs GROUP BY status")
        return {row["status"]: row["count"] for row in rows}

    def report(self, run_id):
        row = self.db.execute("SELECT report_path FROM runs WHERE id=? AND status='completed'", (run_id,)).fetchone()
        if not row:
            raise ValueError("Completed report not found.")
        path = Path(row[0])
        if path.parent.resolve() != (self.root / "reports").resolve():
            raise ValueError("Report path is outside this engine's storage.")
        return {"report": json.loads(path.read_text(encoding="utf-8")), "report_path": str(path)}

    def close(self):
        self.db.close()
