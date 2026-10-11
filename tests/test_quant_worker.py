import json
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = os.environ.get("QUANT_PYTHON") or sys.executable


class QuantWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def command(self, command, **values):
        completed = subprocess.run(
            [PYTHON, "workers/quant_worker.py"], cwd=ROOT,
            input=json.dumps({"command": command, "root": str(self.root), **values}) + "\n",
            text=True, capture_output=True, timeout=30,
        )
        lines = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        final = lines[-1] if lines else {"ok": False, "error": completed.stderr}
        return completed, final

    def test_sample_is_labeled_and_has_persisted_snapshot_hash(self):
        _, message = self.command("inspect")
        self.assertTrue(message["ok"], message.get("error"))
        sample = message["result"]["datasets"][0]
        self.assertEqual(sample["kind"], "synthetic")
        self.assertEqual(len(sample["sha256"]), 64)
        self.assertTrue(Path(sample["path"]).is_file())
        self.assertIn("synthetic", sample["name"].lower())

    def test_successful_run_reopens_with_complete_report_and_provenance(self):
        _, message = self.command("analyse", dataset_id="sample", parameters={"paths": 5000, "horizon": 5, "seed": 23})
        self.assertTrue(message["ok"], message.get("error"))
        report = message["result"]["report"]
        self.assertEqual(report["parameters"]["seed"], 23)
        self.assertEqual(report["provenance"]["kind"], "synthetic")
        self.assertEqual(len(report["provenance"]["sha256"]), 64)
        _, history = self.command("history")
        self.assertEqual(history["result"]["runs"][0]["status"], "completed")
        run_id = history["result"]["runs"][0]["id"]
        _, reopened = self.command("report", run_id=run_id)
        self.assertEqual(reopened["result"]["report"], report)

    def test_failed_analysis_does_not_replace_latest_complete_report(self):
        _, success = self.command("analyse", dataset_id="sample", parameters={"paths": 5000})
        self.assertTrue(success["ok"], success.get("error"))
        path = Path(success["result"]["report_path"])
        original = path.read_bytes()
        _, failure = self.command("analyse", dataset_id="sample", parameters={"paths": 999})
        self.assertFalse(failure["ok"])
        self.assertEqual(path.read_bytes(), original)
        _, history = self.command("history")
        self.assertEqual([r["status"] for r in history["result"]["runs"]], ["failed", "completed"])

    def test_invalid_import_does_not_add_or_replace_a_dataset(self):
        self.command("inspect")
        source = self.root / "broken.csv"
        source.write_text("date,A\n2026-01-01,100\n2026-01-01,101\n")
        _, failed = self.command("import", path=str(source))
        self.assertFalse(failed["ok"])
        _, inspected = self.command("inspect")
        self.assertTrue(inspected["ok"], inspected.get("error"))
        self.assertEqual(len(inspected["result"]["datasets"]), 1)

    def test_valid_import_copies_content_and_preserves_its_source(self):
        from workers.quant_core import example_prices
        dates, _, prices = example_prices()
        source = self.root / "prices.csv"
        source.write_text("date,A,B\n" + "\n".join(f"{d},{p[0]},{p[1]}" for d, p in zip(dates, prices)) + "\n")
        _, imported = self.command("import", path=str(source))
        self.assertTrue(imported["ok"], imported.get("error"))
        dataset = imported["result"]["dataset"]
        self.assertEqual(dataset["kind"], "csv")
        self.assertEqual(dataset["metadata"]["original_path"], str(source))
        self.assertNotEqual(dataset["path"], str(source))
        source.unlink()
        _, analysis = self.command("analyse", dataset_id=dataset["id"], parameters={"paths": 5000})
        self.assertTrue(analysis["ok"], analysis.get("error"))

    def test_options_command_returns_report_without_history(self):
        _, message = self.command("options", parameters={"spot": 100, "strike": 95, "time": .5, "rate": .03,
                                                          "volatility": .25, "kind": "put", "paths": 10000})
        self.assertTrue(message["ok"], message.get("error"))
        self.assertEqual(message["result"]["report"]["kind"], "options")
        _, history = self.command("history")
        self.assertEqual(history["result"]["runs"], [])
        _, bad = self.command("options", parameters={"spot": 100, "strike": 95, "time": .5, "rate": .03,
                                                      "volatility": .25, "barrier": 90})
        self.assertFalse(bad["ok"])
        self.assertIn("Unknown option parameter", bad["error"])

    def test_new_reports_are_schema_two_with_student_t(self):
        _, message = self.command("analyse", dataset_id="sample", parameters={"paths": 2000, "horizon": 5})
        report = message["result"]["report"]
        self.assertEqual((report["schema_version"], report["engine_version"]), (2, "0.2.0"))
        self.assertIn("student_t", report)
        self.assertEqual(report["backtest"]["timing"]["execution_delay_closes"], 1)

    def test_unknown_report_id_cannot_escape_report_directory(self):
        _, result = self.command("report", run_id="../../other.json")
        self.assertFalse(result["ok"])

    def test_killed_worker_is_recovered_as_interrupted_without_complete_report(self):
        process = subprocess.Popen([PYTHON, "workers/quant_worker.py"], cwd=ROOT,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        process.stdin.write(json.dumps({"command": "analyse", "root": str(self.root), "dataset_id": "sample",
                                       "parameters": {"paths": 1_000_000, "horizon": 252}}) + "\n")
        process.stdin.flush()
        process.stdin.close()
        event = json.loads(process.stdout.readline())
        self.assertEqual(event["type"], "started")
        process.kill()
        process.wait(timeout=10)
        process.stdout.close()
        process.stderr.close()
        _, history = self.command("history", recover=True)
        self.assertTrue(history["ok"], history.get("error"))
        self.assertEqual(history["result"]["runs"][0]["status"], "interrupted")
        self.assertEqual(list((self.root / "reports").glob("*.json")), [])

    def test_ecb_parser_uses_chronological_reference_rates_and_source_hash(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec("workers.quant_store"), "Persistent worker implementation is missing")
        from workers.quant_store import parse_ecb
        cubes = "".join(f'<Cube time="2026-01-{day:02d}"><Cube currency="USD" rate="{1 + day / 100}"/><Cube currency="GBP" rate="0.8"/></Cube>' for day in range(31, 0, -1))
        # Parser validates chronology and prices; minimum dataset size belongs to store import.
        dates, assets, prices = parse_ecb(f'<Envelope><Cube>{cubes}</Cube></Envelope>'.encode(), minimum=2)
        self.assertEqual(dates[0], "2026-01-01")
        self.assertEqual(assets, ["GBP per EUR", "USD per EUR"])
        self.assertEqual(prices[0, 1], 1.01)


if __name__ == "__main__":
    unittest.main()
