from __future__ import annotations

from typing import Any


def render_markdown(results: list[dict[str, Any]]) -> str:
    ranked = sorted(results, key=lambda item: item["score"], reverse=True)
    lines = [
        "# Amazon Product Opportunity Report",
        "",
        "| Rank | Opportunity | Niche | Score | Decision | Base profit | Base margin | Flags |",
        "|---:|---|---|---:|---|---:|---:|---|",
    ]
    for rank, result in enumerate(ranked, start=1):
        base = result["scenarios"]["base"]
        flags = ", ".join(result["red_flags"]) or "-"
        lines.append(
            f"| {rank} | {result['opportunity_id']} | {result['niche']} | "
            f"{result['score']:.2f} | {result['decision']} | ${base['profit']:.2f} | "
            f"{base['margin']:.1%} | {flags} |"
        )
    lines.append("")
    return "\n".join(lines)
