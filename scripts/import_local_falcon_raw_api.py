from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.local_falcon_api_fetcher import LocalFalconApiReportBundle
from src.local_falcon_api_plan import LocalFalconApiReportPlan, default_output_path
from src.local_falcon_api_responses import LocalFalconApiResponseError, merge_api_scan_into_summary
from src.local_falcon_api_fetcher import normalize_report_bundle_to_keyword_scan
from src.local_falcon_importer import OutputValidation, validate_local_falcon_summary


class LocalFalconRawApiImportError(ValueError):
    pass


@dataclass(frozen=True)
class RawApiImportResult:
    profile: str
    raw_file_count: int
    output_path: Path
    source_counts: Counter[str]
    query_type_counts: Counter[str]
    google_maps_grid_present: bool
    chatgpt_ai_visibility_present: bool
    google_maps_keyword_scan_count: int
    ai_visibility_record_count: int
    validation: OutputValidation
    warnings: list[str]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize ignored Local Falcon raw API payload files into local_falcon_summary.v2 JSON."
    )
    parser.add_argument("--profile", required=True, help="Dashboard-lab profile slug.")
    parser.add_argument("--raw-dir", required=True, help="Ignored raw API payload directory.")
    parser.add_argument(
        "--output",
        help="Output JSON path. Defaults to exports/local-real/dashboard-lab/{profile}/local-falcon-summary.json.",
    )
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output file.")
    args = parser.parse_args()

    output = Path(args.output) if args.output else default_output_path(args.profile)
    try:
        result = import_raw_api_directory(
            profile=args.profile,
            raw_dir=Path(args.raw_dir),
            output_path=output,
            overwrite=args.overwrite,
        )
    except (LocalFalconRawApiImportError, OSError, json.JSONDecodeError) as exc:
        print(f"Local Falcon raw API import failed safely: {exc}", file=sys.stderr)
        return 1

    _print_safe_result(result)
    return 0


def import_raw_api_directory(
    *,
    profile: str,
    raw_dir: Path,
    output_path: Path,
    overwrite: bool = False,
) -> RawApiImportResult:
    if not raw_dir.exists() or not raw_dir.is_dir():
        raise LocalFalconRawApiImportError("raw API directory is missing")
    if not _is_safe_local_path(raw_dir):
        raise LocalFalconRawApiImportError("raw API directory must be under ignored local/ or .test-tmp-*")
    if not _is_safe_output_path(output_path):
        raise LocalFalconRawApiImportError("output must be under ignored exports/local-real/ or .test-tmp-*")
    if output_path.exists() and not overwrite:
        raise LocalFalconRawApiImportError("output already exists; pass --overwrite to replace it")

    raw_files = sorted(path for path in raw_dir.glob("*.json") if path.is_file())
    if not raw_files:
        raise LocalFalconRawApiImportError("raw API directory does not contain JSON payload files")

    source_counts: Counter[str] = Counter()
    query_type_counts: Counter[str] = Counter()
    scans: list[dict[str, Any]] = []
    google_maps_grid_present = False
    chatgpt_ai_visibility_present = False
    payload: dict[str, Any] | None = None
    warnings: list[str] = []

    for index, raw_file in enumerate(raw_files, start=1):
        raw_payload = _read_raw_payload(raw_file)
        if raw_payload.get("profile") not in {None, "", profile}:
            raise LocalFalconRawApiImportError(f"raw file {index}: profile does not match requested profile")
        scan = _normalize_raw_payload(raw_payload, index)
        source_counts[_source_label(scan)] += 1
        query_type_counts[str(scan.get("query_type") or "map_keyword")] += 1
        if scan.get("query_type") == "map_keyword" and scan.get("grid_points"):
            google_maps_grid_present = True
        if scan.get("query_type") == "ai_visibility_prompt" and (
            scan.get("ai_visibility_points") or scan.get("brand_observations") or scan.get("ai_visibility_sources")
        ):
            chatgpt_ai_visibility_present = True
        scans.append(scan)
        payload = merge_api_scan_into_summary(
            profile=profile,
            keyword_scan=scan,
            existing_summary=payload,
            source_type="api_local_real",
            real_data=True,
        )

    if payload is None:
        raise LocalFalconRawApiImportError("no usable raw API payload files were found")
    validation = validate_local_falcon_summary(payload, output_path)
    warnings.extend(validation.warnings)
    _atomic_write_json(output_path, payload)

    google_maps_count = sum(1 for scan in scans if scan.get("query_type") == "map_keyword")
    ai_visibility_count = sum(1 for scan in scans if scan.get("query_type") == "ai_visibility_prompt")
    return RawApiImportResult(
        profile=profile,
        raw_file_count=len(raw_files),
        output_path=output_path,
        source_counts=source_counts,
        query_type_counts=query_type_counts,
        google_maps_grid_present=google_maps_grid_present,
        chatgpt_ai_visibility_present=chatgpt_ai_visibility_present,
        google_maps_keyword_scan_count=google_maps_count,
        ai_visibility_record_count=ai_visibility_count,
        validation=validation,
        warnings=warnings,
    )


def _normalize_raw_payload(raw_payload: dict[str, Any], file_index: int) -> dict[str, Any]:
    responses = raw_payload.get("responses")
    if not isinstance(responses, dict):
        raise LocalFalconRawApiImportError(f"raw file {file_index}: responses category is missing")
    report_summary = _required_response(responses, "report_summary", file_index)
    grid_points = _required_response(responses, "grid_points", file_index)
    competitors = responses.get("competitors") if isinstance(responses.get("competitors"), dict) else None
    ai_analysis = responses.get("ai_analysis") if isinstance(responses.get("ai_analysis"), dict) else None
    keyword = _extract_keyword(report_summary) or _extract_keyword(grid_points) or _extract_keyword(ai_analysis)
    if not keyword:
        raise LocalFalconRawApiImportError(f"raw file {file_index}: report keyword category is missing")

    source_label = _clean_text(raw_payload.get("source_label")) or _clean_text(raw_payload.get("source_id"))
    source_id = _clean_text(raw_payload.get("source_id")) or _source_id_from_label(source_label)
    query_type = _clean_text(raw_payload.get("query_type")) or _query_type_from_source(source_id or source_label)
    scan_kind = _clean_text(raw_payload.get("scan_kind")) or _scan_kind_from_query_type(query_type)
    report_id_redacted = _clean_text(raw_payload.get("report_id_redacted"))
    bundle = LocalFalconApiReportBundle(
        report=LocalFalconApiReportPlan(
            keyword=keyword,
            report_id=report_id_redacted or "",
            source_id=source_id,
            source_label=source_label,
            query_type=query_type,
            query=keyword,
            scan_kind=scan_kind,
        ),
        report_summary=report_summary,
        grid_points=grid_points,
        competitors=competitors,
        ai_analysis=ai_analysis,
    )
    try:
        scan = normalize_report_bundle_to_keyword_scan(bundle)
    except LocalFalconApiResponseError as exc:
        raise LocalFalconRawApiImportError(f"raw file {file_index}: {exc}") from exc
    if scan.get("query_type") == "ai_visibility_prompt":
        scan["ai_visibility_sources"] = _normalize_ai_visibility_sources(report_summary, ai_analysis)
    return scan


def _required_response(responses: dict[str, Any], key: str, file_index: int) -> dict[str, Any]:
    value = responses.get(key)
    if not isinstance(value, dict):
        raise LocalFalconRawApiImportError(f"raw file {file_index}: {key} category is missing")
    return value


def _read_raw_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LocalFalconRawApiImportError("raw API payload file must contain a JSON object")
    return payload


def _extract_keyword(response: dict[str, Any] | None) -> str | None:
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if isinstance(data, dict):
        value = data.get("keyword")
        if isinstance(value, str) and value.strip():
            return value.strip()
        report = data.get("report")
        if isinstance(report, dict):
            value = report.get("keyword")
            if isinstance(value, str) and value.strip():
                return value.strip()
    value = response.get("keyword")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_ai_visibility_sources(*responses: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    for response in responses:
        data = _data_object(response)
        sources = data.get("sources") if isinstance(data, dict) else None
        if isinstance(sources, list):
            rows.extend(item for item in sources if isinstance(item, dict))
    normalized = []
    seen = set()
    for row in rows:
        item = _drop_empty(
            {
                "source": _clean_text(row.get("source")),
                "title": _clean_text(row.get("title")),
                "subtitle": _clean_text(row.get("subtitle")),
                "link": _clean_text(row.get("link")),
                "count": _int_or_none(row.get("count")),
            }
        )
        key = tuple(sorted(item.items()))
        if item and key not in seen:
            seen.add(key)
            normalized.append(item)
    return normalized


def _data_object(response: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    data = response.get("data")
    return data if isinstance(data, dict) else response


def _print_safe_result(result: RawApiImportResult) -> None:
    print("Imported Local Falcon raw API payloads")
    print(f"Profile: {result.profile}")
    print(f"Output: {result.output_path}")
    print(f"Raw file count: {result.raw_file_count}")
    print("Detected sources:")
    for source, count in sorted(result.source_counts.items()):
        print(f"- {source}: {count}")
    print("Detected query types:")
    for query_type, count in sorted(result.query_type_counts.items()):
        print(f"- {query_type}: {count}")
    print(f"Google Maps grid data present: {'yes' if result.google_maps_grid_present else 'no'}")
    print(f"ChatGPT AI visibility data present: {'yes' if result.chatgpt_ai_visibility_present else 'no'}")
    print(f"Generated Google Maps keyword scans: {result.google_maps_keyword_scan_count}")
    print(f"Generated AI visibility source count: {result.ai_visibility_record_count}")
    print(f"Validation warnings: {len(result.warnings)}")
    print("Report IDs, prompts, API keys, raw payloads, and competitor names were not printed.")


def _atomic_write_json(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp_path, output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _is_safe_local_path(path: Path) -> bool:
    return _is_relative_safe_path(path, ("local/", ".test-tmp-"))


def _is_safe_output_path(path: Path) -> bool:
    return _is_relative_safe_path(path, ("exports/local-real/", ".test-tmp-"))


def _is_relative_safe_path(path: Path, prefixes: tuple[str, ...]) -> bool:
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        relative = path.as_posix()
    return any(relative.startswith(prefix) or f"/{prefix}" in relative for prefix in prefixes)


def _source_label(scan: dict[str, Any]) -> str:
    return str(scan.get("source_label") or scan.get("source_id") or "Local Falcon")


def _source_id_from_label(value: str | None) -> str | None:
    normalized = _normalize_label(value)
    if normalized in {"google_maps", "maps", "google"}:
        return "google_maps"
    if normalized in {"chatgpt", "openai_chatgpt"}:
        return "chatgpt"
    if normalized in {"google_ai_overview", "google_ai_overviews", "ai_overview", "ai_overviews"}:
        return "google_ai_overviews"
    return None


def _query_type_from_source(value: str | None) -> str | None:
    source_id = _source_id_from_label(value) or _normalize_label(value)
    if source_id == "google_maps":
        return "map_keyword"
    if source_id in {"chatgpt", "google_ai_overviews"}:
        return "ai_visibility_prompt"
    return None


def _scan_kind_from_query_type(value: str | None) -> str | None:
    if value == "map_keyword":
        return "map_visibility"
    if value == "ai_visibility_prompt":
        return "ai_visibility_map"
    return None


def _normalize_label(value: str | None) -> str:
    if not value:
        return ""
    import re

    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _clean_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _drop_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in {None, ""}}


if __name__ == "__main__":
    raise SystemExit(main())
