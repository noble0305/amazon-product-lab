from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


COLUMNS = {
    "niche": "细分市场",
    "keyword_1": "热门搜索词 1",
    "keyword_2": "热门搜索词 2",
    "keyword_3": "热门搜索词 3",
    "search_volume_360d": "搜索量（过去 360 天内）",
    "search_growth_180d": "搜索量增长（过去 180 天）",
    "search_volume_90d": "搜索量（过去 90 天内）",
    "search_growth_90d": "搜索量增长（过去 90 天内）",
    "top_clicked_product_count": "点击量最多的商品数量",
    "average_price": "平均价格 (USD)",
    "return_rate": "退货率 (过去 360 天)",
}


def is_opportunity_export(path: str | Path) -> bool:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return any(COLUMNS["niche"] in row for _, row in zip(range(10), csv.reader(handle)))


def _read_export(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))

    header_index = next(
        (index for index, row in enumerate(rows) if COLUMNS["niche"] in row),
        None,
    )
    if header_index is None:
        raise ValueError("未找到商机探测器表头：细分市场")

    header = rows[header_index]
    missing = set(COLUMNS.values()) - set(header)
    if missing:
        raise ValueError(f"缺少商机探测器字段: {', '.join(sorted(missing))}")

    records = []
    for row_number, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not row or not any(value.strip() for value in row):
            continue
        record = dict(zip(header, row))
        if not record.get(COLUMNS["niche"], "").strip():
            raise ValueError(f"row {row_number}: 细分市场不能为空")
        records.append(record)
    if not records:
        raise ValueError("商机探测器 CSV 没有数据")
    return records


def _number(record: dict[str, str], key: str, row_number: int) -> float:
    column = COLUMNS[key]
    try:
        return float(record[column])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"row {row_number}: {column} 必须是数字") from None


def _percentile_scores(values: list[float]) -> list[float]:
    if len(values) == 1:
        return [100.0]
    ordered = sorted(values)
    positions: dict[float, list[int]] = {}
    for index, value in enumerate(ordered):
        positions.setdefault(value, []).append(index)
    return [
        100.0 * sum(positions[value]) / len(positions[value]) / (len(values) - 1)
        for value in values
    ]


def _price_fit_score(price: float) -> float:
    if 20 <= price <= 50:
        return 100.0
    if 15 <= price < 20 or 50 < price <= 60:
        return 60.0
    return 20.0


def _return_score(return_rate: float) -> float:
    return max(0.0, min(100.0, 100.0 * (1.0 - return_rate / 0.15)))


def risk_review_flags(niche: str) -> list[str]:
    value = niche.lower()
    rules = (
        ("pest_control_review", ("flea", "tick", "pesticide", "insecticide", "repellent")),
        (
            "ingestible_review",
            (
                "food",
                "vitamin",
                "multivitamin",
                "supplement",
                "probiotic",
                "mealworm",
                "treat",
                "chew",
                "churro",
            ),
        ),
        ("privacy_review", ("hidden camera", "spy camera", "surveillance")),
    )
    return [
        flag
        for flag, terms in rules
        if any(re.search(rf"\b{re.escape(term)}", value) for term in terms)
    ]


def _source_date(path: Path) -> str | None:
    match = re.search(r"(20\d{2})[_-](\d{1,2})[_-](\d{1,2})", path.stem)
    if not match:
        return None
    year, month, day = (int(value) for value in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def analyze_opportunity_export(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    raw_records = _read_export(source)
    records = []
    for row_number, raw in enumerate(raw_records, start=1):
        records.append(
            {
                "niche": raw[COLUMNS["niche"]].strip(),
                "keywords": [raw[COLUMNS[key]].strip() for key in ("keyword_1", "keyword_2", "keyword_3")],
                **{
                    key: _number(raw, key, row_number)
                    for key in (
                        "search_volume_360d",
                        "search_growth_180d",
                        "search_volume_90d",
                        "search_growth_90d",
                        "top_clicked_product_count",
                        "average_price",
                        "return_rate",
                    )
                },
            }
        )

    metrics = {
        key: _percentile_scores([record[key] for record in records])
        for key in (
            "search_volume_360d",
            "search_volume_90d",
            "search_growth_180d",
            "search_growth_90d",
            "top_clicked_product_count",
        )
    }
    markets = []
    for index, record in enumerate(records):
        demand_score = (
            metrics["search_volume_360d"][index] * 0.30
            + metrics["search_volume_90d"][index] * 0.25
            + metrics["search_growth_180d"][index] * 0.20
            + metrics["search_growth_90d"][index] * 0.25
        )
        click_breadth_score = metrics["top_clicked_product_count"][index]
        price_fit_score = _price_fit_score(record["average_price"])
        return_score = _return_score(record["return_rate"])
        screening_score = (
            demand_score * 0.50
            + click_breadth_score * 0.20
            + price_fit_score * 0.15
            + return_score * 0.15
        )
        review_flags = risk_review_flags(record["niche"])
        review_penalty = min(25.0, 15.0 * len(review_flags))
        markets.append(
            {
                **record,
                "demand_score": round(demand_score, 2),
                "click_breadth_score": round(click_breadth_score, 2),
                "price_fit_score": round(price_fit_score, 2),
                "return_score": round(return_score, 2),
                "raw_screening_score": round(screening_score, 2),
                "risk_review_penalty": review_penalty,
                "screening_score": round(max(0.0, screening_score - review_penalty), 2),
                "manual_review_flags": review_flags,
                "analysis_stage": "demand_screening",
                "next_action": "complete_cost_and_risk_data",
            }
        )

    markets.sort(key=lambda item: item["screening_score"], reverse=True)
    for rank, market in enumerate(markets, start=1):
        market["rank"] = rank

    return {
        "source": {
            "file": source.name,
            "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "collection_date": _source_date(source),
            "data_rows": len(markets),
        },
        "method": {
            "stage": "demand_screening",
            "warning": "未包含成本、广告、合规和侵权数据，不构成采购或利润决策",
        },
        "markets": markets,
    }


ENRICHMENT_FIELDS = [
    "opportunity_id",
    "marketplace",
    "niche",
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
    "compliance_risk",
    "ip_risk",
    "hazmat",
    "seasonal",
    "screening_rank",
    "screening_score",
    "source_file",
    "source_date",
    "source_sha256",
    "manual_review_flags",
]


def _render_market_markdown(analysis: dict[str, Any], limit: int = 50) -> str:
    source = analysis["source"]
    lines = [
        "# 商机探测器需求侧初筛报告",
        "",
        f"- 来源文件：`{source['file']}`",
        f"- 数据日期：{source['collection_date'] or '未提供'}",
        f"- 数据行数：{source['data_rows']}",
        f"- 文件 SHA-256：`{source['sha256']}`",
        "- 重要限制：未包含成本、广告、合规和侵权数据，不构成采购或利润决策。",
        "",
        "| 排名 | 细分市场 | 初筛分 | 需求分 | 点击广度 | 均价 | 90天增长 | 退货率 | 风险复核提示 |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for market in analysis["markets"][:limit]:
        niche = market["niche"].replace("|", "\\|")
        lines.append(
            f"| {market['rank']} | {niche} | {market['screening_score']:.2f} | "
            f"{market['demand_score']:.2f} | {market['click_breadth_score']:.2f} | "
            f"${market['average_price']:.2f} | {market['search_growth_90d']:.1%} | "
            f"{market['return_rate']:.1%} | {', '.join(market['manual_review_flags']) or '-'} |"
        )
    lines.extend(
        [
            "",
            "## 评分口径",
            "",
            "初筛分 = 需求信号 50% + 点击商品广度 20% + 目标价格带匹配 15% + 低退货率 15%。",
            "需求和点击广度按本次导出数据的百分位计算，用于同批候选相对排序。",
            "明显涉及食用、驱虫或隐私监控的关键词只作为人工复核提示，并对初筛分保守降权，不代表最终合规结论。",
            "",
        ]
    )
    return "\n".join(lines)


def write_opportunity_outputs(
    analysis: dict[str, Any], output_dir: str | Path, enrichment_limit: int = 30
) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "market_report.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "market_report.md").write_text(
        _render_market_markdown(analysis),
        encoding="utf-8",
    )

    source = analysis["source"]
    with (output / "candidate_enrichment.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=ENRICHMENT_FIELDS)
        writer.writeheader()
        for market in analysis["markets"][:enrichment_limit]:
            writer.writerow(
                {
                    "opportunity_id": f"AMZ-{market['rank']:03d}",
                    "marketplace": "US",
                    "niche": market["niche"],
                    "sale_price": market["average_price"],
                    "return_rate": market["return_rate"],
                    "demand_score": market["demand_score"],
                    "screening_rank": market["rank"],
                    "screening_score": market["screening_score"],
                    "source_file": source["file"],
                    "source_date": source["collection_date"] or "",
                    "source_sha256": source["sha256"],
                    "manual_review_flags": ",".join(market["manual_review_flags"]),
                }
            )
