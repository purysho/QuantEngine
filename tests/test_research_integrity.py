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
