from __future__ import annotations

from typing import Any


REQUIRED_PROFIT_FIELDS = (
    "sale_price", "landed_cost", "fba_fee", "referral_fee_rate", "storage_cost",
    "return_rate", "return_loss_rate", "conversion_rate", "cpc",
)


def _scenario(inputs: dict[str, Any], mode: str) -> dict[str, float]:
    price = float(inputs["sale_price"])
    conversion = float(inputs["conversion_rate"])
    cpc = float(inputs["cpc"])
    return_rate = float(inputs["return_rate"])
    storage = float(inputs["storage_cost"])
    if conversion <= 0:
        raise ValueError("conversion_rate 必须大于 0")
    if mode == "optimistic":
        conversion *= 1.15
        cpc *= 0.85
        return_rate *= 0.80
    elif mode == "pessimistic":
        price *= 0.90
        conversion *= 0.85
        cpc *= 1.30
        return_rate *= 1.50
        storage *= 1.20
    referral = price * float(inputs["referral_fee_rate"])
    return_loss = price * return_rate * float(inputs["return_loss_rate"])
    ad_cost = cpc / conversion
    profit = (
        price - float(inputs["landed_cost"]) - float(inputs["fba_fee"])
        - referral - storage - return_loss - ad_cost
    )
    return {
        "price": round(price, 5),
        "ad_cost_per_order": round(ad_cost, 5),
        "expected_return_loss": round(return_loss, 5),
        "profit": round(profit, 5),
        "margin": round(profit / price, 5),
    }


def calculate_profit_snapshot(inputs: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_PROFIT_FIELDS if inputs.get(field) in (None, "")]
    if missing:
        raise ValueError(f"缺少利润字段: {', '.join(missing)}")
    scenarios = {mode: _scenario(inputs, mode) for mode in ("optimistic", "base", "pessimistic")}
    base = scenarios["base"]
    price = float(inputs["sale_price"])
    target_profit = price * 0.15
    max_landed_cost = float(inputs["landed_cost"]) + base["profit"] - target_profit
    red_flags = []
    if str(inputs.get("compliance_risk", "unknown")).lower() == "high":
        red_flags.append("high_compliance_risk")
    if str(inputs.get("ip_risk", "unknown")).lower() == "high":
        red_flags.append("high_ip_risk")
    if bool(inputs.get("hazmat")):
        red_flags.append("hazmat")
    if base["margin"] < 0.15:
        red_flags.append("base_margin_below_15_percent")
    return {
        "scenarios": scenarios,
        "max_landed_cost_at_15_percent_margin": round(max_landed_cost, 5),
        "red_flags": red_flags,
        "approval_allowed": not red_flags,
    }


def validate_status_transition(
    current_status: str,
    next_status: str,
    latest_profit: dict[str, Any] | None,
    has_approved_listing: bool,
) -> None:
    allowed = {
        "idea": {"sourcing", "quoted"},
        "sourcing": {"quoted"},
        "quoted": {"approved"},
        "approved": {"listing_ready", "launch_ready"},
        "listing_ready": {"launch_ready"},
        "launch_ready": {"launched"},
        "launched": {"reviewing"},
        "reviewing": {"scale", "stop"},
        "scale": set(),
        "stop": set(),
    }
    if next_status not in allowed.get(current_status, set()):
        raise ValueError(f"不允许从 {current_status} 进入 {next_status}")
    if next_status == "approved":
        if not latest_profit or latest_profit.get("red_flags"):
            raise ValueError("利润或风险红线未通过，不能批准")
        if latest_profit["scenarios"]["base"]["margin"] < 0.15:
            raise ValueError("利润或风险红线未通过，不能批准")
    if next_status in {"listing_ready", "launch_ready"} and current_status not in {
        "approved", "listing_ready", "launch_ready"
    }:
        raise ValueError("产品方案尚未批准")
    if next_status == "launch_ready" and not has_approved_listing:
        raise ValueError("Listing 尚未人工批准")


def calculate_actual_result(inputs: dict[str, Any]) -> dict[str, Any]:
    required = (
        "units_sold", "revenue", "product_cost", "fba_fees", "referral_fees",
        "storage_cost", "ad_spend", "return_loss", "other_cost",
    )
    missing = [field for field in required if inputs.get(field) in (None, "")]
    if missing:
        raise ValueError(f"缺少实验结果字段: {', '.join(missing)}")
    revenue = float(inputs["revenue"])
    costs = sum(float(inputs[field]) for field in required[2:])
    profit = revenue - costs
    return {
        **{field: float(inputs[field]) for field in required},
        "contribution_profit": round(profit, 5),
        "contribution_margin": round(profit / revenue, 5) if revenue else 0.0,
        "profit_per_unit": round(profit / float(inputs["units_sold"]), 5)
        if float(inputs["units_sold"]) else 0.0,
    }


def build_launch_package(concept: dict[str, Any], inventory_quantity: int) -> dict[str, Any]:
    if concept.get("status") not in {"approved", "listing_ready", "launch_ready"}:
        raise ValueError("产品方案尚未通过批准")
    if not concept.get("sku"):
        raise ValueError("缺少 SKU")
    snapshots = concept.get("profit_snapshots", [])
    listings = [item for item in concept.get("listing_versions", []) if item.get("approved")]
    if not snapshots or snapshots[0].get("red_flags"):
        raise ValueError("利润或风险红线未通过")
    if not listings:
        raise ValueError("Listing 尚未人工批准")
    latest_listing = listings[0]
    return {
        "concept_id": concept["id"],
        "sku": concept["sku"],
        "product_name": concept["name"],
        "target_price": concept["target_price"],
        "inventory_quantity": int(inventory_quantity),
        "listing": {
            "title": latest_listing["title"],
            "bullet_points": latest_listing["bullet_points"],
            "description": latest_listing["description"],
            "search_terms": latest_listing["search_terms"],
            "image_paths": latest_listing["image_paths"],
        },
        "evidence": latest_listing["evidence"],
        "profit": snapshots[0],
        "risk": {
            "compliance_risk": concept["compliance_risk"],
            "ip_risk": concept["ip_risk"],
            "hazmat": concept["hazmat"],
        },
        "benchmarks": concept.get("benchmarks", []),
        "manual_publish_required": True,
    }
