import json
import tempfile
import unittest
from pathlib import Path

from experiments.verify_acceptance import verify
from workers.quant_evolve import MLP
import numpy as np


class ResearchIntegrityTests(unittest.TestCase):
    def test_experiment_acceptance_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "result.json"
            p.write_text(json.dumps({"acceptance": {"calibration": False}}))
            self.assertTrue(any("calibration" in x for x in verify([str(p)])))
            p.write_text(json.dumps({"acceptance": {"calibration": 1}}))
            self.assertTrue(verify([str(p)]))
            p.write_text(json.dumps({"acceptance": {}}))
            self.assertTrue(verify([str(p)]))
            p.write_text(json.dumps({"acceptance": {"calibration": True}}))
            self.assertEqual(verify([str(p)]), [])
            self.assertTrue(verify([str(p) + ".missing"]))

    def test_experience_time_scope_excludes_future_and_legacy_rows(self):
        from workers.quant_evolve import Experience

        with tempfile.TemporaryDirectory() as root:
            memory = Experience(Path(root) / "experience.jsonl")
            rows = [
                {"task": "risk", "fingerprint": "data", "genome": {"id": "past"}, "score": 1.0, "block": [0, 9]},
                {"task": "risk", "fingerprint": "data", "genome": {"id": "future"}, "score": 99.0, "block": [10, 20]},
                {"task": "risk", "fingerprint": "data", "genome": {"id": "legacy"}, "score": 100.0},
            ]
            memory.path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            self.assertEqual(memory.load("risk", "data", as_of=10), [{"id": "past"}])
            self.assertEqual({g["id"] for g in memory.load("risk", "data", as_of=20)}, {"past", "future"})

    def test_mlp_scaling_cannot_see_early_stopping_tail(self):
        rng = np.random.default_rng(12)
        x = rng.normal(size=(120, 2))
        y = rng.normal(size=120)
        altered_x = x.copy()
        altered_y = y.copy()
        altered_x[96:] += 1_000
        altered_y[96:] -= 1_000
        a = MLP(hidden=(4,), epochs=2, patience=1, seed=7).fit(x, y)
        b = MLP(hidden=(4,), epochs=2, patience=1, seed=7).fit(altered_x, altered_y)
        np.testing.assert_array_equal(a.mean_, b.mean_)
        np.testing.assert_array_equal(a.scale_, b.scale_)
        self.assertEqual(a.y_mean_, b.y_mean_)
        self.assertEqual(a.y_scale_, b.y_scale_)


if __name__ == "__main__":
    unittest.main()
