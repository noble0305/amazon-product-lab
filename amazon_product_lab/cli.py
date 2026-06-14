from __future__ import annotations

import argparse
import json
from pathlib import Path

from .evaluation import evaluate_candidate
from .io import load_candidates
from .opportunity_import import (
    analyze_opportunity_export,
    is_opportunity_export,
    write_opportunity_outputs,
)
from .reporting import render_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Amazon product opportunities from CSV")
    parser.add_argument("input", type=Path, help="Input CSV file")
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()

    if is_opportunity_export(args.input):
        analysis = analyze_opportunity_export(args.input)
        write_opportunity_outputs(analysis, args.output_dir)
        print(
            f"Analyzed {len(analysis['markets'])} markets. "
            f"Screening reports saved to {args.output_dir}"
        )
        return

    candidates = load_candidates(args.input)
    results = [evaluate_candidate(candidate) for candidate in candidates]
    ranked = sorted(results, key=lambda item: item["score"], reverse=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "report.json").write_text(
        json.dumps(ranked, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "report.md").write_text(render_markdown(ranked), encoding="utf-8")
    print(f"Evaluated {len(ranked)} candidates. Reports saved to {args.output_dir}")


if __name__ == "__main__":
    main()
