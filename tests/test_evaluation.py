import unittest

from amazon_product_lab.evaluation import evaluate_candidate


class EvaluateCandidateTests(unittest.TestCase):
    def setUp(self):
        self.candidate = {
            "opportunity_id": "US-001",
            "marketplace": "US",
            "niche": "drawer organizer",
            "sale_price": 29.99,
            "landed_cost": 7.0,
            "fba_fee": 5.5,
            "referral_fee_rate": 0.15,
            "storage_cost": 0.5,
            "return_rate": 0.05,
            "return_loss_rate": 0.5,
            "conversion_rate": 0.12,
            "cpc": 1.2,
            "demand_score": 82,
            "competition_score": 75,
            "differentiation_score": 80,
            "supply_chain_score": 85,
            "operability_score": 70,
            "compliance_risk": "low",
            "ip_risk": "low",
            "hazmat": False,
            "seasonal": False,
        }

    def test_calculates_base_contribution_profit(self):
        result = evaluate_candidate(self.candidate)

        self.assertAlmostEqual(result["scenarios"]["base"]["profit"], 1.74175, places=5)
        self.assertAlmostEqual(result["scenarios"]["base"]["margin"], 0.05808, places=5)

    def test_rejects_candidate_with_high_compliance_risk(self):
        self.candidate["compliance_risk"] = "high"

        result = evaluate_candidate(self.candidate)

        self.assertEqual(result["decision"], "reject")
        self.assertIn("high_compliance_risk", result["red_flags"])

    def test_rejects_candidate_when_base_margin_is_below_floor(self):
        result = evaluate_candidate(self.candidate)

        self.assertEqual(result["decision"], "reject")
        self.assertIn("base_margin_below_15_percent", result["red_flags"])

    def test_sends_high_scoring_profitable_candidate_to_sampling(self):
        self.candidate.update({"sale_price": 39.99, "cpc": 0.45})

        result = evaluate_candidate(self.candidate)

        self.assertGreaterEqual(result["score"], 80)
        self.assertEqual(result["decision"], "sample")

    def test_rejects_zero_conversion_rate(self):
        self.candidate["conversion_rate"] = 0

        with self.assertRaisesRegex(ValueError, "conversion_rate"):
            evaluate_candidate(self.candidate)

    def test_rejects_component_score_above_100(self):
        self.candidate["demand_score"] = 101

        with self.assertRaisesRegex(ValueError, "demand_score"):
            evaluate_candidate(self.candidate)


if __name__ == "__main__":
    unittest.main()
