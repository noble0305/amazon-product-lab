import unittest

from amazon_product_lab.workflow import (
    calculate_actual_result,
    calculate_profit_snapshot,
    validate_status_transition,
)


class ProductWorkflowTests(unittest.TestCase):
    def test_calculates_three_scenarios_and_max_landed_cost(self):
        result = calculate_profit_snapshot(
            {
                "sale_price": 39.99,
                "landed_cost": 8,
                "fba_fee": 5.5,
                "referral_fee_rate": 0.15,
                "storage_cost": 0.5,
                "return_rate": 0.05,
                "return_loss_rate": 0.5,
                "conversion_rate": 0.12,
                "cpc": 0.45,
                "compliance_risk": "low",
                "ip_risk": "low",
                "hazmat": False,
            }
        )

        self.assertIn("optimistic", result["scenarios"])
        self.assertIn("base", result["scenarios"])
        self.assertIn("pessimistic", result["scenarios"])
        self.assertGreater(result["max_landed_cost_at_15_percent_margin"], 0)
        self.assertTrue(result["approval_allowed"])

    def test_blocks_approval_for_low_margin_or_high_risk(self):
        low_margin = {"scenarios": {"base": {"margin": 0.1}}, "red_flags": ["base_margin_below_15_percent"]}
        high_risk = {"scenarios": {"base": {"margin": 0.3}}, "red_flags": ["high_compliance_risk"]}

        with self.assertRaisesRegex(ValueError, "利润或风险红线"):
            validate_status_transition("quoted", "approved", low_margin, has_approved_listing=False)
        with self.assertRaisesRegex(ValueError, "利润或风险红线"):
            validate_status_transition("quoted", "approved", high_risk, has_approved_listing=False)

    def test_requires_approved_listing_before_launch_ready(self):
        snapshot = {"scenarios": {"base": {"margin": 0.3}}, "red_flags": []}

        with self.assertRaisesRegex(ValueError, "Listing"):
            validate_status_transition("approved", "launch_ready", snapshot, has_approved_listing=False)

    def test_calculates_actual_contribution_profit(self):
        result = calculate_actual_result(
            {
                "units_sold": 100,
                "revenue": 3999,
                "product_cost": 800,
                "fba_fees": 550,
                "referral_fees": 600,
                "storage_cost": 50,
                "ad_spend": 500,
                "return_loss": 100,
                "other_cost": 50,
            }
        )

        self.assertEqual(result["contribution_profit"], 1349)
        self.assertAlmostEqual(result["contribution_margin"], 1349 / 3999, places=5)


if __name__ == "__main__":
    unittest.main()
