from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_falcon_importer import validate_local_falcon_summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a local_falcon_summary.v2 output file and print per-keyword integrity details."
    )
    parser.add_argument("--file", required=True, help="Path to local-falcon-summary.json.")
    args = parser.parse_args()

    path = Path(args.file)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Local Falcon summary validation failed safely: {exc}", file=sys.stderr)
        return 1

    result = validate_local_falcon_summary(payload, path)
    print("Validated Local Falcon summary output")
    print(f"Profile: {result.profile or 'unknown'}")
    print(f"Output: {result.output_path}")
    print(f"Keyword scans: {result.keyword_scan_count}")
    print(f"Featured: {_redact_ai_scan_id(result.featured_keyword_id) or 'none'}")
    print(f"Strongest: {_redact_ai_scan_id(result.strongest_keyword_id) or 'none'}")
    print(f"Weakest: {_redact_ai_scan_id(result.weakest_keyword_id) or 'none'}")
    for item in result.keyword_summaries:
        grid = item["rendered_grid"]
        label = item.get("keyword") or item.get("id") or "unknown"
        if item.get("query_type") == "ai_visibility_prompt":
            label = _redact_prompt_label(str(label))
        print(
            "Keyword: "
            f"{label} | "
            f"total={item['total']}, found={item['found']}, "
            f"top_3={item['top_3']}, top_10={item['top_10']}, "
            f"weak={item['weak_or_not_found']} | "
            f"rendered_grid={grid['rows']}x{grid['columns']} | "
            f"grid_points={item['grid_point_count']} | "
            f"competitors={item['competitor_count']} | "
            f"AI={'yes' if item['ai_analysis_available'] else 'no'} | "
            f"action_bridge={item['action_bridge_count']}"
        )
    for warning in result.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    return 0


def _redact_prompt_label(value: str) -> str:
    text = " ".join(value.split())
    if not text:
        return "[redacted AI prompt]"
    return f"{text[:18]}... [redacted AI prompt]"


def _redact_ai_scan_id(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith(("chatgpt-", "google-ai-overviews-", "google-ai-overview-")):
        return "[redacted AI visibility scan]"
    return value


if __name__ == "__main__":
    raise SystemExit(main())
