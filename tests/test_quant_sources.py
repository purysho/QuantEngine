import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from tests.test_quant_data import french_zip
from workers import quant_store as qs

NAMES = list(qs.INDUSTRY_NAMES)


def daily_dates(n, start=(2000, 1, 3)):
    import datetime as dt
    day, out = dt.date(*start), []
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.strftime("%Y%m%d"))
        day += dt.timedelta(days=1)
    return out


def fixtures(n=60):
    dates = ["19991230", "19991231"] + daily_dates(n)  # Rows before 2000 are dropped by the preset window.
    rng = np.random.default_rng(3)
    factors = "Daily factors\n\n,Mkt-RF,SMB,HML,RF\n" + "".join(
        f"{d},{rng.normal(0, 1):.2f},0.10,0.10,0.01\n" for d in dates) + "\nCopyright\n"
    industry_rows = "".join(f"{d}," + ",".join(f"{rng.normal(0, 1):.2f}" for _ in NAMES) + "\n" for d in dates)
    industries = ("Average Value Weighted Returns -- Daily\n," + ",".join(NAMES) + "\n" + industry_rows +
                  "\nAverage Equal Weighted Returns -- Daily\n," + ",".join(NAMES) + "\n" + industry_rows)
    return french_zip(factors), french_zip(industries), dates


class SourceTests(unittest.TestCase):
    def test_industry_levels_compound_published_returns_from_2000(self):
        factors, industries, dates = fixtures()
        out_dates, assets, prices = qs.industry_prices(factors, industries)
        self.assertEqual(out_dates[0], "2000-01-03")
        self.assertEqual(len(out_dates), len(dates) - 2)
        self.assertEqual(assets[0], "US market (total return)")
        self.assertEqual(assets[1:], [qs.INDUSTRY_NAMES[n] for n in NAMES])
        table = qs.quant_data.parse_french(factors)
        first = table["series"]["Mkt-RF"][2] + table["series"]["RF"][2]
        self.assertAlmostEqual(prices[0, 0], 100 * (1 + first), places=10)

    def test_industry_file_must_match_market_dates(self):
        factors, industries, _ = fixtures()
        other, _, _ = fixtures(61)
        with self.assertRaisesRegex(ValueError, "different dates"):
            qs.industry_prices(other, industries)

    def test_fred_indices_keep_only_complete_days(self):
        csv = ("observation_date,SP500,NASDAQCOM,DJIA\n" +
               "".join(f"2020-01-{d:02d},{3000 + d},{9000 + d},{28000 + d}\n" for d in range(1, 29)) +
               "".join(f"2020-02-{d:02d},{3100 + d},,{28100 + d}\n" for d in range(1, 3)) +
               "".join(f"2020-03-{d:02d},{3200 + d},{9200 + d},{28200 + d}\n" for d in range(1, 29)))
        dates, assets, prices = qs.index_prices(csv.encode())
        self.assertEqual(assets, ["S&P 500", "Nasdaq Composite", "Dow Jones Industrial Average"])
        self.assertEqual(len(dates), 56)
        self.assertNotIn("2020-02-01", dates)

    def test_refresh_saves_hashed_raw_copies_and_marks_dataset_refreshable(self):
        factors, industries, _ = fixtures()
        with tempfile.TemporaryDirectory() as root, mock.patch.object(qs, "download", side_effect=[factors, industries]):
            store = qs.Store(root)
            try:
                dataset = store.refresh("us-industries")
                self.assertEqual(dataset["kind"], "french")
                self.assertTrue(dataset["metadata"]["refreshable"])
                self.assertEqual(dataset["metadata"]["source"], "us-industries")
                for raw in dataset["metadata"]["raw"]:
                    self.assertTrue(Path(raw["path"]).exists())
                with self.assertRaisesRegex(ValueError, "Unknown data source"):
                    store.refresh("broker")
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
