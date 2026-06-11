from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PROFILE = "inn-at-spanish-head"


@dataclass(frozen=True)
class ManifestValidation:
    profile: str
    manifest_path: Path
    report_count: int
    report_source_counts: Counter[str]
    missing_report_ids: int
    duplicate_report_ids: int
    duplicate_source_query_pairs: int
    planned_source_counts: Counter[str]
    planned_missing_report_ids: int
    google_ai_overview_pending_prompts: int
    safe_to_process: bool
    errors: list[str]
    warnings: list[str]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an ignored local Local Falcon report manifest without fetching provider data."
    )
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Profile slug. Defaults to inn-at-spanish-head.")
    parser.add_argument(
        "--manifest",
        help="Private manifest path. Defaults to local/{profile}/local-falcon/report-manifest.json.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest) if args.manifest else _default_manifest_path(args.profile)

    try:
        payload = _read_manifest(manifest_path)
        validation = validate_manifest(payload, profile=args.profile, manifest_path=manifest_path)
    except (OSError, ValueError) as exc:
        print(f"Local Falcon manifest validation failed safely: {exc}", file=sys.stderr)
        return 1

    _print_validation(validation)
    return 0 if validation.safe_to_process else 1


def validate_manifest(payload: dict[str, Any], *, profile: str, manifest_path: Path) -> ManifestValidation:
    errors: list[str] = []
    warnings: list[str] = []

    manifest_profile = _text(payload.get("profile"))
    if manifest_profile and manifest_profile != profile:
        errors.append("manifest profile does not match requested profile")
    if not manifest_profile:
        warnings.append("manifest profile is missing")

    reports = _object_rows(payload.get("reports"))
    planned_rows = _object_rows(payload.get("planned_or_in_progress_sources"))
    report_source_counts: Counter[str] = Counter()
    planned_source_counts: Counter[str] = Counter()
    report_ids: list[str] = []
    source_query_pairs: list[tuple[str, str]] = []
    missing_report_ids = 0

    for row in reports:
        source = _source_label(row)
        query = _query_label(row)
        report_source_counts[source] += 1

        report_id = _text(row.get("report_id") or row.get("id"))
        if not report_id:
            missing_report_ids += 1
        else:
            report_ids.append(report_id)

        if source and query:
            source_query_pairs.append((_normalize(source), _normalize(query)))

    if not reports:
        errors.append("manifest reports array is missing or empty")
    if missing_report_ids:
        errors.append("one or more existing report rows are missing report IDs")

    duplicate_report_ids = _duplicate_count(report_ids)
    if duplicate_report_ids:
        errors.append("duplicate report IDs found")

    duplicate_source_query_pairs = _duplicate_count(source_query_pairs)
    if duplicate_source_query_pairs:
        errors.append("duplicate source/query pairs found")

    planned_missing_report_ids = 0
    google_ai_overview_pending_prompts = 0
    for row in planned_rows:
        source = _source_label(row)
        planned_source_counts[source] += 1
        if not _text(row.get("report_id") or row.get("id")):
            planned_missing_report_ids += 1
            if _normalize(source) in {"google_ai_overview", "google_ai_overviews"}:
                google_ai_overview_pending_prompts += 1

    safe_to_process = not errors
    return ManifestValidation(
        profile=profile,
        manifest_path=manifest_path,
        report_count=len(reports),
        report_source_counts=report_source_counts,
        missing_report_ids=missing_report_ids,
        duplicate_report_ids=duplicate_report_ids,
        duplicate_source_query_pairs=duplicate_source_query_pairs,
        planned_source_counts=planned_source_counts,
        planned_missing_report_ids=planned_missing_report_ids,
        google_ai_overview_pending_prompts=google_ai_overview_pending_prompts,
        safe_to_process=safe_to_process,
        errors=errors,
        warnings=warnings,
    )


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"manifest not found at {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("manifest is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("manifest must contain a JSON object")
    return payload


def _print_validation(validation: ManifestValidation) -> None:
    print("Local Falcon manifest validation")
    print(f"Profile: {validation.profile}")
    print(f"Manifest: {validation.manifest_path}")
    print(f"Total existing reports: {validation.report_count}")
    print("Existing reports by source:")
    for source, count in sorted(validation.report_source_counts.items()):
        print(f"- {source}: {count}")
    if not validation.report_source_counts:
        print("- none")

    print(f"Missing existing report IDs: {validation.missing_report_ids}")
    print(f"Duplicate report IDs: {validation.duplicate_report_ids}")
    print(f"Duplicate source/query pairs: {validation.duplicate_source_query_pairs}")
    print("Planned/pending sources:")
    for source, count in sorted(validation.planned_source_counts.items()):
        print(f"- {source}: {count}")
    if not validation.planned_source_counts:
        print("- none")
    print(f"Planned/pending rows without report IDs: {validation.planned_missing_report_ids}")
    print(f"Google AI Overview prompts without report IDs: {validation.google_ai_overview_pending_prompts}")

    if validation.warnings:
        print("Warnings:")
        for warning in validation.warnings:
            print(f"- {warning}")

    if validation.errors:
        print("Errors:")
        for error in validation.errors:
            print(f"- {error}")

    print(f"Safe to process existing report IDs: {'yes' if validation.safe_to_process else 'no'}")
    print("No provider data was fetched. No API keys, full report IDs, prompts, or payloads were printed.")


def _default_manifest_path(profile: str) -> Path:
    return Path("local") / profile / "local-falcon" / "report-manifest.json"


def _object_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _source_label(row: dict[str, Any]) -> str:
    return (
        _text(row.get("source_label"))
        or _text(row.get("source"))
        or _text(row.get("source_id"))
        or _text(row.get("platform"))
        or "Unknown"
    )


def _query_label(row: dict[str, Any]) -> str:
    return _text(row.get("query")) or _text(row.get("keyword")) or _text(row.get("prompt"))


def _duplicate_count(values: list[Any]) -> int:
    counts = Counter(values)
    return sum(count - 1 for count in counts.values() if count > 1)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


if __name__ == "__main__":
    raise SystemExit(main())
