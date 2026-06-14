import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amazon_product_lab.cli import main
from amazon_product_lab.opportunity_import import (
    analyze_opportunity_export,
    risk_review_flags,
    write_opportunity_outputs,
)


class OpportunityImportTests(unittest.TestCase):
    def test_flags_categories_needing_manual_risk_review(self):
        self.assertEqual(
            risk_review_flags("flea and tick prevention for dogs"),
            ["pest_control_review"],
        )
        self.assertEqual(
            risk_review_flags("hidden camera"),
            ["privacy_review"],
        )
        self.assertEqual(
            risk_review_flags("organic dog treats"),
            ["ingestible_review"],
        )
        self.assertEqual(
            risk_review_flags("dog multivitamin"),
            ["ingestible_review"],
        )
        self.assertEqual(risk_review_flags("decorative wall sticker"), [])
        self.assertEqual(risk_review_flags("drawer organizer"), [])

    def test_reads_amazon_export_with_preamble_and_ranks_markets(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "export.csv"
            self._write_export(source)

            analysis = analyze_opportunity_export(source)

            self.assertEqual(len(analysis["markets"]), 2)
            self.assertEqual(analysis["markets"][0]["niche"], "growing niche")
            self.assertEqual(analysis["markets"][0]["rank"], 1)
            self.assertEqual(analysis["source"]["data_rows"], 2)
            self.assertEqual(len(analysis["source"]["sha256"]), 64)

    def test_marks_result_as_demand_screening_without_profit_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "export.csv"
            self._write_export(source)

            market = analyze_opportunity_export(source)["markets"][0]

            self.assertEqual(market["analysis_stage"], "demand_screening")
            self.assertEqual(market["next_action"], "complete_cost_and_risk_data")
            self.assertNotIn("profit", market)
            self.assertNotIn("sample", market.values())

    def test_rejects_export_missing_required_amazon_column(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "export.csv"
            self._write_export(source, omit="平均价格 (USD)")

            with self.assertRaisesRegex(ValueError, "平均价格"):
                analyze_opportunity_export(source)

    def test_writes_report_and_enrichment_template(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "细分市场搜索结果_2026_6_14.csv"
            output = Path(directory) / "output"
            self._write_export(source)

            write_opportunity_outputs(analyze_opportunity_export(source), output)

            self.assertTrue((output / "market_report.json").exists())
            report = (output / "market_report.md").read_text(encoding="utf-8")
            self.assertIn("需求侧初筛", report)
            self.assertIn("不构成采购或利润决策", report)
            with (output / "candidate_enrichment.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["niche"], "growing niche")
            self.assertEqual(rows[0]["sale_price"], "30.0")
            self.assertEqual(rows[0]["landed_cost"], "")
            self.assertEqual(rows[0]["source_date"], "2026-06-14")

    def test_cli_auto_detects_amazon_opportunity_export(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "export.csv"
            output = Path(directory) / "output"
            self._write_export(source)

            with patch("sys.argv", ["amazon_product_lab", str(source), "--output-dir", str(output)]):
                main()

            self.assertTrue((output / "market_report.md").exists())
            self.assertFalse((output / "report.md").exists())

    def _write_export(self, path: Path, omit: str | None = None) -> None:
        fields = [
            "细分市场",
            "热门搜索词 1",
            "热门搜索词 2",
            "热门搜索词 3",
            "搜索量（过去 360 天内）",
            "搜索量增长（过去 180 天）",
            "搜索量（过去 90 天内）",
            "搜索量增长（过去 90 天内）",
            "点击量最多的商品数量",
            "平均价格 (USD)",
            "退货率 (过去 360 天)",
        ]
        if omit:
            fields.remove(omit)
        rows = [
            {
                "细分市场": "flat niche",
                "热门搜索词 1": "flat",
                "热门搜索词 2": "flat two",
                "热门搜索词 3": "flat three",
                "搜索量（过去 360 天内）": "10000",
                "搜索量增长（过去 180 天）": "-0.2",
                "搜索量（过去 90 天内）": "1000",
                "搜索量增长（过去 90 天内）": "-0.3",
                "点击量最多的商品数量": "10",
                "平均价格 (USD)": "12",
                "退货率 (过去 360 天)": "0.12",
            },
            {
                "细分市场": "growing niche",
                "热门搜索词 1": "growing",
                "热门搜索词 2": "growing two",
                "热门搜索词 3": "growing three",
                "搜索量（过去 360 天内）": "50000",
                "搜索量增长（过去 180 天）": "0.3",
                "搜索量（过去 90 天内）": "20000",
                "搜索量增长（过去 90 天内）": "0.5",
                "点击量最多的商品数量": "50",
                "平均价格 (USD)": "30",
                "退货率 (过去 360 天)": "0.03",
            },
        ]
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            handle.write("按细分市场搜索: \n\n")
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
