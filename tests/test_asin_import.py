import csv
import tempfile
import unittest
from pathlib import Path

from amazon_product_lab.asin_import import analyze_asin_export, write_asin_outputs


class AsinImportTests(unittest.TestCase):
    def test_ranks_high_click_low_review_product_first(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ASIN Explorer 搜索结果_2026_6_14.csv"
            self._write_export(source)

            analysis = analyze_asin_export(source)

            self.assertEqual(analysis["products"][0]["asin"], "B000000001")
            self.assertEqual(analysis["products"][0]["rank"], 1)
            self.assertEqual(analysis["source"]["data_rows"], 4)
            self.assertEqual(analysis["method"]["stage"], "product_opportunity_screening")
            self.assertIn("不构成利润结论", analysis["method"]["warning"])

    def test_treats_zero_rating_and_bsr_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "export.csv"
            self._write_export(source)

            product = next(item for item in analyze_asin_export(source)["products"] if item["asin"] == "B000000003")

            self.assertIsNone(product["rating"])
            self.assertIsNone(product["bsr"])
            self.assertLess(product["data_completeness"], 100)
            self.assertIn("missing_demand_data", product["data_flags"])

    def test_handles_clicked_product_with_zero_reviews(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "export.csv"
            self._write_export(source)

            analysis = analyze_asin_export(source)

            self.assertEqual(len(analysis["products"]), 4)

    def test_writes_product_report_and_cost_template(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ASIN Explorer 搜索结果_2026_6_14.csv"
            output = Path(directory) / "output"
            self._write_export(source)

            write_asin_outputs(analyze_asin_export(source), output)

            self.assertTrue((output / "asin_report.json").exists())
            report = (output / "asin_report.md").read_text(encoding="utf-8")
            self.assertIn("ASIN 产品机会初筛", report)
            with (output / "product_enrichment.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["asin"], "B000000001")
            self.assertEqual(rows[0]["landed_cost"], "")

    def _write_export(self, path: Path) -> None:
        fields = [
            "商品名称", "ASIN", "品牌", "类别", "发布日期",
            "搜索点击量（过去 360 天）", "平均售价（过去 90 天）(USD)",
            "平均售价（过去 360 天）(USD)", "总评价数", "平均评分",
            "平均畅销排名 (BSR)", "销售伙伴的平均数量",
        ]
        rows = [
            ["High demand organizer", "B000000001", "NewBrand", "Dogs/Accessories", "2025-01-01", "20000", "29.99", "30.99", "80", "4.1", "300", "1"],
            ["Established organizer", "B000000002", "BigBrand", "Dogs/Accessories", "2019-01-01", "7000", "31.99", "31.50", "8000", "4.8", "50", "4"],
            ["Unknown product", "B000000003", "Unknown", "Dogs/Accessories", "2026-01-01", "", "", "", "0", "0", "0", ""],
            ["New product", "B000000004", "New", "Dogs/Accessories", "2026-01-01", "100", "25", "25", "0", "4", "900", "1"],
        ]
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            handle.write("按 ASIN 搜索: \n\n")
            writer = csv.writer(handle)
            writer.writerow(fields)
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
