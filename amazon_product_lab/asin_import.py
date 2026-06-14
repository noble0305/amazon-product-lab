from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

from .opportunity_import import risk_review_flags


ASIN_COLUMNS = {
    "title": "商品名称",
    "asin": "ASIN",
    "brand": "品牌",
    "category": "类别",
    "launch_date": "发布日期",
    "search_clicks_360d": "搜索点击量（过去 360 天）",
    "average_price_90d": "平均售价（过去 90 天）(USD)",
    "average_price_360d": "平均售价（过去 360 天）(USD)",
    "review_count": "总评价数",
    "rating": "平均评分",
    "bsr": "平均畅销排名 (BSR)",
    "seller_count": "销售伙伴的平均数量",
}


def is_asin_export(path: str | Path) -> bool:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return any(ASIN_COLUMNS["asin"] in row for _, row in zip(range(10), csv.reader(handle)))


def _source_date(path: Path) -> str | None:
    match = re.search(r"(20\d{2})[_-](\d{1,2})[_-](\d{1,2})", path.stem)
    if not match:
        return None
    year, month, day = (int(value) for value in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def _read_export(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    header_index = next(
        (index for index, row in enumerate(rows) if ASIN_COLUMNS["asin"] in row),
        None,
    )
    if header_index is None:
        raise ValueError("未找到 ASIN Explorer 表头：ASIN")
    header = rows[header_index]
    missing = set(ASIN_COLUMNS.values()) - set(header)
    if missing:
        raise ValueError(f"缺少 ASIN Explorer 字段: {', '.join(sorted(missing))}")
    records = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not row or not any(value.strip() for value in row):
            continue
        record = dict(zip(header, row))
        if not record.get(ASIN_COLUMNS["asin"], "").strip():
            raise ValueError(f"row {row_number}: ASIN 不能为空")
        records.append(record)
    if not records:
        raise ValueError("ASIN Explorer CSV 没有数据")
    return records


def _optional_number(record: dict[str, str], key: str, zero_is_missing: bool = False) -> float | None:
    value = record.get(ASIN_COLUMNS[key], "").strip()
    if not value:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    if zero_is_missing and number <= 0:
        return None
    return number


def _percentiles(values: list[float | None], inverse: bool = False) -> list[float | None]:
    present = sorted(value for value in values if value is not None)
    if not present:
        return [None] * len(values)
    if len(present) == 1:
        return [100.0 if value is not None else None for value in values]
    positions: dict[float, list[int]] = {}
    for index, value in enumerate(present):
        positions.setdefault(value, []).append(index)
    scores = []
    for value in values:
        if value is None:
            scores.append(None)
            continue
        score = 100.0 * (sum(positions[value]) / len(positions[value])) / (len(present) - 1)
        scores.append(100.0 - score if inverse else score)
    return scores


def _weighted_score(components: list[tuple[float | None, float]]) -> float | None:
    available = [(score, weight) for score, weight in components if score is not None]
    if not available:
        return None
    total_weight = sum(weight for _, weight in available)
    return sum(float(score) * weight for score, weight in available) / total_weight


def _price_fit(price: float | None) -> float | None:
    if price is None:
        return None
    if 20 <= price <= 50:
        return 100.0
    if 15 <= price < 20 or 50 < price <= 60:
        return 60.0
    return 20.0


def _price_stability(price_90d: float | None, price_360d: float | None) -> float | None:
    if price_90d is None or price_360d is None or price_360d <= 0:
        return None
    change = abs(price_90d - price_360d) / price_360d
    return max(0.0, 100.0 - change * 400.0)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def analyze_asin_export(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    raw_records = _read_export(source)
    collection_date_text = _source_date(source)
    collection_date = date.fromisoformat(collection_date_text) if collection_date_text else None
    products = []
    for raw in raw_records:
        rating = _optional_number(raw, "rating", zero_is_missing=True)
        bsr = _optional_number(raw, "bsr", zero_is_missing=True)
        seller_count = _optional_number(raw, "seller_count", zero_is_missing=True)
        launch_text = raw[ASIN_COLUMNS["launch_date"]].strip()
        launch_date = _parse_date(launch_text)
        clicks = _optional_number(raw, "search_clicks_360d", zero_is_missing=True)
        reviews = _optional_number(raw, "review_count")
        price_90d = _optional_number(raw, "average_price_90d", zero_is_missing=True)
        price_360d = _optional_number(raw, "average_price_360d", zero_is_missing=True)
        age_days = (
            max(1, (collection_date - launch_date).days)
            if collection_date and launch_date and launch_date <= collection_date
            else None
        )
        traction = (
            clicks / (1.0 + math.log1p(max(0.0, reviews)))
            if clicks is not None and reviews is not None
            else None
        )
        products.append(
            {
                "title": raw[ASIN_COLUMNS["title"]].strip(),
                "asin": raw[ASIN_COLUMNS["asin"]].strip(),
                "brand": raw[ASIN_COLUMNS["brand"]].strip(),
                "category": raw[ASIN_COLUMNS["category"]].strip(),
                "launch_date": launch_text or None,
                "age_days": age_days,
                "search_clicks_360d": clicks,
                "average_price_90d": price_90d,
                "average_price_360d": price_360d,
                "review_count": reviews,
                "rating": rating,
                "bsr": bsr,
                "seller_count": seller_count,
                "traction_efficiency": traction,
            }
        )

    click_scores = _percentiles([item["search_clicks_360d"] for item in products])
    bsr_scores = _percentiles([item["bsr"] for item in products], inverse=True)
    review_scores = _percentiles([item["review_count"] for item in products], inverse=True)
    traction_scores = _percentiles([item["traction_efficiency"] for item in products])
    rating_gap_scores = _percentiles([item["rating"] for item in products], inverse=True)

    for index, product in enumerate(products):
        demand_score = _weighted_score([(click_scores[index], 0.70), (bsr_scores[index], 0.30)])
        competition_score = _weighted_score(
            [(review_scores[index], 0.65), (traction_scores[index], 0.35)]
        )
        differentiation_score = _weighted_score(
            [
                (rating_gap_scores[index], 0.60),
                (_price_stability(product["average_price_90d"], product["average_price_360d"]), 0.40),
            ]
        )
        price_score = _price_fit(product["average_price_90d"])
        completeness_fields = (
            "search_clicks_360d", "average_price_90d", "average_price_360d",
            "review_count", "rating", "bsr", "seller_count",
        )
        completeness = 100.0 * sum(product[field] is not None for field in completeness_fields) / len(completeness_fields)
        raw_score = _weighted_score(
            [
                (demand_score, 0.35),
                (competition_score, 0.30),
                (differentiation_score, 0.20),
                (price_score, 0.15),
            ]
        ) or 0.0
        has_demand_evidence = demand_score is not None
        confidence_adjusted = (
            raw_score * (0.60 + 0.40 * completeness / 100.0)
            if has_demand_evidence
            else 0.0
        )
        review_flags = risk_review_flags(f"{product['title']} {product['category']}")
        penalty = min(25.0, 15.0 * len(review_flags))
        data_flags = []
        if product["search_clicks_360d"] is None and product["bsr"] is None:
            data_flags.append("missing_demand_data")
        if product["average_price_90d"] is None:
            data_flags.append("missing_price_data")
        product.update(
            {
                "demand_score": round(demand_score, 2) if demand_score is not None else None,
                "competition_score": round(competition_score, 2) if competition_score is not None else None,
                "differentiation_score": round(differentiation_score, 2) if differentiation_score is not None else None,
                "price_space_score": round(price_score, 2) if price_score is not None else None,
                "raw_opportunity_score": round(raw_score, 2),
                "data_completeness": round(completeness, 2),
                "risk_review_penalty": penalty,
                "opportunity_score": round(max(0.0, confidence_adjusted - penalty), 2),
                "manual_review_flags": review_flags,
                "data_flags": data_flags,
                "analysis_stage": "product_opportunity_screening",
                "next_action": (
                    "complete_cost_and_logistics_data"
                    if has_demand_evidence
                    else "collect_demand_data"
                ),
            }
        )

    products.sort(key=lambda item: item["opportunity_score"], reverse=True)
    for rank, product in enumerate(products, start=1):
        product["rank"] = rank
    return {
        "source": {
            "file": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "collection_date": collection_date_text,
            "data_rows": len(products),
        },
        "method": {
            "stage": "product_opportunity_screening",
            "warning": "仅评估需求、竞争、差异化和价格空间；缺少成本、物流、广告和转化数据，不构成利润结论",
        },
        "products": products,
    }


PRODUCT_ENRICHMENT_FIELDS = [
    "asin", "title", "brand", "category", "sale_price", "landed_cost", "fba_fee",
    "referral_fee_rate", "storage_cost", "return_rate", "return_loss_rate",
    "conversion_rate", "cpc", "package_length_in", "package_width_in",
    "package_height_in", "shipping_weight_lb", "compliance_risk", "ip_risk",
    "hazmat", "seasonal", "opportunity_rank", "opportunity_score",
    "data_completeness", "source_file", "source_date", "source_sha256",
]


def _render_markdown(analysis: dict[str, Any], limit: int = 50) -> str:
    source = analysis["source"]
    lines = [
        "# ASIN 产品机会初筛报告", "",
        f"- 来源文件：`{source['file']}`", f"- 数据日期：{source['collection_date'] or '未提供'}",
        f"- 数据行数：{source['data_rows']}", f"- 文件 SHA-256：`{source['sha256']}`",
        "- 重要限制：缺少成本、物流、广告和转化数据，不构成利润结论。", "",
        "| 排名 | ASIN | 商品 | 机会分 | 完整度 | 点击量 | 评价数 | 均价 | 评分 | BSR | 风险提示 |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in analysis["products"][:limit]:
        title = item["title"].replace("|", "\\|")
        lines.append(
            f"| {item['rank']} | {item['asin']} | {title} | {item['opportunity_score']:.2f} | "
            f"{item['data_completeness']:.0f}% | {item['search_clicks_360d'] or '-'} | "
            f"{item['review_count'] if item['review_count'] is not None else '-'} | "
            f"{('$%.2f' % item['average_price_90d']) if item['average_price_90d'] is not None else '-'} | "
            f"{item['rating'] or '-'} | {item['bsr'] or '-'} | "
            f"{', '.join(item['manual_review_flags']) or '-'} |"
        )
    lines.extend(["", "机会分 = 需求 35% + 竞争可进入性 30% + 差异化空间 20% + 价格空间 15%，并按数据完整度降低置信度。", ""])
    return "\n".join(lines)


def write_asin_outputs(analysis: dict[str, Any], output_dir: str | Path, limit: int = 30) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "asin_report.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "asin_report.md").write_text(_render_markdown(analysis), encoding="utf-8")
    source = analysis["source"]
    with (output / "product_enrichment.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=PRODUCT_ENRICHMENT_FIELDS)
        writer.writeheader()
        for item in analysis["products"][:limit]:
            writer.writerow(
                {
                    "asin": item["asin"], "title": item["title"], "brand": item["brand"],
                    "category": item["category"], "sale_price": item["average_price_90d"] or "",
                    "opportunity_rank": item["rank"], "opportunity_score": item["opportunity_score"],
                    "data_completeness": item["data_completeness"], "source_file": source["file"],
                    "source_date": source["collection_date"] or "", "source_sha256": source["sha256"],
                }
            )
