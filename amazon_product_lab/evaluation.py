from __future__ import annotations

from typing import Any


WEIGHTS = {
    "demand_score": 0.20,
    "competition_score": 0.20,
    "differentiation_score": 0.20,
    "economic_score": 0.20,
    "supply_chain_score": 0.10,
    "operability_score": 0.10,
}


def _validate_candidate(candidate: dict[str, Any]) -> None:
    if float(candidate["conversion_rate"]) <= 0:
        raise ValueError("conversion_rate must be greater than zero")
    for field in (
        "demand_score",
        "competition_score",
        "differentiation_score",
        "supply_chain_score",
        "operability_score",
    ):
        value = float(candidate[field])
        if not 0 <= value <= 100:
            raise ValueError(f"{field} must be between 0 and 100")


def _scenario(candidate: dict[str, Any], mode: str) -> dict[str, float]:
    price = float(candidate["sale_price"])
    conversion = float(candidate["conversion_rate"])
    cpc = float(candidate["cpc"])
    return_rate = float(candidate["return_rate"])
    storage_cost = float(candidate["storage_cost"])

    if mode == "optimistic":
        conversion *= 1.15
        cpc *= 0.85
        return_rate *= 0.80
    elif mode == "pessimistic":
        price *= 0.90
        conversion *= 0.85
        cpc *= 1.30
        return_rate *= 1.50
        storage_cost *= 1.20

    referral_fee = price * float(candidate["referral_fee_rate"])
    expected_return_loss = price * return_rate * float(candidate["return_loss_rate"])
    ad_cost_per_order = cpc / conversion
    profit = (
        price
        - float(candidate["landed_cost"])
        - float(candidate["fba_fee"])
        - referral_fee
        - storage_cost
        - expected_return_loss
        - ad_cost_per_order
    )

    return {
        "price": round(price, 5),
        "ad_cost_per_order": round(ad_cost_per_order, 5),
        "profit": round(profit, 5),
        "margin": round(profit / price, 5),
    }


def evaluate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    _validate_candidate(candidate)
    scenarios = {
        mode: _scenario(candidate, mode)
        for mode in ("optimistic", "base", "pessimistic")
    }
    base_margin = scenarios["base"]["margin"]
    economic_score = max(0.0, min(100.0, base_margin * 400.0))

    component_scores = {
        key: economic_score if key == "economic_score" else float(candidate[key])
        for key in WEIGHTS
    }
    score = sum(component_scores[key] * weight for key, weight in WEIGHTS.items())

    red_flags: list[str] = []
    if str(candidate.get("compliance_risk", "")).lower() == "high":
        red_flags.append("high_compliance_risk")
    if str(candidate.get("ip_risk", "")).lower() == "high":
        red_flags.append("high_ip_risk")
    if bool(candidate.get("hazmat")):
        red_flags.append("hazmat")
    if base_margin < 0.15:
        red_flags.append("base_margin_below_15_percent")

    if red_flags:
        decision = "reject"
    elif score >= 80:
        decision = "sample"
    elif score >= 65:
        decision = "watch"
    else:
        decision = "reject"

    return {
        "opportunity_id": candidate["opportunity_id"],
        "niche": candidate["niche"],
        "score": round(score, 2),
        "decision": decision,
        "red_flags": red_flags,
        "component_scores": {key: round(value, 2) for key, value in component_scores.items()},
        "scenarios": scenarios,
    }
