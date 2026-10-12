"""Adversarial evidence regressions; these are software checks, not alpha tests."""
import json
import tempfile
import unittest
from pathlib import Path

from experiments.audit_live_pilot import audit
from experiments.exposure_ledger import ExposureLedger, fingerprint
from experiments.prospective import prepare_forecast, commit_forecast, settle_forecast


class EvidenceIntegrityTests(unittest.TestCase):
    def test_audit_rejects_changed_losses_even_with_matching_forecast_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = root / '0000000001.forecast.json'
            receipt = root / '0000000001.receipt.json'
            settled = root / '0000000001.settled.json'
            commit_forecast(prepare_forecast(dataset_sha256=fingerprint('run'), index=1,
                model_commit='frozen', candidate=.01, historical_mean=.005), p, receipt_file=receipt)
            settle_forecast(p, receipt, outcome=.02, settlement_file=settled)
            result = json.loads(settled.read_text())
            result['squared_losses']['candidate'] = 0.0
            settled.write_text(json.dumps(result))
            with self.assertRaisesRegex(ValueError, 'loss|Loss'):
                audit(root)

    def test_orphan_receipt_blocks_restart(self):
        from experiments.live_pilot import LivePilot
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, '0000000001.receipt.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'Existing pilot run'):
                LivePilot(tmp, product='BTC-USD', model_commit='frozen')

    def test_busy_exposure_ledger_fails_closed_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, 'exposures.jsonl')
            Path(str(path) + '.lock').write_text('occupied')
            with self.assertRaisesRegex(ValueError, 'locked|busy'):
                ExposureLedger(path).reveal(fingerprint('data'), 0, 10,
                    prediction_sha256=fingerprint('predictions'))
            self.assertFalse(path.exists(), 'Busy ledger must not be created or modified')


if __name__ == '__main__':
    unittest.main()
