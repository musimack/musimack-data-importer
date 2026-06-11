from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "local_falcon_summary.v2"
PROVIDER = "local_falcon"
PROVIDER_LABEL = "Local Falcon / Local Visibility"
DEFAULT_COMPETITOR_CAP = 15


class LocalFalconImportError(ValueError):
    pass


@dataclass(frozen=True)
class ImportSummary:
    profile: str
    keyword: str
    output_path: Path
    data_points: dict[str, int]
    competitor_count: int
    ai_analysis_available: bool
    rendered_grid: dict[str, int]
    warnings: list[str]


@dataclass(frozen=True)
class OutputValidation:
    profile: str
    output_path: Path | None
    keyword_scan_count: int
    featured_keyword_id: str | None
    strongest_keyword_id: str | None
    weakest_keyword_id: str | None
    keyword_summaries: list[dict[str, Any]]
    warnings: list[str]


def keyword_id(keyword: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", keyword.strip().lower()).strip("-")
    return slug or "keyword-scan"


def normalize_rank(value: Any) -> int | str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text in {"-", "n/a", "na", "none", "not found", "notfound", "missing"}:
        return None
    if "20" in text and "+" in text:
        return "20+"
    match = re.search(r"\d+", text)
    if not match:
        return None
    rank = int(match.group(0))
    if rank > 20:
        return "20+"
    return rank


def rank_status(rank: int | str | None) -> str:
    if rank is None:
        return "not_found"
    if rank == "20+":
        return "weak"
    if rank <= 3:
        return "top_3"
    if rank <= 10:
        return "top_10"
    return "top_20"


def import_local_falcon_csv(
    *,
    profile: str,
    keyword: str,
    scan_report_path: Path | str,
    data_points_path: Path | str,
    output_path: Path | str,
    business_name: str | None = None,
    ai_analysis_path: Path | str | None = None,
    featured_keyword_id: str | None = None,
    overwrite: bool = False,
    competitor_cap: int = DEFAULT_COMPETITOR_CAP,
) -> ImportSummary:
    scan_report_path = Path(scan_report_path)
    data_points_path = Path(data_points_path)
    output_path = Path(output_path)
    ai_path = Path(ai_analysis_path) if ai_analysis_path else None

    report_rows = _read_csv(scan_report_path)
    point_rows = _read_csv(data_points_path)
    report = _report_metadata(report_rows, keyword, business_name)
    if business_name:
        report["business"]["name"] = business_name

    scan_id = keyword_id(keyword)
    grid_points = normalize_grid_points(point_rows, report["business"].get("name"))
    data_counts = derive_data_point_counts(grid_points)
    competitors = normalize_competitors(point_rows, report["business"].get("name"), competitor_cap)
    ai_analysis = parse_ai_analysis(_read_text(ai_path) if ai_path else None)

    keyword_scan = {
        "id": scan_id,
        "keyword": keyword,
        "scan_date": report.get("scan_date"),
        "grid_size_label": report.get("grid_size_label"),
        "rendered_grid": rendered_grid(grid_points),
        "radius_miles": report.get("radius_miles"),
        "center": report.get("center"),
        "business": report.get("business"),
        "data_points": data_counts,
        "local_falcon_metrics": report.get("local_falcon_metrics"),
        "grid_points": grid_points,
        "competitors": competitors,
        "ai_analysis": ai_analysis,
        "action_bridge": build_action_bridge(data_counts, grid_points, competitors),
    }

    payload = _load_existing_payload(output_path, profile, overwrite)
    scans = [scan for scan in payload.get("keyword_scans", []) if scan.get("id") != scan_id]
    scans.append(_drop_none(keyword_scan))
    payload["keyword_scans"] = scans
    payload["summary"] = _build_summary(scans, featured_keyword_id or payload.get("summary", {}).get("featured_keyword_id"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    warnings: list[str] = []
    if len(scans) > 10:
        warnings.append("More than 10 keyword scans are present; dashboard setup normally uses 5 to 10.")

    return ImportSummary(
        profile=profile,
        keyword=keyword,
        output_path=output_path,
        data_points=data_counts,
        competitor_count=len(competitors),
        ai_analysis_available=ai_analysis.get("available") is True,
        rendered_grid=keyword_scan["rendered_grid"],
        warnings=warnings,
    )


def normalize_grid_points(rows: list[dict[str, str]], business_name: str | None = None) -> list[dict[str, Any]]:
    if business_name and any(_get(row, "data point id", "data point id#") for row in rows):
        return _normalize_result_rows_as_grid_points(rows, business_name)

    points: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        rank = normalize_rank(_get(row, "rank", "position", "business rank", "client rank", "map rank"))
        point = {
            "row": _int_or_none(_get(row, "row", "grid row", "y")),
            "col": _int_or_none(_get(row, "col", "column", "grid col", "grid column", "x")),
            "rank": rank,
            "status": rank_status(rank),
            "zone": _get(row, "zone", "quadrant", "area"),
            "latitude": _float_or_none(_get(row, "latitude", "lat", "search latitude", "point latitude")),
            "longitude": _float_or_none(_get(row, "longitude", "lng", "lon", "search longitude", "point longitude")),
            "label": _get(row, "label", "location", "location descriptor", "search location", "point label"),
            "_index": index,
        }
        points.append(_drop_none(point))

    _derive_missing_grid_positions(points)
    for point in points:
        point.pop("_index", None)
        if not point.get("zone"):
            point["zone"] = _zone(point.get("row"), point.get("col"), rendered_grid(points))
    return points


def derive_data_point_counts(grid_points: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"total": len(grid_points), "found": 0, "top_3": 0, "top_10": 0, "top_20": 0, "not_found_or_20_plus": 0}
    for point in grid_points:
        status = point.get("status")
        rank = point.get("rank")
        if isinstance(rank, int):
            counts["found"] += 1
        if status == "top_3":
            counts["top_3"] += 1
        if status in {"top_3", "top_10"}:
            counts["top_10"] += 1
        if status in {"top_3", "top_10", "top_20"}:
            counts["top_20"] += 1
        if status in {"weak", "not_found"}:
            counts["not_found_or_20_plus"] += 1
    return counts


def rendered_grid(points: list[dict[str, Any]]) -> dict[str, int]:
    rows = [point.get("row") for point in points if isinstance(point.get("row"), int)]
    cols = [point.get("col") for point in points if isinstance(point.get("col"), int)]
    return {
        "rows": (max(rows) + 1) if rows else 0,
        "columns": (max(cols) + 1) if cols else 0,
    }


def validate_local_falcon_summary(
    payload: dict[str, Any],
    output_path: Path | str | None = None,
) -> OutputValidation:
    warnings: list[str] = []
    scans = payload.get("keyword_scans", [])
    summary = payload.get("summary", {})
    path = Path(output_path) if output_path else None

    if payload.get("schema_version") != SCHEMA_VERSION:
        warnings.append(f"schema_version is not {SCHEMA_VERSION}.")
    if payload.get("provider") != PROVIDER:
        warnings.append("provider is not local_falcon.")
    if payload.get("source_type") not in {"local_real", "api_fixture", "api_local_real"}:
        warnings.append("source_type is not local_real, api_fixture, or api_local_real.")
    if not isinstance(scans, list):
        warnings.append("keyword_scans is not a list.")
        scans = []
    if len(scans) > 10:
        warnings.append("More than 10 keyword scans are present; dashboard setup normally uses 5 to 10.")

    keyword_summaries: list[dict[str, Any]] = []
    for scan in scans:
        if not isinstance(scan, dict):
            warnings.append("A keyword scan is not an object.")
            continue
        counts = scan.get("data_points") if isinstance(scan.get("data_points"), dict) else {}
        grid_points = scan.get("grid_points") if isinstance(scan.get("grid_points"), list) else []
        grid = scan.get("rendered_grid") if isinstance(scan.get("rendered_grid"), dict) else {}
        competitors = scan.get("competitors") if isinstance(scan.get("competitors"), list) else []
        action_bridge = scan.get("action_bridge") if isinstance(scan.get("action_bridge"), list) else []
        ai_analysis = scan.get("ai_analysis") if isinstance(scan.get("ai_analysis"), dict) else {}
        ai_visibility_points = scan.get("ai_visibility_points") if isinstance(scan.get("ai_visibility_points"), list) else []
        has_source_metadata = any(scan.get(key) for key in ("source_id", "source_label", "query_type", "query", "scan_kind"))
        is_ai_visibility = scan.get("query_type") == "ai_visibility_prompt"
        label = _validation_label(scan, is_ai_visibility=is_ai_visibility)

        total = _count_value(counts, "total")
        found = _count_value(counts, "found")
        top_3 = _count_value(counts, "top_3")
        top_10 = _count_value(counts, "top_10")
        top_20 = _count_value(counts, "top_20")
        weak = _count_value(counts, "not_found_or_20_plus")
        derived = derive_data_point_counts(grid_points) if grid_points else None
        derived_grid = rendered_grid(grid_points) if grid_points else None

        if total <= 0:
            warnings.append(f"{label}: data point counts are missing or empty.")
        if grid_points and total != len(grid_points):
            warnings.append(f"{label}: total data point count does not match grid point count.")
        if derived and any(counts.get(key) != derived.get(key) for key in ("total", "found", "top_3", "top_10", "top_20", "not_found_or_20_plus")):
            warnings.append(f"{label}: data point counts do not match derived grid point counts.")
        if found > total or top_3 > found or top_10 > found or top_20 > found:
            warnings.append(f"{label}: data point count hierarchy is inconsistent.")
        if total and found + weak != total:
            warnings.append(f"{label}: found plus weak/not-found does not equal total.")
        if not grid_points:
            warnings.append(f"{label}: no grid points are present.")
        if not grid.get("rows") or not grid.get("columns"):
            warnings.append(f"{label}: rendered grid dimensions are missing.")
        if derived_grid and grid != derived_grid:
            warnings.append(f"{label}: rendered grid dimensions do not match grid points.")
        if not competitors and not is_ai_visibility:
            warnings.append(f"{label}: no competitors are present.")
        if not is_ai_visibility and not any(item.get("relationship") == "client" for item in competitors if isinstance(item, dict)):
            warnings.append(f"{label}: client competitor relationship was not found.")
        if not ai_analysis.get("available"):
            warnings.append(f"{label}: AI analysis is missing.")
        if has_source_metadata:
            if not scan.get("source_id"):
                warnings.append(f"{label}: source_id is missing.")
            if not scan.get("query_type"):
                warnings.append(f"{label}: query_type is missing.")
            if not scan.get("query"):
                warnings.append(f"{label}: query is missing.")
            if scan.get("query_type") == "ai_visibility_prompt" and not (scan.get("prompt") or scan.get("query")):
                warnings.append(f"{label}: AI visibility prompt is missing.")
        if is_ai_visibility:
            if not scan.get("brand_observations"):
                warnings.append(f"{label}: AI visibility brand observations are missing.")
            if not scan.get("brand_phrases"):
                warnings.append(f"{label}: AI visibility brand phrases are missing.")
            if not scan.get("ai_visibility_metrics"):
                warnings.append(f"{label}: AI visibility metrics are missing.")
            if "ai_visibility_points" in scan and not isinstance(scan.get("ai_visibility_points"), list):
                warnings.append(f"{label}: AI visibility points are not a list.")
            for point in ai_visibility_points:
                if not isinstance(point, dict):
                    warnings.append(f"{label}: an AI visibility point is not an object.")
                    continue
                if "observed" in point and not isinstance(point.get("observed"), bool):
                    warnings.append(f"{label}: AI visibility point observed value is not a boolean.")
                if "rank" in point:
                    warnings.append(f"{label}: AI visibility point should use observation_sequence instead of rank.")

        keyword_summaries.append(
            {
                "id": scan.get("id"),
                "keyword": scan.get("keyword"),
                "total": total,
                "found": found,
                "top_3": top_3,
                "top_10": top_10,
                "top_20": top_20,
                "weak_or_not_found": weak,
                "rendered_grid": {"rows": grid.get("rows") or 0, "columns": grid.get("columns") or 0},
                "grid_point_count": len(grid_points),
                "competitor_count": len(competitors),
                "ai_visibility_point_count": len(ai_visibility_points),
                "ai_analysis_available": ai_analysis.get("available") is True,
                "action_bridge_count": len(action_bridge),
                "source_id": scan.get("source_id"),
                "query_type": scan.get("query_type"),
            }
        )

    return OutputValidation(
        profile=str(payload.get("fixture_profile") or ""),
        output_path=path,
        keyword_scan_count=len(scans),
        featured_keyword_id=summary.get("featured_keyword_id"),
        strongest_keyword_id=summary.get("strongest_keyword_id"),
        weakest_keyword_id=summary.get("weakest_keyword_id"),
        keyword_summaries=keyword_summaries,
        warnings=warnings,
    )


def normalize_competitors(
    rows: list[dict[str, str]],
    client_business_name: str | None,
    competitor_cap: int = DEFAULT_COMPETITOR_CAP,
) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = _get(row, "competitor", "competitor name", "business", "business name", "name", "result name")
        if not name:
            continue
        key = name.casefold()
        rank = normalize_rank(_get(row, "competitor rank", "result rank", "rank", "position"))
        entry = by_name.setdefault(
            key,
            {
                "name": name,
                "rank": rank if isinstance(rank, int) else None,
                "found_points": 0,
                "top_3_points": 0,
                "top_10_points": 0,
                "solv": _float_or_none(_get(row, "solv", "share of local voice")),
                "arp": _float_or_none(_get(row, "arp", "average rank position")),
                "atrp": _float_or_none(_get(row, "atrp", "average total rank position")),
                "rating": _float_or_none(_get(row, "rating", "stars")),
                "reviews": _int_or_none(_get(row, "reviews", "review count")),
                "category": _get(row, "category", "primary category"),
                "address": _get(row, "address", "business address"),
            },
        )
        explicit_found = _int_or_none(_get(row, "found points", "found_points", "found", "points found"))
        explicit_top_3 = _int_or_none(_get(row, "top 3 points", "top_3_points", "top 3", "top_3"))
        explicit_top_10 = _int_or_none(_get(row, "top 10 points", "top_10_points", "top 10", "top_10"))
        if explicit_found is not None or explicit_top_3 is not None or explicit_top_10 is not None:
            entry["found_points"] = max(entry["found_points"], explicit_found or 0)
            entry["top_3_points"] = max(entry["top_3_points"], explicit_top_3 or 0)
            entry["top_10_points"] = max(entry["top_10_points"], explicit_top_10 or 0)
        elif isinstance(rank, int):
            entry["found_points"] += 1
            if rank <= 3:
                entry["top_3_points"] += 1
            if rank <= 10:
                entry["top_10_points"] += 1
        if isinstance(rank, int) and (entry.get("rank") is None or rank < entry["rank"]):
            entry["rank"] = rank

    competitors = [_drop_none(value) for value in by_name.values()]
    competitors.sort(key=lambda item: (-(item.get("solv") or 0), -(item.get("top_3_points") or 0), item.get("rank") or 999))

    client_key = client_business_name.casefold() if client_business_name else None
    leader_key = competitors[0]["name"].casefold() if competitors else None
    for competitor in competitors:
        name_key = competitor["name"].casefold()
        if client_key and name_key == client_key:
            competitor["relationship"] = "client"
        elif name_key == leader_key:
            competitor["relationship"] = "market_leader"
        elif (competitor.get("top_10_points") or 0) > 0:
            competitor["relationship"] = "watch"
        elif (competitor.get("found_points") or 0) > 0:
            competitor["relationship"] = "vulnerable"
        else:
            competitor["relationship"] = "other"

    if competitor_cap > 0 and len(competitors) > competitor_cap:
        focused = competitors[:competitor_cap]
        if client_key and not any(item["name"].casefold() == client_key for item in focused):
            client = next((item for item in competitors if item["name"].casefold() == client_key), None)
            if client:
                focused[-1] = client
        competitors = focused
    return competitors


def parse_ai_analysis(text: str | None) -> dict[str, Any]:
    if not text or not text.strip():
        return {"available": False}
    clean = text.strip()
    sections = _parse_sections(clean)
    return {
        "available": True,
        "summary": sections.get("summary") or clean[:700],
        "issues": _section_lines(sections, "issues", "issue", "problems"),
        "improvements": _section_lines(sections, "improvements", "improvement", "opportunities"),
        "recommendations": _section_lines(sections, "recommendations", "recommendation", "actions"),
        "vulnerable_competitors": _section_lines(sections, "vulnerable competitors", "vulnerable_competitors"),
    }


def build_action_bridge(
    counts: dict[str, int],
    grid_points: list[dict[str, Any]],
    competitors: list[dict[str, Any]],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    total = counts.get("total") or 0
    top_10_share = (counts.get("top_10") or 0) / total if total else 0
    if top_10_share < 0.5:
        actions.append(
            {
                "priority": "high",
                "area": "Local visibility coverage",
                "theme": "Service relevance",
                "issue": "Fewer than half of scanned points are visible in the top 10.",
                "recommended_action": "Strengthen relevant service-page copy, internal links, local proof, and GBP updates for the tracked keyword.",
            }
        )

    weak_by_zone: dict[str, int] = {}
    for point in grid_points:
        if point.get("status") in {"weak", "not_found"}:
            weak_by_zone[str(point.get("zone") or "Unknown")] = weak_by_zone.get(str(point.get("zone") or "Unknown"), 0) + 1
    if weak_by_zone:
        zone = max(weak_by_zone, key=weak_by_zone.get)
        actions.append(
            {
                "priority": "medium",
                "area": zone,
                "theme": "Map grid gaps",
                "issue": f"{zone} has the highest concentration of weak or missing grid points.",
                "recommended_action": "Add locally relevant proof, supporting content, GBP posts, and internal links for this area without overstating location claims.",
            }
        )

    market_leader = next((item for item in competitors if item.get("relationship") == "market_leader"), None)
    if market_leader:
        actions.append(
            {
                "priority": "medium",
                "area": "Competitive review",
                "theme": "Competitor visibility",
                "issue": f"{market_leader['name']} is the strongest visible competitor in this scan.",
                "recommended_action": "Compare visible competitor positioning, categories, review signals, and page relevance to identify practical content and local SEO improvements.",
            }
        )
    return actions[:3]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise LocalFalconImportError(f"CSV file not found: {path}")
    try:
        text = _read_text(path)
    except UnicodeDecodeError as exc:
        raise LocalFalconImportError(f"CSV file could not be decoded: {path}") from exc
    reader = csv.DictReader(text.splitlines())
    return [{_normalize_key(key): (value or "").strip() for key, value in row.items() if key} for row in reader]


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    sample = data[:200]
    if sample.count(b"\x00") > len(sample) // 4:
        return data.decode("utf-16-le")
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8")


def _report_metadata(rows: list[dict[str, str]], keyword: str, business_name: str | None) -> dict[str, Any]:
    row = _find_business_row(rows, business_name) or (rows[0] if rows else {})
    business = {
        "name": business_name or _get(row, "business name", "client business", "name"),
        "address": _get(row, "business address", "address"),
        "rating": _float_or_none(_get(row, "rating", "business rating")),
        "reviews": _int_or_none(_get(row, "reviews", "review count")),
    }
    return {
        "keyword": _get(row, "keyword", "search term") or keyword,
        "scan_date": _get(row, "scan date", "date", "created at", "scan_date"),
        "grid_size_label": _get(row, "grid size", "grid", "grid_size"),
        "radius_miles": _float_or_none(_get(row, "radius miles", "radius", "radius_miles")),
        "center": _drop_none(
            {
                "latitude": _float_or_none(_get(row, "center latitude", "center lat", "latitude", "lat")),
                "longitude": _float_or_none(_get(row, "center longitude", "center lng", "center lon", "longitude", "lng", "lon")),
            }
        ),
        "business": _drop_none(business),
        "local_falcon_metrics": _drop_none(
            {
                "arp": _float_or_none(_get(row, "arp", "average rank position")),
                "atrp": _float_or_none(_get(row, "atrp", "average total rank position")),
                "solv": _float_or_none(_get(row, "solv", "share of local voice")),
            }
        ),
    }


def _load_existing_payload(output_path: Path, profile: str, overwrite: bool) -> dict[str, Any]:
    if output_path.exists() and not overwrite:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != SCHEMA_VERSION:
            raise LocalFalconImportError(f"existing output is not {SCHEMA_VERSION}: {output_path}")
        return payload
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": PROVIDER,
        "provider_label": PROVIDER_LABEL,
        "source_type": "local_real",
        "real_data": True,
        "fixture_profile": profile,
        "summary": {},
        "keyword_scans": [],
    }


def _build_summary(scans: list[dict[str, Any]], featured_keyword_id: str | None) -> dict[str, Any]:
    strongest_scan = max(scans, key=_strongest_coverage_key) if scans else None
    weakest_scan = min(scans, key=_weakest_coverage_key) if scans else None
    strongest = strongest_scan["id"] if strongest_scan else None
    weakest = weakest_scan["id"] if weakest_scan else None
    featured = featured_keyword_id or strongest
    return _drop_none(
        {
            "keyword_count": len(scans),
            "featured_keyword_id": featured,
            "strongest_keyword_id": strongest,
            "weakest_keyword_id": weakest,
            "summary_note": "Local Falcon CSV import generated by musimack-data-importer.",
        }
    )


def _strongest_coverage_key(scan: dict[str, Any]) -> tuple[float, float, float, float, str]:
    counts = scan.get("data_points", {})
    total = counts.get("total") or 0
    if not total:
        return (0, 0, 0, 0, str(scan.get("id") or ""))
    return (
        (counts.get("top_3") or 0) / total,
        (counts.get("top_10") or 0) / total,
        (counts.get("found") or 0) / total,
        -((counts.get("not_found_or_20_plus") or 0) / total),
        str(scan.get("id") or ""),
    )


def _weakest_coverage_key(scan: dict[str, Any]) -> tuple[float, float, float, str]:
    counts = scan.get("data_points", {})
    total = counts.get("total") or 0
    if not total:
        return (-1, -1, 0, str(scan.get("id") or ""))
    return (
        (counts.get("top_10") or 0) / total,
        (counts.get("found") or 0) / total,
        -((counts.get("not_found_or_20_plus") or 0) / total),
        str(scan.get("id") or ""),
    )


def _count_value(counts: dict[str, Any], key: str) -> int:
    value = counts.get(key)
    return value if isinstance(value, int) else 0


def _validation_label(scan: dict[str, Any], *, is_ai_visibility: bool) -> str:
    value = str(scan.get("keyword") or scan.get("id") or "unknown keyword")
    if not is_ai_visibility:
        return value
    text = " ".join(value.split())
    if not text:
        return "[redacted AI prompt]"
    return f"{text[:18]}... [redacted AI prompt]"


def _derive_missing_grid_positions(points: list[dict[str, Any]]) -> None:
    if all(isinstance(point.get("row"), int) and isinstance(point.get("col"), int) for point in points):
        return
    coords = [point for point in points if isinstance(point.get("latitude"), float) and isinstance(point.get("longitude"), float)]
    if len(coords) == len(points) and points:
        lats = sorted({_coord_key(point["latitude"]) for point in points}, reverse=True)
        lngs = sorted({_coord_key(point["longitude"]) for point in points})
        lat_index = {value: index for index, value in enumerate(lats)}
        lng_index = {value: index for index, value in enumerate(lngs)}
        for point in points:
            point["row"] = lat_index[_coord_key(point["latitude"])]
            point["col"] = lng_index[_coord_key(point["longitude"])]
        return
    columns = int(math.sqrt(len(points))) if len(points) and int(math.sqrt(len(points))) ** 2 == len(points) else max(1, math.ceil(math.sqrt(len(points) or 1)))
    for point in points:
        index = point.get("_index") or 0
        point["row"] = index // columns
        point["col"] = index % columns


def _normalize_result_rows_as_grid_points(rows: list[dict[str, str]], business_name: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        point_id = _get(row, "data point id", "data point id#")
        if not point_id:
            continue
        groups.setdefault(point_id, []).append(row)

    points: list[dict[str, Any]] = []
    business_key = business_name.casefold()
    for index, point_id in enumerate(sorted(groups, key=_natural_sort_key)):
        point_rows = groups[point_id]
        base = point_rows[0]
        match = next(
            (
                row
                for row in point_rows
                if (_get(row, "business", "business name", "name") or "").casefold() == business_key
            ),
            None,
        )
        rank = normalize_rank(_get(match, "rank", "position")) if match else None
        point = {
            "row": None,
            "col": None,
            "rank": rank,
            "status": rank_status(rank),
            "zone": _get(base, "zone", "quadrant", "area"),
            "latitude": _float_or_none(_get(base, "latitude", "lat", "search latitude", "point latitude")),
            "longitude": _float_or_none(_get(base, "longitude", "lng", "lon", "search longitude", "point longitude")),
            "label": f"Data point {point_id}",
            "_index": index,
        }
        points.append(_drop_none(point))

    _derive_missing_grid_positions(points)
    for point in points:
        point.pop("_index", None)
        if not point.get("zone"):
            point["zone"] = _zone(point.get("row"), point.get("col"), rendered_grid(points))
    return points


def _natural_sort_key(value: str) -> tuple[int, str]:
    number = _int_or_none(value)
    return (number if number is not None else 999999, value)


def _coord_key(value: float) -> float:
    return round(value, 6)


def _zone(row: Any, col: Any, grid: dict[str, int]) -> str:
    if not isinstance(row, int) or not isinstance(col, int) or not grid["rows"] or not grid["columns"]:
        return "Unknown"
    vertical = "N" if row < grid["rows"] / 3 else "S" if row >= grid["rows"] * 2 / 3 else ""
    horizontal = "W" if col < grid["columns"] / 3 else "E" if col >= grid["columns"] * 2 / 3 else ""
    return f"{vertical}{horizontal}" or "Center"


def _parse_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"summary": []}
    current = "summary"
    for line in text.splitlines():
        stripped = line.strip()
        heading = stripped.rstrip(":").lower()
        if heading in {"summary", "issues", "issue", "problems", "improvements", "improvement", "opportunities", "recommendations", "recommendation", "actions", "vulnerable competitors", "vulnerable_competitors"}:
            current = heading
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(stripped)
    return {key: "\n".join(value).strip() for key, value in sections.items() if "\n".join(value).strip()}


def _section_lines(sections: dict[str, str], *names: str) -> list[str]:
    text = next((sections[name] for name in names if name in sections), "")
    lines = []
    for line in text.splitlines():
        item = line.strip().lstrip("-*0123456789. ").strip()
        if item:
            lines.append(item)
    return lines


def _get(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(_normalize_key(name))
        if value not in {None, ""}:
            return value
    return None


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(key).strip().lower()).strip()


def _int_or_none(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    match = re.search(r"-?\d+", str(value))
    return int(match.group(0)) if match else None


def _float_or_none(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if match:
        return float(match.group(0))
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return None


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None and item != {} and item != ""}


def _find_business_row(rows: list[dict[str, str]], business_name: str | None) -> dict[str, str] | None:
    if not business_name:
        return None
    business_key = business_name.casefold()
    return next(
        (
            row
            for row in rows
            if (_get(row, "business", "business name", "name") or "").casefold() == business_key
        ),
        None,
    )
