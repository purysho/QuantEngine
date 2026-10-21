"""One JSON request, progress events, one final result. Worker owns database writes."""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
import sys
import time

# Apply before importing NumPy/SciPy, including direct CLI use.
for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[variable] = "1" if os.environ.get("QUANT_LOW_CPU") == "1" else "2"

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import scipy

from quant_core import analyse
from quant_options import market_surface, options_report
from quant_learning import learn
from quant_store import SOURCES, Store


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")), flush=True)


def main():
    store = None
    run_id = None
    try:
        line = sys.stdin.readline(65_537)
        if len(line) > 65_536:
            raise ValueError("Worker request exceeds 64 KB.")
        request = json.loads(line)
        if not isinstance(request, dict) or not isinstance(request.get("root"), str):
            raise ValueError("A JSON command and explicit storage root are required.")
        store = Store(request["root"])
        command = request.get("command")
        if command == "inspect":
            recovered = store.recover() if request.get("recover") else 0
            result = {"datasets": store.datasets(), "runs": store.history(), "stats": store.stats(), "recovered": recovered,
                      "root": str(store.root), "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__}}
        elif command == "import":
            result = {"dataset": store.import_csv(request.get("path", "")), "datasets": store.datasets()}
        elif command == "refresh":
            source = request.get("source", "ecb")
            if source not in SOURCES:
                raise ValueError("Unknown data source.")
            result = {"dataset": store.refresh(source), "datasets": store.datasets()}
        elif command == "ingest":
            result = {"dataset": store.ingest(request.get("path", ""), request.get("dataset_id"), request.get("name", ""),
                                              request.get("metadata", {}), request.get("source_url")),
                      "datasets": store.datasets()}
        elif command == "market-surface":
            # The option chain is staged as a file in sources/ because it exceeds the 64 KB request limit.
            staged = Path(request.get("path", "")).resolve()
            if staged.parent != (store.root / "sources").resolve() or staged.suffix != ".json":
                raise ValueError("Only option chains staged in the engine's sources folder can be read.")
            chain = json.loads(staged.read_text(encoding="utf-8"))
            staged.unlink(missing_ok=True)
            rate = request.get("rate", 0.0)
            if isinstance(rate, bool) or not isinstance(rate, (int, float)):
                raise ValueError("Rate must be a number.")
            result = {"surface": market_surface(chain, float(rate), as_of=str(chain.get("asOf", ""))[:10] or time.strftime("%Y-%m-%d"))}
        elif command == "strategy-lab":
            # Stage 2 evidence on fresh French-library data; raw files are kept with their hashes.
            from quant_store import download
            from quant_data import FRENCH_URL
            from quant_strategies import run_lab
            emit({"type": "progress", "stage": "Downloading 100 years of US market data", "fraction": 0.02})
            contents = [download(FRENCH_URL.format(name=name), 32 * 1024 * 1024)
                        for name in ("F-F_Research_Data_Factors_daily", "12_Industry_Portfolios_daily")]
            raw = [store.save_source(f"french-lab-{i}", c) for i, c in enumerate(contents)]
            lab = run_lab(*contents, progress=lambda stage, fraction: emit({"type": "progress", "stage": stage, "fraction": 0.1 + 0.9 * fraction}))
            lab["data"]["raw"] = raw
            lab["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            folder = store.root / "strategies"
            folder.mkdir(exist_ok=True)
            (folder / "lab.json").write_text(json.dumps(lab, allow_nan=False, default=float), encoding="utf-8")
            result = {"lab": lab}
        elif command == "strategy-signal":
            from quant_core import load_prices
            from quant_strategies import paper_signal
            staged = Path(request.get("path", "")).resolve()
            if staged.parent != (store.root / "sources").resolve() or staged.suffix != ".csv":
                raise ValueError("Only price files staged in the engine's sources folder can be read.")
            dates, symbols, closes = load_prices(staged)
            staged.unlink(missing_ok=True)
            family = request.get("family")
            if family not in ("trend", "sectors"):
                raise ValueError("Unknown strategy family.")
            rf_annual = request.get("rf_annual", 0.0)
            if isinstance(rf_annual, bool) or not isinstance(rf_annual, (int, float)) or not -0.05 <= rf_annual <= 0.25:
                raise ValueError("Risk-free rate must be a number between -5% and 25%.")
            since = request.get("since")
            result = {"signal": paper_signal(family, dates, closes, symbols, float(rf_annual), since if isinstance(since, str) else None)}
        elif command == "history":
            if request.get("recover"):
                store.recover()
            result = {"runs": store.history(), "stats": store.stats()}
        elif command == "report":
            result = store.report(request.get("run_id", ""))
        elif command == "analyse":
            dataset, (dates, assets, prices) = store.load(request.get("dataset_id", "sample"))
            parameters = request.get("parameters", {})
            if not isinstance(parameters, dict):
                raise ValueError("Analysis parameters must be an object.")
            allowed = {"paths", "horizon", "seed", "lookback", "rebalance", "cost_bps", "shrinkage"}
            if set(parameters) - allowed:
                raise ValueError("Unknown analysis parameter.")
            run_id = store.begin_run(dataset, parameters)
            emit({"type": "started", "run_id": run_id, "dataset_id": dataset["id"]})
            started = time.perf_counter()
            last_progress = -1
            def progress(stage, fraction):
                nonlocal last_progress
                bucket = int(fraction * 20)
                if bucket != last_progress or stage != "Simulating Gaussian risk":
                    emit({"type": "progress", "stage": stage, "fraction": fraction})
                    last_progress = bucket
            report = analyse(dates, assets, prices, progress=progress, **parameters)
            report["provenance"] = dataset
            report["runtime"] = {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                                 "blas_threads": int(os.environ["OPENBLAS_NUM_THREADS"]), "platform": platform.system()}
            duration = (time.perf_counter() - started) * 1000
            path = store.finish_run(run_id, report, duration)
            result = {"report": report, "report_path": path, "runs": store.history(), "stats": store.stats()}
        elif command == "learn":
            # Bounded evolutionary learning on the selected snapshot; never alters datasets or reports.
            dataset, (dates, assets, prices) = store.load(request.get("dataset_id", "sample"))
            budget = request.get("budget_seconds", 20)
            if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not 2 <= budget <= 600:
                raise ValueError("Learning budget must be 2-600 seconds.")
            result = {"learning": learn(store.root, dataset, dates, prices, budget_seconds=float(budget),
                                        progress=lambda stage, fraction: emit({"type": "progress", "stage": stage, "fraction": fraction}))}
        elif command == "learning":
            from quant_learning import history
            result = {"learning": history(store.root)}
        elif command == "options":
            # Hypothetical option contracts: never touches price snapshots or research history.
            parameters = request.get("parameters")
            if not isinstance(parameters, dict):
                raise ValueError("Option parameters must be an object.")
            started = time.perf_counter()
            report = options_report(parameters, progress=lambda stage, fraction: emit(
                {"type": "progress", "stage": stage, "fraction": fraction}))
            report["runtime"] = {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                                 "duration_ms": (time.perf_counter() - started) * 1000}
            result = {"report": report}
        else:
            raise ValueError("Unknown worker command.")
        emit({"type": "result", "ok": True, "result": result})
        return 0
    except Exception as exc:
        if store and run_id:
            store.fail_run(run_id, exc)
        emit({"type": "result", "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    sys.exit(main())
