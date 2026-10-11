import unittest

import numpy as np

from workers import quant_validation as val


def data(n=400, beta=(.5, 0., 0.), noise=1.0, seed=1, horizon=1):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, len(beta)))
    y = x @ np.asarray(beta) + noise * rng.normal(size=n)
    clock = np.arange(n)
    return x, y, clock.copy(), clock + horizon


class ChronologicalRidgeTests(unittest.TestCase):
    def run_model(self, x, y, available, ends, **kw):
        return val.chronological_ridge(x, y, feature_available=available, label_end=ends,
                                       initial_train=100, test_size=50, final_holdout=100, **kw)

    def test_known_linear_relationship_beats_baselines(self):
        result = self.run_model(*data(n=600, beta=(1., -.5, 0.), noise=.5))
        coefficients = np.asarray(result["final_model"]["coefficients_standardised"]) / np.asarray(result["final_model"]["feature_scale"])
        np.testing.assert_allclose(coefficients, [1., -.5, 0.], atol=.12)
        self.assertGreater(result["holdout"]["oos_r2_vs_mean"], .7)
        self.assertLess(result["holdout"]["mse"], result["holdout"]["zero_forecast_mse"])

    def test_leaked_feature_is_rejected_before_scoring(self):
        x, y, available, ends = data()
        available[250] = 251
        with self.assertRaisesRegex(ValueError, "Leaked feature: row 250"):
            self.run_model(x, y, available, ends)

    def test_incomplete_or_invalid_labels_and_arrays_are_rejected(self):
        x, y, available, ends = data()
        bad_ends = ends.copy(); bad_ends[10] = 10
        cases = [(x, y, available, bad_ends), (x[:-1], y, available, ends),
                 (np.where(np.arange(400)[:, None] == 3, np.nan, x), y, available, ends),
                 (x, y, available.astype(float), ends)]
        for case in cases:
            with self.assertRaises(ValueError):
                self.run_model(*case)

    def test_overlapping_labels_are_purged_before_each_evaluation(self):
        x, y, available, ends = data(horizon=5)
        result = self.run_model(x, y, available, ends)
        for row in result["ledger"]:
            for block in row["blocks"]:
                self.assertLess(block["last_train_label_end"], block["evaluation_start"])
                self.assertEqual(block["train_rows"], block["evaluation_start"] - 5)  # Rows j with j + 5 < s.
        self.assertLess(result["final_model"]["last_train_label_end"], result["holdout"]["start"])

    def test_holdout_cannot_influence_selection_or_scaling(self):
        x, y, available, ends = data()
        base = self.run_model(x, y, available, ends)
        x2, y2 = x.copy(), y.copy()
        x2[300:] *= 1e3
        y2[300:] = 50.0
        changed = self.run_model(x2, y2, available, ends)
        self.assertEqual(base["selected_alpha"], changed["selected_alpha"])
        self.assertEqual(base["ledger"], changed["ledger"])
        self.assertEqual(base["final_model"], changed["final_model"])
        self.assertNotEqual(base["holdout"]["mse"], changed["holdout"]["mse"])

    def test_future_perturbation_leaves_prior_fits_unchanged(self):
        x, y, available, ends = data()
        base = self.run_model(x, y, available, ends)
        y2 = y.copy(); y2[220:] += 3.0
        changed = self.run_model(x, y2, available, ends)
        for a, b in zip(base["ledger"], changed["ledger"]):
            for block_a, block_b in zip(a["blocks"], b["blocks"]):
                if block_a["evaluation_start"] <= 200:
                    self.assertEqual(block_a["predictions"], block_b["predictions"])

    def test_every_candidate_is_logged(self):
        result = self.run_model(*data(), alphas=(0., 1., 1e4))
        self.assertEqual([row["alpha"] for row in result["ledger"]], [0., 1., 1e4])
        self.assertEqual(result["candidates_tried"], 3)
        self.assertIn(result["selected_alpha"], (0., 1., 1e4))


if __name__ == "__main__":
    unittest.main()
