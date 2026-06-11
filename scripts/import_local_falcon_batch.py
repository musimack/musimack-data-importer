from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_falcon_importer import (
    DEFAULT_COMPETITOR_CAP,
    LocalFalconImportError,
    import_local_falcon_csv,
    validate_local_falcon_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import a local manifest of multiple Local Falcon keyword exports into one summary JSON."
    )
    parser.add_argument("--manifest", required=True, help="Local JSON manifest path.")
    parser.add_argument("--output", help="Override manifest output path.")
    parser.add_argument("--overwrite", action="store_true", help="Replace the output file before importing the first keyword.")
    parser.add_argument(
        "--competitor-cap",
        type=int,
        help=f"Override manifest/default competitor cap. Defaults to {DEFAULT_COMPETITOR_CAP}.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        result = import_manifest(
            manifest=manifest,
            manifest_path=manifest_path,
            output_override=Path(args.output) if args.output else None,
            overwrite=args.overwrite,
            competitor_cap_override=args.competitor_cap,
        )
    except (LocalFalconImportError, OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        print(f"Local Falcon batch import failed safely: {exc}", file=sys.stderr)
        return 1

    validation = result["validation"]
    print("Imported Local Falcon batch")
    print(f"Profile: {validation.profile}")
    print(f"Output: {validation.output_path}")
    print(f"Keyword scans: {validation.keyword_scan_count}")
    print(f"Featured: {validation.featured_keyword_id or 'none'}")
    print(f"Strongest: {validation.strongest_keyword_id or 'none'}")
    print(f"Weakest: {validation.weakest_keyword_id or 'none'}")
    for item in validation.keyword_summaries:
        grid = item["rendered_grid"]
        print(
            "Keyword: "
            f"{item.get('keyword') or item.get('id') or 'unknown'} | "
            f"total={item['total']}, found={item['found']}, "
            f"top_3={item['top_3']}, top_10={item['top_10']}, "
            f"weak={item['weak_or_not_found']} | "
            f"rendered_grid={grid['rows']}x{grid['columns']} | "
            f"competitors={item['competitor_count']} | "
            f"AI={'yes' if item['ai_analysis_available'] else 'no'} | "
            f"action_bridge={item['action_bridge_count']}"
        )
    for warning in result["warnings"] + validation.warnings:
        print(f"WARN: {warning}", file=sys.stderr)
    return 0


def import_manifest(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    output_override: Path | None = None,
    overwrite: bool = False,
    competitor_cap_override: int | None = None,
) -> dict[str, Any]:
    base_dir = Path.cwd()
    profile = _required_text(manifest, "profile")
    keywords = manifest.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("manifest must include a non-empty keywords list.")

    output = output_override or _optional_path(manifest.get("output"), base_dir)
    if output is None:
        output = Path("exports") / "local-real" / "dashboard-lab" / profile / "local-falcon-summary.json"
    output = _resolve_path(output, base_dir)
    featured_keyword_id = manifest.get("featured_keyword_id")
    competitor_cap = competitor_cap_override or int(manifest.get("competitor_cap") or DEFAULT_COMPETITOR_CAP)
    business_name = manifest.get("business_name")
    warnings: list[str] = []
    if len(keywords) > 10:
        warnings.append("More than 10 keyword exports are in the manifest; dashboard setup normally uses 5 to 10.")

    for index, item in enumerate(keywords):
        if not isinstance(item, dict):
            raise ValueError("each manifest keyword entry must be an object.")
        import_local_falcon_csv(
            profile=profile,
            keyword=_required_text(item, "keyword"),
            business_name=item.get("business_name") or business_name,
            scan_report_path=_resolve_path(_required_text(item, "scan_report"), base_dir),
            data_points_path=_resolve_path(_required_text(item, "data_points"), base_dir),
            ai_analysis_path=_optional_path(item.get("ai_analysis"), base_dir),
            output_path=output,
            featured_keyword_id=str(featured_keyword_id) if featured_keyword_id else None,
            overwrite=overwrite and index == 0,
            competitor_cap=competitor_cap,
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    return {
        "output": output,
        "validation": validate_local_falcon_summary(payload, output),
        "warnings": warnings,
    }


def _required_text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"manifest field is required: {key}")
    return value


def _optional_path(value: Any, base_dir: Path) -> Path | None:
    if value in {None, ""}:
        return None
    if not isinstance(value, str):
        raise ValueError("manifest path fields must be strings.")
    return _resolve_path(value, base_dir)


def _resolve_path(value: str | Path, base_dir: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


if __name__ == "__main__":
    raise SystemExit(main())
