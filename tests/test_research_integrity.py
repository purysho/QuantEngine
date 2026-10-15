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

    def test_failed_research_finding_is_disclosed_not_presented_as_success(self):
        from experiments.verify_acceptance import verify
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "research.json"
            p.write_text(json.dumps({
                "acceptance": {"numerical_safety": True},
                "unresolved_research_findings": {
                    "alpha_vs_mean_baseline": {
                        "observed_pass": False,
                        "requires_fresh_holdout": True,
                        "reason": "Historical learner underperformed its baseline."
                    }
                }
            }))
            self.assertEqual(verify([str(p)]), [])
            p.write_text(json.dumps({
                "acceptance": {"numerical_safety": True},
                "unresolved_research_findings": {"alpha": {"observed_pass": 0}}
            }))
            self.assertTrue(verify([str(p)]))

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

    def test_point_in_time_vintage_requires_publication_before_prediction(self):
        from workers.quant_point_in_time import asof_snapshot

        rows = [
            {"series_id": "MACRO", "observation_date": "2020-01-01",
             "published_at": "2020-02-01T09:00:00Z", "value": 1.0},
            {"series_id": "MACRO", "observation_date": "2020-01-01",
             "published_at": "2020-03-01T09:00:00Z", "value": 2.0},
        ]
        self.assertEqual(asof_snapshot(rows, "2020-01-31T18:00:00Z"), {})
        key = "MACRO|2020-01-01"
        self.assertEqual(asof_snapshot(rows, "2020-02-02T00:00:00Z")[key]["value"], 1.0)
        self.assertEqual(asof_snapshot(rows, "2020-03-02T00:00:00Z")[key]["value"], 2.0)
        with self.assertRaises(ValueError):
            asof_snapshot(rows, "2020-03-02T00:00:00")
        with self.assertRaises(ValueError):
            asof_snapshot([{**rows[0], "value": float("nan")}], "2020-03-02T00:00:00Z")
        with self.assertRaises(ValueError):
            asof_snapshot([rows[0], {**rows[0], "value": 5.0}], "2020-03-02T00:00:00Z")

    def test_hac_loss_comparison_captures_serial_dependence(self):
        from workers.quant_model_selection import newey_west_mean, paired_loss_comparison

        x = np.array([0.4, 0.5, 0.6, 0.4, 0.5, 0.6])
        iid = newey_west_mean(x, lags=0)
        self.assertAlmostEqual(iid["mean"], 0.5)
        self.assertAlmostEqual(iid["long_run_variance"], float(np.var(x)))
        self.assertAlmostEqual(iid["standard_error"], float(np.std(x))/np.sqrt(len(x)))
        dependent = newey_west_mean(x, lags=1)
        self.assertTrue(np.isfinite(dependent["standard_error"]))
        better = paired_loss_comparison(np.full(40, 0.8) + np.linspace(-0.01, 0.01, 40),
                                        np.full(40, 1.0), lags=3)
        self.assertTrue(better["candidate_better_at_nominal_95"])
        tied = paired_loss_comparison(np.ones(40), np.ones(40), lags=3)
        self.assertFalse(tied["candidate_better_at_nominal_95"])
        with self.assertRaises(ValueError):
            paired_loss_comparison(np.ones(10), np.ones(9), lags=1)
        with self.assertRaises(ValueError):
            newey_west_mean(np.ones(5), lags=5)

    def test_prospective_commit_and_settle_is_single_use(self):
        from experiments.prospective import prepare_forecast, commit_forecast, settle_forecast
        from experiments.exposure_ledger import fingerprint

        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            p, r, s = [base / name for name in ("prediction.json", "receipt.json", "settlement.json")]
            envelope = prepare_forecast(dataset_sha256=fingerprint("future"), index=100,
                                        model_commit="frozen_sha", candidate=0.01, historical_mean=0.002)
            commit_forecast(envelope, p, receipt_file=r)
            with self.assertRaises(FileExistsError):
                commit_forecast(envelope, p, receipt_file=r)
            result = settle_forecast(p, r, outcome=0.02, settlement_file=s)
            self.assertAlmostEqual(result["squared_losses"]["candidate"], 0.0001)
            self.assertGreater(result["squared_losses"]["baseline_zero"],
                               result["squared_losses"]["candidate"])
            with self.assertRaises(FileExistsError):
                settle_forecast(p, r, outcome=0.02, settlement_file=s)
            p.write_text(p.read_text().replace("0.01", "0.03"))
            with self.assertRaisesRegex(ValueError, "does not match"):
                settle_forecast(p, r, outcome=0.02, settlement_file=base / "another.json")

    def test_stationary_bootstrap_reality_check_accounts_for_model_search(self):
        from workers.quant_model_selection import (
            stationary_bootstrap_indices, white_reality_check
        )
        rng = np.random.default_rng(7)
        indices = stationary_bootstrap_indices(100, expected_block=5, rng=rng)
        self.assertEqual(len(indices), 100)
        self.assertTrue(((indices >= 0) & (indices < 100)).all())
        baseline = np.ones(80)
        tied = np.column_stack([baseline, baseline, baseline])
        result = white_reality_check(tied, baseline, expected_block=5,
                                     repetitions=200, seed=21)
        self.assertEqual(result["one_sided_p_value"], 1.)
        superior = np.column_stack([np.full(80, .5), baseline, baseline])
        win = white_reality_check(superior, baseline, expected_block=5,
                                  repetitions=200, seed=21)
        self.assertEqual(win["best_candidate_index"], 0)
        self.assertLess(win["one_sided_p_value"], .05)
        self.assertEqual(win["one_sided_p_value"],
                         white_reality_check(superior, baseline, expected_block=5,
                                             repetitions=200, seed=21)["one_sided_p_value"])
        with self.assertRaises(ValueError):
            white_reality_check(superior, baseline[:-1],
                                expected_block=5, repetitions=200)

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
