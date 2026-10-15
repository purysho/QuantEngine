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
from quant_options import options_report
from quant_learning import learn
from quant_store import Store
from quant_paper import PaperLedger


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
            paper=PaperLedger(store.root)
            try:
                try:result["paper"]=paper.summary()
                except Exception as exc:result["paper_error"]=str(exc)
            finally:paper.close()
        elif command == "paper":
            values=request.get("paper")
            if not isinstance(values,dict):raise ValueError("Paper operation required.")
            operation=values.get("operation");cid=values.get("id")
            paper=PaperLedger(store.root)
            try:
                allowed={"create":{"operation","mode","source","assumptions"},"ingest":{"operation","id","quote"},"control":{"operation","id","halted"},"summary":{"operation","id"},"export":{"operation","id"}}
                if operation not in allowed or set(values)-allowed[operation]:raise ValueError("Unknown paper operation/input.")
                if operation=="create":value=paper.create(mode=values.get("mode"),source=values.get("source"),assumptions=values.get("assumptions"))
                elif operation=="ingest":value=paper.ingest(cid,values.get("quote"))
                elif operation=="control":value=paper.control(cid,values.get("halted"))
                elif operation=="export":value=paper.export(cid)
                else:value=paper.summary(cid)
                result={"export" if operation=="export" else "paper":value}
            finally:paper.close()
        elif command == "import":
            result = {"dataset": store.import_csv(request.get("path", "")), "datasets": store.datasets()}
        elif command == "refresh":
            result = {"dataset": store.refresh_ecb(), "datasets": store.datasets()}
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
