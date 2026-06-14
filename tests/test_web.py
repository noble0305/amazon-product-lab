import csv
import io
import unittest
from pathlib import Path

from amazon_product_lab.web import analyze_upload


class WebAnalysisTests(unittest.TestCase):
    def test_web_assets_expose_sort_controls_and_amazon_keyword_links(self):
        asset_dir = Path(__file__).parents[1] / "amazon_product_lab" / "web_assets"
        html = (asset_dir / "index.html").read_text(encoding="utf-8")
        javascript = (asset_dir / "app.js").read_text(encoding="utf-8")

        self.assertIn('data-sort="screening_score"', html)
        self.assertIn('aria-sort="none"', html)
        self.assertIn("sortFilter", javascript)
        self.assertIn("https://www.amazon.com/s?k=", javascript)
        self.assertIn('target="_blank"', javascript)
        self.assertIn('rel="noopener noreferrer"', javascript)
        self.assertIn("renderAsinTable", javascript)
        self.assertIn("data_completeness", javascript)
        self.assertIn("https://www.amazon.com/dp/", javascript)

    def test_analyzes_uploaded_amazon_export_and_returns_download(self):
        payload = self._export_bytes()

        response = analyze_upload("细分市场搜索结果_2026_6_14.csv", payload)

        self.assertEqual(response["analysis"]["source"]["data_rows"], 1)
        self.assertEqual(response["analysis"]["source"]["collection_date"], "2026-06-14")
        self.assertEqual(response["analysis"]["markets"][0]["niche"], "drawer organizer")
        rows = list(csv.DictReader(io.StringIO(response["enrichment_csv"])))
        self.assertEqual(rows[0]["niche"], "drawer organizer")
        self.assertEqual(rows[0]["landed_cost"], "")

    def test_analyzes_uploaded_asin_export(self):
        fields = [
            "商品名称", "ASIN", "品牌", "类别", "发布日期",
            "搜索点击量（过去 360 天）", "平均售价（过去 90 天）(USD)",
            "平均售价（过去 360 天）(USD)", "总评价数", "平均评分",
            "平均畅销排名 (BSR)", "销售伙伴的平均数量",
        ]
        output = io.StringIO()
        output.write("按 ASIN 搜索: \n\n")
        writer = csv.writer(output)
        writer.writerow(fields)
        writer.writerow(["Drawer organizer", "B000000001", "Brand", "Home/Storage", "2025-01-01", "5000", "29.99", "30.99", "80", "4.1", "300", "1"])

        response = analyze_upload(
            "ASIN Explorer 搜索结果_2026_6_14.csv",
            output.getvalue().encode("utf-8-sig"),
        )

        self.assertEqual(response["dataset_type"], "asin")
        self.assertEqual(response["analysis"]["products"][0]["asin"], "B000000001")
        self.assertEqual(response["download_name"], "product_enrichment.csv")

    def test_rejects_empty_upload(self):
        with self.assertRaisesRegex(ValueError, "文件为空"):
            analyze_upload("empty.csv", b"")

    def _export_bytes(self) -> bytes:
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
        output = io.StringIO()
        output.write("按细分市场搜索: \n\n")
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "细分市场": "drawer organizer",
                "热门搜索词 1": "drawer organizer",
                "热门搜索词 2": "organizer",
                "热门搜索词 3": "drawer storage",
                "搜索量（过去 360 天内）": "50000",
                "搜索量增长（过去 180 天）": "0.2",
                "搜索量（过去 90 天内）": "15000",
                "搜索量增长（过去 90 天内）": "0.3",
                "点击量最多的商品数量": "30",
                "平均价格 (USD)": "29.99",
                "退货率 (过去 360 天)": "0.03",
            }
        )
        return output.getvalue().encode("utf-8-sig")


if __name__ == "__main__":
    unittest.main()
