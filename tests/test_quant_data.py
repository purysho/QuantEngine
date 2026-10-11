import io
import math
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

from workers import quant_data as qd


def french_zip(body: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("F-F_Test_daily.csv", body)
    return buffer.getvalue()


FRENCH = """This file was created by using the test database.

,Mkt-RF,SMB,HML,RF
19260701,    0.09,   -0.23,   -0.28,    0.01
19260702,    0.45,  -99.99,   -0.03,    0.01
19260706,    0.17,    0.29,   -0.38,    0.01

Copyright test
"""

INDUSTRY = """Header text

  Average Value Weighted Returns -- Daily
,A,B
19260701,   1.00,  -1.00
19260702,   2.00,   0.50

  Average Equal Weighted Returns -- Daily
,A,B
19260701,   9.00,   9.00
"""


class DataTests(unittest.TestCase):
    def test_fred_missing_values_are_nan_not_filled(self):
        table = qd.parse_fred("observation_date,VIXCLS,X\n1990-01-02,17.24,1\n1990-01-03,,.\n1990-01-04,18.5,2\n")
        self.assertEqual(table["dates"][0].isoformat(), "1990-01-02")
        self.assertTrue(math.isnan(table["series"]["VIXCLS"][1]))
        self.assertTrue(math.isnan(table["series"]["X"][1]))
        with self.assertRaises(ValueError):
            qd.parse_fred("observation_date,X\n1990-01-03,1\n1990-01-02,2\n")
        with self.assertRaises(ValueError):
            qd.parse_fred("something,else\n")

    def test_french_percent_to_decimal_sentinels_and_sections(self):
        table = qd.parse_french(french_zip(FRENCH))
        np.testing.assert_allclose(table["series"]["Mkt-RF"], [.0009, .0045, .0017])
        self.assertTrue(math.isnan(table["series"]["SMB"][1]))
        self.assertEqual(len(table["dates"]), 3)  # Stops at the copyright block.
        vw = qd.parse_french(french_zip(INDUSTRY), "Average Value Weighted Returns -- Daily")
        np.testing.assert_allclose(vw["series"]["A"], [.01, .02])
        ew = qd.parse_french(french_zip(INDUSTRY + "19260702,   1.00,   1.00\n"), "Average Equal Weighted Returns -- Daily")
        self.assertEqual(ew["series"]["A"][0], .09)

    def test_cache_records_provenance_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            data = b"observation_date,X\n2020-01-01,1\n"
            (folder / "f.csv").write_bytes(data)
            import hashlib, json
            (folder / "demo.json").write_text(json.dumps({"name": "demo", "file": "f.csv", "sha256": hashlib.sha256(data).hexdigest()}))
            content, meta = qd.fetch("http://unused", folder, "demo", offline=True)
            self.assertEqual(content, data)
            (folder / "f.csv").write_bytes(b"tampered")
            with self.assertRaises(ValueError):
                qd.fetch("http://unused", folder, "demo", offline=True)
            with self.assertRaises(FileNotFoundError):
                qd.fetch("http://unused", folder, "missing", offline=True)

    def test_align_drops_missing_and_unmatched_dates(self):
        import datetime as dt
        d = [dt.date(2020, 1, i) for i in (1, 2, 3, 4)]
        dates, a, b = qd.align(d, np.array([1., np.nan, 3., 4.]), d[1:], np.array([20., 30., np.nan]))
        self.assertEqual(dates, [d[2]])
        self.assertEqual((a[0], b[0]), (3., 30.))


if __name__ == "__main__":
    unittest.main()
