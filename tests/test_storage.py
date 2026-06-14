import tempfile
import unittest
from pathlib import Path

from amazon_product_lab.storage import ProductLabStore


class ProductLabStoreTests(unittest.TestCase):
    def test_persists_and_restores_latest_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProductLabStore(Path(directory) / "lab.db")
            run_id = store.save_analysis(
                "asin",
                {"source": {"file": "asin.csv"}, "products": [{"asin": "B001"}]},
                "template",
                "product_enrichment.csv",
            )

            latest = store.get_latest_analysis()

            self.assertEqual(latest["id"], run_id)
            self.assertEqual(latest["dataset_type"], "asin")
            self.assertEqual(latest["analysis"]["products"][0]["asin"], "B001")

    def test_creates_concept_with_benchmark_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProductLabStore(Path(directory) / "lab.db")

            concept = store.create_concept(
                {
                    "name": "Dog leash concept",
                    "target_customer": "large dog owners",
                    "pain_point": "hands-free control",
                    "differentiation": "replaceable wrist strap",
                    "target_price": 29.99,
                    "benchmarks": [{"asin": "B001", "title": "Reference", "opportunity_score": 80}],
                }
            )

            restored = store.get_concept(concept["id"])
            self.assertEqual(restored["status"], "idea")
            self.assertEqual(restored["benchmarks"][0]["asin"], "B001")

    def test_keeps_profit_snapshot_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProductLabStore(Path(directory) / "lab.db")
            concept = store.create_concept(
                {"name": "Concept", "target_customer": "buyer", "pain_point": "pain", "differentiation": "difference", "target_price": 30, "benchmarks": []}
            )

            store.add_profit_snapshot(concept["id"], {"base": {"profit": 5, "margin": 0.16}})
            store.add_profit_snapshot(concept["id"], {"base": {"profit": 7, "margin": 0.23}})

            restored = store.get_concept(concept["id"])
            self.assertEqual(len(restored["profit_snapshots"]), 2)
            self.assertEqual(restored["profit_snapshots"][0]["base"]["profit"], 7)

    def test_rejects_approved_listing_without_image_rights(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProductLabStore(Path(directory) / "lab.db")
            concept = store.create_concept(
                {"name": "Concept", "target_customer": "buyer", "pain_point": "pain", "differentiation": "difference", "target_price": 30, "benchmarks": []}
            )

            with self.assertRaisesRegex(ValueError, "图片授权"):
                store.add_listing_version(
                    concept["id"],
                    {
                        "title": "Approved title",
                        "bullet_points": ["Evidence-backed benefit"],
                        "description": "Description",
                        "search_terms": "keyword",
                        "evidence": "Supplier specification",
                        "image_paths": ["images/main.jpg"],
                        "image_rights_confirmed": False,
                        "approved": True,
                    },
                )

    def test_records_status_decision_history(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProductLabStore(Path(directory) / "lab.db")
            concept = store.create_concept(
                {"name": "Concept", "target_customer": "buyer", "pain_point": "pain", "differentiation": "difference", "target_price": 30, "benchmarks": []}
            )

            restored = store.set_status(concept["id"], "sourcing", "开始询价")

            self.assertEqual(restored["decision_events"][0]["from_status"], "idea")
            self.assertEqual(restored["decision_events"][0]["to_status"], "sourcing")
            self.assertEqual(restored["decision_events"][0]["reason"], "开始询价")

    def test_rejects_unsafe_supplier_url(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProductLabStore(Path(directory) / "lab.db")
            concept = store.create_concept(
                {"name": "Concept", "target_customer": "buyer", "pain_point": "pain", "differentiation": "difference", "target_price": 30, "benchmarks": []}
            )

            with self.assertRaisesRegex(ValueError, "http/https"):
                store.add_supplier_quote(
                    concept["id"],
                    {"supplier_name": "Supplier", "product_url": "javascript:alert(1)", "unit_cost": 2},
                )


if __name__ == "__main__":
    unittest.main()
