import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from workers import quant_evolve as ev


def toy_task():
    # Known optimum a=3, b='y'; noise-free so evolution must find it.
    def evaluate(g, start, end):
        return -abs(g["a"] - 3) - (0 if g["b"] == "y" else 2) + 0 * start
    return ev.Task("toy", {"a": list(range(10)), "b": ["x", "y", "z"]}, evaluate, lambda g: g["b"], {"a": 0, "b": "x"}, "toy")


class EvolutionTests(unittest.TestCase):
    def test_mlp_learns_nonlinearity_ridge_cannot(self):
        rng = np.random.default_rng(0)
        x = rng.uniform(-2, 2, (1500, 1))
        y = np.sin(2 * x[:, 0]) + .05 * rng.normal(size=1500)
        net = ev.MLP(hidden=(16,), l2=1e-4, lr=2e-2, epochs=800, patience=80, seed=1).fit(x[:1200], y[:1200])
        mlp_mse = np.mean((net.predict(x[1200:]) - y[1200:]) ** 2)
        beta = np.polyfit(x[:1200, 0], y[:1200], 1)
        linear_mse = np.mean((np.polyval(beta, x[1200:, 0]) - y[1200:]) ** 2)
        self.assertLess(mlp_mse, .3 * linear_mse)
        again = ev.MLP(hidden=(16,), l2=1e-4, lr=2e-2, epochs=800, patience=80, seed=1).fit(x[:1200], y[:1200])
        np.testing.assert_array_equal(net.predict(x[1200:]), again.predict(x[1200:]))

    def test_evolution_finds_known_optimum_and_records_lineage(self):
        evo = ev.Evolution(toy_task(), population=10, seed=3)
        for _ in range(12):
            best = evo.step(0, 1)
        self.assertEqual(evo.nodes[best]["genome"], {"a": 3, "b": "y"})
        g = ev.graph(evo)
        ids = {n["id"] for n in g["nodes"]}
        self.assertTrue(all(e["source"] in ids and e["target"] in ids for e in g["edges"]))
        self.assertTrue({"mutation", "crossover", "elite"} & {e["kind"] for e in g["edges"]})

    def test_prequential_champions_cannot_see_the_future(self):
        r = np.random.default_rng(5).standard_t(4, 4000) * .01
        settings = dict(first=2000, block=500, validation=500, generations=2, population=6, seed=1)
        a = ev.prequential(ev.risk_task(r), len(r), **settings)
        shocked = r.copy(); shocked[3200:] *= 4
        b = ev.prequential(ev.risk_task(shocked), len(shocked), **settings)
        # Blocks ending before the shock choose identical champions with identical scores.
        for x, y in zip(a["curve"], b["curve"]):
            if x["end"] <= 3200:
                self.assertEqual(x["genome"], y["genome"])
                self.assertEqual(x["out_of_sample_score"], y["out_of_sample_score"])
        self.assertTrue(all(np.isfinite(c["out_of_sample_score"]) for c in a["curve"]))

    def test_alpha_task_scores_signal_above_noise(self):
        rng = np.random.default_rng(2)
        n = 3000
        r = np.empty(n); r[0] = 0
        for t in range(1, n):
            r[t] = -.3 * r[t - 1] + .01 * rng.normal()  # Strong negative autocorrelation: r1 predicts.
        task = ev.alpha_task(r)
        signal = task.score({"model": "ridge", "features": 1, "ridge": 1., "hidden": 4, "layers": 1, "l2": 1e-3}, 2000, 2600)
        noise = task.score({"model": "zero", "features": 1, "ridge": 1., "hidden": 4, "layers": 1, "l2": 1e-3}, 2000, 2600)
        self.assertGreater(signal, 5)
        self.assertLess(noise, signal)

    def test_experience_round_trip_prefers_same_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = ev.Experience(Path(tmp) / "exp.jsonl")
            memory.remember("toy", "data-a", {"curve": [{"genome": {"a": 1}, "out_of_sample_score": 1., "start": 0, "end": 1}]})
            memory.remember("toy", "data-b", {"curve": [{"genome": {"a": 2}, "out_of_sample_score": 9., "start": 0, "end": 1}]})
            self.assertEqual(memory.load("toy", "data-a")[0], {"a": 1})
            self.assertEqual(memory.load("toy", "data-b")[0], {"a": 2})
            self.assertEqual(memory.load("other", "data-a"), [])


if __name__ == "__main__":
    unittest.main()


class ReproducibilityTests(unittest.TestCase):
    def test_same_seed_same_result_under_different_hash_seeds(self):
        import json, os, subprocess, sys
        # The project root is passed explicitly: embedded (._pth) runtimes and -P never add the cwd to sys.path.
        code = ("import json,sys; sys.path.insert(0, sys.argv[1]); import numpy as np; from workers import quant_evolve as ev; "
                "r=np.random.default_rng(5).standard_t(4,3000)*.01; "
                "out=ev.prequential(ev.risk_task(r),len(r),first=2000,block=500,validation=500,generations=2,population=8,seed=3); "
                "print(json.dumps([c['genome'] for c in out['curve']]+[c['out_of_sample_score'] for c in out['curve']]))")
        root = Path(__file__).resolve().parents[1]
        runs = [subprocess.run([sys.executable, "-P", "-c", code, str(root)], cwd=root, capture_output=True, text=True, timeout=300,
                               env={**os.environ, "PYTHONHASHSEED": h}) for h in ("1", "98765")]
        outputs = [run.stdout for run in runs]
        self.assertTrue(outputs[0].strip(), runs[0].stderr[-2000:])
        self.assertEqual(outputs[0], outputs[1])
