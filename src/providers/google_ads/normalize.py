from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit


def micros_to_currency(value: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return round(number / 1_000_000, 6)


def normalize_ctr(value: Any) -> float | None:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.endswith("%"):
            number = _number(stripped[:-1])
            return None if number is None else round(number / 100, 6)
    return _number(value)


def normalize_landing_page_url(url: str | None) -> str | None:
    if not url:
        return None
    stripped = str(url).strip()
    if not stripped:
        return None
    parsed = urlsplit(stripped)
    if parsed.scheme and parsed.netloc:
        return parsed.path or "/"
    return stripped.split("?", 1)[0].split("#", 1)[0] or "/"


def normalize_campaign_rows(mock_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in mock_rows:
        cost = micros_to_currency(_field(row, "metrics.cost_micros", "cost_micros"))
        clicks = _int(_field(row, "metrics.clicks", "clicks")) or 0
        impressions = _int(_field(row, "metrics.impressions", "impressions")) or 0
        conversions = _number(_field(row, "metrics.conversions", "conversions")) or 0.0
        calls = _int(_field(row, "calls"))
        rows.append(
            _without_none(
                {
                    "campaign": _field(row, "campaign.name", "campaign") or "",
                    "spend": cost,
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": _derived_ctr(row, clicks, impressions),
                    "avg_cpc": _derived_avg_cpc(row, cost, clicks),
                    "conversions": conversions,
                    "calls": calls,
                    "cost_per_call": _cost_per_call(cost, calls),
                }
            )
        )
    return rows


def normalize_keyword_rows(mock_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in mock_rows:
        cost = micros_to_currency(_field(row, "metrics.cost_micros", "cost_micros"))
        clicks = _int(_field(row, "metrics.clicks", "clicks")) or 0
        impressions = _int(_field(row, "metrics.impressions", "impressions")) or 0
        calls = _int(_field(row, "calls"))
        rows.append(
            _without_none(
                {
                    "keyword": _field(row, "ad_group_criterion.keyword.text", "keyword") or "",
                    "campaign": _field(row, "campaign.name", "campaign") or "",
                    "match_type": _field(row, "ad_group_criterion.keyword.match_type", "match_type"),
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": _derived_ctr(row, clicks, impressions),
                    "avg_cpc": _derived_avg_cpc(row, cost, clicks),
                    "cost": cost,
                    "conversions": _number(_field(row, "metrics.conversions", "conversions")) or 0.0,
                    "calls": calls,
                    "cost_per_call": _cost_per_call(cost, calls),
                    "landing_page": normalize_landing_page_url(_field(row, "landing_page")),
                }
            )
        )
    return rows


def normalize_search_term_rows(mock_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in mock_rows:
        cost = micros_to_currency(_field(row, "metrics.cost_micros", "cost_micros"))
        clicks = _int(_field(row, "metrics.clicks", "clicks")) or 0
        impressions = _int(_field(row, "metrics.impressions", "impressions")) or 0
        calls = _int(_field(row, "calls"))
        rows.append(
            _without_none(
                {
                    "search_term": _field(row, "search_term_view.search_term", "search_term") or "",
                    "matched_keyword": _field(
                        row,
                        "segments.keyword.info.text",
                        "matched_keyword",
                    ),
                    "campaign": _field(row, "campaign.name", "campaign") or "",
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": _derived_ctr(row, clicks, impressions),
                    "cost": cost,
                    "conversions": _number(_field(row, "metrics.conversions", "conversions")) or 0.0,
                    "calls": calls,
                }
            )
        )
    return rows


def normalize_landing_page_rows(mock_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in mock_rows:
        cost = micros_to_currency(_field(row, "metrics.cost_micros", "cost_micros"))
        clicks = _int(_field(row, "metrics.clicks", "clicks")) or 0
        impressions = _int(_field(row, "metrics.impressions", "impressions")) or 0
        calls = _int(_field(row, "calls"))
        rows.append(
            _without_none(
                {
                    "landing_page": normalize_landing_page_url(
                        _field(row, "expanded_landing_page_view.expanded_final_url", "landing_page", "final_url")
                    )
                    or "",
                    "campaign": _field(row, "campaign.name", "campaign") or "",
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": _derived_ctr(row, clicks, impressions),
                    "cost": cost,
                    "conversions": _number(_field(row, "metrics.conversions", "conversions")) or 0.0,
                    "calls": calls,
                    "cost_per_call": _cost_per_call(cost, calls),
                }
            )
        )
    return rows


def normalize_time_series(mock_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_date: dict[str, dict[str, Any]] = {}
    for row in mock_rows:
        date = str(_field(row, "segments.date", "date") or "").strip()
        if not date:
            continue
        aggregate = rows_by_date.setdefault(
            date,
            {
                "date": date,
                "spend": 0.0,
                "clicks": 0,
                "impressions": 0,
                "conversions": 0.0,
            },
        )
        aggregate["spend"] = round(aggregate["spend"] + _time_series_spend(row), 6)
        aggregate["clicks"] += _int(_field(row, "metrics.clicks", "clicks")) or 0
        aggregate["impressions"] += _int(_field(row, "metrics.impressions", "impressions")) or 0
        aggregate["conversions"] = round(
            aggregate["conversions"] + (_number(_field(row, "metrics.conversions", "conversions")) or 0.0),
            6,
        )
        _sum_optional_int(aggregate, row, "interactions")
        _sum_optional_int(aggregate, row, "tracked_calls", "tracked_calls", "calls")
        _sum_optional_int(aggregate, row, "form_fills")
        _sum_optional_int(aggregate, row, "tracked_leads")
    return [_without_none(rows_by_date[date]) for date in sorted(rows_by_date)]


def build_summary_from_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    spend = round(sum(_number(row.get("cost", row.get("spend"))) or 0 for row in materialized), 6)
    clicks = sum(_int(row.get("clicks")) or 0 for row in materialized)
    impressions = sum(_int(row.get("impressions")) or 0 for row in materialized)
    conversions = round(sum(_number(row.get("conversions")) or 0 for row in materialized), 6)
    calls = sum(_int(row.get("calls")) or 0 for row in materialized)
    return _without_none(
        {
            "spend": spend,
            "clicks": clicks,
            "impressions": impressions,
            "ctr": round(clicks / impressions, 6) if impressions else 0.0,
            "avg_cpc": round(spend / clicks, 6) if clicks else 0.0,
            "conversions": conversions,
            "cost_per_conversion": round(spend / conversions, 6) if conversions else None,
            "calls": calls if calls else None,
            "cost_per_call": round(spend / calls, 6) if calls else None,
        }
    )


def _sum_optional_int(aggregate: dict[str, Any], row: dict[str, Any], output_key: str, *input_paths: str) -> None:
    value = _int(_field(row, *(input_paths or (output_key,))))
    if value is None:
        return
    aggregate[output_key] = int(aggregate.get(output_key, 0)) + value


def _time_series_spend(row: dict[str, Any]) -> float:
    micros = _field(row, "metrics.cost_micros", "cost_micros")
    if micros is not None:
        return micros_to_currency(micros) or 0.0
    return _number(_field(row, "spend", "cost")) or 0.0


def _derived_ctr(row: dict[str, Any], clicks: int, impressions: int) -> float:
    supplied = normalize_ctr(_field(row, "metrics.ctr", "ctr"))
    if supplied is not None:
        return supplied
    return round(clicks / impressions, 6) if impressions else 0.0


def _derived_avg_cpc(row: dict[str, Any], cost: float | None, clicks: int) -> float | None:
    supplied = micros_to_currency(_field(row, "metrics.average_cpc", "average_cpc_micros"))
    if supplied is not None:
        return supplied
    if cost is not None and clicks:
        return round(cost / clicks, 6)
    return None


def _cost_per_call(cost: float | None, calls: int | None) -> float | None:
    if cost is None or not calls:
        return None
    return round(cost / calls, 6)


def _field(row: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        value = _nested(row, path)
        if value is not None:
            return value
    return None


def _nested(row: dict[str, Any], path: str) -> Any:
    if path in row:
        return row[path]
    current: Any = row
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def _int(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    return int(number)


def _without_none(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value is not None}
