"""Desktop-facing continuous learning: bounded evolution runs on the selected snapshot.

Each run appends to <storage>/learning/: an experience file of good genomes (warm start for the
next run) and a history of runs, so the app can show learning over time. Only past data of the
snapshot is used; results are prequential (frozen champion scored on the following block).
"""
from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

import numpy as np

try:
    from . import quant_evolve as ev
except ImportError:
    import quant_evolve as ev


def _series(prices) -> np.ndarray:
    p = np.asarray(prices, dtype=np.float64)
    returns = p[1:] / p[:-1] - 1
    return returns.mean(axis=1)  # Equal-weight portfolio of the snapshot's assets.


MIN_HISTORY = 270  # Enough completed labels for the alpha task's 200-row minimum after feature warm-up.


def plan(n: int) -> dict:
    """Adaptive blocks so short snapshots still learn: up to six evaluation blocks after MIN_HISTORY."""
    block = int(min(500, max(40, (n - MIN_HISTORY) // 6)))
    return {"block": block, "validation": block, "first": max(MIN_HISTORY, n - 6 * block)}


def _finite(value):
    return float(value) if value is not None and np.isfinite(value) else None


def learn(root, dataset: dict, dates, prices, *, budget_seconds: float = 20.0, progress=None) -> dict:
    folder = Path(root) / "learning"
    folder.mkdir(parents=True, exist_ok=True)
    memory = ev.Experience(folder / "experience.jsonl")
    r = _series(prices)
    if len(r) < MIN_HISTORY + 80:
        raise ValueError(f"Learning needs at least {MIN_HISTORY + 80} returns; import a longer price history.")
    layout = plan(len(r))
    started = time.perf_counter()
    runs = {}
    tasks = (("risk", ev.risk_task(r, p=.01)), ("alpha", ev.alpha_task(r, train=min(1500, layout["first"]))))
    for i, (name, task) in enumerate(tasks):
        if progress:
            progress(f"Evolving {name} models", i / len(tasks))
        if name == "risk":  # Shorter windows so small snapshots have valid genomes.
            task.space["window"] = [w for w in (120, 250, 500, 750, 1000) if w <= layout["first"] - layout["validation"]] or [120]
            task.baseline["window"] = task.space["window"][0] if 500 not in task.space["window"] else 500
        remaining = max(2.0, budget_seconds - (time.perf_counter() - started)) / (len(tasks) - i)
        result = ev.prequential(task, len(r), first=layout["first"], block=layout["block"], validation=layout["validation"],
                                generations=2, population=8, seed=len(memory.load(name, dataset["sha256"], 50)),
                                experience=memory.load(name, dataset["sha256"]), evidence_windows=4, guard=True,
                                budget_seconds=remaining)
        memory.remember(name, dataset["sha256"], result)
        for c in result["curve"]:
            c["period"] = f"{dates[c['start'] + 1]}..{dates[c['end']]}"  # Return t ends at price t + 1.
        for c in result["curve"]:
            c["out_of_sample_score"], c["baseline_score"] = _finite(c["out_of_sample_score"]), _finite(c["baseline_score"])
        runs[name] = {"describe": result["describe"], "blocks": result["blocks"], "mean_out_of_sample": _finite(result["mean_out_of_sample"]),
                      "mean_baseline": _finite(result["mean_baseline"]), "share_blocks_beating_baseline": result["share_blocks_beating_baseline"],
                      "guard_share": result["guard_share"], "evaluations": result["evaluations"],
                      "champion": result["curve"][-1]["genome"] if result["curve"] else None,
                      "curve": [{k: c[k] for k in ("period", "family", "out_of_sample_score", "baseline_score", "guard_kept_baseline")}
                                for c in result["curve"]],
                      "graph": result["graph"]}
    summary = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "dataset": dataset["name"],
               "dataset_sha256": dataset["sha256"], "returns": len(r), "layout": layout,
               "seconds": round(time.perf_counter() - started, 2), "tasks": runs}
    with (folder / "history.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({**summary, "tasks": {k: {kk: vv for kk, vv in v.items() if kk not in ("graph", "curve")}
                                                     for k, v in runs.items()}}) + "\n")
    summary["history"] = history(root)["runs"]
    if progress:
        progress("Learning complete", 1.0)
    return summary


def history(root, limit: int = 200) -> dict:
    path = Path(root) / "learning" / "history.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []
    memories = Path(root) / "learning" / "experience.jsonl"
    count = sum(1 for _ in memories.open(encoding="utf-8")) if memories.exists() else 0
    return {"runs": rows[-limit:], "memories": count}
