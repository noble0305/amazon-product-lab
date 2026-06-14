import csv
import tempfile
import unittest
from pathlib import Path

from amazon_product_lab.io import load_candidates
from amazon_product_lab.reporting import render_markdown


class CandidateIoTests(unittest.TestCase):
    def test_loads_typed_candidate_from_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.csv"
            self._write_csv(path, hazmat="false")

            candidate = load_candidates(path)[0]

            self.assertEqual(candidate["sale_price"], 39.99)
            self.assertEqual(candidate["hazmat"], False)

    def test_rejects_csv_with_missing_required_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidates.csv"
            self._write_csv(path, niche=None)

            with self.assertRaisesRegex(ValueError, "niche"):
                load_candidates(path)

    def test_markdown_report_places_highest_score_first(self):
        results = [
            {"opportunity_id": "A", "niche": "low", "score": 66, "decision": "watch", "red_flags": [], "scenarios": {"base": {"profit": 2, "margin": 0.1}}},
            {"opportunity_id": "B", "niche": "high", "score": 88, "decision": "sample", "red_flags": [], "scenarios": {"base": {"profit": 8, "margin": 0.25}}},
        ]

        report = render_markdown(results)

        self.assertLess(report.index("high"), report.index("low"))

    def _write_csv(self, path: Path, **overrides):
        row = {
            "opportunity_id": "US-001",
            "marketplace": "US",
            "niche": "drawer organizer",
            "sale_price": "39.99",
            "landed_cost": "7",
            "fba_fee": "5.5",
            "referral_fee_rate": "0.15",
            "storage_cost": "0.5",
            "return_rate": "0.05",
            "return_loss_rate": "0.5",
            "conversion_rate": "0.12",
            "cpc": "0.45",
            "demand_score": "82",
            "competition_score": "75",
            "differentiation_score": "80",
            "supply_chain_score": "85",
            "operability_score": "70",
            "compliance_risk": "low",
            "ip_risk": "low",
            "hazmat": "false",
            "seasonal": "false",
        }
        for key, value in overrides.items():
            if value is None:
                row.pop(key)
            else:
                row[key] = value
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=row.keys())
            writer.writeheader()
            writer.writerow(row)


if __name__ == "__main__":
    unittest.main()
