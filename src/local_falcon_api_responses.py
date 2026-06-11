from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_falcon_importer import (
    PROVIDER,
    PROVIDER_LABEL,
    SCHEMA_VERSION,
    build_action_bridge,
    derive_data_point_counts,
    keyword_id,
    normalize_competitors,
    normalize_rank,
    parse_ai_analysis,
    rank_status,
    rendered_grid,
)


class LocalFalconApiResponseError(ValueError):
    pass


def normalize_api_report_to_keyword_scan(
    report_response: dict[str, Any],
    *,
    grid_response: dict[str, Any] | None = None,
    competitor_response: dict[str, Any] | None = None,
    ai_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = _data_object(report_response)
    keyword = _required_string(report, "keyword", "report keyword is required")
    business = _business(report)
    grid_points = normalize_api_grid_points(grid_response or report_response, business.get("name"))
    ai_client_place_id = _first_string(report, "ai_place_id", "client_place_id", "place_id")
    ai_places = _normalize_ai_places(report)
    data_counts = derive_data_point_counts(grid_points)
    competitors = normalize_api_competitors(competitor_response or report_response, business.get("name"))
    ai_analysis = normalize_api_ai_analysis(ai_response or report_response)
    brand_observations = normalize_api_brand_observations(report_response, ai_response, business.get("name"))
    brand_phrases = normalize_api_brand_phrases(report_response, ai_response)
    ai_visibility_metrics = normalize_api_visibility_metrics(
        brand_observations,
        brand_phrases,
        business.get("name"),
        report_response,
        ai_response,
    )
    scan = {
        "id": keyword_id(keyword),
        "keyword": keyword,
        "scan_date": _first_string(report, "scan_date", "date", "timestamp"),
        "grid_size_label": _grid_size_label(report.get("grid_size") or report.get("grid_size_label")),
        "rendered_grid": rendered_grid(grid_points),
        "radius_miles": _number_or_none(report.get("radius_miles") or report.get("radius")),
        "center": _drop_none(
            {
                "latitude": _number_or_none(report.get("center_latitude") or report.get("lat")),
                "longitude": _number_or_none(report.get("center_longitude") or report.get("lng")),
            }
        ),
        "business": business,
        "data_points": data_counts,
        "local_falcon_metrics": _drop_none(
            {
                "arp": _number_or_none(report.get("arp")),
                "atrp": _number_or_none(report.get("atrp")),
                "solv": _number_or_none(report.get("solv")),
            }
        ),
        "grid_points": grid_points,
        "competitors": competitors,
        "ai_analysis": ai_analysis,
        "_ai_client_place_id": ai_client_place_id,
        "_ai_places": ai_places,
        "action_bridge": build_action_bridge(data_counts, grid_points, competitors),
    }
    if brand_observations:
        scan["brand_observations"] = brand_observations
    if brand_phrases:
        scan["brand_phrases"] = brand_phrases
    if ai_visibility_metrics:
        scan["ai_visibility_metrics"] = ai_visibility_metrics
    return _drop_none(scan)


def normalize_api_grid_points(response: dict[str, Any], business_name: str | None = None) -> list[dict[str, Any]]:
    data = _data_object(response)
    rows = _first_list(data, "grid_points", "data_points", "points")
    if rows is None:
        rows = _first_list(response, "grid_points", "data_points", "points")
    if rows is None:
        raise LocalFalconApiResponseError("grid points are required")

    points = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise LocalFalconApiResponseError("grid point rows must be objects")
        rank_value = row.get("rank")
        if rank_value is None and business_name:
            rank_value = _rank_from_results(row.get("results"), business_name)
        ai_result = _first_result(row.get("results"))
        rank = normalize_rank(rank_value)
        ai_results = _normalize_ai_result_rows(row.get("results"))
        ai_result = ai_results[0] if ai_results else ai_result
        point = {
            "row": _int_or_none(row.get("row")),
            "col": _int_or_none(_first_present(row, "col", "column")),
            "rank": rank,
            "status": rank_status(rank),
            "zone": _first_string(row, "zone", "area", "label"),
            "latitude": _number_or_none(_first_present(row, "latitude", "lat")),
            "longitude": _number_or_none(_first_present(row, "longitude", "lng")),
            "label": _first_string(row, "label", "name"),
            "observed": _bool_or_none(_first_present(row, "observed", "mentioned", "found")),
            "observation_sequence": _int_or_none(
                _first_present(row, "observation_sequence", "sequence", "observed_order", "order", "position")
                if _first_present(row, "observation_sequence", "sequence", "observed_order", "order", "position") is not None
                else _first_present(ai_result or {}, "observation_sequence", "sequence", "position", "rank")
            ),
            "ai_visibility_value": _int_or_none(
                _first_present(row, "ai_visibility_value", "visibility_value", "observation_value", "value")
                if _first_present(row, "ai_visibility_value", "visibility_value", "observation_value", "value") is not None
                else _first_present(ai_result or {}, "ai_visibility_value", "value", "rank")
            ),
            "brand_name": _first_string(row, "brand_name", "brand", "provider", "entity")
            or _first_string(ai_result or {}, "brand_name", "brand", "provider", "name", "entity"),
            "place_id": _first_string(row, "place_id") or _first_string(ai_result or {}, "place_id"),
            "relationship": _first_string(row, "relationship") or _first_string(ai_result or {}, "relationship"),
            "sentiment": _first_string(row, "sentiment") or _first_string(ai_result or {}, "sentiment"),
            "result_count": _int_or_none(row.get("count")) or (len(ai_results) if ai_results else None),
            "_ai_results": ai_results,
            "_index": index,
        }
        points.append(_drop_none(point))

    _derive_missing_positions(points)
    grid = rendered_grid(points)
    for point in points:
        point.pop("_index", None)
        if not point.get("zone"):
            point["zone"] = _zone(point.get("row"), point.get("col"), grid)
    return points


def normalize_api_competitors(response: dict[str, Any], client_business_name: str | None) -> list[dict[str, Any]]:
    data = _data_object(response)
    rows = _first_list(data, "competitors", "businesses", "results")
    if rows is None:
        return []
    csv_like_rows = []
    for row in rows:
        if not isinstance(row, dict):
            raise LocalFalconApiResponseError("competitor rows must be objects")
        derived_counts = _competitor_counts_from_points(row)
        csv_like_rows.append(
            {
                "business": str(row.get("name") or row.get("business") or ""),
                "rank": str(row.get("rank") or row.get("position") or ""),
                "found points": str(row.get("found_points") or row.get("found") or derived_counts.get("found_points") or ""),
                "top 3 points": str(row.get("top_3_points") or row.get("top3") or derived_counts.get("top_3_points") or ""),
                "top 10 points": str(row.get("top_10_points") or row.get("top10") or derived_counts.get("top_10_points") or ""),
                "solv": str(row.get("solv") or ""),
                "arp": str(row.get("arp") or ""),
                "atrp": str(row.get("atrp") or ""),
                "rating": str(row.get("rating") or ""),
                "reviews": str(row.get("reviews") or ""),
                "category": str(row.get("category") or ""),
                "address": str(row.get("address") or ""),
            }
        )
    return normalize_competitors(csv_like_rows, client_business_name)


def normalize_api_ai_analysis(response: dict[str, Any] | None) -> dict[str, Any]:
    if not response:
        return {"available": False}
    data = _data_object(response)
    ai = data.get("ai_analysis") or data.get("analysis") or response.get("ai_analysis")
    if not ai:
        return {"available": False}
    if isinstance(ai, str):
        return parse_ai_analysis(ai)
    if not isinstance(ai, dict):
        return {"available": False}
    return {
        "available": True,
        "summary": str(ai.get("summary") or ""),
        "issues": _string_list(ai.get("issues")),
        "improvements": _string_list(ai.get("improvements")),
        "recommendations": _string_list(ai.get("recommendations")),
        "vulnerable_competitors": _string_list(ai.get("vulnerable_competitors")),
    }


def normalize_api_brand_observations(
    report_response: dict[str, Any],
    ai_response: dict[str, Any] | None = None,
    client_business_name: str | None = None,
) -> list[dict[str, Any]]:
    rows = _first_nested_list(
        report_response,
        ai_response,
        "brand_observations",
        "brand_mentions",
        "brands_mentioned",
        "mentioned_brands",
        "brands",
        "observations",
    )
    if rows is None:
        return []
    observations = []
    client_key = client_business_name.casefold() if client_business_name else None
    for row in rows:
        if not isinstance(row, dict):
            continue
        brand_name = _first_string(row, "brand_name", "brand", "name", "business", "company")
        if not brand_name:
            continue
        relationship = _first_string(row, "relationship")
        if not relationship and client_key and brand_name.casefold() == client_key:
            relationship = "client"
        observation = _drop_none(
            {
                "brand_name": brand_name,
                "relationship": relationship,
                "observation_count": _int_or_none(
                    row.get("observation_count")
                    or row.get("mention_count")
                    or row.get("mentions")
                    or row.get("count")
                ),
                "map_points_observed": _int_or_none(
                    row.get("map_points_observed")
                    or row.get("points_observed")
                    or row.get("observed_points")
                    or row.get("found_points")
                ),
                "observation_sequence": _int_or_none(
                    row.get("observation_sequence")
                    or row.get("sequence")
                    or row.get("observed_order")
                    or row.get("order")
                    or row.get("position")
                ),
                "sentiment": _first_string(row, "sentiment", "brand_sentiment"),
                "share_of_ai_voice": _number_or_none(
                    row.get("share_of_ai_voice")
                    or row.get("saiv")
                    or row.get("share")
                    or row.get("voice_share")
                ),
            }
        )
        observations.append(observation)
    return observations


def normalize_api_brand_phrases(
    report_response: dict[str, Any],
    ai_response: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows = _first_nested_list(
        report_response,
        ai_response,
        "brand_phrases",
        "phrases",
        "phrase_mentions",
        "ai_phrases",
    )
    if rows is None:
        return []
    phrases = []
    for row in rows:
        if isinstance(row, str):
            phrase = row.strip()
            if phrase:
                phrases.append({"phrase": phrase})
            continue
        if not isinstance(row, dict):
            continue
        phrase = _first_string(row, "phrase", "text", "content", "label")
        if not phrase:
            continue
        phrases.append(
            _drop_none(
                {
                    "phrase": phrase,
                    "count": _int_or_none(row.get("count") or row.get("phrase_count") or row.get("mentions")),
                    "sentiment": _first_string(row, "sentiment", "phrase_sentiment"),
                    "brand_name": _first_string(row, "brand_name", "brand", "related_brand"),
                }
            )
        )
    return phrases


def normalize_api_visibility_metrics(
    observations: list[dict[str, Any]],
    phrases: list[dict[str, Any]],
    client_business_name: str | None,
    report_response: dict[str, Any],
    ai_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit = _first_nested_object(report_response, ai_response, "ai_visibility_metrics", "visibility_metrics")
    if not observations and not phrases and not explicit:
        return {}
    client_key = client_business_name.casefold() if client_business_name else None
    client = None
    if client_key:
        client = next(
            (
                item
                for item in observations
                if str(item.get("brand_name") or "").casefold() == client_key
                or item.get("relationship") == "client"
            ),
            None,
        )
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}
    for phrase in phrases:
        sentiment = str(phrase.get("sentiment") or "").casefold()
        if sentiment in sentiments:
            sentiments[sentiment] += int(phrase.get("count") or 1)
    total_mentions = sum(int(item.get("observation_count") or 0) for item in observations)
    metrics = _drop_none(
        {
            "mentions_client": bool(client) if client_business_name else _bool_or_none((explicit or {}).get("mentions_client")),
            "client_brand_name": client.get("brand_name") if client else client_business_name,
            "client_observation_count": (client or {}).get("observation_count"),
            "client_sentiment": (client or {}).get("sentiment"),
            "share_of_ai_voice": _number_or_none(
                (client or {}).get("share_of_ai_voice")
                or (explicit or {}).get("share_of_ai_voice")
                or (explicit or {}).get("saiv")
            ),
            "total_brand_mentions": total_mentions or _int_or_none((explicit or {}).get("total_brand_mentions")),
            "positive_phrase_count": sentiments["positive"] or None,
            "neutral_phrase_count": sentiments["neutral"] or None,
            "negative_phrase_count": sentiments["negative"] or None,
        }
    )
    client_phrases = [
        phrase
        for phrase in phrases
        if client_key and str(phrase.get("brand_name") or "").casefold() == client_key
    ]
    if client_phrases:
        metrics["client_brand_phrases"] = client_phrases
    return metrics


def merge_api_scan_into_summary(
    *,
    profile: str,
    keyword_scan: dict[str, Any],
    existing_summary: dict[str, Any] | None = None,
    featured_keyword_id: str | None = None,
    source_type: str = "api_fixture",
    real_data: bool = False,
) -> dict[str, Any]:
    payload = existing_summary or {
        "schema_version": SCHEMA_VERSION,
        "provider": PROVIDER,
        "provider_label": PROVIDER_LABEL,
        "source_type": source_type,
        "real_data": real_data,
        "fixture_profile": profile,
        "summary": {},
        "keyword_scans": [],
    }
    if source_type:
        payload["source_type"] = source_type
    payload["real_data"] = bool(real_data)
    scan_id = keyword_scan.get("id")
    scans = [
        scan
        for scan in payload.get("keyword_scans", [])
        if isinstance(scan, dict) and scan.get("id") != scan_id
    ]
    scans.append(keyword_scan)
    payload["keyword_scans"] = scans
    payload["summary"] = _build_summary(scans, featured_keyword_id or payload.get("summary", {}).get("featured_keyword_id"))
    if source_type == "api_local_real":
        payload["summary"]["summary_note"] = "Local Falcon API read-only output normalized by musimack-data-importer."
    return payload


def load_synthetic_api_fixture(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LocalFalconApiResponseError("synthetic API fixture must contain a JSON object")
    return payload


def _data_object(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data")
    if isinstance(data, dict):
        report = data.get("report")
        if isinstance(report, dict):
            merged = dict(report)
            for key, value in data.items():
                if key != "report" and key not in merged:
                    merged[key] = value
            return merged
        return data
    return response


def _business(report: dict[str, Any]) -> dict[str, Any]:
    business = report.get("business") or report.get("location") or {}
    if not isinstance(business, dict):
        business = {}
    return _drop_none(
        {
            "name": business.get("name") or report.get("business_name") or report.get("location"),
            "address": business.get("address") or report.get("business_address"),
            "rating": _number_or_none(business.get("rating")),
            "reviews": _int_or_none(business.get("reviews")),
        }
    )


def _competitor_counts_from_points(row: dict[str, Any]) -> dict[str, int]:
    points = row.get("data_points")
    if not isinstance(points, list):
        return {}
    found = top_3 = top_10 = 0
    for point in points:
        if not isinstance(point, dict):
            continue
        rank = normalize_rank(point.get("rank"))
        if isinstance(rank, int):
            found += 1
            if rank <= 3:
                top_3 += 1
            if rank <= 10:
                top_10 += 1
    return {
        "found_points": found,
        "top_3_points": top_3,
        "top_10_points": top_10,
    }


def _rank_from_results(results: Any, business_name: str) -> Any:
    if not isinstance(results, list):
        return None
    target = business_name.casefold()
    for result in results:
        if not isinstance(result, dict):
            continue
        name = str(result.get("name") or result.get("business") or "")
        if name.casefold() == target:
            return result.get("rank") or result.get("position")
    return None


def _first_result(results: Any) -> dict[str, Any] | None:
    if not isinstance(results, list):
        return None
    return next((item for item in results if isinstance(item, dict)), None)


def _normalize_ai_result_rows(results: Any) -> list[dict[str, Any]]:
    if not isinstance(results, list):
        return []
    normalized = []
    for item in results:
        if not isinstance(item, dict):
            continue
        normalized.append(
            _drop_none(
                {
                    "rank": _int_or_none(item.get("rank")),
                    "observation_sequence": _int_or_none(
                        _first_present(item, "observation_sequence", "sequence", "position", "rank")
                    ),
                    "ai_visibility_value": _int_or_none(_first_present(item, "ai_visibility_value", "value", "rank")),
                    "brand_name": _first_string(item, "brand_name", "brand", "provider", "name", "entity"),
                    "place_id": _first_string(item, "place_id"),
                    "relationship": _first_string(item, "relationship"),
                    "sentiment": _first_string(item, "sentiment"),
                }
            )
        )
    return normalized


def _normalize_ai_places(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    places = report.get("places")
    if not isinstance(places, dict):
        return {}
    normalized = {}
    for place_id, value in places.items():
        if not isinstance(value, dict):
            continue
        key = str(place_id).strip()
        if not key:
            continue
        normalized[key] = _drop_none(
            {
                "place_id": key,
                "brand_name": _first_string(value, "brand_name", "brand", "name", "business_name", "provider"),
                "share_of_ai_voice": _number_or_none(
                    _first_present(value, "share_of_ai_voice", "saiv", "share", "voice_share")
                ),
            }
        )
    return normalized


def _build_summary(scans: list[dict[str, Any]], featured_keyword_id: str | None) -> dict[str, Any]:
    strongest_scan = max(scans, key=_strongest_coverage_key) if scans else None
    weakest_scan = min(scans, key=_weakest_coverage_key) if scans else None
    strongest = strongest_scan["id"] if strongest_scan else None
    weakest = weakest_scan["id"] if weakest_scan else None
    sources = _available_sources(scans)
    featured = featured_keyword_id or strongest
    return _drop_none(
        {
            "keyword_count": len(scans),
            "scan_count": len(scans),
            "featured_keyword_id": featured,
            "featured_scan_id": featured,
            "strongest_keyword_id": strongest,
            "strongest_scan_id": strongest,
            "weakest_keyword_id": weakest,
            "weakest_scan_id": weakest,
            "available_sources": sources,
            "default_source_id": _default_source_id(sources),
            "summary_note": "Synthetic Local Falcon API fixture normalized by musimack-data-importer.",
        }
    )


def _available_sources(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    sources = []
    for scan in scans:
        source_id = scan.get("source_id")
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        sources.append(
            _drop_none(
                {
                    "source_id": source_id,
                    "source_label": scan.get("source_label"),
                    "query_type": scan.get("query_type"),
                    "scan_kind": scan.get("scan_kind"),
                    "scan_id": scan.get("id"),
                }
            )
        )
    return sources


def _default_source_id(sources: list[dict[str, Any]]) -> str | None:
    if any(source.get("source_id") == "google_maps" for source in sources):
        return "google_maps"
    return str(sources[0].get("source_id")) if sources else None


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


def _derive_missing_positions(points: list[dict[str, Any]]) -> None:
    if all(isinstance(point.get("row"), int) and isinstance(point.get("col"), int) for point in points):
        return
    columns = int(len(points) ** 0.5)
    columns = columns if columns and columns * columns == len(points) else max(1, columns + 1)
    for index, point in enumerate(points):
        point["row"] = index // columns
        point["col"] = index % columns


def _zone(row: Any, col: Any, grid: dict[str, int]) -> str:
    if row is None or col is None:
        return "Unknown"
    vertical = "N" if row == 0 else "S" if row == grid.get("rows", 0) - 1 else ""
    horizontal = "W" if col == 0 else "E" if col == grid.get("columns", 0) - 1 else ""
    return (vertical + horizontal) or "Center"


def _first_list(payload: dict[str, Any], *keys: str) -> list[Any] | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return None


def _first_nested_list(report_response: dict[str, Any], ai_response: dict[str, Any] | None, *keys: str) -> list[Any] | None:
    for payload in (report_response, ai_response):
        if not isinstance(payload, dict):
            continue
        data = _data_object(payload)
        direct = _first_list(data, *keys)
        if direct is not None:
            return direct
        nested_ai = data.get("ai_visibility") or data.get("ai_analysis") or data.get("analysis")
        if isinstance(nested_ai, dict):
            nested = _first_list(nested_ai, *keys)
            if nested is not None:
                return nested
    return None


def _first_nested_object(report_response: dict[str, Any], ai_response: dict[str, Any] | None, *keys: str) -> dict[str, Any] | None:
    for payload in (report_response, ai_response):
        if not isinstance(payload, dict):
            continue
        data = _data_object(payload)
        for key in keys:
            value = data.get(key)
            if isinstance(value, dict):
                return value
        nested_ai = data.get("ai_visibility") or data.get("ai_analysis") or data.get("analysis")
        if isinstance(nested_ai, dict):
            for key in keys:
                value = nested_ai.get(key)
                if isinstance(value, dict):
                    return value
    return None


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value is not None and value != "":
            return value
    return None


def _required_string(payload: dict[str, Any], key: str, message: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LocalFalconApiResponseError(message)
    return value.strip()


def _grid_size_label(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if "x" in text.lower() else f"{text}x{text}"


def _number_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "yes", "1"}:
            return True
        if text in {"false", "no", "0"}:
            return False
    return None


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: nested for key, nested in value.items() if nested is not None and nested != {}}
