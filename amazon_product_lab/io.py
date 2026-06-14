from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


TEXT_FIELDS = {
    "opportunity_id",
    "marketplace",
    "niche",
    "compliance_risk",
    "ip_risk",
}
BOOLEAN_FIELDS = {"hazmat", "seasonal"}
NUMBER_FIELDS = {
    "sale_price",
    "landed_cost",
    "fba_fee",
    "referral_fee_rate",
    "storage_cost",
    "return_rate",
    "return_loss_rate",
    "conversion_rate",
    "cpc",
    "demand_score",
    "competition_score",
    "differentiation_score",
    "supply_chain_score",
    "operability_score",
}
REQUIRED_FIELDS = TEXT_FIELDS | BOOLEAN_FIELDS | NUMBER_FIELDS


def _parse_bool(value: str, field: str, row_number: int) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"row {row_number}: {field} must be true or false")


def load_candidates(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required fields: {', '.join(sorted(missing))}")

        candidates = []
        for row_number, row in enumerate(reader, start=2):
            candidate: dict[str, Any] = {}
            for field in TEXT_FIELDS:
                value = (row.get(field) or "").strip()
                if not value:
                    raise ValueError(f"row {row_number}: {field} is required")
                candidate[field] = value
            for field in NUMBER_FIELDS:
                try:
                    candidate[field] = float(row[field])
                except (TypeError, ValueError):
                    raise ValueError(f"row {row_number}: {field} must be a number") from None
            for field in BOOLEAN_FIELDS:
                candidate[field] = _parse_bool(row[field], field, row_number)
            candidates.append(candidate)

    if not candidates:
        raise ValueError("CSV contains no candidates")
    return candidates
