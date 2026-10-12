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
            self.assertEqual(memory.load("risk", "other", as_of=20), [])

    def test_exposure_ledger_rejects_replays_and_overlaps(self):
        from experiments.exposure_ledger import ExposureLedger, AlreadyExposedError, fingerprint

        with tempfile.TemporaryDirectory() as root:
            ledger = ExposureLedger(Path(root) / "seen.jsonl")
            dataset = fingerprint({"data": "fixture"})
            forecast = fingerprint({"prediction": 1})
            ledger.reveal(dataset, 100, 200, prediction_sha256=forecast)
            self.assertTrue(ledger.exposed(dataset, 150, 180))
            with self.assertRaises(AlreadyExposedError):
                ledger.reveal(dataset, 100, 200, prediction_sha256=forecast)
            with self.assertRaises(AlreadyExposedError):
                ledger.reveal(dataset, 199, 210, prediction_sha256=forecast)
            ledger.reveal(dataset, 200, 250, prediction_sha256=forecast)
            ledger.reveal(fingerprint({"data": "other"}), 100, 200, prediction_sha256=forecast)

    def test_guard_model_selection_cannot_read_reserved_adoption_windows(self):
        from workers.quant_evolve import Task, prequential

        def task(adoption_bonus):
            def score(genome, start, end):
                if start >= 40 and start < 70 and genome["a"] == 1:
                    return adoption_bonus
                return float(-genome["a"])
            return Task("guard", {"a": [0, 1]}, score, lambda g: "toy", {"a": 0}, "fixture")

        settings = dict(first=70, block=10, validation=10, evidence_windows=6,
                        guard=True, generations=2, population=8, seed=13)
        a = prequential(task(10.0), 80, **settings)
        b = prequential(task(-10.0), 80, **settings)
        self.assertEqual(a["curve"][0]["champion"], b["curve"][0]["champion"])
        self.assertEqual(a["curve"][0]["validation_score"], b["curve"][0]["validation_score"])
        self.assertEqual(a["curve"][0]["genome"], b["curve"][0]["genome"])

    def test_sealed_judge_rejects_tampering_and_repeated_disclosure(self):
        from experiments.blind_judge import commit, evaluate
        from experiments.exposure_ledger import AlreadyExposedError, fingerprint

        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            digest = fingerprint({"dataset": "anonymous"})
            prediction = path / "predictions.json"
            labels = path / "hidden.json"
            seal = path / "commitment.json"
            ledger = path / "exposures.jsonl"
            forecast = {"dataset_sha256": digest, "start": 0, "end": 3,
                        "predictions": [0.0, 0.01, -0.01]}
            prediction.write_text(json.dumps(forecast))
            labels.write_text(json.dumps({"dataset_sha256": digest, "start": 0, "end": 3,
                                          "outcomes": [0.01, 0.0, -0.01]}))
            seal.write_text(json.dumps(commit(prediction)))
            result = evaluate(prediction, seal, labels, ledger)
            self.assertEqual(result["count"], 3)
            self.assertGreaterEqual(result["mse"], 0)
            with self.assertRaises(AlreadyExposedError):
                evaluate(prediction, seal, labels, ledger)
            forecast["predictions"][1] = 1.0
            prediction.write_text(json.dumps(forecast))
            with self.assertRaisesRegex(ValueError, "differ from sealed commitment"):
                evaluate(prediction, seal, labels, ledger)

    def test_legacy_import_path_is_redacted_on_read(self):
        from workers.quant_store import Store

        row = {"assets_json": '["Asset"]',
               "metadata_json": json.dumps({"original_path": "/private/user/data.csv",
                                            "raw_sha256": "abc"})}
        result = Store.dataset_row(row)
        self.assertEqual(result["metadata"]["original_filename"], "data.csv")
        self.assertNotIn("original_path", result["metadata"])
        self.assertEqual(result["metadata"]["raw_sha256"], "abc")

    def test_unseen_stream_only_exposes_past_and_rejects_replay(self):
        from experiments.sequential_unseen import evaluate_stream
        from experiments.exposure_ledger import AlreadyExposedError, fingerprint

        values = [0.01, 0.02, -0.01, 0.05, -0.04]
        observed = []
        def predictor(history):
            observed.append(history)
            return history[-1]
        with tempfile.TemporaryDirectory() as root:
            opts = dict(dataset_sha256=fingerprint({"new": "unknown synthetic"}),
                        ledger_path=Path(root)/"ledger.jsonl", minimum_history=2)
            result = evaluate_stream(values, predictor, **opts)
            self.assertEqual(result["n"], 3)
            self.assertEqual(observed, [tuple(values[:2]), tuple(values[:3]), tuple(values[:4])])
            with self.assertRaises(AlreadyExposedError):
                evaluate_stream(values, predictor, **opts)
            with self.assertRaises(ValueError):
                evaluate_stream(values, lambda _: float("nan"),
                                dataset_sha256=fingerprint("another"), ledger_path=opts["ledger_path"])

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
