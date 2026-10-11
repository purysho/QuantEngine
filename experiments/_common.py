"""Shared provenance for offline experiments. Results are measured, never edited by hand."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import sys
from pathlib import Path

import os

# Same thread policy as the desktop worker: oversubscribed BLAS threads made the
# VaR experiment spend 17 CPU-minutes for 7 wall-minutes.
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(variable, "1")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import scipy

RESULTS = ROOT / "experiments" / "results"


def array_hash(*arrays) -> str:
    digest = hashlib.sha256()
    for array in arrays:
        value = np.ascontiguousarray(np.asarray(array, dtype=np.float64))
        digest.update(str(value.shape).encode())
        digest.update(value.tobytes())
    return digest.hexdigest()


def write(name: str, payload: dict, started: float, finished: float) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    payload = {"experiment": name,
               "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "duration_seconds": round(finished - started, 3),
               "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                           "scipy": scipy.__version__, "platform": platform.platform()},
               **payload}
    path = RESULTS / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return path
