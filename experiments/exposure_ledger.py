"""Append-only disclosure ledger for research blocks.

This is a local safety control, NOT an independent BlackBox judge: a researcher
who controls this file can delete it. A final holdout needs a separate custodian.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


class AlreadyExposedError(ValueError):
    pass


def fingerprint(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ExposureLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def exposed(self, dataset_sha256: str, start: int, end: int) -> bool:
        if not self.path.exists():
            return False
        with self.path.open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record["dataset_sha256"] == dataset_sha256 and max(start, record["start"]) < min(end, record["end"]):
                    return True
        return False

    def reveal(self, dataset_sha256: str, start: int, end: int, *, prediction_sha256: str) -> dict:
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end):
            raise ValueError("Require nonempty [start, end) integer block.")
        if len(dataset_sha256) != 64 or len(prediction_sha256) != 64:
            raise ValueError("Require SHA-256 fingerprints.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic exclusive sidecar works on Windows and POSIX. Never auto-break a
        # stale lock: a crash requires custodian inspection, not an unsafe retry.
        lock = Path(str(self.path) + ".lock")
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ValueError("Exposure ledger is locked/busy; inspect a stale lock before retry.") from exc
        try:
            os.close(fd)
            with self.path.open("a+", encoding="utf-8") as target:
                target.seek(0)
                for line in target:
                    if line.strip():
                        old = json.loads(line)
                        if old["dataset_sha256"] == dataset_sha256 and max(start, old["start"]) < min(end, old["end"]):
                            raise AlreadyExposedError("Block overlaps previously disclosed observations.")
                record = {"dataset_sha256": dataset_sha256, "start": start, "end": end,
                          "prediction_sha256": prediction_sha256}
                target.seek(0, os.SEEK_END)
                target.write(json.dumps(record, sort_keys=True) + "\n")
                target.flush()
                os.fsync(target.fileno())
                return record
        finally:
            lock.unlink()
