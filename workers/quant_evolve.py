"""Evolutionary model search that keeps learning, judged prequentially so it cannot fool itself.

Each *task* defines a genome space and a fitness that uses only data the genome could have
seen. Time is cut into blocks. Before block k the population evolves on a validation window
that ends where block k starts; the champion is frozen and then scored on block k. The
sequence of those block scores is the honest learning curve, and it is compared with a fixed
baseline. Populations persist in an experience store so later runs start from what earlier
runs learned. Every genome keeps its parents and the operator that made it (lineage graph).
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

try:
    from .quant_varbacktest import rolling_var_levels
except ImportError:  # Executed as a script from workers/ (desktop worker).
    from quant_varbacktest import rolling_var_levels


# ------------------------------------------------------------------ neural network (NumPy, CPU)

class MLP:
    """One or two tanh hidden layers, Adam, L2, chronological early stopping. Deterministic per seed."""

    def __init__(self, hidden=(8,), l2=1e-3, lr=1e-2, epochs=300, patience=25, seed=0):
        self.hidden, self.l2, self.lr, self.epochs, self.patience, self.seed = tuple(hidden), l2, lr, epochs, patience, seed

    def _forward(self, x, params):
        activations = [x]
        for i, (w, b) in enumerate(params):
            z = activations[-1] @ w + b
            activations.append(np.tanh(z) if i < len(params) - 1 else z)
        return activations

    def fit(self, x, y):
        rng = np.random.default_rng(self.seed)
        cut = max(1, int(len(x) * .8))  # Split chronologically before fitting any preprocessing.
        train_x, train_y = x[:cut], y[:cut]
        self.mean_, self.scale_ = train_x.mean(axis=0), np.where(train_x.std(axis=0) > 1e-12, train_x.std(axis=0), 1.0)
        self.y_mean_, self.y_scale_ = float(train_y.mean()), float(train_y.std() or 1.0)
        xs, ys = (x - self.mean_) / self.scale_, ((y - self.y_mean_) / self.y_scale_)[:, None]
        xt, yt, xv, yv = xs[:cut], ys[:cut], xs[cut:], ys[cut:]
        sizes = [x.shape[1], *self.hidden, 1]
        params = [(rng.normal(0, 1 / math.sqrt(a), (a, b)), np.zeros(b)) for a, b in zip(sizes[:-1], sizes[1:])]
        m = [(np.zeros_like(w), np.zeros_like(b)) for w, b in params]
        v = [(np.zeros_like(w), np.zeros_like(b)) for w, b in params]
        best, best_loss, wait = params, math.inf, 0
        for epoch in range(1, self.epochs + 1):
            acts = self._forward(xt, params)
            delta = (acts[-1] - yt) * 2 / len(xt)
            grads = []
            for i in range(len(params) - 1, -1, -1):
                w, _ = params[i]
                grads.append((acts[i].T @ delta + 2 * self.l2 * w, delta.sum(axis=0)))
                if i:
                    delta = (delta @ w.T) * (1 - acts[i] ** 2)
            grads.reverse()
            new = []
            for i, ((w, b), (gw, gb)) in enumerate(zip(params, grads)):
                m[i] = (.9 * m[i][0] + .1 * gw, .9 * m[i][1] + .1 * gb)
                v[i] = (.999 * v[i][0] + .001 * gw * gw, .999 * v[i][1] + .001 * gb * gb)
                c1, c2 = 1 - .9 ** epoch, 1 - .999 ** epoch
                new.append((w - self.lr * (m[i][0] / c1) / (np.sqrt(v[i][0] / c2) + 1e-8),
                            b - self.lr * (m[i][1] / c1) / (np.sqrt(v[i][1] / c2) + 1e-8)))
            params = new
            loss = float(np.mean((self._forward(xv, params)[-1] - yv) ** 2)) if len(xv) else 0.0
            if loss < best_loss - 1e-9:
                best, best_loss, wait = params, loss, 0
            else:
                wait += 1
                if wait >= self.patience:
                    break
        self.params_ = best
        return self

    def predict(self, x):
        return self._forward((x - self.mean_) / self.scale_, self.params_)[-1][:, 0] * self.y_scale_ + self.y_mean_


# ------------------------------------------------------------------ tasks

@dataclass
class Task:
    name: str
    space: dict                         # gene -> list of choices
    evaluate: Callable[[dict, int, int], float]  # (genome, start, end) -> score on [start, end); higher is better
    family: Callable[[dict], str]
    baseline: dict
    describe: str
    cache: dict = field(default_factory=dict)

    def score(self, genome, start, end):
        key = (json.dumps(genome, sort_keys=True), start, end)
        if key not in self.cache:
            try:
                self.cache[key] = float(self.evaluate(genome, start, end))
            except (ValueError, np.linalg.LinAlgError, FloatingPointError):
                self.cache[key] = -math.inf  # An unusable genome (e.g. window too short to fit) loses; the run continues.
        return self.cache[key]


def risk_task(returns, p: float = .01) -> Task:
    """Next-day VaR forecasting; score = minus the pinball (quantile) loss x 1e4 over [start, end)."""
    r = np.asarray(returns, dtype=np.float64)

    def evaluate(g, start, end):
        window = g["window"]
        if start - window < 0:
            return -math.inf
        segment = r[start - window:end]
        forecast = rolling_var_levels(segment, window=window, levels=(p,), method=g["method"], refit_every=g["refit_every"])[p]
        realised, q = r[start:end], -forecast
        return -1e4 * float(np.mean((p - (realised < q)) * (realised - q)))

    return Task("risk", {"method": ["historical", "gaussian", "student_t", "garch_t", "gjr_fhs"], "window": [250, 500, 750, 1000],
                         "refit_every": [25, 50, 100]}, evaluate, lambda g: g["method"],
                {"method": "historical", "window": 500, "refit_every": 50},
                f"One-day {100 * (1 - p):.0f}% VaR; fitness = -pinball loss (x1e4), a strictly consistent quantile score.")


FEATURES = ("r1", "r5", "r21", "vol21", "vol63", "abs1")


def _features(r):
    """Feature row t uses returns up to and including t (known at close t); target is r[t + 1]."""
    n = len(r)
    c1 = np.r_[0.0, np.cumsum(r)]
    c2 = np.r_[0.0, np.cumsum(r * r)]
    out = {}
    for name, w in (("r5", 5), ("r21", 21)):
        out[name] = np.r_[np.full(w - 1, np.nan), (c1[w:] - c1[:-w])[: n - w + 1]]
    for name, w in (("vol21", 21), ("vol63", 63)):
        s = np.r_[np.full(w - 1, np.nan), (c2[w:] - c2[:-w])[: n - w + 1]]
        m = np.r_[np.full(w - 1, np.nan), (c1[w:] - c1[:-w])[: n - w + 1]]
        out[name] = np.sqrt(np.maximum(s / w - (m / w) ** 2, 0))
    out["r1"], out["abs1"] = r.copy(), np.abs(r)
    return np.column_stack([out[f] for f in FEATURES])


def alpha_task(returns, train: int = 1500) -> Task:
    """Next-day return prediction; score = out-of-sample R^2 (%) vs the training-mean forecast."""
    r = np.asarray(returns, dtype=np.float64)
    X, y = _features(r)[:-1], r[1:]   # Row t predicts r[t + 1]; its label completes at t + 1.

    def evaluate(g, start, end):
        lo = max(63, start - train)
        mask = [i for i, f in enumerate(FEATURES) if g["features"] >> i & 1] or [0]
        xtr, ytr = X[lo:start - 1, mask], y[lo:start - 1]   # Labels complete strictly before `start`.
        xte, yte = X[start - 1:end - 1, mask], y[start - 1:end - 1]
        if len(ytr) < 200 or not len(yte):
            return -math.inf
        mean = float(ytr.mean())
        if g["model"] == "zero":
            pred = np.zeros(len(yte))
        elif g["model"] == "mean":
            pred = np.full(len(yte), mean)
        elif g["model"] == "ridge":
            mu, sd = xtr.mean(axis=0), np.where(xtr.std(axis=0) > 1e-12, xtr.std(axis=0), 1)
            zt = (xtr - mu) / sd
            beta = np.linalg.solve(zt.T @ zt + g["ridge"] * np.eye(zt.shape[1]), zt.T @ (ytr - mean))
            pred = mean + ((xte - mu) / sd) @ beta
        else:
            net = MLP(hidden=(g["hidden"],) * g["layers"], l2=g["l2"], seed=7).fit(xtr, ytr)
            pred = net.predict(xte)
        denominator = float(np.sum((yte - mean) ** 2))
        return 100 * (1 - float(np.sum((yte - pred) ** 2)) / denominator) if denominator > 0 else 0.0

    return Task("alpha", {"model": ["zero", "mean", "ridge", "mlp"], "features": list(range(1, 2 ** len(FEATURES))),
                          "ridge": [1., 10., 100., 1000.], "hidden": [4, 8, 16], "layers": [1, 2], "l2": [1e-4, 1e-3, 1e-2]},
                evaluate, lambda g: g["model"], {"model": "mean", "features": 1, "ridge": 100., "hidden": 8, "layers": 1, "l2": 1e-3},
                "Next-day return; fitness = out-of-sample R^2 (%) vs the training mean (Campbell-Thompson).")


# ------------------------------------------------------------------ evolution

def _key(genome):
    return hashlib.sha1(json.dumps(genome, sort_keys=True).encode()).hexdigest()[:10]


class Evolution:
    def __init__(self, task: Task, *, population: int = 12, elite: int = 2, immigrants: int = 2, seed: int = 0,
                 experience: list | None = None):
        self.task, self.size, self.elite, self.immigrants = task, population, elite, immigrants
        self.rng = np.random.default_rng(seed)
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.generation = 0
        seeds = [dict(g) for g in (experience or [])][: population // 2]
        self.population = [self._node(g, [], "experience") for g in seeds]
        self.population.append(self._node(dict(task.baseline), [], "baseline"))
        while len(self.population) < population:
            self.population.append(self._node(self._random(), [], "random"))

    def _random(self):
        return {gene: choices[int(self.rng.integers(len(choices)))] for gene, choices in self.task.space.items()}

    def _node(self, genome, parents, operator):
        node_id = f"g{self.generation}-{_key(genome)}"
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, "genome": genome, "family": self.task.family(genome), "generation": self.generation,
                                   "operator": operator, "parents": parents, "fitness": None}
            for parent in parents:
                self.edges.append({"source": parent, "target": node_id, "kind": operator})
        return node_id

    def _mutate(self, genome):
        child = dict(genome)
        gene = list(self.task.space)[int(self.rng.integers(len(self.task.space)))]
        choices = self.task.space[gene]
        if gene == "features":
            child[gene] = int(child[gene]) ^ (1 << int(self.rng.integers(len(FEATURES)))) or 1  # Flip one feature bit.
        else:
            child[gene] = choices[int(self.rng.integers(len(choices)))]
        return child

    def _crossover(self, a, b):
        return {gene: (a if self.rng.random() < .5 else b)[gene] for gene in self.task.space}

    def step(self, start, end, fitness: Callable[[dict], float] | None = None):
        """Score the population (default: on [start, end), data before the next block) and breed the next generation."""
        for node_id in self.population:
            genome = self.nodes[node_id]["genome"]
            self.nodes[node_id]["fitness"] = fitness(genome) if fitness else self.task.score(genome, start, end)
        # dict.fromkeys de-duplicates in insertion order; a set would make tie-breaks depend on PYTHONHASHSEED.
        ranked = sorted(dict.fromkeys(self.population), key=lambda n: -self.nodes[n]["fitness"])
        self.generation += 1
        next_population = [self._node(self.nodes[n]["genome"], [n], "elite") for n in ranked[: self.elite]]
        for _ in range(self.immigrants):
            next_population.append(self._node(self._random(), [], "immigrant"))
        while len(next_population) < self.size:
            tournament = lambda: min(self.rng.choice(ranked, size=min(3, len(ranked)), replace=False), key=lambda n: -self.nodes[n]["fitness"])
            a, b = tournament(), tournament()
            if self.rng.random() < .5 and a != b:
                child = self._crossover(self.nodes[a]["genome"], self.nodes[b]["genome"])
                next_population.append(self._node(child, [a, b], "crossover"))
            else:
                next_population.append(self._node(self._mutate(self.nodes[a]["genome"]), [a], "mutation"))
        self.population = next_population
        return ranked[0]


def prequential(task: Task, n: int, *, first: int, block: int, validation: int, generations: int = 3, population: int = 12,
                seed: int = 0, experience: list | None = None, budget_seconds: float | None = None,
                evidence_windows: int = 1, decay: float = .85, guard: bool = False) -> dict:
    """Evolve on data before t, freeze the champion, score it on [t, t + block). Repeat as time advances.

    ``evidence_windows`` > 1 scores genomes on the last K validation windows (decay-weighted) instead of
    one, which reduces winner's-curse selection. When ``guard`` is enabled,
    the newest three disjoint windows are reserved *solely* for adoption testing;
    model search uses the older windows. This is an independent acceptance gate,
    not a multiple-testing-corrected significance claim.
    """
    evo = Evolution(task, population=population, seed=seed, experience=experience)
    started = time.perf_counter()
    curve = []
    incumbent = dict(task.baseline)  # The adopted model; a challenger must significantly beat it to replace it.
    for t in range(first, n - block + 1, block):
        windows = [(t - validation - j * block, t - j * block) for j in range(evidence_windows) if t - validation - j * block >= 0]
        # Keep the three most recent windows untouched by model search.
        # Both sides must be non-overlapping for a standard-error gate to mean anything.
        if guard:
            if validation > block:
                raise ValueError("Guard needs non-overlapping evaluation windows (validation <= block).")
            selection_windows = windows[3:]
            adoption_windows = windows[:3]
        else:
            selection_windows = windows
            adoption_windows = []
        weights = np.array([decay ** j for j in range(len(selection_windows))])

        def fitness(genome):
            if not selection_windows:
                return -math.inf
            scores = np.array([task.score(genome, a, b) for a, b in selection_windows])
            if not np.isfinite(scores).all():
                return -math.inf
            return float(weights @ scores / weights.sum())

        champion = None
        for _ in range(generations):
            champion = evo.step((selection_windows or windows)[0][0], (selection_windows or windows)[0][1], fitness)
        genome = evo.nodes[champion]["genome"]
        guarded = False
        if guard:
            if genome != incumbent:
                diffs = np.array([task.score(genome, a, b) - task.score(incumbent, a, b) for a, b in adoption_windows])
                standard_error = diffs.std(ddof=1) / math.sqrt(len(diffs)) if len(diffs) >= 3 and selection_windows else math.inf
                if not np.isfinite(diffs).all() or not len(selection_windows) or diffs.mean() - 2 * standard_error <= 0:
                    genome, guarded = dict(incumbent), True
            incumbent = dict(genome)
        out_of_sample = task.score(genome, t, t + block)
        baseline = task.score(task.baseline, t, t + block)
        evo.nodes[champion]["champion"] = True
        curve.append({"start": t, "end": t + block, "champion": champion, "genome": genome, "family": task.family(genome), "guard_kept_baseline": guarded,
                      "validation_score": evo.nodes[champion]["fitness"], "out_of_sample_score": out_of_sample,
                      "baseline_score": baseline, "beats_baseline": out_of_sample > baseline})
        if budget_seconds and time.perf_counter() - started > budget_seconds:
            break
    oos = np.array([c["out_of_sample_score"] for c in curve]); base = np.array([c["baseline_score"] for c in curve])
    finite = np.isfinite(oos) & np.isfinite(base)
    return {"task": task.name, "describe": task.describe, "blocks": len(curve), "curve": curve,
            "mean_out_of_sample": float(oos[finite].mean()) if finite.any() else None,
            "mean_baseline": float(base[finite].mean()) if finite.any() else None,
            "share_blocks_beating_baseline": float(np.mean(oos[finite] > base[finite])) if finite.any() else None,
            "evaluations": len(task.cache), "seconds": time.perf_counter() - started,
            "guard_share": float(np.mean([c["guard_kept_baseline"] for c in curve])) if curve else 0.0,
            "graph": graph(evo), "experience": [evo.nodes[n]["genome"] for n in sorted(
                (n for n in evo.nodes if evo.nodes[n]["fitness"] is not None and math.isfinite(evo.nodes[n]["fitness"])),
                key=lambda n: -evo.nodes[n]["fitness"])[:6]]}


def graph(evo: Evolution, limit: int = 400) -> dict:
    """Lineage graph for the 3D 'second mind' view: nodes are evaluated genomes, edges are how they were bred."""
    scored = [n for n in evo.nodes.values() if n["fitness"] is not None or n.get("champion")]
    keep = {n["id"] for n in sorted(scored, key=lambda n: (-(n.get("champion") is True), -(n["fitness"] or -math.inf)))[:limit]}
    nodes = [{"id": n["id"], "family": n["family"], "generation": n["generation"], "operator": n["operator"],
              "fitness": n["fitness"] if n["fitness"] is not None and math.isfinite(n["fitness"]) else None,
              "champion": bool(n.get("champion")), "label": ", ".join(f"{k}={v}" for k, v in n["genome"].items())}
             for n in evo.nodes.values() if n["id"] in keep]
    edges = [e for e in evo.edges if e["source"] in keep and e["target"] in keep]
    return {"nodes": nodes, "edges": edges}


class Experience:
    """Append-only JSON-lines memory of good genomes per task and data fingerprint."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load(self, task: str, fingerprint: str, limit: int = 6, *, as_of: int | None = None) -> list:
        if not self.path.exists():
            return []
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows = [r for r in rows if r.get("task") == task]
        if as_of is not None:
            # Fail closed: legacy rows without a complete observation interval cannot
            # prove they were available at this replay clock.
            rows = [r for r in rows if isinstance(r.get("block"), list)
                    and len(r["block"]) == 2
                    and all(type(v) is int for v in r["block"])
                    and 0 <= r["block"][0] < r["block"][1] <= as_of]
        # Prefer memories from the same data, then from any data (transfer), best first.
        rows.sort(key=lambda r: (r.get("fingerprint") != fingerprint, -(r.get("score") or -1e18)))
        seen, out = set(), []
        for r in rows:
            key = json.dumps(r["genome"], sort_keys=True)
            if key not in seen:
                seen.add(key); out.append(r["genome"])
            if len(out) >= limit:
                break
        return out

    def remember(self, task: str, fingerprint: str, result: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            for c in result["curve"][-3:]:
                stream.write(json.dumps({"task": task, "fingerprint": fingerprint, "genome": c["genome"],
                                         "score": c["out_of_sample_score"], "block": [c["start"], c["end"]],
                                         "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}) + "\n")
