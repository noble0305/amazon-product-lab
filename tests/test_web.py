import csv
import io
import unittest

from amazon_product_lab.web import analyze_upload


class WebAnalysisTests(unittest.TestCase):
    def test_analyzes_uploaded_amazon_export_and_returns_download(self):
        payload = self._export_bytes()

        response = analyze_upload("细分市场搜索结果_2026_6_14.csv", payload)

        self.assertEqual(response["analysis"]["source"]["data_rows"], 1)
        self.assertEqual(response["analysis"]["source"]["collection_date"], "2026-06-14")
        self.assertEqual(response["analysis"]["markets"][0]["niche"], "drawer organizer")
        rows = list(csv.DictReader(io.StringIO(response["enrichment_csv"])))
        self.assertEqual(rows[0]["niche"], "drawer organizer")
        self.assertEqual(rows[0]["landed_cost"], "")

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
