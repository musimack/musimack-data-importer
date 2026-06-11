from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .local_falcon_api_plan import LocalFalconApiReportPlan, default_output_path
from .local_falcon_api_responses import (
    LocalFalconApiResponseError,
    merge_api_scan_into_summary,
    normalize_api_report_to_keyword_scan,
)
from .local_falcon_importer import OutputValidation, build_action_bridge, validate_local_falcon_summary


class LocalFalconApiFetcherError(RuntimeError):
    pass


class LocalFalconApiTransport(Protocol):
    def get_report_summary(self, report_id: str) -> dict[str, Any]:
        ...

    def get_grid_points(self, report_id: str) -> dict[str, Any]:
        ...

    def get_competitors(self, report_id: str) -> dict[str, Any] | None:
        ...

    def get_ai_analysis(self, report_id: str) -> dict[str, Any] | None:
        ...


@dataclass(frozen=True)
class LocalFalconApiFetchRequest:
    profile: str
    reports: list[LocalFalconApiReportPlan]
    output: Path | None = None
    featured_keyword_id: str | None = None
    existing_summary: dict[str, Any] | None = None
    source_type: str = "api_fixture"
    real_data: bool = False
    dry_run: bool = True
    no_write: bool = True

    @property
    def output_path(self) -> Path:
        return self.output or default_output_path(self.profile)


@dataclass(frozen=True)
class LocalFalconApiReportBundle:
    report: LocalFalconApiReportPlan
    report_summary: dict[str, Any]
    grid_points: dict[str, Any]
    competitors: dict[str, Any] | None
    ai_analysis: dict[str, Any] | None


@dataclass(frozen=True)
class LocalFalconApiFetchResult:
    profile: str
    report_count: int
    keyword_scans: list[dict[str, Any]]
    summary: dict[str, Any]
    validation: OutputValidation
    warnings: list[str]
    dry_run: bool
    no_write: bool
    output_path: Path


class LocalFalconApiFetcher:
    def __init__(self, transport: LocalFalconApiTransport | None = None):
        self._transport = transport

    def fetch_report_bundle(self, report: LocalFalconApiReportPlan) -> LocalFalconApiReportBundle:
        if self._transport is None:
            raise LocalFalconApiFetcherError(
                "Live Local Falcon API transport is not implemented. "
                "Provide a fake transport for tests or wait for an approved live API milestone."
            )
        if not report.report_id.strip():
            raise LocalFalconApiFetcherError("report_id is required")
        try:
            report_summary = self._transport.get_report_summary(report.report_id)
            grid_points = self._transport.get_grid_points(report.report_id)
            competitors = self._transport.get_competitors(report.report_id)
            ai_analysis = self._transport.get_ai_analysis(report.report_id)
        except Exception as exc:
            raise LocalFalconApiFetcherError(f"Local Falcon fake transport failed: {exc}") from exc
        if not isinstance(report_summary, dict):
            raise LocalFalconApiFetcherError("report summary response must be an object")
        if not isinstance(grid_points, dict):
            raise LocalFalconApiFetcherError("grid points response must be an object")
        if competitors is not None and not isinstance(competitors, dict):
            raise LocalFalconApiFetcherError("competitor response must be an object when present")
        if ai_analysis is not None and not isinstance(ai_analysis, dict):
            raise LocalFalconApiFetcherError("AI analysis response must be an object when present")
        return LocalFalconApiReportBundle(
            report=report,
            report_summary=report_summary,
            grid_points=grid_points,
            competitors=competitors,
            ai_analysis=ai_analysis,
        )

    def fetch(self, request: LocalFalconApiFetchRequest) -> LocalFalconApiFetchResult:
        if not request.reports:
            raise LocalFalconApiFetcherError("at least one report is required")
        payload: dict[str, Any] | None = request.existing_summary
        scans = []
        warnings = []
        for report in request.reports:
            bundle = self.fetch_report_bundle(report)
            try:
                scan = normalize_report_bundle_to_keyword_scan(bundle)
            except LocalFalconApiResponseError as exc:
                raise LocalFalconApiFetcherError(f"failed to normalize report '{report.report_id}': {exc}") from exc
            scans.append(scan)
            if scan.get("ai_analysis", {}).get("available") is not True:
                warnings.append(f"{scan.get('keyword') or report.keyword}: AI analysis unavailable.")
            if not scan.get("competitors"):
                warnings.append(f"{scan.get('keyword') or report.keyword}: competitor report unavailable.")
            payload = merge_api_scan_into_summary(
                profile=request.profile,
                keyword_scan=scan,
                existing_summary=payload,
                featured_keyword_id=request.featured_keyword_id,
                source_type=request.source_type,
                real_data=request.real_data,
            )
        assert payload is not None
        validation = validate_local_falcon_summary(payload, request.output_path)
        return LocalFalconApiFetchResult(
            profile=request.profile,
            report_count=len(request.reports),
            keyword_scans=scans,
            summary=payload,
            validation=validation,
            warnings=[*warnings, *validation.warnings],
            dry_run=request.dry_run,
            no_write=request.no_write,
            output_path=request.output_path,
        )


def fetch_report_bundle(
    report: LocalFalconApiReportPlan,
    transport: LocalFalconApiTransport | None = None,
) -> LocalFalconApiReportBundle:
    return LocalFalconApiFetcher(transport).fetch_report_bundle(report)


def normalize_report_bundle_to_keyword_scan(bundle: LocalFalconApiReportBundle) -> dict[str, Any]:
    scan = normalize_api_report_to_keyword_scan(
        bundle.report_summary,
        grid_response=bundle.grid_points,
        competitor_response=bundle.competitors,
        ai_response=bundle.ai_analysis,
    )
    return _attach_report_metadata(scan, bundle.report)


def normalize_report_bundle_to_summary(
    *,
    profile: str,
    bundle: LocalFalconApiReportBundle,
    existing_summary: dict[str, Any] | None = None,
    featured_keyword_id: str | None = None,
) -> dict[str, Any]:
    return merge_api_scan_into_summary(
        profile=profile,
        keyword_scan=normalize_report_bundle_to_keyword_scan(bundle),
        existing_summary=existing_summary,
        featured_keyword_id=featured_keyword_id,
    )


def _attach_report_metadata(scan: dict[str, Any], report: LocalFalconApiReportPlan) -> dict[str, Any]:
    query = report.query or report.keyword
    if not any([report.source_id, report.source_label, report.query_type, report.scan_kind]):
        return _remove_ai_internal_fields(scan)
    source_id = report.source_id
    scan["query"] = query
    scan["keyword"] = query
    if source_id:
        scan["source_id"] = source_id
        scan["id"] = f"{_slug(source_id)}-{_slug(query)}"
    if report.source_label:
        scan["source_label"] = report.source_label
    if report.query_type:
        scan["query_type"] = report.query_type
        if report.query_type == "ai_visibility_prompt":
            _attach_ai_visibility_fields(scan, query)
    if report.scan_kind:
        scan["scan_kind"] = report.scan_kind
    if report.report_id:
        scan["report_id_redacted"] = _redacted_report_id(report.report_id)
    return _remove_ai_internal_fields(scan)


def _attach_ai_visibility_fields(scan: dict[str, Any], query: str) -> None:
    scan["prompt"] = query
    scan["competitors"] = []
    scan["brand_phrases"] = scan.get("brand_phrases") or []
    ai_points = _normalize_ai_visibility_points(
        scan.get("grid_points", []),
        client_place_id=scan.get("_ai_client_place_id"),
        places=scan.get("_ai_places") if isinstance(scan.get("_ai_places"), dict) else {},
    )
    brand_observations = _aggregate_ai_brand_observations(ai_points)
    scan["ai_visibility_points"] = ai_points
    if brand_observations:
        scan["brand_observations"] = brand_observations
    else:
        scan["brand_observations"] = scan.get("brand_observations") or []
    scan["ai_visibility_metrics"] = _merge_ai_visibility_metrics(
        scan.get("ai_visibility_metrics") if isinstance(scan.get("ai_visibility_metrics"), dict) else {},
        ai_points,
        brand_observations,
    )
    scan["action_bridge"] = build_action_bridge(
        scan.get("data_points", {}),
        scan.get("grid_points", []),
        [],
    )


def _slug(value: str) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-") or "scan"


def _normalize_ai_visibility_points(
    grid_points: list[Any],
    *,
    client_place_id: str | None = None,
    places: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    places = places or {}
    ai_points = []
    for index, point in enumerate(grid_points):
        if not isinstance(point, dict):
            continue
        nested_results = point.get("_ai_results") if isinstance(point.get("_ai_results"), list) else []
        primary_result = _primary_ai_result(nested_results, client_place_id)
        observed = bool(nested_results) or point.get("observed")
        if not isinstance(observed, bool):
            observed = _has_ai_visibility_evidence(point)
        place_id = primary_result.get("place_id") or point.get("place_id")
        place = places.get(str(place_id)) if place_id else None
        relationship = _ai_relationship(primary_result, point, place_id, client_place_id)
        if relationship == "client" and not place_id and client_place_id:
            place_id = client_place_id
            place = places.get(str(place_id))
        observation_sequence = primary_result.get("observation_sequence") or point.get("observation_sequence")
        ai_visibility_value = primary_result.get("ai_visibility_value") or point.get("ai_visibility_value")
        ai_point = _drop_none(
            {
                "grid_index": index + 1,
                "row": point.get("row"),
                "col": point.get("col"),
                "latitude": point.get("latitude"),
                "longitude": point.get("longitude"),
                "observed": observed,
                "ai_visibility_status": "observed" if observed else "not_observed",
                "observation_sequence": observation_sequence,
                "ai_visibility_value": ai_visibility_value,
                "brand_name": primary_result.get("brand_name") or (place or {}).get("brand_name") or point.get("brand_name"),
                "place_id": place_id,
                "relationship": relationship,
                "sentiment": primary_result.get("sentiment") or point.get("sentiment"),
                "share_of_ai_voice": (place or {}).get("share_of_ai_voice"),
                "result_count": len(nested_results) if nested_results else point.get("result_count"),
            }
        )
        ai_points.append(ai_point)
        point["ai_visibility_status"] = ai_point["ai_visibility_status"]
    return ai_points


def _primary_ai_result(results: list[Any], client_place_id: str | None) -> dict[str, Any]:
    normalized = [item for item in results if isinstance(item, dict)]
    if client_place_id:
        match = next((item for item in normalized if str(item.get("place_id") or "") == client_place_id), None)
        if match:
            return match
    return normalized[0] if normalized else {}


def _ai_relationship(
    result: dict[str, Any],
    point: dict[str, Any],
    place_id: Any,
    client_place_id: str | None,
) -> str | None:
    if client_place_id and place_id and str(place_id) == client_place_id:
        return "client"
    return result.get("relationship") or point.get("relationship") or ("observed_brand" if result else None)


def _aggregate_ai_brand_observations(ai_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for point in ai_points:
        if point.get("observed") is not True:
            continue
        brand_name = point.get("brand_name")
        place_id = point.get("place_id")
        if not brand_name and not place_id:
            continue
        key = str(place_id or brand_name).casefold()
        entry = by_key.setdefault(
            key,
            {
                "brand_name": brand_name,
                "place_id": place_id,
                "relationship": point.get("relationship") or "observed_brand",
                "observation_count": 0,
                "map_points_observed": 0,
                "_sequences": [],
                "share_of_ai_voice": point.get("share_of_ai_voice"),
            },
        )
        if not entry.get("brand_name") and brand_name:
            entry["brand_name"] = brand_name
        if not entry.get("place_id") and place_id:
            entry["place_id"] = place_id
        if point.get("relationship") == "client":
            entry["relationship"] = "client"
        entry["observation_count"] += int(point.get("result_count") or 1)
        entry["map_points_observed"] += 1
        if isinstance(point.get("observation_sequence"), int):
            entry["_sequences"].append(point["observation_sequence"])
        if entry.get("share_of_ai_voice") is None and point.get("share_of_ai_voice") is not None:
            entry["share_of_ai_voice"] = point.get("share_of_ai_voice")

    observations = []
    for entry in by_key.values():
        sequences = entry.pop("_sequences", [])
        if sequences:
            entry["best_observation_sequence"] = min(sequences)
            entry["average_observation_sequence"] = round(sum(sequences) / len(sequences), 2)
        observations.append(_drop_none(entry))
    observations.sort(
        key=lambda item: (
            0 if item.get("relationship") == "client" else 1,
            item.get("best_observation_sequence") or 999,
            str(item.get("brand_name") or item.get("place_id") or ""),
        )
    )
    return observations


def _merge_ai_visibility_metrics(
    existing: dict[str, Any],
    ai_points: list[dict[str, Any]],
    brand_observations: list[dict[str, Any]],
) -> dict[str, Any]:
    observed = [point for point in ai_points if point.get("observed") is True]
    client = next((item for item in brand_observations if item.get("relationship") == "client"), None)
    metrics = dict(existing)
    metrics.update(
        _drop_none(
            {
                "map_point_count": len(ai_points),
                "observed_point_count": len(observed),
                "not_observed_point_count": len(ai_points) - len(observed),
                "total_brand_mentions": sum(int(item.get("observation_count") or 0) for item in brand_observations),
                "unique_brand_count": len(brand_observations),
                "mentions_client": bool(client),
                "client_brand_name": (client or {}).get("brand_name"),
                "client_observation_count": (client or {}).get("observation_count"),
                "client_best_observation_sequence": (client or {}).get("best_observation_sequence"),
                "client_average_observation_sequence": (client or {}).get("average_observation_sequence"),
                "share_of_ai_voice": (client or {}).get("share_of_ai_voice") or existing.get("share_of_ai_voice"),
            }
        )
    )
    return metrics


def _has_ai_visibility_evidence(point: dict[str, Any]) -> bool:
    for key in ("observation_sequence", "ai_visibility_value", "brand_name", "relationship", "sentiment"):
        if point.get(key) is not None:
            return True
    return bool(point.get("result_count"))


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None and item != {} and item != ""}


def _remove_ai_internal_fields(scan: dict[str, Any]) -> dict[str, Any]:
    scan.pop("_ai_client_place_id", None)
    scan.pop("_ai_places", None)
    for point in scan.get("grid_points", []):
        if isinstance(point, dict):
            point.pop("_ai_results", None)
    return scan


def _redacted_report_id(value: str) -> str:
    text = str(value)
    if len(text) <= 8:
        return "****"
    return f"{text[:4]}****{text[-4:]}"
