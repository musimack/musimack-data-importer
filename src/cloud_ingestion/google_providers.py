"""GA4/GSC weekly adapters using in-memory credentials and pre-issue budgets.

The CLI does not instantiate these adapters in P2-3B. They are exercised only
with fake transports and credentials until a later milestone authorizes real
provider calls.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable

from src.config import DateRange, Ga4Config
from src.providers.ga4.client import Ga4DataClient
from src.providers.ga4.normalize import DimensionRow, Metric, normalize_traffic_overview
from src.providers.gsc.client import GscFetchConfig, GscSearchConsoleClient

from .budget import ProviderRequestBudget
from .domain import CredentialMaterial, IngestionConfiguration, ProviderOutput, RunRequest
from .errors import BudgetError, ConfigurationError, ProviderError


class GoogleGa4WeeklyProvider:
    provider = "ga4"

    def __init__(self, client_factory: Callable[..., Ga4DataClient] = Ga4DataClient) -> None:
        self._client_factory = client_factory

    def planned_requests(self, request: RunRequest, configuration: IngestionConfiguration) -> int:
        return 5

    def retrieve(
        self,
        request: RunRequest,
        configuration: IngestionConfiguration,
        credential: CredentialMaterial,
        budget: ProviderRequestBudget,
    ) -> ProviderOutput:
        if configuration.external_resource_type != "ga4_property":
            raise ConfigurationError("GA4 configuration resource type is invalid")
        client = self._client_factory(
            Ga4Config(
                auth_method="in_memory",
                property_id=configuration.external_resource_id,
                oauth_client_secrets_file=None,
                oauth_token_file=None,
                service_account_file=None,
                service_account_info=None,
            ),
            credential_loader=lambda: credential.value,
            request_counter=budget,
        )
        try:
            normalized = normalize_traffic_overview(
                client.run_traffic_overview(DateRange(request.week_start, request.week_end))
            )
        except BudgetError:
            raise
        except Exception as exc:
            raise ProviderError() from exc
        metrics = [_metric(metric, "ga4.runReport.v1") for metric in normalized.metrics]
        daily = []
        for row in normalized.time_series:
            for key, unit in (("users", "count"), ("sessions", "count"), ("views", "count"), ("event_count", "count")):
                if key in row:
                    daily.append(
                        {
                            "metric_key": key,
                            "date": row["date"],
                            "value": row[key],
                            "unit": unit,
                            "aggregation": "sum",
                            "provenance": "ga4.runReport.v1",
                        }
                    )
        ranked = []
        dimension_rows = [
            *normalized.channel_rows,
            *normalized.top_page_rows,
            *normalized.source_medium_rows,
            *normalized.landing_page_rows,
        ]
        for rank, dimension_row in enumerate(dimension_rows, start=1):
            ranked.extend(_ranked_metrics(dimension_row, rank, "ga4.runReport.v1"))
        observed_dates = {item["date"] for item in daily}
        return ProviderOutput(
            freshness=_freshness(request, observed_dates),
            source={"identity": "ga4.weekly_traffic_overview.v1", "contract_version": 1},
            metrics=metrics,
            daily=daily,
            ranked=ranked,
        )


class GoogleGscWeeklyProvider:
    provider = "gsc"

    def __init__(self, client_factory: Callable[..., GscSearchConsoleClient] = GscSearchConsoleClient) -> None:
        self._client_factory = client_factory

    def planned_requests(self, request: RunRequest, configuration: IngestionConfiguration) -> int:
        return 1

    def retrieve(
        self,
        request: RunRequest,
        configuration: IngestionConfiguration,
        credential: CredentialMaterial,
        budget: ProviderRequestBudget,
    ) -> ProviderOutput:
        if configuration.external_resource_type != "gsc_site":
            raise ConfigurationError("GSC configuration resource type is invalid")
        client = self._client_factory(
            GscFetchConfig("", "", configuration.external_resource_id, row_limit=25000),
            credential_loader=lambda: credential.value,
            request_counter=budget,
        )
        try:
            response = client.query_search_analytics(
                request.week_start.isoformat(),
                request.week_end.isoformat(),
            )
            return _normalize_gsc(request, response)
        except BudgetError:
            raise
        except Exception as exc:
            raise ProviderError() from exc


def _metric(metric: Metric, provenance: str) -> dict[str, Any]:
    aggregation = "average" if metric.unit in {"ratio", "seconds"} else "sum"
    return {
        "metric_key": metric.name,
        "value": metric.value,
        "unit": metric.unit,
        "aggregation": aggregation,
        "provenance": provenance,
    }


def _ranked_metrics(row: DimensionRow, rank: int, provenance: str) -> list[dict[str, Any]]:
    dimension = row.kind or "dimension"
    identity = hashlib.sha256(f"{dimension}\0{row.label}".encode("utf-8")).hexdigest()[:24]
    return [
        {
            "dimension": dimension,
            "identity": identity,
            "label": row.label,
            "rank": rank,
            "metric": _metric(metric, provenance),
        }
        for metric in row.metrics
    ]


def _normalize_gsc(request: RunRequest, response: dict[str, Any]) -> ProviderOutput:
    rows = response.get("rows", [])
    if not isinstance(rows, list):
        raise ProviderError("GSC response rows are invalid")
    by_date: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_query: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    by_page: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("keys"), list) or len(row["keys"]) < 3:
            continue
        query, page, day = (str(value) for value in row["keys"][:3])
        clicks = _number(row.get("clicks"))
        impressions = _number(row.get("impressions"))
        position = _number(row.get("position"))
        for bucket in (by_date[day], by_query[query], by_page[page]):
            bucket["clicks"] += clicks
            bucket["impressions"] += impressions
            bucket["weighted_position"] += position * impressions
    totals = _rollup(by_date.values())
    metrics = [
        _observation("clicks", totals["clicks"], "count", "sum"),
        _observation("impressions", totals["impressions"], "count", "sum"),
        _observation("ctr", _ratio(totals["clicks"], totals["impressions"]), "ratio", "average"),
        _observation(
            "average_position",
            _ratio(totals["weighted_position"], totals["impressions"]),
            "position",
            "average",
        ),
    ]
    daily = []
    for day, bucket in sorted(by_date.items()):
        daily.extend(
            [
                {**_observation("clicks", bucket["clicks"], "count", "sum"), "date": day},
                {**_observation("impressions", bucket["impressions"], "count", "sum"), "date": day},
            ]
        )
    ranked = []
    for dimension, buckets in (("query", by_query), ("page", by_page)):
        ordered = sorted(buckets.items(), key=lambda item: item[1]["clicks"], reverse=True)[:10]
        for index, (label, bucket) in enumerate(ordered, start=1):
            ranked.append(
                {
                    "dimension": dimension,
                    "identity": hashlib.sha256(f"{dimension}\0{label}".encode("utf-8")).hexdigest()[:24],
                    "label": label,
                    "rank": index,
                    "metric": _observation("clicks", bucket["clicks"], "count", "sum"),
                }
            )
    return ProviderOutput(
        freshness=_freshness(request, set(by_date)),
        source={"identity": "gsc.weekly_search_analytics.v1", "contract_version": 1},
        metrics=metrics,
        daily=daily,
        ranked=ranked,
    )


def _observation(key: str, value: float, unit: str, aggregation: str) -> dict[str, Any]:
    return {
        "metric_key": key,
        "value": round(value, 6),
        "unit": unit,
        "aggregation": aggregation,
        "provenance": "gsc.searchAnalytics.query.v1",
    }


def _freshness(request: RunRequest, observed_dates: set[str]) -> dict[str, Any]:
    actual_days = len(observed_dates)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    state = "available" if actual_days == 7 else "partial" if actual_days else "unavailable"
    return {
        "state": state,
        "available_through": max(observed_dates) if observed_dates else None,
        "first_available_date": min(observed_dates) if observed_dates else None,
        "last_available_date": max(observed_dates) if observed_dates else None,
        "expected_observation_count": 7,
        "actual_observation_count": actual_days,
        "missing_observation_count": 7 - actual_days,
        "generated_at": generated_at,
        "checked_at": generated_at,
    }


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _rollup(values) -> dict[str, float]:
    total = defaultdict(float)
    for value in values:
        for key, number in value.items():
            total[key] += number
    return total
