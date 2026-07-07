from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Metric:
    name: str
    value: float
    unit: str

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "unit": self.unit}


@dataclass(frozen=True)
class DimensionRow:
    label: str
    metrics: list[Metric]
    kind: str | None = None

    def as_dict(self) -> dict[str, Any]:
        row = {"label": self.label, "metrics": [metric.as_dict() for metric in self.metrics]}
        if self.kind:
            row["kind"] = self.kind
        return row


@dataclass(frozen=True)
class NormalizedTrafficOverview:
    metrics: list[Metric]
    time_series: list[dict[str, Any]]
    channel_rows: list[DimensionRow]
    top_page_rows: list[DimensionRow]
    source_medium_rows: list[DimensionRow]
    landing_page_rows: list[DimensionRow]
    warnings: list[str]


METRIC_NAME_MAP = {
    "activeUsers": ("users", "count"),
    "totalUsers": ("users", "count"),
    "newUsers": ("new_users", "count"),
    "sessions": ("sessions", "count"),
    "engagedSessions": ("engaged_sessions", "count"),
    "engagementRate": ("engagement_rate", "ratio"),
    "averageSessionDuration": ("average_session_duration_seconds", "seconds"),
    "averageEngagementTime": ("average_engagement_time_seconds", "seconds"),
    "screenPageViews": ("views", "count"),
    "conversions": ("conversions", "count"),
    "keyEvents": ("key_events", "count"),
    "eventCount": ("event_count", "count"),
}


def normalize_traffic_overview(raw_response: dict[str, Any]) -> NormalizedTrafficOverview:
    if _is_richer_response(raw_response):
        return _normalize_richer_traffic_overview(raw_response)
    return _normalize_legacy_traffic_overview(raw_response)


def _normalize_richer_traffic_overview(raw_response: dict[str, Any]) -> NormalizedTrafficOverview:
    trend = _normalize_legacy_traffic_overview(raw_response.get("traffic_overview", {}))
    channel_rows, channel_warnings = _normalize_channel_rows(
        raw_response.get("channel_breakdown", {})
    )
    top_page_rows, top_page_warnings = _normalize_top_page_rows(raw_response.get("top_pages", {}))
    source_medium_rows, source_medium_warnings = _normalize_source_medium_rows(
        raw_response.get("source_medium", {})
    )
    landing_page_rows, landing_page_warnings = _normalize_landing_page_rows(
        raw_response.get("landing_pages", {})
    )
    warnings = [
        *trend.warnings,
        *channel_warnings,
        *top_page_warnings,
        *source_medium_warnings,
        *landing_page_warnings,
        *[str(warning) for warning in raw_response.get("warnings", []) if str(warning).strip()],
    ]
    return NormalizedTrafficOverview(
        metrics=trend.metrics,
        time_series=trend.time_series,
        channel_rows=channel_rows,
        top_page_rows=top_page_rows,
        source_medium_rows=source_medium_rows,
        landing_page_rows=landing_page_rows,
        warnings=sorted(set(warnings)),
    )


def _normalize_legacy_traffic_overview(raw_response: dict[str, Any]) -> NormalizedTrafficOverview:
    metric_headers = [header.get("name", "") for header in raw_response.get("metricHeaders", [])]
    dimension_headers = [
        header.get("name", "") for header in raw_response.get("dimensionHeaders", [])
    ]
    totals = defaultdict(float)
    by_date: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_channel: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    warnings: list[str] = []

    for row in raw_response.get("rows", []):
        dimensions = [value.get("value", "") for value in row.get("dimensionValues", [])]
        metric_values = [value.get("value", "0") for value in row.get("metricValues", [])]
        date_value = _dimension_value(dimension_headers, dimensions, "date")
        channel = _dimension_value(dimension_headers, dimensions, "sessionDefaultChannelGroup")

        row_values = {
            header: _safe_float(raw_value)
            for header, raw_value in zip(metric_headers, metric_values)
        }
        row_sessions = row_values.get("sessions", 0.0)
        for header, normalized in row_values.items():
            name_unit = METRIC_NAME_MAP.get(header)
            if not name_unit:
                warnings.append(f"Unsupported GA4 metric omitted: {header}")
                continue
            name, _unit = name_unit
            if name in {"engagement_rate", "average_session_duration_seconds"} and row_sessions > 0:
                normalized = normalized * row_sessions
            totals[name] += normalized
            if date_value:
                by_date[date_value][name] += normalized
            if channel:
                by_channel[channel][name] += normalized

    metrics = _summary_metrics(totals)
    time_series = _time_series(by_date)
    channel_rows = _channel_rows(by_channel)
    return NormalizedTrafficOverview(
        metrics=metrics,
        time_series=time_series,
        channel_rows=channel_rows,
        top_page_rows=[],
        source_medium_rows=[],
        landing_page_rows=[],
        warnings=sorted(set(warnings)),
    )


def _summary_metrics(totals: dict[str, float]) -> list[Metric]:
    sessions = totals.get("sessions", 0.0)
    engaged_sessions = totals.get("engaged_sessions", 0.0)
    if sessions > 0 and "engagement_rate" in totals:
        engagement_rate = totals["engagement_rate"] / sessions
    elif sessions > 0:
        engagement_rate = engaged_sessions / sessions
    else:
        engagement_rate = 0.0

    metrics = []
    _append_if_present(metrics, totals, "users", "count")
    _append_if_present(metrics, totals, "new_users", "count")
    _append_if_present(metrics, totals, "sessions", "count")
    _append_if_present(metrics, totals, "engaged_sessions", "count")
    if "engagement_rate" in totals or sessions > 0:
        metrics.append(Metric("engagement_rate", _clean_number(engagement_rate), "ratio"))
    if "average_session_duration_seconds" in totals:
        value = totals["average_session_duration_seconds"] / sessions if sessions > 0 else 0.0
        metrics.append(
            Metric("average_session_duration_seconds", _clean_number(value), "seconds")
        )
    _append_if_present(metrics, totals, "views", "count")
    _append_if_present(metrics, totals, "event_count", "count")
    _append_if_present(metrics, totals, "key_events", "count")
    _append_if_present(metrics, totals, "conversions", "count")
    return metrics


def _time_series(by_date: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    rows = []
    for raw_date, values in sorted(by_date.items()):
        parsed = _parse_ga4_date(raw_date)
        if not parsed:
            continue
        rows.append(
            {
                "date": parsed,
                "users": _clean_number(values.get("users", 0.0)),
                "sessions": _clean_number(values.get("sessions", 0.0)),
                "views": _clean_number(values.get("views", 0.0)),
                "event_count": _clean_number(values.get("event_count", 0.0)),
            }
        )
    return rows


def _channel_rows(by_channel: dict[str, dict[str, float]]) -> list[DimensionRow]:
    rows = []
    for label, values in sorted(
        by_channel.items(), key=lambda item: item[1].get("sessions", 0.0), reverse=True
    )[:10]:
        rows.append(
            DimensionRow(
                label=label.strip() or "Unassigned",
                kind="traffic_channels",
                metrics=[
                    Metric("sessions", _clean_number(values.get("sessions", 0.0)), "count"),
                    Metric("users", _clean_number(values.get("users", 0.0)), "count"),
                    Metric("views", _clean_number(values.get("views", 0.0)), "count"),
                    Metric(
                        "engagement_rate",
                        _clean_number(_weighted_average(values, "engagement_rate", "sessions")),
                        "ratio",
                    ),
                    Metric("key_events", _clean_number(values.get("key_events", 0.0)), "count"),
                    Metric("conversions", _clean_number(values.get("conversions", 0.0)), "count"),
                ],
            )
        )
    return rows


def _normalize_channel_rows(raw_response: dict[str, Any]) -> tuple[list[DimensionRow], list[str]]:
    metric_headers = [header.get("name", "") for header in raw_response.get("metricHeaders", [])]
    dimension_headers = [
        header.get("name", "") for header in raw_response.get("dimensionHeaders", [])
    ]
    by_channel: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    warnings: list[str] = []

    for row in raw_response.get("rows", []):
        dimensions = [value.get("value", "") for value in row.get("dimensionValues", [])]
        metric_values = [value.get("value", "0") for value in row.get("metricValues", [])]
        channel = _dimension_value(dimension_headers, dimensions, "sessionDefaultChannelGroup")
        if not channel:
            continue
        row_values = {
            header: _safe_float(raw_value)
            for header, raw_value in zip(metric_headers, metric_values)
        }
        sessions = row_values.get("sessions", 0.0)
        for header, raw_value in row_values.items():
            name_unit = METRIC_NAME_MAP.get(header)
            if not name_unit:
                warnings.append(f"Unsupported GA4 channel metric omitted: {header}")
                continue
            name, _unit = name_unit
            value = raw_value
            if name in {"engagement_rate", "average_session_duration_seconds"} and sessions > 0:
                value = raw_value * sessions
            by_channel[channel][name] += value

    return _channel_rows(by_channel), warnings


def _normalize_top_page_rows(raw_response: dict[str, Any]) -> tuple[list[DimensionRow], list[str]]:
    metric_headers = [header.get("name", "") for header in raw_response.get("metricHeaders", [])]
    dimension_headers = [
        header.get("name", "") for header in raw_response.get("dimensionHeaders", [])
    ]
    rows: list[DimensionRow] = []
    warnings: list[str] = []

    for row in raw_response.get("rows", [])[:10]:
        dimensions = [value.get("value", "") for value in row.get("dimensionValues", [])]
        metric_values = [value.get("value", "0") for value in row.get("metricValues", [])]
        title = (_dimension_value(dimension_headers, dimensions, "pageTitle") or "").strip()
        path = (_dimension_value(dimension_headers, dimensions, "pagePath") or "").strip()
        label = _page_label(title, path)
        if not label:
            continue
        row_values = {
            header: _safe_float(raw_value)
            for header, raw_value in zip(metric_headers, metric_values)
        }
        metrics = []
        for header, raw_value in row_values.items():
            name_unit = METRIC_NAME_MAP.get(header)
            if not name_unit:
                warnings.append(f"Unsupported GA4 top page metric omitted: {header}")
                continue
            name, unit = name_unit
            metrics.append(Metric(name, _clean_number(raw_value), unit))
        rows.append(DimensionRow(label=label, kind="top_pages", metrics=metrics))

    return rows, warnings


def _normalize_source_medium_rows(raw_response: dict[str, Any]) -> tuple[list[DimensionRow], list[str]]:
    metric_headers = [header.get("name", "") for header in raw_response.get("metricHeaders", [])]
    dimension_headers = [
        header.get("name", "") for header in raw_response.get("dimensionHeaders", [])
    ]
    by_source: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    warnings: list[str] = []

    for row in raw_response.get("rows", []):
        dimensions = [value.get("value", "") for value in row.get("dimensionValues", [])]
        metric_values = [value.get("value", "0") for value in row.get("metricValues", [])]
        source_medium = _dimension_value(dimension_headers, dimensions, "sessionSourceMedium")
        if not source_medium:
            continue
        row_values = {
            header: _safe_float(raw_value)
            for header, raw_value in zip(metric_headers, metric_values)
        }
        sessions = row_values.get("sessions", 0.0)
        for header, raw_value in row_values.items():
            name_unit = METRIC_NAME_MAP.get(header)
            if not name_unit:
                warnings.append(f"Unsupported GA4 source/source-medium metric omitted: {header}")
                continue
            name, _unit = name_unit
            value = raw_value
            if name in {"engagement_rate", "average_session_duration_seconds"} and sessions > 0:
                value = raw_value * sessions
            by_source[source_medium][name] += value

    rows = []
    for label, values in sorted(
        by_source.items(), key=lambda item: item[1].get("sessions", 0.0), reverse=True
    )[:10]:
        rows.append(
            DimensionRow(
                label=label.strip() or "(not set)",
                kind="source_medium",
                metrics=[
                    Metric("sessions", _clean_number(values.get("sessions", 0.0)), "count"),
                    Metric("users", _clean_number(values.get("users", 0.0)), "count"),
                    Metric(
                        "engagement_rate",
                        _clean_number(_weighted_average(values, "engagement_rate", "sessions")),
                        "ratio",
                    ),
                    Metric(
                        "average_session_duration_seconds",
                        _clean_number(
                            _weighted_average(
                                values,
                                "average_session_duration_seconds",
                                "sessions",
                            )
                        ),
                        "seconds",
                    ),
                    Metric("event_count", _clean_number(values.get("event_count", 0.0)), "count"),
                    Metric("key_events", _clean_number(values.get("key_events", 0.0)), "count"),
                    Metric("conversions", _clean_number(values.get("conversions", 0.0)), "count"),
                ],
            )
        )
    return rows, warnings


def _normalize_landing_page_rows(raw_response: dict[str, Any]) -> tuple[list[DimensionRow], list[str]]:
    metric_headers = [header.get("name", "") for header in raw_response.get("metricHeaders", [])]
    dimension_headers = [
        header.get("name", "") for header in raw_response.get("dimensionHeaders", [])
    ]
    rows: list[DimensionRow] = []
    warnings: list[str] = []

    for row in raw_response.get("rows", [])[:10]:
        dimensions = [value.get("value", "") for value in row.get("dimensionValues", [])]
        metric_values = [value.get("value", "0") for value in row.get("metricValues", [])]
        path = (
            _dimension_value(dimension_headers, dimensions, "landingPagePlusQueryString")
            or _dimension_value(dimension_headers, dimensions, "landingPage")
            or ""
        ).strip()
        if not path:
            continue
        row_values = {
            header: _safe_float(raw_value)
            for header, raw_value in zip(metric_headers, metric_values)
        }
        metrics = []
        for header, raw_value in row_values.items():
            name_unit = METRIC_NAME_MAP.get(header)
            if not name_unit:
                warnings.append(f"Unsupported GA4 landing page metric omitted: {header}")
                continue
            name, unit = name_unit
            metrics.append(Metric(name, _clean_number(raw_value), unit))
        rows.append(DimensionRow(label=path, kind="landing_pages", metrics=metrics))

    return rows, warnings


def _is_richer_response(raw_response: dict[str, Any]) -> bool:
    return any(
        key in raw_response
        for key in (
            "traffic_overview",
            "channel_breakdown",
            "top_pages",
            "source_medium",
            "landing_pages",
        )
    )


def _weighted_average(values: dict[str, float], name: str, weight_name: str) -> float:
    weight = values.get(weight_name, 0.0)
    if weight <= 0:
        return 0.0
    return values.get(name, 0.0) / weight


def _page_label(title: str, path: str) -> str:
    if title and path:
        return f"{title} ({path})"
    return title or path


def _dimension_value(headers: list[str], values: list[str], name: str) -> str | None:
    try:
        index = headers.index(name)
    except ValueError:
        return None
    return values[index] if index < len(values) else None


def _safe_float(value: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _clean_number(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    rounded = round(value, 6)
    if abs(rounded - round(rounded)) < 0.000001:
        return float(round(rounded))
    return rounded


def _append_if_present(
    metrics: list[Metric], totals: dict[str, float], name: str, unit: str
) -> None:
    if name in totals:
        metrics.append(Metric(name, _clean_number(totals.get(name, 0.0)), unit))


def _parse_ga4_date(value: str) -> str | None:
    try:
        return date(int(value[0:4]), int(value[4:6]), int(value[6:8])).isoformat()
    except (TypeError, ValueError):
        return None
